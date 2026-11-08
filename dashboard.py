"""Viral Moment Clips — one calm screen from a fresh video to a published Short.

Flow: Make new clips (finds, downloads, cuts, subtitles) → Review → Publish.
Everything else (manual choice, filters, history, settings) stays one tab away.
"""
import os
import inspect
import datetime as dt
from zoneinfo import ZoneInfo
import streamlit as st
import pipeline as p
import app_runtime as runtime
import preparation as prep
import content_policy as policy
import scouting
import studio
import troubleshooting
os.chdir(p.ROOT)
st.set_page_config(page_title='Viral Moment Clips',page_icon='🎬',layout='wide')
st.markdown("""<style>
:root{--vmc-accent:#0a84ff;--vmc-card:#1c1c1e;--vmc-line:rgba(255,255,255,.08);--vmc-dim:#98989d}
html,body,[class*="css"],.stApp,button,input,textarea,select{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","SF Pro Display","Helvetica Neue",Inter,Arial,sans-serif!important;-webkit-font-smoothing:antialiased}
.block-container{padding-top:2.4rem;max-width:1080px}
header[data-testid="stHeader"]{background:transparent}
h1,h2,h3{letter-spacing:-.022em;font-weight:650}
.vmc-title{font-size:2.4rem!important;font-weight:700;letter-spacing:-.035em;line-height:1.1;margin:0}
.vmc-sub{color:var(--vmc-dim);font-size:1.05rem;margin:.35rem 0 1.6rem}
.vmc-pill{display:inline-block;letter-spacing:0;line-height:1.4;padding:.18rem .7rem;border-radius:999px;font-size:.78rem;font-weight:600;margin-left:.5rem;vertical-align:middle}
.vmc-ok{background:rgba(48,209,88,.16);color:#30d158}.vmc-warn{background:rgba(255,159,10,.16);color:#ff9f0a}
.vmc-meta{color:var(--vmc-dim);font-size:.86rem;line-height:1.35}
div[data-testid="stVerticalBlockBorderWrapper"]{border-radius:18px;border-color:var(--vmc-line)!important;background:var(--vmc-card)}
.stButton>button,.stDownloadButton>button,.stLinkButton>a,.stFormSubmitButton>button{border-radius:980px;font-weight:600;padding:.45rem 1.1rem;border:1px solid var(--vmc-line)}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"]{background:var(--vmc-accent);border:0;color:#fff}
.stButton>button[kind="primary"]:hover{filter:brightness(1.12)}
button[data-baseweb="tab"]{font-weight:600;font-size:1rem;padding:.55rem 1.1rem}
[data-testid="stExpander"] details{border-radius:14px;border-color:var(--vmc-line)}
[data-testid="stImage"] img,video{border-radius:14px}
.stProgress>div>div>div>div{background:var(--vmc-accent)}
</style>""",unsafe_allow_html=True)
for folder in ['inbox','jobs','exports']: (p.DATA/folder).mkdir(parents=True,exist_ok=True)


@st.cache_data(ttl=30,show_spinner=False)
def setup_checks():
    return runtime.readiness()


def show_problem(error, action=''):
    help=troubleshooting.explain(error,action)
    st.error(help['title'])
    st.markdown('\n'.join(f"{i}. {step}" for i,step in enumerate(help['steps'],1)))
    if help.get('command'): st.code(help['command'],language='bash')


def launch(action,data=None):
    try: runtime.start(action,data); st.rerun()
    except Exception as exc: show_problem(exc)


def fill(widget):
    """Full-width keyword for this Streamlit version (older releases lack width='stretch')."""
    width=inspect.signature(widget).parameters.get('width')
    return {'width':'stretch'} if width is not None and isinstance(width.default,str) else {'use_container_width':True}


FILL_BUTTON=fill(st.button); FILL_LINK=fill(st.link_button); FILL_IMAGE=fill(st.image); FILL_TABLE=fill(st.dataframe)


def meta(text):
    st.markdown(f'<div class="vmc-meta">{text}</div>',unsafe_allow_html=True)


state=runtime.active(); busy=state.get('status')=='running'
settings=p.read(p.ROOT/'config/settings.json')
defaults=studio.preferences()
checks=setup_checks()
missing=[x for x in checks if x['required'] and not x['ok']]
status=('<span class="vmc-pill vmc-warn">Setup needed — see Settings</span>' if missing
        else '<span class="vmc-pill vmc-ok">Ready</span>')
st.markdown(f'<div class="vmc-title">Viral Moment Clips{status}</div>'
            '<div class="vmc-sub">Find a fresh video, cut 15–180 s English-subtitled moments, publish publicly when you approve.</div>',
            unsafe_allow_html=True)

jobs=[]
for path in sorted((p.DATA/'exports').glob('*/job.json'),key=lambda x:x.stat().st_mtime):
    try: jobs.append((path,p.read(path)))
    except Exception: pass
pending=[(path,job) for path,job in jobs if not (path.parent/'upload.json').exists()]


@st.fragment(run_every='3s')
def activity():
    current=runtime.active()
    # The card refreshes on its own; reload the page when a task starts or ends so
    # every button returns to the right enabled state.
    if (current.get('status')=='running') != busy: st.rerun()
    with st.container(border=True):
        status=current.get('status')
        if status=='running':
            message=current.get('stage',current.get('action',''))
            progress=current.get('progress')
            st.progress((progress or 0)/100,text=message)
            eta=current.get('eta_seconds')
            note='Keep your Mac awake. You can close this page; work continues and progress is saved.'
            if eta is not None and progress:
                mins,secs=divmod(int(eta),60)
                note=f'About {mins} min {secs:02d} s left. '+note if mins else f'About {secs} s left. '+note
            meta(note)
            return
        left,right=st.columns([3,1],vertical_alignment='center')
        with left:
            if pending:
                st.markdown(f'### {len(pending)} clip{"s" if len(pending)!=1 else ""} ready to review')
                meta('Open Review below, watch them, then publish. Or make more clips first.')
            else:
                st.markdown('### Make new clips')
                meta('One press finds the strongest fresh video for your filters, cuts the best complete moments with English subtitles and brings them to Review. Nothing is published until you approve.')
        with right:
            if st.button('Make new clips',type='primary',**FILL_BUTTON,key='auto'): launch('auto')
        if status=='failed':
            failures=current.get('failures',[])
            if failures:
                st.error(f"{len(failures)} clip(s) could not be published. Successful uploads are kept.")
                for failure in failures:
                    st.write('**'+failure.get('title','Clip')+'**')
                    show_problem(failure['error'],'publish')
            else: show_problem(current.get('error','Task failed'),current.get('action',''))
        elif status=='interrupted': show_problem(current.get('error','Task interrupted'))
        elif status=='complete' and current.get('action')!='update': meta('✓ '+current.get('stage','Finished'))
activity()

review,discover,published,tools=st.tabs([f'Review ({len(pending)})','Discover','Published','Settings'])


def approve(path, job, title, description, audience):
    job.update(title=title.strip(),description=description,made_for_kids=audience=='Made for kids',
               privacy='public',needs_editorial_review=False)
    job.pop('publish_at',None)
    p.write(path,job); p.write(p.DATA/'jobs'/(job['id']+'.json'),job); p.approve(job)


with review:
    if not pending:
        st.info('Nothing to review. Press **Make new clips**, or pick a video in Discover.')
    publishable=[]; cards=[]
    top=st.container()
    for number,(path,job) in enumerate(pending,1):
        with st.container(border=True):
            if not (path.parent/'clip.mp4').is_file():
                st.markdown(f"**{job.get('title','Clip')}**")
                st.warning('The rendered video file is missing. Delete this clip and make it again.')
                if st.button('Delete',key='del-'+job['id'],disabled=busy): p.discard_clip(job['id']); st.rerun()
                continue
            video,form=st.columns([1,2],gap='large')
            video.video(str(path.parent/'clip.mp4'))
            with form:
                blocked=''
                if float(job['end'])-float(job['start'])>policy.MAX_CLIP_SECONDS: blocked='This draft is longer than 180 seconds and cannot be published.'
                else:
                    conflicts=p.upload_conflicts(job,check_video=False)
                    if conflicts: blocked='Already published from this moment: '+p.describe_conflicts(conflicts)+'. Publishing is blocked to avoid a duplicate upload.'
                title=st.text_input('Title',job['title'],max_chars=100,key='title-'+job['id'])
                meta(f"{job['end']-job['start']:.0f} s · {job.get('caption_status','')}")
                edit=job.get('editorial',{})
                if edit.get('why_this_cut'): meta('Why this moment: '+edit['why_this_cut'])
                if blocked: st.warning(blocked)
                with st.expander('Details'):
                    description=st.text_area('Description',job.get('description',''),key='desc-'+job['id'])
                    audience=st.selectbox('Audience',['Not made for kids','Made for kids'],index=1 if job.get('made_for_kids') else 0,key='aud-'+job['id'])
                    meta(f"Source: {job['source_url']} · {job['start']:.1f}–{job['end']:.1f} s")
                    if edit.get('alternative_titles'): st.write('Other titles:',edit['alternative_titles'])
                    if job.get('transcript_excerpt'): meta(job['transcript_excerpt'])
                    if (path.parent/'captions.srt').exists():
                        st.download_button('Download English subtitles',data=(path.parent/'captions.srt').read_bytes(),file_name=job['id']+'.en.srt',key='srt-'+job['id'])
                go,drop=st.columns(2)
                if go.button('Publish',type='primary',key='pub-'+job['id'],disabled=busy or bool(blocked) or not title.strip(),**FILL_BUTTON,
                             help='Your approval. The clip goes public on YouTube right away.'):
                    try:
                        with p.lock(): approve(path,job,title,description,audience)
                        launch('publish',dict(ids=[job['id']]))
                    except Exception as exc: show_problem(exc)
                if drop.button('Delete',key='del-'+job['id'],disabled=busy,**FILL_BUTTON):
                    p.discard_clip(job['id']); st.rerun()
                if not blocked and title.strip(): publishable.append((path,job,title,description,audience))
    with top:
        if len(publishable)>1:
            a,b=st.columns([3,1],vertical_alignment='center')
            a.markdown(f'**{len(publishable)} clips can be published.** Each goes public immediately with the title shown.')
            if b.button(f'Publish all {len(publishable)}',type='primary',disabled=busy,**FILL_BUTTON,key='publish-all'):
                try:
                    with p.lock():
                        for item in publishable: approve(*item)
                    launch('publish',dict(ids=[item[1]['id'] for item in publishable]))
                except Exception as exc: show_problem(exc)

with discover:
    with st.container(border=True):
        a,b=st.columns([4,1],vertical_alignment='bottom')
        url=a.text_input('Have a link? Paste one YouTube video',key='source_link',placeholder='https://www.youtube.com/watch?v=…')
        if b.button('Make clips',type='primary',disabled=busy or not url.strip(),**FILL_BUTTON,key='link-make'):
            launch('prepare',dict(url=url.strip()))
        meta(f'Finished, public videos up to {policy.MAX_SOURCE_SECONDS//60} minutes. Live, upcoming, age-restricted and members-only videos are skipped automatically.')
    prefs=scouting.preferences()
    head,refresh=st.columns([3,1],vertical_alignment='center')
    with head:
        st.markdown('### Fresh videos with traction')
        meta(f"Last {prefs['days']} day{'s' if int(prefs['days'])>1 else ''} · {int(prefs['min_views']):,}+ views · "
             f"{int(prefs['min_views_per_hour']):,}+ views/hour · {prefs['source_preference']} · up to {policy.MAX_SOURCE_SECONDS//60} min")
    if refresh.button('Search again',disabled=busy,**FILL_BUTTON,key='scout'): launch('scout')
    with st.expander('Filters'):
        with st.form('discovery-filters'):
            available=list(dict.fromkeys([x['name'] for x in policy.TOPICS]+[x['name'] for x in policy.discovery_config(p.read(p.ROOT/'config/discovery.json'))['topics']]))
            categories=st.multiselect('Categories',available,default=[x for x in prefs['categories'] if x in available],help='Leave empty to search all categories.')
            a,b=st.columns(2)
            days=a.selectbox('Uploaded within',[1,3,7,30],index=[1,3,7,30].index(int(prefs['days'])),format_func=lambda x:f'Last {x} day'+('s' if x>1 else ''))
            preference=b.selectbox('Source preference',['Prefer independent','Any source','Exclude likely official'],index=['Prefer independent','Any source','Exclude likely official'].index(prefs['source_preference']))
            min_views=a.number_input('Minimum views',min_value=0,value=int(prefs['min_views']),step=1000)
            min_vph=b.number_input('Minimum views per hour',min_value=0,value=int(prefs['min_views_per_hour']),step=100)
            events=st.text_area('Events to follow (one search per line)',value=prefs['event_queries'],placeholder='Player name + controversy\nChampions League + fan reaction')
            include=st.text_input('Must mention any of (comma-separated)',value=prefs['include_keywords'])
            exclude=st.text_input('Exclude words (comma-separated)',value=prefs['exclude_keywords'])
            blocked=st.text_input('Blocked channels or IDs (comma-separated)',value=prefs['blocked_channels'])
            meta('Independent/official status and topics are metadata estimates. Scores measure source traction, not guaranteed Shorts views. Standalone music releases stay excluded.')
            if st.form_submit_button('Save filters',type='primary',disabled=busy):
                try:
                    scouting.save_preferences(dict(categories=categories,days=days,min_views=min_views,min_views_per_hour=min_vph,source_preference=preference,event_queries=events,include_keywords=include,exclude_keywords=exclude,blocked_channels=blocked)); st.rerun()
                except Exception as exc: show_problem(exc)
    if (p.DATA/'discovery-rotation.json').exists():
        scan=p.read(p.DATA/'discovery-rotation.json')
        for warning in scan.get('errors',[]): show_problem(warning,'scout')
    ranked=p.DATA/'ranked-candidates.json'
    if ranked.exists():
        saved=p.read(ranked)
        if any(x.get('policy_version')!=policy.VERSION for x in saved):
            st.info('Some saved results predate the latest rules.')
            if st.button('Recheck saved results',disabled=busy): launch('rescreen')
        matches=scouting.visible_ranked(saved)
        visible=scouting.shortlist(matches)
        if not visible: st.info('No saved videos meet your filters. Search again, or widen the date window / lower the view thresholds. The list is never padded with weak matches.')
        grid=st.columns(2,gap='medium')
        for index,item in enumerate(visible):
            with grid[index%2].container(border=True):
                st.image(f"https://i.ytimg.com/vi/{item['id']}/mqdefault.jpg",**FILL_IMAGE)
                st.markdown(f"**{item['title']}**")
                signal=item.get('measured_views_per_hour')
                if signal is None: signal=item.get('average_views_per_hour',0)
                length=item.get('duration_seconds')
                meta(f"{item.get('source','')} · {item.get('views',0):,} views · {signal:,.0f}/hour"
                     +(f" · {length//60}:{length%60:02d}" if length else '')+f" · {', '.join(item.get('categories',[]))}")
                meta(f"{item.get('signal_label','Average')} · {item.get('source_type','')} · {item['policy']['language_status']}")
                a,b,c=st.columns([2,1,1])
                if a.button('Make clips',key='generate-'+item['id'],type='primary',disabled=busy,**FILL_BUTTON):
                    launch('prepare',dict(url=item['url'],title=item['title']))
                b.link_button('Watch',item['url'],**FILL_LINK)
                if c.button('Hide',key='hide-'+item['id'],disabled=busy,**FILL_BUTTON):
                    scouting.hide_video(item); st.rerun()
        meta(f'{len(visible)} of up to 10 choices · at most two per channel · {len(matches)} matches before diversity.')
    else: st.info('Press **Search again** for your first list, or paste a link above.')
    hidden=scouting.hidden_videos()
    if hidden:
        with st.expander(f'Hidden ({len(hidden)})'):
            for ident,record in hidden.items():
                a,b=st.columns([4,1],vertical_alignment='center')
                a.write(record['title'])
                if b.button('Restore',key='restore-'+ident,disabled=busy): scouting.restore_video(ident); st.rerun()
    skipped=[dict(title=x['title'],reason=x['reason']) for x in scouting.unsupported_videos().values()]
    if (p.DATA/'scouting-exclusions.json').exists(): skipped+=[dict(title=x.get('title',''),reason=x.get('reason','')) for x in p.read(p.DATA/'scouting-exclusions.json')]
    if skipped:
        with st.expander(f'Skipped automatically ({len(skipped)})'):
            meta('Music releases, live or unfinished streams, videos over 20 minutes and videos YouTube would not provide are left out before anything downloads.')
            st.dataframe(skipped,**FILL_TABLE,hide_index=True)
    with st.expander('Manual tools — imported videos and visual moments'):
        meta('For dance, sports action or trailers, import a video and choose the moment yourself. Clips are made from files you already downloaded, without downloading again.')
        if st.button('Import the link above without cutting',disabled=busy or not url.strip()):
            launch('import',dict(url=url.strip()))
        try: catalog=prep.source_catalog() if not busy else []
        except Exception as exc: show_problem(exc); catalog=[]
        if catalog:
            source=st.selectbox('Imported video',catalog,format_func=lambda x:x['label'])
            a,b=st.columns(2)
            if a.button('Make clips automatically',disabled=busy,**FILL_BUTTON):
                launch('prepare',dict(path=str(source['path']),source_url=source['url']))
            if source['url'].startswith('https://'): b.link_button('Watch original',source['url'],**FILL_LINK)
            if st.checkbox('Preview the full video'): st.video(str(source['path']))
            a,b=st.columns(2)
            manual_start=a.number_input('Start (seconds)',min_value=0.,value=0.)
            manual_end=b.number_input('End (seconds)',min_value=1.,value=30.)
            manual_title=st.text_input('English title for this moment',max_chars=100)
            if st.button('Create visual clip',disabled=busy):
                if not manual_title.strip() or not 1<=manual_end-manual_start<=policy.MAX_CLIP_SECONDS:
                    st.error('Enter an English title and choose a clip between 1 and 180 seconds.')
                else: launch('visual',dict(path=str(source['path']),source_url=source['url'],
                                         start=manual_start,end=manual_end,title=manual_title))
        else: meta('No imported videos yet, or a task is using the library.')

with published:
    today=dt.datetime.now(ZoneInfo(defaults['timezone'])).date()
    rows=studio.publication_rows(jobs,defaults['timezone'])
    a,b,c,d=st.columns([2,2,2,2],vertical_alignment='bottom')
    period=a.selectbox('Show',['Today','Choose a day','Month','Year','All dates'])
    day=b.date_input('Date',value=today) if period=='Choose a day' else today
    years=sorted({x['day'].year for x in rows if x['day']}|{today.year},reverse=True)
    year=b.selectbox('Year',years) if period in ('Month','Year') else today.year
    month=c.selectbox('Month',list(range(1,13)),index=today.month-1,format_func=lambda x:dt.date(2000,x,1).strftime('%B')) if period=='Month' else None
    if d.button('Sync dates from YouTube',disabled=busy,**FILL_BUTTON,help='Reads exact publication times for older uploads. Never re-uploads.'): launch('sync_history')
    query=st.text_input('Search titles',placeholder='Search published titles')
    shown=studio.filter_publications(rows,period,day,year,month,query)
    meta(f'{sum(bool(x["record"].get("video_id")) for x in shown)} published · {sum(not bool(x["record"].get("video_id")) for x in shown)} to check · {defaults["timezone"]} · uploads made by this app')
    for row in shown:
        record=row['record']; job=row['job']
        with st.container(border=True):
            a,b=st.columns([4,1],vertical_alignment='center')
            a.markdown('**'+job['title']+'**')
            with a: meta(row['date_label']+' · '+record.get('privacy','visibility not recorded'))
            if record.get('video_id'): b.link_button('Watch','https://www.youtube.com/watch?v='+record['video_id'],**FILL_LINK)
            else:
                show_problem('uncertain upload')
                with st.expander('Technical upload record'): st.json(record)
    if not shown: st.info('No uploads match. Choose All dates to see everything.')

with tools:
    st.markdown('### Setup')
    if missing: st.warning(f'{len(missing)} required item(s) missing. Run the commands below in Terminal from the project folder.')
    else: st.success('Everything required is installed and running.')
    with st.expander('Setup check details',expanded=bool(missing)):
        st.code(runtime.readiness_report(checks),language=None)
        if st.button('Re-run setup check'): setup_checks.clear(); st.rerun()
    a,b=st.columns(2)
    if a.button('Verify YouTube connection',disabled=busy,**FILL_BUTTON):
        try: st.success('Connected to '+p.channel()['name'])
        except Exception as exc: show_problem(exc)
    if b.button('Update app',disabled=busy,**FILL_BUTTON,help='Keeps your videos, sign-in and settings. A failed check restores the previous code.'): launch('update')
    st.markdown('### Preferences')
    with st.form('preferences'):
        capability=p.caption_capability()
        captions=st.toggle('Add English subtitles',value=bool(defaults['captions']))
        if not capability['supported']: meta(capability['reason']+' One-time fix in Terminal: <code>brew install ffmpeg-full</code>')
        quality=st.selectbox('Transcription',['base','small','medium'],index=['base','small','medium'].index(defaults['transcription_model']),format_func=lambda x:{'base':'Fastest · base','small':'Balanced · small (recommended)','medium':'Most accurate, slowest · medium'}[x])
        zones=['America/Toronto','America/Vancouver','Europe/London','UTC']
        timezone=st.selectbox('History timezone',zones,index=zones.index(defaults['timezone']) if defaults['timezone'] in zones else 0)
        limit=st.number_input('Daily upload attempt limit (UTC day)',min_value=1,max_value=100,value=int(settings.get('max_uploads_per_day',20)))
        meta('Publishing is always public immediately after your approval. Your Mac must stay awake during processing and uploads.')
        if st.form_submit_button('Save',type='primary',disabled=busy):
            try:
                with p.lock(): settings['max_uploads_per_day']=int(limit); p.write(p.ROOT/'config/settings.json',settings)
                studio.save_preferences(dict(captions=captions,transcription_model=quality,timezone=timezone))
                st.rerun()
            except Exception as exc: show_problem(exc)

with st.expander('Activity and diagnostics',expanded=False):
    report=runtime.diagnostics()
    st.code(report,language=None)
    st.download_button('Download diagnostics to share',report,'viral-moment-clips-diagnostics.txt')
    meta('Credentials are filtered; check before sharing. The previous manual dashboard is still available: <code>python -m streamlit run dashboard_legacy.py</code>')
