"""Guided local production studio."""
import os
from pathlib import Path
import streamlit as st
import pipeline as p
import app_runtime as runtime
import preparation as prep
import content_policy as policy
os.chdir(p.ROOT)
st.set_page_config(page_title='Viral Moment Clips',page_icon='🎬',layout='wide')
st.title('🎬 Viral Moment Clips')
st.caption('English audience · Clips up to 60 seconds · Public publishing')
for folder in ['inbox','jobs','exports']: (p.DATA/folder).mkdir(parents=True,exist_ok=True)

def launch(action,data=None):
    try: runtime.start(action,data); st.rerun()
    except Exception as exc: st.error(str(exc))

state=runtime.active(); busy=state.get('status')=='running'
settings=p.read(p.ROOT/'config/settings.json')
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
    if current:
        status=current.get('status'); message=current.get('stage',current.get('action',''))
        if status=='running': st.info('Working: '+message+' · You may leave or refresh this page.')
        elif status=='failed': st.error(current.get('error','Task failed'))
        elif status=='interrupted': st.warning(current.get('error'))
        else: st.success(message+'. Refresh the workspace below to see new clips.')
activity()
if st.button('Refresh workspace'): st.rerun()
find,make,review,published,tools=st.tabs(['1 · Find videos','2 · Make clips','3 · Review & publish','Published','Activity & settings'])
with find:
    st.subheader('Find promising videos across every topic')
    st.info('All topics remain eligible. Gaming, hot interviews, movie trailers, music reactions, African urban dance and TikTok dance challenges are included. Official artist music releases are filtered using metadata indicators.')
    st.caption('One scan searches rotating topics and ranks results by available engagement signals. Scores are estimates, not guaranteed views.')
    if st.button('Find and rank videos',type='primary',disabled=busy): launch('scout')
    ranked=p.DATA/'ranked-candidates.json'
    if ranked.exists():
        for item in policy.visible_candidates(p.read(ranked))[:50]:
            with st.expander(item['title']):
                st.caption(item['policy']['language_status'])
                st.write(item.get('source','')); st.link_button('Watch original',item['url'])
                st.caption(f"Views: {item.get('views',0):,} · Priority: {item.get('priority_score',0)}")
                if st.button('Use this video',key='use-'+item['video_id'] if 'video_id' in item else 'use-'+item['url'],disabled=busy):
                    st.session_state['source_link']=item['url']; st.success('Selected. Open 2 · Make clips.')
    else: st.info('Run your first scan, or go directly to Make clips with a video link.')
    if (p.DATA/'scouting-exclusions.json').exists():
        with st.expander('Why some sources were excluded'):
            st.dataframe(p.read(p.DATA/'scouting-exclusions.json'))
with make:
    st.subheader('Generate a ready-to-review batch')
    mode=st.radio('Start from',['YouTube link','Already imported video'],horizontal=True)
    source=None
    if mode=='YouTube link':
        url=st.text_input('Video link',key='source_link')
        clearance=st.text_input('Permission record',help='For example: your own footage, licence number, or creator permission email.')
        if st.button('Import only — choose a visual moment afterward',disabled=busy):
            if not url or not clearance.strip(): st.error('Enter the link and permission record.')
            else: launch('import',dict(url=url,clearance=clearance))
        st.caption('For dance or other visual action: import only, then select Already imported video and choose a visual moment manually.')
    else:
        try: catalog=prep.source_catalog() if not busy else []
        except Exception as exc: st.error(str(exc)); catalog=[]
        if catalog:
            source=st.selectbox('Numbered source videos',catalog,format_func=lambda x:x['label'])
            st.link_button('Watch original',source['url']) if source['url'].startswith('https://') else None
            if st.checkbox('Preview full source'): st.video(str(source['path']))
        else: st.info('No sources available, or a task is using the library. Refresh after it finishes.')
    if source:
        with st.expander('Choose a visual moment manually — dance, gaming action or trailers'):
            st.caption('The AI editor selects dialogue. For a visual moment, preview the source and choose the start and end yourself. Keep it understandable to an English-speaking audience.')
            a,b=st.columns(2)
            manual_start=a.number_input('Visual clip start (seconds)',min_value=0.,value=0.)
            manual_end=b.number_input('Visual clip end (seconds)',min_value=1.,value=30.)
            manual_title=st.text_input('English title for this visual moment',max_chars=100)
            if st.button('Create visual preview',disabled=busy):
                if not manual_title.strip() or not 1<=manual_end-manual_start<=60:
                    st.error('Enter an English title and choose a clip between 1 and 60 seconds.')
                else: launch('visual',dict(path=str(source['path']),source_url=source['url'],
                                         start=manual_start,end=manual_end,title=manual_title))
    count=st.slider('Clips to suggest',1,5,3)
    with st.expander('Editing options'):
        captions=st.checkbox('Burn in captions',value=False)
        st.caption('Uses local Qwen AI to study English dialogue and choose complete scenes with supported, curiosity-driven titles. Action and visual reactions need your review.')
    if st.button('Generate clips',type='primary',disabled=busy):
        if mode=='YouTube link':
            if not url or not clearance.strip(): st.error('Enter the link and permission record.')
            else: launch('prepare',dict(url=url,clearance=clearance,count=count,captions=captions))
        elif source: launch('prepare',dict(path=str(source['path']),source_url=source['url'],count=count,captions=captions))
    st.caption('Downloading, transcription, scene selection, titles and rendering happen in one background task. No upload happens here.')

jobs=[]
for path in sorted((p.DATA/'exports').glob('*/job.json'),key=lambda x:x.stat().st_mtime):
    try: jobs.append((path,p.read(path)))
    except Exception: pass
with review:
    pending=[(path,job) for path,job in jobs if not (path.parent/'upload.json').exists()]
    st.subheader(f'{len(pending)} clips awaiting review')
    st.caption('Watch each clip, edit its title, select the audience, then publish. Publishing sends it to YouTube as public immediately; playback still depends on YouTube processing.')
    ready=[]
    for number,(path,job) in enumerate(pending,1):
        with st.expander(f"Clip {number:03d} · {job['title']}"):
            st.video(str(path.parent/'clip.mp4'))
            st.caption(f"Source: {job['source_url']} · {job['start']:.1f}–{job['end']:.1f}s")
            if float(job['end'])-float(job['start'])>60:
                st.warning('This older draft is longer than 60 seconds and cannot be published. Generate a new batch or choose a shorter visual cut.')
                continue
            edit=job.get('editorial',{})
            if edit:
                st.write(edit.get('topic','')); st.write('Why this moment: '+edit.get('why_this_cut',''))
                st.write('Other titles:',edit.get('alternative_titles',[]))
                with st.expander('Transcript evidence'): st.write(edit.get('evidence_quote','')); st.write(job.get('transcript_excerpt',''))
            with st.form('review-'+job['id']):
                title=st.text_input('Title',job['title'],max_chars=100)
                description=st.text_area('Description',job.get('description',''))
                audience=st.selectbox('Audience',['Choose…','Not made for kids','Made for kids'])
                ref=st.text_input('Permission record',value=job.get('clearance_reference',''))
                watched=st.checkbox('I reviewed the clip and title, confirmed English dialogue (or a visual clip understandable without dialogue) and English metadata, and approve public publishing.')
                save=st.form_submit_button('Save as ready to publish',disabled=busy)
            if save:
                if not title.strip() or audience=='Choose…' or not ref.strip() or not watched: st.error('Complete the title, audience, permission record and review confirmation.')
                else:
                    try:
                        with p.lock():
                            job.update(title=title.strip(),description=description,made_for_kids=audience=='Made for kids',privacy='public',needs_editorial_review=False,clearance_reference=ref.strip())
                            job.pop('publish_at',None)
                            p.write(path,job); p.write(p.DATA/'jobs'/(job['id']+'.json'),job); p.approve(job,ref)
                        st.rerun()
                    except Exception as exc: st.error(str(exc))
            if job.get('privacy')=='public' and not job.get('needs_editorial_review'):
                try: p.check_approval(job); approved=True
                except Exception: approved=False
                if approved:
                    st.success('Ready · Public immediately')
                    if st.checkbox('Include in publish batch',key='select-'+job['id']): ready.append(job['id'])
                    if st.button('Publish this clip now',key='publish-'+job['id'],disabled=busy): launch('publish',dict(ids=[job['id']]))
    if st.button(f'Publish selected clips ({len(ready)})',type='primary',disabled=busy or not ready): launch('publish',dict(ids=ready))
with published:
    found=False
    for path,job in reversed(jobs):
        receipt=path.parent/'upload.json'
        if receipt.exists():
            found=True; record=p.read(receipt); st.write(job['title'])
            if record.get('video_id'): st.link_button('Watch on YouTube','https://www.youtube.com/watch?v='+record['video_id'])
            else: st.warning('Upload outcome uncertain. Check YouTube Studio before retrying.'); st.json(record)
    if not found: st.info('Uploaded videos will appear here.')
with tools:
    st.subheader('Activity and diagnostics')
    report=runtime.diagnostics()
    st.code(report,language=None)
    st.download_button('Download diagnostics to share',report,'viral-moment-clips-diagnostics.txt')
    st.caption('Use the copy control on the log box to copy diagnostics. Credentials are filtered; check before sharing.')
    st.subheader('App updates')
    st.caption('Updates preserve your videos, credentials and local configuration. The updater requires the installed Mac launcher. A failed code/dependency check restores the previous code; dependency versions may still have changed.')
    if st.button('Update app',disabled=busy): launch('update')
    limit=st.number_input('Daily upload attempt limit',min_value=1,max_value=100,value=int(settings.get('max_uploads_per_day',20)))
    if st.button('Save settings',disabled=busy):
        with p.lock(): settings['max_uploads_per_day']=int(limit); p.write(p.ROOT/'config/settings.json',settings)
        st.rerun()
    with st.expander('Manual tools and troubleshooting'):
        st.caption('The previous manual dashboard remains available with: python -m streamlit run dashboard_legacy.py')
        st.caption('If the app cannot start, logs are at data/logs/activity.log in the project folder.')
