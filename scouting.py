"""Measured source signals and a transparent prioritization heuristic, not a forecast."""
import datetime as dt
import math
import re
import statistics
import pipeline as p
import content_policy as policy

DEFAULTS=dict(categories=[x['name'] for x in policy.TOPICS],days=3,min_views=5000,
              min_views_per_hour=200,source_preference='Prefer independent',
              include_keywords='',exclude_keywords='',blocked_channels='',event_queries='')
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
    'Movie trailers':r'trailer|teaser', 'Music reactions':r'react|first time hearing'}


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
    found=[name for name,terms in CATEGORY_TERMS.items() if re.search(terms,text)]
    via=item.get('discovered_via','')
    if via in CATEGORY_TERMS and via not in found: found.append(via)
    return found or ([via] if via and not via.startswith('Popular chart:') else ['Other'])


def filter_ranked(items, prefs=None, now=None):
    prefs=preferences() if prefs is None else prefs
    now=now or dt.datetime.now(dt.timezone.utc)
    result=[]
    for item in items:
        try: age=(now-dt.datetime.fromisoformat(item['published'].replace('Z','+00:00'))).total_seconds()/3600
        except (KeyError,ValueError,TypeError): continue
        if age>int(prefs['days'])*24 or age<-.25: continue
        if item.get('views',0)<float(prefs['min_views']): continue
        signal=item.get('measured_views_per_hour')
        if signal is None: signal=item.get('average_views_per_hour',0)
        if signal<float(prefs['min_views_per_hour']): continue
        if not 15<=item.get('duration_seconds',0)<=10800: continue
        text=(item.get('title','')+' '+item.get('source','')).casefold()
        if any(x in text for x in keyword_list(prefs['exclude_keywords'])): continue
        required=keyword_list(prefs['include_keywords'])
        if required and not any(x in text for x in required): continue
        blocked=keyword_list(prefs['blocked_channels'])
        if item.get('source','').casefold() in blocked or item.get('channel_id','').casefold() in blocked: continue
        source_type=policy.source_type(item)
        if prefs['source_preference']=='Exclude likely official' and source_type.startswith('Likely'): continue
        categories=categories_for(item)
        if prefs['categories'] and not set(categories).intersection(prefs['categories']) and item.get('discovered_via')!='Your event search': continue
        row=dict(item,categories=categories,source_type=source_type)
        row['display_score']=item.get('priority_score',0)+(5 if prefs['source_preference']=='Prefer independent' and source_type.startswith('Unverified') else 0)
        result.append(row)
    return sorted(result,key=lambda x:x['display_score'],reverse=True)


def shortlist(items, limit=10):
    """Keep ten strong choices without letting one channel fill the list."""
    selected=[]; per_source={}; titles=set()
    for item in items:
        title=re.sub(r'\W+',' ',item.get('title','').casefold()).strip()
        source=item.get('channel_id') or item.get('source','')
        if title in titles or per_source.get(source,0)>=2: continue
        selected.append(item); titles.add(title); per_source[source]=per_source.get(source,0)+1
        if len(selected)>=limit: break
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


def visible_ranked(items):
    hidden=hidden_videos()
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
                           channel_id=snippet.get('channelId',''),
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
    topic_budget=min(budget-len(requests),len(topics))
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
    hidden=hidden_videos()
    rows=sorted(policy.visible_candidates([x for x in found.values() if x['id'] not in hidden and x.get('published','')>=after]),key=lambda x:x.get('published',''),reverse=True)[:1000]
    p.write(old,rows)
    p.write(state_path,{'next_topic':(cursor+topic_budget)%len(topics), 'last_topics':queried,
                        'event_cursor':int(state.get('event_cursor',0))+1,
                        'last_scan':now.isoformat(),'errors':errors})
    if errors and not rows: raise RuntimeError('Discovery failed. '+' | '.join(errors))
    return {'saved_candidates':len(rows),'searched_topics':queried,'next_topic':topics[(cursor+topic_budget)%len(topics)]['name'],'warnings':errors}
