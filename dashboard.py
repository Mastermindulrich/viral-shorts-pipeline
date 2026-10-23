"""Local browser control panel. Start with Launch.command or streamlit run dashboard.py."""
import os
from pathlib import Path
import uuid
import streamlit as st
import pipeline as p

os.chdir(p.ROOT)
for folder in ['inbox', 'jobs', 'exports']:
    (p.DATA/folder).mkdir(parents=True, exist_ok=True)
st.set_page_config(page_title='Viral Moment Clips', page_icon='🎬', layout='wide')
st.title('Viral Moment Clips')
st.caption('Original sound. Local production. Review before publishing.')


def task(fn, *args):
    try:
        with st.spinner('Working… Keep this page open.'):
            with p.lock():
                result = fn(*args)
        st.success('Done')
        return result
    except Exception as exc:
        st.error(str(exc))
        return None


with st.sidebar:
    st.subheader('YouTube connection')
    st.caption('Expected: Viral Moment Clips')
    if st.button('Check connected channel'):
        result = task(p.channel)
        if result:
            st.success(result['name'])
    st.caption('If read-only permission is missing, run python pipeline.py auth once in Terminal.')
    st.info('Daily limit: 3 upload attempts. Uploads require exact-video approval.')

create, queue, discovery, preparation = st.tabs(['Create a clip', 'Review queue', 'Source discovery', 'Prepare a batch'])
with create:
    st.subheader('Choose a local video')
    st.caption('Put full videos in data/inbox. Use the Refresh button after adding files.')
    if st.button('Refresh files'):
        st.rerun()
    files = sorted(x for x in (p.DATA/'inbox').iterdir() if x.suffix.lower() in ('.mp4','.mov','.mkv','.webm','.m4v'))
    if not files:
        st.info('No source videos yet. Open data/inbox in Finder and add a video.')
    else:
        src = st.selectbox('Source video', files, format_func=lambda x:x.name)
        try:
            duration = float(p.probe(src)['format']['duration'])
            st.caption(f'Duration: {duration:.1f} seconds')
            with st.form('clip'):
                title = st.text_input('Title', max_chars=100)
                reference = st.text_input('Original source URL or local source reference', value=f'Local file: {src.name}')
                a,b = st.columns(2)
                start = a.number_input('Start (seconds)', min_value=0., max_value=max(0.,duration-1), value=0.)
                end = b.number_input('End (seconds)', min_value=1., max_value=duration, value=min(45.,duration))
                layout = st.selectbox('Framing', ['fit','crop'], format_func=lambda x:'Full picture with padding' if x=='fit' else 'Center crop — check faces')
                description = st.text_area('Description and credits')
                audience = st.selectbox('Audience declaration', ['Choose…','Not made for kids','Made for kids'])
                submitted = st.form_submit_button('Create preview')
            if submitted:
                if audience == 'Choose…':
                    st.error('Choose the audience declaration.')
                else:
                    job = dict(id='clip-'+uuid.uuid4().hex[:12], input=str(src.relative_to(p.ROOT)),
                               source_url=reference, start=start, end=end, title=title, description=description,
                               layout=layout, made_for_kids=audience=='Made for kids', privacy='private')
                    try:
                        p.validate(job)
                        with p.lock():
                            p.write(p.DATA/'jobs'/(job['id']+'.json'),job)
                        task(p.render,job)
                    except Exception as exc:
                        st.error(str(exc))
        except Exception as exc:
            st.error(f'Cannot inspect source: {exc}')

with queue:
    st.subheader('Review finished clips')
    jobs = sorted((p.DATA/'exports').glob('*/job.json'),key=lambda x:x.stat().st_mtime,reverse=True)
    if not jobs:
        st.info('Create a preview first.')
    for path in jobs:
        try:
            job = p.read(path)
            dest = p.output(job)
            with st.expander(job['title']+' · '+job['id']):
                st.video(str(dest/'clip.mp4'))
                st.write(job.get('description',''))
                st.caption('Source: '+job['source_url'])
                if (dest/'upload.json').exists():
                    receipt = p.read(dest/'upload.json')
                    if receipt.get('video_id'):
                        st.link_button('Open uploaded video','https://www.youtube.com/watch?v='+receipt['video_id'])
                    else:
                        st.warning('Upload was attempted. Inspect YouTube Studio before retrying.')
                    continue
                if job.get('needs_editorial_review'):
                    st.warning('Automatic draft: review the suggested title, full clip context and audience declaration before approval.')
                    st.write(job.get('transcript_excerpt',''))
                    with st.form('edit-'+job['id']):
                        draft_title=st.text_input('Edit draft title',value=job['title'],max_chars=100)
                        draft_description=st.text_area('Edit draft description',value=job.get('description',''))
                        draft_audience=st.selectbox('Audience for this draft',['Choose…','Not made for kids','Made for kids'])
                        save_draft=st.form_submit_button('Save reviewed metadata')
                    if save_draft:
                        if draft_audience=='Choose…' or not draft_title.strip():
                            st.error('Choose an audience and enter a title.')
                        else:
                            def save_review():
                                job.update(title=draft_title,description=draft_description,
                                           made_for_kids=draft_audience=='Made for kids',needs_editorial_review=False)
                                (dest/'approval.json').unlink(missing_ok=True)
                                p.write(path,job)
                                p.write(p.DATA/'jobs'/(job['id']+'.json'),job)
                                return True
                            if task(save_review): st.rerun()
                    continue
                if not (dest/'approval.json').exists():
                    with st.form('approve-'+job['id']):
                        privacy = st.selectbox('Upload visibility',['private','unlisted','public'],key='privacy-'+job['id'])
                        date = st.text_input('Optional scheduled time (ISO format with timezone)',placeholder='2030-01-01T12:00:00-05:00',key='date-'+job['id'])
                        clearance = st.text_input('Your external clearance reference',key='clear-'+job['id'])
                        checked = st.checkbox('I reviewed this clip, its context, captions, title and audience setting.',key='check-'+job['id'])
                        approved = st.form_submit_button('Approve this version')
                    if approved:
                        if not checked or not clearance.strip():
                            st.error('Review confirmation and external reference are required.')
                        elif date and privacy!='private':
                            st.error('Scheduled uploads must be private until publication.')
                        else:
                            def approve_version():
                                job['privacy']=privacy
                                if date.strip(): job['publish_at']=date.strip()
                                else: job.pop('publish_at',None)
                                # Visibility only changes metadata, not video bytes.
                                p.write(dest/'job.json',job)
                                p.write(p.DATA/'jobs'/(job['id']+'.json'),job)
                                p.approve(job,clearance)
                                return True
                            if task(approve_version): st.rerun()
                else:
                    st.write('Approved visibility: '+job.get('privacy','private'))
                    if job.get('publish_at'): st.write('Publish at: '+job['publish_at'])
                    confirmed=st.checkbox('Upload this approved version to Viral Moment Clips',key='upload-confirm-'+job['id'])
                    if st.button('Upload approved clip',key='upload-'+job['id'],disabled=not confirmed):
                        task(p.upload,job)
                        st.rerun()
        except Exception as exc:
            st.error(f'{path.parent.name}: {exc}')

with discovery:
    st.subheader('Monitor source channels')
    st.caption('Starter research list: experiments, science and interviews. These are scouting sources, not licensed partners.')
    if st.button('Add starter research channels'):
        def add_starters():
            existing=p.read(p.ROOT/'config'/'sources.json')
            ids={s['channel_id'] for s in existing}
            existing.extend(s for s in p.read(p.ROOT/'config'/'starter-sources.json') if s['channel_id'] not in ids)
            p.write(p.ROOT/'config'/'sources.json',existing)
        task(add_starters)
    st.caption('Recent uploads from chosen channels. Discovery does not download, clear, or publish footage.')
    with st.form('source'):
        name=st.text_input('Creator name')
        cid=st.text_input('YouTube channel ID (UC…, not @handle)')
        save=st.form_submit_button('Add source')
    if save:
        import re
        if not name.strip() or not re.fullmatch(r'UC[\w-]{22}',cid.strip()):
            st.error('Enter a creator name and valid channel ID.')
        else:
            def add_source():
                sources=p.read(p.ROOT/'config'/'sources.json')
                if not any(s['channel_id']==cid.strip() for s in sources):
                    sources.append(dict(name=name.strip(),channel_id=cid.strip()))
                    p.write(p.ROOT/'config'/'sources.json',sources)
            task(add_source)
    sources=p.read(p.ROOT/'config'/'sources.json')
    st.write(sources or 'No channels configured yet.')
    if st.button('Find recent videos'):
        task(p.discover)
    if (p.DATA/'candidates.json').exists():
        for item in p.read(p.DATA/'candidates.json'):
            st.write(item['source']+' · '+item['title'])
            st.link_button('View source',item['url'])


with preparation:
    import preparation as prep
    st.subheader('Turn a longer video into clip drafts')
    st.caption('Free local speech analysis. No narration. Drafts are never automatically approved or uploaded.')
    st.info('Install the optional tools once: python -m pip install -r requirements-preparation.txt')
    with st.form('import-video'):
        video_link=st.text_input('YouTube video link')
        external_ref=st.text_input('External content-clearance reference')
        import_confirm=st.checkbox('This source is cleared through my separate process for downloading and editing.')
        import_submit=st.form_submit_button('Import source video')
    if import_submit:
        if not import_confirm:
            st.error('Confirm source clearance first.')
        else:
            imported=task(prep.import_video,video_link,external_ref)
            if imported:
                st.session_state['imported_source']=imported
                st.success('Source imported. Choose it below to prepare drafts.')
    choices=sorted(x for x in (p.DATA/'inbox').glob('*') if x.suffix.lower() in ('.mp4','.mov','.mkv','.webm'))
    choices+=sorted(x for x in (p.DATA/'imports').glob('*/source.*') if x.suffix.lower() in ('.mp4','.mov','.mkv','.webm'))
    if choices:
        selected=st.selectbox('Video to analyze',choices,format_func=lambda x:x.parent.name+'/'+x.name)
        source_record=selected.parent/'source.json'
        ref=p.read(source_record)['source_url'] if source_record.exists() else 'Local file: '+selected.name
        with st.form('prepare-batch'):
            source_ref=st.text_input('Source reference for draft credits',value=ref)
            n=st.slider('Maximum draft clips',1,5,3)
            model=st.selectbox('Local transcription model',['base','small'],help='Base is faster. Small may recognize speech more accurately.')
            caps=st.checkbox('Burn in captions (requires FFmpeg subtitles/libass support)',value=False)
            prepare_submit=st.form_submit_button('Analyze speech and create previews')
        if prepare_submit:
            st.caption('First run downloads a free speech model. Long videos may take significant time on CPU.')
            result=task(prep.prepare,selected,source_ref,n,model,caps)
            if result:
                st.success(f'{len(result)} draft clips ready in Review queue. Edit their metadata, review and approve there.')
    else:
        st.caption('Import a source above or place a local video in data/inbox.')
