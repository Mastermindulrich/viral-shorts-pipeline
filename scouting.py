"""Measured source signals and a transparent prioritization heuristic, not a forecast."""
import datetime as dt
import math
import re
import statistics
import pipeline as p
import content_policy as policy


def hidden_videos():
    path=p.DATA/'scouting-hidden.json'
    return p.read(path) if path.exists() else {}


def hide_video(item):
    ident=item['id']
    with p.lock():
        hidden=hidden_videos()
        hidden[ident]={'title':item.get('title',ident),'hidden_at':dt.datetime.now(dt.timezone.utc).isoformat()}
        p.write(p.DATA/'scouting-hidden.json',hidden)


def restore_video(ident):
    with p.lock():
        hidden=hidden_videos();hidden.pop(ident,None)
        p.write(p.DATA/'scouting-hidden.json',hidden)


def visible_ranked(items):
    hidden=hidden_videos()
    current=[x for x in items if x.get('policy_version')==policy.VERSION and x['id'] not in hidden]
    return policy.visible_candidates(current)


def duration_seconds(value):
    m=re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?',value or '')
    return sum(int(v or 0)*w for v,w in zip(m.groups(),(3600,60,1))) if m else None


def rank(items, previous, now):
    groups={}
    for x in items:
        age=max(1.,(now-dt.datetime.fromisoformat(x['published'].replace('Z','+00:00'))).total_seconds()/3600)
        x['average_views_per_hour']=x['views']/age
        old=previous.get(x['id'])
        x['measured_views_per_hour']=None
        if old:
            elapsed=(now-dt.datetime.fromisoformat(old['observed_at'])).total_seconds()/3600
            if elapsed>=.25 and x['views']>=old['views']:
                x['measured_views_per_hour']=(x['views']-old['views'])/elapsed
        groups.setdefault(x['source'],[]).append(x['average_views_per_hour'])
    for x in items:
        median=statistics.median(groups[x['source']])
        x['relative_to_source_median']=round(x['average_views_per_hour']/max(1,median),2)
        signal=x['measured_views_per_hour'] if x['measured_views_per_hour'] is not None else x['average_views_per_hour']
        x['priority_score']=round(math.log1p(signal)*8+min(x['relative_to_source_median'],5)*5,1)
        x['eligible_long_source']=90<=x['duration_seconds']<=10800
        x['observed_at']=now.isoformat()
    return sorted(items,key=lambda x:x['priority_score'],reverse=True)


def refresh():
    from googleapiclient.discovery import build
    service=build('youtube','v3',credentials=p.credentials(),cache_discovery=False)
    candidates=p.read(p.DATA/'candidates.json')
    hidden=hidden_videos()
    lookup={x['id']:x for x in candidates if x['id'] not in hidden}
    items=[]; excluded=[]
    ids=list(lookup)
    for offset in range(0,len(ids),50):
        response=service.videos().list(part='snippet,statistics,contentDetails',id=','.join(ids[offset:offset+50])).execute()
        for item in response.get('items',[]):
            if item['id'] not in lookup: continue
            secs=duration_seconds(item.get('contentDetails',{}).get('duration'))
            if secs is None or item['snippet'].get('liveBroadcastContent') in ('live','upcoming'): continue
            snippet=item['snippet']
            candidate=dict(lookup[item['id']],title=snippet['title'],source=snippet['channelTitle'],
                           categoryId=snippet.get('categoryId',''),description=snippet.get('description',''),
                           defaultAudioLanguage=snippet.get('defaultAudioLanguage',''),
                           defaultLanguage=snippet.get('defaultLanguage',''))
            decision=policy.screen(candidate)
            if not decision['eligible']:
                excluded.append(dict(id=item['id'],title=candidate['title'],reason=decision['reason']))
                continue
            items.append(dict(candidate,policy=decision,policy_version=policy.VERSION,published=snippet['publishedAt'],duration_seconds=secs,
                              views=int(item.get('statistics',{}).get('viewCount',0)),
                              likes=int(item.get('statistics',{}).get('likeCount',0))))
    snapshot=p.DATA/'scout-snapshot.json'
    previous=p.read(snapshot) if snapshot.exists() else {}
    now=dt.datetime.now(dt.timezone.utc)
    result=rank(items,previous,now)
    # Retain the baseline until 15 minutes elapse, so repeated clicks don't erase velocity measurement.
    for item in result:
        old=previous.get(item['id'])
        if not old or (now-dt.datetime.fromisoformat(old['observed_at'])).total_seconds()>=900:
            previous[item['id']]={'views':item['views'],'observed_at':now.isoformat()}
    p.write(snapshot,previous)
    p.write(p.DATA/'ranked-candidates.json',result)
    p.write(p.DATA/'scouting-exclusions.json',excluded)
    return result


def discover_broad():
    """Cross-topic public discovery with a bounded, rotating free-quota search budget."""
    from googleapiclient.discovery import build
    service=build('youtube','v3',credentials=p.credentials(),cache_discovery=False)
    cfg=policy.discovery_config(p.read(p.ROOT/'config'/'discovery.json'))
    state_path=p.DATA/'discovery-rotation.json'
    state=p.read(state_path) if state_path.exists() else {'next_topic':0}
    topics=cfg['topics']
    budget=min(4,max(1,int(cfg.get('searches_per_scan',4))))
    cursor=int(state.get('next_topic',0))
    now=dt.datetime.now(dt.timezone.utc)
    after=(now-dt.timedelta(days=3)).isoformat().replace('+00:00','Z')
    found={}; errors=[]; queried=[]
    old=p.DATA/'candidates.json'
    if old.exists(): found={x['id']:x for x in p.read(old)}
    for region in cfg.get('regions',['US'])[:3]:
        try:
            response=service.videos().list(part='snippet',chart='mostPopular',regionCode=region,maxResults=50).execute()
            for x in response.get('items',[]):
                sn=x['snippet']
                found[x['id']]=dict(id=x['id'],title=sn['title'],url='https://www.youtube.com/watch?v='+x['id'],
                                    published=sn['publishedAt'],source=sn['channelTitle'],discovered_via='Popular chart: '+region)
        except Exception as exc: errors.append(f'{region} popular chart: {exc}')
    for offset in range(min(budget,len(topics))):
        topic=topics[(cursor+offset)%len(topics)]
        queried.append(topic['name'])
        try:
            response=service.search().list(part='snippet',type='video',q=topic['query'],order='viewCount',
                                           publishedAfter=after,maxResults=20,relevanceLanguage='en').execute()
            for x in response.get('items',[]):
                vid=x.get('id',{}).get('videoId')
                if not vid: continue
                sn=x['snippet']
                found[vid]=dict(id=vid,title=sn['title'],url='https://www.youtube.com/watch?v='+vid,
                               published=sn['publishedAt'],source=sn['channelTitle'],discovered_via=topic['name'])
        except Exception as exc: errors.append(f"{topic['name']}: {exc}")
    hidden=hidden_videos()
    rows=sorted(policy.visible_candidates([x for x in found.values() if x['id'] not in hidden]),key=lambda x:x.get('published',''),reverse=True)[:1000]
    p.write(old,rows)
    p.write(state_path,{'next_topic':(cursor+budget)%max(1,len(topics)), 'last_topics':queried,
                        'last_scan':now.isoformat(),'errors':errors})
    if errors: raise RuntimeError('Partial discovery saved. '+' | '.join(errors))
    return {'saved_candidates':len(rows),'searched_topics':queried,'next_topic':topics[(cursor+budget)%len(topics)]['name']}
