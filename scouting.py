"""Measured source signals and a transparent prioritization heuristic, not a forecast."""
import datetime as dt
import math
import re
import statistics
import pipeline as p
import content_policy as policy
import learning

DEFAULTS=dict(categories=[x['name'] for x in policy.TOPICS],days=3,min_views=5000,
              min_views_per_hour=200,source_preference='Prefer independent',
              include_keywords='',exclude_keywords='',blocked_channels='',event_queries='',
              focus=policy.FOCUS['name'])
FOCUS_BOOST=8
TRENDING_BOOST=12
# Smarter discovery (owner 2026-11-24): clickable titles and stories people are talking about
# right now (news desk buzz terms) rank higher; learning.py adds what the channel's own viewers
# watch and demotes channels whose videos keep failing.
CLICK_WEIGHT=.6
BUZZ_BOOST=10
NICHE_SHARE=3
TRENDING_NAME='Trending today'
TRENDING_FEED='https://trends.google.com/trending/rss?geo={region}'
CATEGORY_TERMS={
    'Champions League and football':r'champions league|football|soccer|mbapp[eé]|messi|ronaldo|goal|real madrid|barcelona',
    'Viral sports moments':r'\bnba\b|basketball|football|soccer|tennis|athlete|sport|lebron|curry|boxing|ufc',
    'Influencer life':r'influencer|creator|drama|vlog|mrbeast',
    'Streamer moments':r'streamer|kai cenat|ishowspeed|adin ross|twitch|streaming',
    'Just happened':r'breaking|caught on camera|unexpected|incident|just happened|unbelievable',
    'Sports controversies':r'athlete|football|mbapp[eé]|apolog|controvers|sport|nba',
    'Movie scenes and fan cuts':r'movie|film|scene|cinema',
    'Engineering hacks':r'engineering|hack|invention|mechanism|diy|experiment|machine',
    'Celebrity viral footage':r'celebrity|celebrities|red carpet|paparazzi|premiere|fashion|actress|actor|model',
    'Gaming and streamers':r'gaming|gamer|gameplay|streamer|twitch',
    'Hot interviews':r'interview|podcast|debate|heated',
    'African urban dance':r'african|amapiano|afrobeats|azonto|dance',
    'TikTok dance challenges':r'tiktok|dance challenge',
    'Movie trailers':r'trailer|teaser', 'Music reactions':r'react|first time hearing',
    policy.FOCUS['name']:policy.FOCUS['pattern'],
    'Breaking news today':r'breaking|news|today|just in|update|announce',
    'Politics today':r'politic|president|senate|congress|election|minister|parliament|trump|white house|debate',
    'World news and geopolitics':r'war|iran|israel|russia|ukraine|china|nato|missile|strike|sanction|blockade|ceasefire|geopolit',
    'Celebrity news':r'celebrity|kardashian|beyonc|taylor swift|drake|rihanna|diddy|met gala|oscars|grammy'}


def preferences():
    path=p.DATA/'scouting-preferences.json'
    return dict(DEFAULTS,**(p.read(path) if path.exists() else {}))


def save_preferences(values):
    result=dict(preferences(),**values)
    if int(result['days']) not in (1,3,7,30): raise ValueError('Choose 1, 3, 7 or 30 days')
    if result['source_preference'] not in ('Prefer independent','Any source','Exclude likely official'):
        raise ValueError('Invalid source preference')
    if min(float(result['min_views']),float(result['min_views_per_hour']))<0:
        raise ValueError('View thresholds must be nonnegative')
    with p.lock(): p.write(p.DATA/'scouting-preferences.json',result)
    return result


def keyword_list(value):
    return [x.strip().casefold() for x in value.split(',') if x.strip()]


def categories_for(item):
    text=(item.get('title','')+' '+item.get('source','')).casefold()
    found=[name for name,terms in CATEGORY_TERMS.items() if re.search(terms,text,re.I)]
    via=item.get('discovered_via','')
    if via in CATEGORY_TERMS and via not in found: found.append(via)
    return found or ([via] if via and not via.startswith('Popular chart:') else ['Other'])


def filter_ranked(items, prefs=None, now=None):
    prefs=preferences() if prefs is None else prefs
    now=now or dt.datetime.now(dt.timezone.utc)
    buzz=[x.casefold() for x in newsdesk_terms(now) if len(x)>=4][:40]
    result=[]
    for item in items:
        try: age=(now-dt.datetime.fromisoformat(item['published'].replace('Z','+00:00'))).total_seconds()/3600
        except (KeyError,ValueError,TypeError): continue
        if age>int(prefs['days'])*24 or age<-.25: continue
        if item.get('views',0)<float(prefs['min_views']): continue
        signal=item.get('measured_views_per_hour')
        if signal is None: signal=item.get('average_views_per_hour',0)
        if signal<float(prefs['min_views_per_hour']): continue
        if item.get('duration_seconds') is None or policy.source_problem(item): continue
        text=(item.get('title','')+' '+item.get('source','')).casefold()
        if any(x in text for x in keyword_list(prefs['exclude_keywords'])): continue
        required=keyword_list(prefs['include_keywords'])
        if required and not any(x in text for x in required): continue
        blocked=keyword_list(prefs['blocked_channels'])
        if item.get('source','').casefold() in blocked or item.get('channel_id','').casefold() in blocked: continue
        source_type=policy.source_type(item)
        if prefs['source_preference']=='Exclude likely official' and source_type.startswith('Likely'): continue
        categories=categories_for(item)
        focus=bool(prefs.get('focus')) and policy.is_focus(item)
        trending=item.get('discovered_via')==TRENDING_NAME
        if prefs['categories'] and not set(categories).intersection(prefs['categories']) and item.get('discovered_via')!='Your event search' and not focus and not trending: continue
        penalty=learning.source_penalty(item,now)
        if penalty is None: continue  # this channel's videos never produced a usable clip (paused 14 days)
        row=dict(item,categories=categories,source_type=source_type,focus=focus,niche=policy.niche(item),
                 clickability=policy.clickability(item))
        row['buzz']=buzz_match(item,buzz)
        row['display_score']=round(item.get('priority_score',0)+(5 if prefs['source_preference']=='Prefer independent' and source_type.startswith('Unverified') else 0)
                                   +(FOCUS_BOOST if focus else 0)+(TRENDING_BOOST if trending else 0)
                                   +row['clickability']*CLICK_WEIGHT+(BUZZ_BOOST if row['buzz'] else 0)
                                   +learning.niche_boost(row['niche'])-penalty,1)
        result.append(row)
    return sorted(result,key=lambda x:x['display_score'],reverse=True)


def buzz_match(item, terms):
    """The first buzz term (X, Google Trends, news desk) that the video's title mentions, or ''."""
    title=item.get('title','').casefold()
    for term in terms:
        if re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',title): return term
    return ''


def shortlist(items, limit=10):
    """Keep ten strong choices without letting one channel or one niche fill the list.

    First pass: at most two per channel and NICHE_SHARE per niche, so the list spans several
    niches. Second pass fills any remaining places (still two per channel) in score order."""
    selected=[]; per_source={}; per_niche={}; titles=set()
    for capped in (True,False):
        for item in items:
            if len(selected)>=limit: break
            if any(item is x for x in selected): continue
            title=re.sub(r'\W+',' ',item.get('title','').casefold()).strip()
            source=item.get('channel_id') or item.get('source','')
            group=item.get('niche') or policy.niche(item)
            if title in titles or per_source.get(source,0)>=2: continue
            if capped and per_niche.get(group,0)>=NICHE_SHARE: continue
            selected.append(item); titles.add(title); per_source[source]=per_source.get(source,0)+1
            per_niche[group]=per_niche.get(group,0)+1
    return selected


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


def unsupported_videos():
    path=p.DATA/'scouting-unsupported.json'
    return p.read(path) if path.exists() else {}


def mark_unsupported(ident, title, reason):
    """Remember a video the download step refused, so later scans never offer it again."""
    with p.lock():
        records=unsupported_videos()
        records[ident]={'title':title or ident,'reason':str(reason)[:300],
                        'marked_at':dt.datetime.now(dt.timezone.utc).isoformat()}
        p.write(p.DATA/'scouting-unsupported.json',records)


def skipped_ids():
    return set(hidden_videos())|set(unsupported_videos())


def visible_ranked(items):
    hidden=skipped_ids()
    current=[x for x in items if x.get('policy_version')==policy.VERSION and x['id'] not in hidden]
    return filter_ranked(policy.visible_candidates(current))


def duration_seconds(value):
    m=re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?',value or '')
    return sum(int(v or 0)*w for v,w in zip(m.groups(),(3600,60,1))) if m else None


def rank(items, previous, now):
    groups={}
    for x in items:
        age=max(1.,(now-dt.datetime.fromisoformat(x['published'].replace('Z','+00:00'))).total_seconds()/3600)
        x['average_views_per_hour']=x['views']/age
        x['age_hours']=round(age,1)
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
        freshness=16*math.exp(-x['age_hours']/72)
        engagement=min(8,100*x.get('likes',0)/max(1,x['views']))
        event=4 if re.search(r'breaking|apolog|controvers|reaction|caught on camera|incredible',x.get('title',''),re.I) else 0
        x['priority_score']=round(math.log1p(signal)*8+min(x['relative_to_source_median'],5)*3+freshness+engagement+event,1)
        x['signal_label']='Measured growth' if x['measured_views_per_hour'] is not None else 'Lifetime average; growth not yet measured'
        x['eligible_long_source']=90<=x['duration_seconds']<=10800
        x['observed_at']=now.isoformat()
    return sorted(items,key=lambda x:x['priority_score'],reverse=True)


def refresh():
    from googleapiclient.discovery import build
    service=build('youtube','v3',credentials=p.credentials(),cache_discovery=False)
    candidates=p.read(p.DATA/'candidates.json') if (p.DATA/'candidates.json').exists() else []
    hidden=skipped_ids()
    region=str(p.read(p.ROOT/'config'/'discovery.json').get('home_region','CA')) if (p.ROOT/'config'/'discovery.json').exists() else 'CA'
    lookup={x['id']:x for x in candidates if x['id'] not in hidden}
    items=[]; excluded=[]
    ids=list(lookup)
    for offset in range(0,len(ids),50):
        # Extra parts cost no extra quota and let step 1 drop videos the download step would refuse.
        response=service.videos().list(part='snippet,statistics,contentDetails,status,liveStreamingDetails',
                                       id=','.join(ids[offset:offset+50])).execute()
        for item in response.get('items',[]):
            if item['id'] not in lookup: continue
            snippet=item['snippet']; details=item.get('contentDetails',{}); status=item.get('status',{})
            live=item.get('liveStreamingDetails',{})
            restriction=details.get('regionRestriction',{})
            facts=dict(duration_seconds=duration_seconds(details.get('duration')),
                       live_status=snippet.get('liveBroadcastContent','none'),
                       live_started=live.get('actualStartTime','') or live.get('scheduledStartTime',''),
                       live_ended=live.get('actualEndTime',''),
                       age_restricted=details.get('contentRating',{}).get('ytRating')=='ytAgeRestricted',
                       privacy=status.get('privacyStatus',''),upload_status=status.get('uploadStatus',''),
                       region_blocked=region in restriction.get('blocked',[]) or
                                      ('allowed' in restriction and region not in restriction['allowed']))
            problem='Duration not available (live or unfinished)' if facts['duration_seconds'] is None else policy.source_problem(facts)
            if problem:
                excluded.append(dict(id=item['id'],title=snippet.get('title',''),reason=problem))
                continue
            candidate=dict(lookup[item['id']],title=snippet['title'],source=snippet['channelTitle'],
                           channel_id=snippet.get('channelId',''),
                           categoryId=snippet.get('categoryId',''),description=snippet.get('description',''),
                           defaultAudioLanguage=snippet.get('defaultAudioLanguage',''),
                           defaultLanguage=snippet.get('defaultLanguage',''))
            decision=policy.screen(candidate)
            if not decision['eligible']:
                excluded.append(dict(id=item['id'],title=candidate['title'],reason=decision['reason']))
                continue
            items.append(dict(candidate,**facts,policy=decision,policy_version=policy.VERSION,published=snippet['publishedAt'],
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


def newsdesk_terms(now=None, max_age_hours=6):
    """Buzz terms the news desk saved (X, Google Trends, Reddit), strongest first.

    Reads data/newsdesk/trending-terms.json when it is fresh; [] when missing or stale."""
    now=now or dt.datetime.now(dt.timezone.utc)
    try:
        saved=p.read(p.DATA/'newsdesk'/'trending-terms.json')
        if (now-dt.datetime.fromisoformat(saved['updated_at'])).total_seconds()>max_age_hours*3600: return []
        terms=sorted(saved.get('terms') or [],key=lambda t:-float(t.get('weight') or 0))
        # Reddit entries are whole post titles, too long to work as search queries.
        return [str(t['term']).strip()[:120] for t in terms
                if str(t.get('term') or '').strip() and not str(t.get('source') or '').startswith('Reddit')]
    except Exception: return []


def trending_queries(regions, fetch=None, now=None):
    """What is buzzing now: news desk terms (X, Reddit, Trends) first, then Google Trends.

    X/Twitter trends need a paid API, so the news desk's scan and Google's free daily
    feed are the signal. Returns [] on any failure; scans then use topics only."""
    found=[]
    for term in newsdesk_terms(now)+google_trends(regions,fetch,now):
        if term.casefold() not in {x.casefold() for x in found}: found.append(term)
    return found[:40]


def google_trends(regions, fetch=None, now=None):
    """Today's top searches (Google Trends daily feed), cached for an hour."""
    import urllib.request
    import xml.etree.ElementTree as ET
    now=now or dt.datetime.now(dt.timezone.utc)
    cache=p.DATA/'trending.json'
    try:
        saved=p.read(cache)
        if (now-dt.datetime.fromisoformat(saved['fetched_at'])).total_seconds()<3600 and saved.get('queries'):
            return saved['queries']
    except Exception: pass
    fetch=fetch or (lambda url: urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=15).read())
    found=[]
    for region in list(regions)[:3]:
        try:
            root=ET.fromstring(fetch(TRENDING_FEED.format(region=region)))
            for item in root.iter('item'):
                title=(item.findtext('title') or '').strip()
                if title and title.casefold() not in {x.casefold() for x in found}: found.append(title[:120])
        except Exception as exc:
            print(f'Trending feed {region} unavailable: {exc}',flush=True)
    if found:
        try: p.write(cache,dict(fetched_at=now.isoformat(),queries=found[:40]))
        except Exception: pass
    return found[:40]


def discover_broad():
    """Cross-topic public discovery with a bounded, rotating free-quota search budget."""
    from googleapiclient.discovery import build
    service=build('youtube','v3',credentials=p.credentials(),cache_discovery=False)
    cfg=policy.discovery_config(p.read(p.ROOT/'config'/'discovery.json'))
    prefs=preferences()
    state_path=p.DATA/'discovery-rotation.json'
    state=p.read(state_path) if state_path.exists() else {'next_topic':0}
    topics=cfg['topics']
    if prefs['categories']:
        by_name={x['name']:x for x in topics}
        topics=[by_name[name] for name in prefs['categories'] if name in by_name]
    if not topics: raise ValueError('Choose at least one discovery category')
    budget=min(4,max(1,int(cfg.get('searches_per_scan',4))))
    cursor=int(state.get('next_topic',0))
    now=dt.datetime.now(dt.timezone.utc)
    after=(now-dt.timedelta(days=int(prefs['days']))).isoformat().replace('+00:00','Z')
    found={}; errors=[]; queried=[]
    old=p.DATA/'candidates.json'
    if old.exists(): found={x['id']:x for x in p.read(old) if x.get('published','')>=after}
    for region in cfg.get('regions',['US'])[:3]:
        try:
            response=service.videos().list(part='snippet',chart='mostPopular',regionCode=region,maxResults=50).execute()
            for x in response.get('items',[]):
                sn=x['snippet']
                found[x['id']]=dict(id=x['id'],title=sn['title'],url='https://www.youtube.com/watch?v='+x['id'],
                                    published=sn['publishedAt'],source=sn['channelTitle'],discovered_via='Popular chart: '+region)
        except Exception as exc: errors.append(f'{region} popular chart: {exc}')
    requests=[]
    event_queries=[x.strip()[:300] for x in prefs['event_queries'].splitlines() if x.strip()]
    if event_queries:
        requests.append(dict(name='Your event search',query=event_queries[int(state.get('event_cursor',0))%len(event_queries)]))
    if prefs.get('trending',True) and budget-len(requests)>=3:
        # What people searched most in the last day (Google Trends), searched on YouTube.
        trends=trending_queries(cfg.get('regions',['US']))
        if trends:
            trend_cursor=int(state.get('trend_cursor',0))
            for n in range(min(2,len(trends))):
                requests.append(dict(name=TRENDING_NAME,query=trends[(trend_cursor+n)%len(trends)]))
            state['trend_cursor']=trend_cursor+2
    if prefs.get('focus') and budget-len(requests)>=2:
        # One search per scan for the trending game; the rest stays broad.
        queries=policy.FOCUS['queries']; focus_cursor=int(state.get('focus_cursor',0))
        requests.append(dict(name=policy.FOCUS['name'],query=queries[focus_cursor%len(queries)],focus=True))
        state['focus_cursor']=(focus_cursor+1)%len(queries)
    topic_budget=max(0,min(budget-len(requests),len(topics)))
    requests.extend(topics[(cursor+offset)%len(topics)] for offset in range(topic_budget))
    for offset,topic in enumerate(requests):
        queried.append(topic['name'])
        try:
            order='date' if (cursor+offset)%2 else 'viewCount'
            response=service.search().list(part='snippet',type='video',q=topic['query'],order=order,
                                           publishedAfter=after,maxResults=20,relevanceLanguage='en').execute()
            for x in response.get('items',[]):
                vid=x.get('id',{}).get('videoId')
                if not vid: continue
                sn=x['snippet']
                found[vid]=dict(id=vid,title=sn['title'],url='https://www.youtube.com/watch?v='+vid,
                               published=sn['publishedAt'],source=sn['channelTitle'],discovered_via=topic['name'])
        except Exception as exc: errors.append(f"{topic['name']}: {exc}")
    hidden=skipped_ids()
    rows=sorted(policy.visible_candidates([x for x in found.values() if x['id'] not in hidden and x.get('published','')>=after]),key=lambda x:x.get('published',''),reverse=True)[:1000]
    p.write(old,rows)
    p.write(state_path,{'next_topic':(cursor+topic_budget)%len(topics), 'last_topics':queried,
                        'focus_cursor':int(state.get('focus_cursor',0)),'trend_cursor':int(state.get('trend_cursor',0)),
                        'event_cursor':int(state.get('event_cursor',0))+1,
                        'last_scan':now.isoformat(),'errors':errors})
    if errors and not rows: raise RuntimeError('Discovery failed. '+' | '.join(errors))
    return {'saved_candidates':len(rows),'searched_topics':queried,'next_topic':topics[(cursor+topic_budget)%len(topics)]['name'],'warnings':errors}
