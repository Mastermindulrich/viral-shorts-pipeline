"""What the app learns from its own results, so each round picks better videos.

Two local memories under data/learning/ (owner 2026-11-24: smarter discovery, fewer wasted rounds):

* sources.json: per source channel, how often its videos produced clips and why they failed.
  Channels whose videos keep failing (no complete English scene, not English, refused download)
  are ranked lower, and after three failures with no success they are skipped for 14 days, so
  the autopilot stops spending 10 minutes of download and transcription on them.
* niches.json: how the channel's own Shorts performed per niche (views from the YouTube Data
  API, one cheap call a day). Niches that viewers watch get a ranking boost, weak ones a small
  penalty. With fewer than three posted Shorts in a niche nothing changes.

Everything here only reorders candidates. Content rules and screening are never relaxed."""
import datetime as dt
import statistics
import pipeline as p
import content_policy as policy

FOLDER='learning'
SKIP_AFTER=3
SKIP_DAYS=14
NICHE_REFRESH_HOURS=20


def _path(name):
    return p.DATA/FOLDER/name


def _load(name):
    path=_path(name)
    try: return p.read(path) if path.exists() else {}
    except (OSError,ValueError): return {}


def channel_key(item):
    return str(item.get('channel_id') or item.get('source') or item.get('channelTitle') or item.get('creator') or '').strip().casefold()


def record_source(item, ok, reason=''):
    """Remember whether a source channel's video produced clips. Never raises."""
    try:
        key=channel_key(item)
        if not key: return
        data=_load('sources.json')
        row=data.get(key,dict(name=item.get('source') or item.get('creator') or key,ok=0,failed=0,reasons={}))
        now=dt.datetime.now(dt.timezone.utc).isoformat()
        if ok: row['ok']+=1; row['last_ok']=now
        else:
            row['failed']+=1; row['last_failed']=now
            short=str(reason)[:80]
            row['reasons'][short]=row['reasons'].get(short,0)+1
            row['reasons']=dict(sorted(row['reasons'].items(),key=lambda x:-x[1])[:5])
        data[key]=row
        p.write(_path('sources.json'),data)
    except Exception as exc:
        print(f'Learning skipped: {exc}',flush=True)


def source_penalty(item, now=None):
    """Ranking points to subtract for a channel whose videos keep failing (0-24), or None to skip it."""
    row=_load('sources.json').get(channel_key(item))
    if not row: return 0
    failed,ok=row.get('failed',0),row.get('ok',0)
    if failed>=SKIP_AFTER and ok==0:
        try:
            last=dt.datetime.fromisoformat(row['last_failed'])
            if ((now or dt.datetime.now(dt.timezone.utc))-last).days<SKIP_DAYS: return None
        except (KeyError,ValueError): return None
    return min(24,max(0,8*failed-6*ok))


def niche_boost(name):
    return float(_load('niches.json').get('boost',{}).get(name,0))


def refresh_niches(service=None, now=None, force=False):
    """Read view counts of the channel's recent Shorts and score each niche. At most once a day."""
    now=now or dt.datetime.now(dt.timezone.utc)
    current=_load('niches.json')
    try:
        if not force and current.get('updated') and (now-dt.datetime.fromisoformat(current['updated'])).total_seconds()<NICHE_REFRESH_HOURS*3600:
            return current
    except ValueError: pass
    rows=[]
    for path in (p.DATA/'exports').glob('*/upload.json'):
        try:
            receipt=p.read(path)
            if receipt.get('state')!='uploaded' or not receipt.get('video_id'): continue
            job=p.read(path.parent/'job.json')
        except (OSError,ValueError): continue
        source={}
        try: source=p.read(p.Path(job['input']).parent/'source.json')
        except Exception: pass
        rows.append(dict(video_id=receipt['video_id'],niche=policy.niche(dict(title=job.get('title',''),source_title=source.get('title','')))))
    if not rows: return current
    if service is None:
        from googleapiclient.discovery import build
        service=build('youtube','v3',credentials=p.credentials(),cache_discovery=False)
    views={}
    ids=[x['video_id'] for x in rows][-200:]
    for offset in range(0,len(ids),50):
        response=service.videos().list(part='statistics',id=','.join(ids[offset:offset+50])).execute()
        for item in response.get('items',[]):
            views[item['id']]=int(item.get('statistics',{}).get('viewCount',0))
    per={}
    for row in rows:
        if row['video_id'] in views: per.setdefault(row['niche'],[]).append(views[row['video_id']])
    everything=[v for values in per.values() for v in values]
    overall=statistics.median(everything) if everything else 0
    boost={}
    for name,values in per.items():
        if len(values)<3 or overall<=0: continue
        ratio=statistics.median(values)/overall
        # Twice the channel median = +8, half = -4; bounded so learning never dominates freshness.
        boost[name]=round(max(-4,min(8,8*(ratio-1) if ratio>=1 else -8*(1-ratio))),1)
    result=dict(updated=now.isoformat(),overall_median_views=overall,
                niches={k:dict(shorts=len(v),median_views=statistics.median(v)) for k,v in per.items()},boost=boost)
    p.write(_path('niches.json'),result)
    return result


def summary():
    """Plain-English lines for the dashboard."""
    lines=[]
    niches=_load('niches.json')
    if niches.get('boost'):
        best=sorted(niches['boost'].items(),key=lambda x:-x[1])
        good=[k for k,v in best if v>0][:3]
        weak=[k for k,v in best if v<0][:2]
        if good: lines.append('Your viewers watch these niches most, so they are picked first: '+', '.join(good)+'.')
        if weak: lines.append('Weaker niches, picked a little less often: '+', '.join(weak)+'.')
    sources=_load('sources.json')
    skipped=[row.get('name',key) for key,row in sources.items() if source_penalty(dict(channel_id=key)) is None]
    if skipped: lines.append(f'{len(skipped)} channel(s) paused for 14 days because their videos never produced a usable clip.')
    return lines
