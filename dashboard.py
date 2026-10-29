"""Guided local production studio."""
import os
import datetime as dt
from zoneinfo import ZoneInfo
from pathlib import Path
import streamlit as st
import pipeline as p
import app_runtime as runtime
import preparation as prep
import content_policy as policy
import scouting
import studio
os.chdir(p.ROOT)
st.set_page_config(page_title='Viral Moment Clips',page_icon='🎬',layout='wide')
st.markdown("""<style>
.block-container{padding-top:2rem;max-width:1200px}
.vmc-head{display:flex;align-items:baseline;gap:.8rem;flex-wrap:wrap;margin-bottom:.2rem}
.vmc-head h1{margin:0;font-size:2rem;font-weight:800;letter-spacing:-.02em;background:linear-gradient(90deg,#ff4b5c,#ff9a5c);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.vmc-chip{display:inline-block;padding:.15rem .65rem;border-radius:999px;font-size:.78rem;background:#232838;color:#c9d1e3;border:1px solid #2f364a}
div[data-testid="stVerticalBlockBorderWrapper"]{border-radius:14px}
.stButton>button,.stDownloadButton>button{border-radius:10px;font-weight:600}
.stButton>button[kind="primary"]{background:linear-gradient(90deg,#ff4b5c,#ff7a4b);border:0}
.stButton>button[kind="primary"]:hover{filter:brightness(1.1)}
div[data-testid="stMetric"]{background:#181c27;border:1px solid #2a3144;border-radius:14px;padding:.7rem 1rem}
button[data-baseweb="tab"]{font-weight:600;padding:.6rem 1rem}
[data-testid="stExpander"]{border-radius:12px}
video{border-radius:12px}
</style>
<div class="vmc-head"><h1>🎬 Viral Moment Clips</h1>
<span class="vmc-chip">English audience</span><span class="vmc-chip">15–180 s coherent cuts</span><span class="vmc-chip">Public on approval</span></div>""",unsafe_allow_html=True)
for folder in ['inbox','jobs','exports']: (p.DATA/folder).mkdir(parents=True,exist_ok=True)

@st.cache_data(ttl=30,show_spinner=False)
def setup_checks():
    return runtime.readiness()

def launch(action,data=None):
    try: runtime.start(action,data); st.rerun()
    except Exception as exc: st.error(str(exc))

state=runtime.active(); busy=state.get('status')=='running'
settings=p.read(p.ROOT/'config/settings.json')
defaults=studio.preferences()
with st.sidebar:
    st.subheader('Your studio')
    st.write('Channel: Viral Moment Clips')
    st.write('Publishing: **Public immediately**')
    st.caption(f"Upload limit: {settings.get('max_uploads_per_day',20)} attempts / UTC day")
    if st.button('Verify YouTube connection',disabled=busy):
        try: st.success(p.channel()['name'])
        except Exception as exc: st.error(str(exc))
    st.caption('Your Mac must stay awake during processing and uploads.')

@st.fragment(run_every='3s')
def activity():
    current=runtime.active()
    # The banner refreshes independently; refresh the whole page on task completion
    # so controls do not retain the previous disabled state.
    if (current.get('status')=='running') != busy:
        st.rerun()
    if current:
        status=current.get('status'); message=current.get('stage',current.get('action',''))
        if status=='running': st.info('Working: '+message+' · You may leave or refresh this page.')
        elif status=='failed': st.error(current.get('error','Task failed'))
        elif status=='interrupted': st.warning(current.get('error'))
        else: st.success(message+'. Refresh the workspace below to see new clips.')
activity()
awaiting=len([1 for x in (p.DATA/'exports').glob('*/job.json') if not (x.parent/'upload.json').exists()])
hero,stat=st.columns([3,1],vertical_alignment='center')
with hero:
    if st.button('✨ Make clips automatically',type='primary',disabled=busy,use_container_width=True,
                 help='Finds the best new video from your saved filters, cuts the clips and puts them in Review & publish. You only approve the final posting.'):
        launch('auto')
    st.caption('1 · Find a fresh video   →   2 · Cut the best moments with English subtitles   →   3 · You approve in Review & publish')
with stat:
    st.metric('Awaiting your approval',awaiting)
    if st.button('Refresh',use_container_width=True): st.rerun()
find,make,review,published,tools=st.tabs(['Find videos','Make clips from a link','Review & publish','Published','Settings'])
with find:
    st.subheader('10 recent videos with traction')
    st.caption('Fresh sports moments, controversies, streamers, influencer life, unexpected events, movie cuts, engineering and celebrity footage. Your existing dance, interview and reaction categories remain available. Standalone music releases stay excluded.')
    prefs=scouting.preferences()
    with st.expander('Discovery filters — saved for future scans'):
        with st.form('discovery-filters'):
            available=list(dict.fromkeys([x['name'] for x in policy.TOPICS]+[x['name'] for x in policy.discovery_config(p.read(p.ROOT/'config/discovery.json'))['topics']]))
            categories=st.multiselect('Content categories',available,default=[x for x in prefs['categories'] if x in available],help='Leave empty to search all categories.')
            a,b=st.columns(2)
            days=a.selectbox('Uploaded within',[1,3,7,30],index=[1,3,7,30].index(int(prefs['days'])),format_func=lambda x:f'Last {x} day'+('s' if x>1 else ''))
            preference=b.selectbox('Source preference',['Prefer independent','Any source','Exclude likely official'],index=['Prefer independent','Any source','Exclude likely official'].index(prefs['source_preference']))
            min_views=a.number_input('Minimum source views',min_value=0,value=int(prefs['min_views']),step=1000)
            min_vph=b.number_input('Minimum views per hour',min_value=0,value=int(prefs['min_views_per_hour']),step=100)
            events=st.text_area('Specific events to follow (optional, one search per line)',value=prefs['event_queries'],placeholder='Player name + controversy\nChampions League + fan reaction')
            include=st.text_input('Must mention any of these (optional, comma-separated)',value=prefs['include_keywords'])
            exclude=st.text_input('Exclude words or phrases (comma-separated)',value=prefs['exclude_keywords'])
            blocked=st.text_input('Blocked channel names or IDs (exact, comma-separated)',value=prefs['blocked_channels'])
            st.caption('Independent/official status and topics are metadata estimates. A recent upload may show an older event. Scores measure source traction, not guaranteed Shorts views.')
            if st.form_submit_button('Save discovery filters',disabled=busy):
                scouting.save_preferences(dict(categories=categories,days=days,min_views=min_views,min_views_per_hour=min_vph,source_preference=preference,event_queries=events,include_keywords=include,exclude_keywords=exclude,blocked_channels=blocked)); st.rerun()
    st.caption(f"Last {prefs['days']} days · {prefs['min_views']:,}+ views · {prefs['min_views_per_hour']:,}+ views/hour · {prefs['source_preference']}")
    if st.button('Find and rank videos',disabled=busy): launch('scout')
    if (p.DATA/'discovery-rotation.json').exists():
        scan=p.read(p.DATA/'discovery-rotation.json')
        st.caption('Last searched: '+', '.join(scan.get('last_topics',[]))+'. Next scans rotate through your selected topics.')
        for warning in scan.get('errors',[]): st.warning(warning)
    ranked=p.DATA/'ranked-candidates.json'
    if ranked.exists():
        saved=p.read(ranked)
        if any(x.get('policy_version')!=policy.VERSION for x in saved):
            st.info('Older results need a refresh with the latest discovery rules. Run a new scan for recent choices.')
            if st.button('Recheck saved results',disabled=busy): launch('rescreen')
        matches=scouting.visible_ranked(saved)
        visible=scouting.shortlist(matches)
        st.caption(f'{len(visible)} of up to 10 choices · {len(matches)} matches before shortlist diversity. Hidden videos stay hidden.')
        if not visible: st.info('No saved videos meet these filters. Run a scan, or lower the view thresholds / widen the date window. The app will not fill the list with weak matches.')
        for item in visible:
            with st.expander(item['title']):
                st.caption(item['policy']['language_status'])
                st.write(item.get('source','')); st.link_button('Watch original',item['url'])
                signal=item.get('measured_views_per_hour')
                if signal is None: signal=item.get('average_views_per_hour',0)
                st.caption(f"{item.get('views',0):,} views · {signal:,.0f} views/hour · {item.get('signal_label','Average')} · Uploaded {item.get('published','')}")
                st.caption(item['source_type']+' · '+', '.join(item['categories']))
                if st.button('Use this video',key='use-'+item['id']):
                    st.session_state['source_link']=item['url']; st.success('Selected. Open Make clips from a link.')
                if st.button('Generate clips from this video',key='generate-'+item['id'],type='primary',disabled=busy):
                    launch('prepare',dict(url=item['url']))
                if st.button('Hide this video',key='hide-'+item['id'],disabled=busy):
                    scouting.hide_video(item); st.rerun()
    else: st.info('Run your first scan, or go directly to Make clips with a video link.')
    hidden=scouting.hidden_videos()
    if hidden:
        with st.expander(f'Hidden videos ({len(hidden)})'):
            for ident,record in hidden.items():
                st.write(record['title'])
                if st.button('Restore to scouting',key='restore-'+ident,disabled=busy):
                    scouting.restore_video(ident); st.rerun()
    if (p.DATA/'scouting-exclusions.json').exists():
        with st.expander('Why some sources were excluded'):
            st.dataframe(p.read(p.DATA/'scouting-exclusions.json'))
with make:
    st.subheader('Make clips from a link or an imported video')
    mode=st.radio('Start from',['YouTube link','Already imported video'],horizontal=True)
    source=None; url=''
    if mode=='YouTube link':
        url=st.text_input('Video link',key='source_link')
        if st.button('Make clips',type='primary',disabled=busy or not url):
            launch('prepare',dict(url=url))
        if st.button('Import only — choose a visual moment manually',disabled=busy or not url):
            launch('import',dict(url=url))
        st.caption('The number of clips is chosen automatically from the video length and quality. For dance or other visual action, import only, then choose Already imported video.')
    else:
        try: catalog=prep.source_catalog() if not busy else []
        except Exception as exc: st.error(str(exc)); catalog=[]
        if catalog:
            source=st.selectbox('Numbered source videos',catalog,format_func=lambda x:x['label'])
            st.link_button('Watch original',source['url']) if source['url'].startswith('https://') else None
            if st.checkbox('Preview full source'): st.video(str(source['path']))
            if st.button('Make clips',type='primary',disabled=busy):
                launch('prepare',dict(path=str(source['path']),source_url=source['url']))
        else: st.info('No sources available, or a task is using the library. Refresh after it finishes.')
    if source:
        with st.expander('Choose a visual moment manually — dance, gaming action or trailers'):
            st.caption('For a visual moment, preview the source and choose the start and end yourself. Keep it understandable to an English-speaking audience.')
            a,b=st.columns(2)
            manual_start=a.number_input('Visual clip start (seconds)',min_value=0.,value=0.)
            manual_end=b.number_input('Visual clip end (seconds)',min_value=1.,value=30.)
            manual_title=st.text_input('English title for this visual moment',max_chars=100)
            if st.button('Create visual preview',disabled=busy):
                if not manual_title.strip() or not 1<=manual_end-manual_start<=180:
                    st.error('Enter an English title and choose a clip between 1 and 180 seconds.')
                else: launch('visual',dict(path=str(source['path']),source_url=source['url'],
                                         start=manual_start,end=manual_end,title=manual_title))
    with st.expander('Editing options'):
        capability=p.caption_capability()
        captions=st.checkbox('Add English subtitles automatically',value=bool(defaults['captions']))
        if not capability['supported']: st.caption(capability['reason'])
        quality=st.selectbox('Transcription quality',['base','small','medium'],index=['base','small','medium'].index(defaults['transcription_model']),format_func=lambda x:{'base':'Fastest · base','small':'Balanced · small (recommended)','medium':'Most accurate, slowest · medium'}[x])
        if st.button('Save editing options',disabled=busy):
            studio.save_preferences(dict(captions=captions,transcription_model=quality)); st.rerun()
    editor_check=[x for x in setup_checks() if x['name'] in ('Ollama running','Local AI editor model') and not x['ok']]
    if editor_check:
        st.warning('The local AI editor is not ready, so clip making will stop before downloading. '+
                   ' · '.join(x['detail']+' — run: '+x['fix'] for x in editor_check)+'. Manual visual clips still work.')
    st.caption('Download, transcription, scene selection, titles and rendering run in one background task. Nothing is uploaded until you approve it in Review & publish.')

jobs=[]
for path in sorted((p.DATA/'exports').glob('*/job.json'),key=lambda x:x.stat().st_mtime):
    try: jobs.append((path,p.read(path)))
    except Exception: pass
with review:
    pending=[(path,job) for path,job in jobs if not (path.parent/'upload.json').exists()]
    st.subheader(f'{len(pending)} clips awaiting your approval')
    st.caption('Watch, adjust the title if you like, then press Publish — that press is your approval, and the clip goes public on YouTube immediately. Delete anything you do not want.')
    publishable=[]
    for number,(path,job) in enumerate(pending,1):
        with st.container(border=True):
            st.markdown(f"**Clip {number} · {job['title']}**")
            if not (path.parent/'clip.mp4').is_file():
                st.warning('The rendered video file is missing. Delete this clip and make it again.')
                if st.button('Delete this clip',key='del-'+job['id'],disabled=busy): p.discard_clip(job['id']); st.rerun()
                continue
            video,form=st.columns([1,2])
            video.video(str(path.parent/'clip.mp4'))
            with form:
                st.caption(f"{job['end']-job['start']:.0f}s · Source: {job['source_url']} · {job['start']:.1f}–{job['end']:.1f}s"+(' · '+job['caption_status'] if job.get('caption_status') else ''))
                blocked=''
                if float(job['end'])-float(job['start'])>180: blocked='This draft is longer than 180 seconds and cannot be published.'
                else:
                    conflicts=p.upload_conflicts(job,check_video=False)
                    if conflicts: blocked='Already published from this moment: '+p.describe_conflicts(conflicts)+'. Publishing is blocked to avoid a duplicate upload.'
                if blocked: st.warning(blocked)
                edit=job.get('editorial',{})
                if edit: st.caption('Why this moment: '+edit.get('why_this_cut',''))
                title=st.text_input('Title',job['title'],max_chars=100,key='title-'+job['id'])
                with st.expander('Description, audience and details'):
                    description=st.text_area('Description',job.get('description',''),key='desc-'+job['id'])
                    audience=st.selectbox('Audience',['Not made for kids','Made for kids'],index=1 if job.get('made_for_kids') else 0,key='aud-'+job['id'])
                    if edit:
                        st.write('Other titles:',edit.get('alternative_titles',[]))
                        st.caption(job.get('transcript_excerpt',''))
                    if (path.parent/'captions.srt').exists():
                        st.download_button('Download English subtitles',data=(path.parent/'captions.srt').read_bytes(),file_name=job['id']+'.en.srt',key='srt-'+job['id'])
                go,drop=st.columns(2)
                if go.button('Publish now',type='primary',key='pub-'+job['id'],disabled=busy or bool(blocked) or not title.strip(),use_container_width=True):
                    try:
                        with p.lock():
                            job.update(title=title.strip(),description=description,made_for_kids=audience=='Made for kids',privacy='public',needs_editorial_review=False)
                            job.pop('publish_at',None)
                            p.write(path,job); p.write(p.DATA/'jobs'/(job['id']+'.json'),job); p.approve(job)
                        launch('publish',dict(ids=[job['id']]))
                    except Exception as exc: st.error(str(exc))
                if drop.button('Delete',key='del-'+job['id'],disabled=busy,use_container_width=True):
                    p.discard_clip(job['id']); st.rerun()
                if not blocked: publishable.append((path,job,title,description,audience))
    if len(publishable)>1:
        if st.button(f'Approve & publish all {len(publishable)} clips',disabled=busy,help='Uses the titles shown above. Each is published publicly right away.'):
            ids=[]
            try:
                with p.lock():
                    for path,job,title,description,audience in publishable:
                        job.update(title=title.strip(),description=description,made_for_kids=audience=='Made for kids',privacy='public',needs_editorial_review=False)
                        job.pop('publish_at',None)
                        p.write(path,job); p.write(p.DATA/'jobs'/(job['id']+'.json'),job); p.approve(job); ids.append(job['id'])
                launch('publish',dict(ids=ids))
            except Exception as exc: st.error(str(exc))
with published:
    st.subheader('Published videos by date')
    today=dt.datetime.now(ZoneInfo(defaults['timezone'])).date()
    rows=studio.publication_rows(jobs,defaults['timezone'])
    st.caption('Upload history from this app · Timezone: '+defaults['timezone']+'. Older records retain their original UTC date because no exact upload time was stored.')
    if st.button('Refresh publication dates from YouTube',disabled=busy): launch('sync_history')
    a,b,c=st.columns(3)
    period=a.selectbox('Show',['Today','Choose a day','Month','Year','All dates'])
    day=b.date_input('Date',value=today) if period=='Choose a day' else today
    years=sorted({x['day'].year for x in rows if x['day']}|{today.year},reverse=True)
    year=b.selectbox('Year',years) if period in ('Month','Year') else today.year
    month=c.selectbox('Month',list(range(1,13)),index=today.month-1,format_func=lambda x:dt.date(2000,x,1).strftime('%B')) if period=='Month' else None
    query=st.text_input('Search published titles')
    shown=studio.filter_publications(rows,period,day,year,month,query)
    st.caption(f'{sum(bool(x["record"].get("video_id")) for x in shown)} published · {sum(not bool(x["record"].get("video_id")) for x in shown)} upload attempts to check')
    for row in shown:
        record=row['record']; job=row['job']
        st.write('**'+job['title']+'**'); st.caption(row['date_label']+' · Visibility: '+record.get('privacy','not recorded'))
        if record.get('video_id'): st.link_button('Watch on YouTube','https://www.youtube.com/watch?v='+record['video_id'])
        else: st.warning('Upload outcome uncertain. Check YouTube Studio before retrying.'); st.json(record)
    if not shown: st.info('No uploads match this date or search. Choose All dates to see the complete history.')
with tools:
    st.subheader('Mac setup check')
    checks=setup_checks()
    missing=[x for x in checks if x['required'] and not x['ok']]
    if missing: st.warning(f'{len(missing)} required item(s) missing. Run the commands below in Terminal from the project folder.')
    else: st.success('Everything required is installed and running.')
    st.code(runtime.readiness_report(checks),language=None)
    if st.button('Re-run setup check'): setup_checks.clear(); st.rerun()
    st.subheader('Activity and diagnostics')
    report=runtime.diagnostics()
    st.code(report,language=None)
    st.download_button('Download diagnostics to share',report,'viral-moment-clips-diagnostics.txt')
    st.caption('Use the copy control on the log box to copy diagnostics. Credentials are filtered; check before sharing.')
    st.subheader('App updates')
    st.caption('Updates preserve your videos, credentials and local configuration. The updater requires the installed Mac launcher. A failed code/dependency check restores the previous code; dependency versions may still have changed.')
    if st.button('Update app',disabled=busy): launch('update')
    st.subheader('English subtitles')
    st.write(p.caption_capability()['reason'])
    if not p.caption_capability()['supported']:
        st.caption('One-time Mac setup: open Terminal and run this command, then close and reopen the studio. The app detects this build automatically.')
        st.code('brew install ffmpeg-full',language='bash')
    timezone=st.selectbox('Publishing history timezone',['America/Toronto','America/Vancouver','Europe/London','UTC'],index=['America/Toronto','America/Vancouver','Europe/London','UTC'].index(defaults['timezone']) if defaults['timezone'] in ['America/Toronto','America/Vancouver','Europe/London','UTC'] else 0)
    limit=st.number_input('Daily upload attempt limit',min_value=1,max_value=100,value=int(settings.get('max_uploads_per_day',20)))
    if st.button('Save settings',disabled=busy):
        with p.lock(): settings['max_uploads_per_day']=int(limit); p.write(p.ROOT/'config/settings.json',settings)
        studio.save_preferences(dict(timezone=timezone))
        st.rerun()
    with st.expander('Manual tools and troubleshooting'):
        st.caption('The previous manual dashboard remains available with: python -m streamlit run dashboard_legacy.py')
        st.caption('If the app cannot start, logs are at data/logs/activity.log in the project folder.')
