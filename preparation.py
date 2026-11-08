"""On-demand source import and draft batches; never uploads or approves content."""
import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import pipeline as p
import content_policy as policy

MAX_SOURCE_SECONDS = policy.MAX_SOURCE_SECONDS
# yt-dlp messages that mean YouTube will not hand this video to an anonymous
# download. Retrying cannot help, so they become a plain ValueError.
UNSUPPORTED_HINTS = ('sign in to confirm','private video','members-only','members only','join this channel',
                     'not available in your country','blocked it in your country','video unavailable',
                     'premieres in','live event will begin','this live event','is not a valid url','unsupported url',
                     'requested format is not available','copyright','account associated','has been removed',
                     'age-restricted','inappropriate','confirm your age','drm')


def source_problem(info):
    """Reason yt-dlp metadata shows a video cannot be processed, or ''."""
    status = str(info.get('live_status') or '')
    if info.get('is_live') or status in ('is_live','is_upcoming','post_live'):
        return 'This video is still live, upcoming or still processing after a live stream. Try it once YouTube finishes processing.'
    availability = str(info.get('availability') or '')
    if availability in ('private','premium_only','subscriber_only','needs_auth'):
        return 'YouTube only allows signed-in or paying viewers to watch this video, so it cannot be downloaded.'
    if int(info.get('age_limit') or 0) >= 18:
        return 'This video is age-restricted, so it cannot be downloaded without signing in.'
    duration = info.get('duration')
    if not duration:
        return 'YouTube did not report a length for this video (often a live or unfinished upload).'
    if duration > MAX_SOURCE_SECONDS:
        return f'This video is longer than {MAX_SOURCE_SECONDS//60} minutes. Choose a shorter one so processing stays fast.'
    if duration < policy.MIN_SOURCE_SECONDS:
        return f'This video is shorter than {policy.MIN_SOURCE_SECONDS} seconds, too short to cut a clip from.'
    return ''


def download_refused(exc):
    text = str(exc).lower()
    return any(hint in text for hint in UNSUPPORTED_HINTS)


def video_url(url):
    parsed = urlparse(url.strip())
    if parsed.scheme != 'https' or parsed.username or parsed.password:
        raise ValueError('Use an HTTPS YouTube video link')
    host = parsed.hostname
    if host == 'youtu.be':
        vid = parsed.path.strip('/')
    elif host in ('www.youtube.com','youtube.com','m.youtube.com'):
        if parsed.path == '/watch':
            vid = parse_qs(parsed.query).get('v',[''])[0]
        elif re.fullmatch(r'/(shorts|live)/[^/]+/?',parsed.path):
            vid = parsed.path.rstrip('/').split('/')[-1]
        else:
            vid = ''
    else:
        vid = ''
    if not re.fullmatch(r'[\w-]{11}',vid,flags=re.ASCII):
        raise ValueError('Use one video link, not a playlist, channel or other website')
    return 'https://www.youtube.com/watch?v='+vid


def import_video(url, clearance=''):
    url = video_url(url)
    clearance = clearance.strip() or p.DEFAULT_REFERENCE
    from yt_dlp import YoutubeDL
    vid = parse_qs(urlparse(url).query)['v'][0]
    folder = p.DATA/'imports'/vid
    receipt = folder/'source.json'
    if receipt.exists():
        old = p.read(receipt)
        if Path(old['input']).is_file():
            decision=policy.screen(old)
            if not decision['eligible']: raise ValueError(decision['reason'])
            return old
    opts = dict(noplaylist=True, outtmpl=str(folder/'source.%(ext)s'),
                format='bv*[height<=720][ext=mp4]+ba[ext=m4a]/bv*[height<=720]+ba/b[height<=720]/b',
                merge_output_format='mp4', socket_timeout=30, retries=3, fragment_retries=3, quiet=True,
                concurrent_fragment_downloads=4, max_filesize=2_000_000_000)
    from yt_dlp.utils import DownloadError
    try:
        with YoutubeDL(opts) as ydl:
            # Read metadata once and check it before anything is written to disk.
            info = ydl.extract_info(url,download=False)
            problem = source_problem(info)
            if problem: raise ValueError(problem)
            decision=policy.screen(dict(title=info.get('title',''),creator=info.get('uploader',''),
                                        description=info.get('description',''),audio_language=info.get('language',''),
                                        categoryId='10' if 'Music' in (info.get('categories') or []) else ''))
            if not decision['eligible']: raise ValueError(decision['reason'])
            folder.mkdir(parents=True, exist_ok=True)
            # Reuse the metadata already read instead of asking YouTube twice.
            try: info = ydl.process_ie_result(info, download=True)
            except (TypeError, KeyError, AttributeError): info = ydl.extract_info(url, download=True)
    except DownloadError as exc:
        if download_refused(exc):
            raise ValueError('YouTube will not provide this video for download: '+str(exc).replace('ERROR: ','')[:240]) from exc
        raise
    files = [x for x in folder.glob('source.*') if x.suffix.lower() in ('.mp4','.mkv','.webm','.mov')]
    if len(files)!=1:
        raise ValueError('Download did not produce one merged video. Check FFmpeg and source availability.')
    p.probe(files[0])
    record = dict(input=str(files[0].resolve()),source_url=url,title=info.get('title',''),
                  creator=info.get('uploader',''),clearance_reference=clearance.strip(),
                  audio_language=info.get('language',''),description=info.get('description',''),
                  categoryId='10' if 'Music' in (info.get('categories') or []) else '')
    p.write(receipt,record)
    return record


def windows(segments, limit=3):
    # Deterministic speech-window heuristic: prioritize intelligible, complete sentences.
    results=[]
    for i, first in enumerate(segments):
        chosen=[]
        for seg in segments[i:]:
            if float(seg['end'])-float(first['start'])>50:
                break
            chosen.append(seg)
            if float(seg['end'])-float(first['start'])>=25 and re.search(r'[.!?]$',seg['text'].strip()):
                break
        if not chosen: continue
        a,b=float(first['start']),float(chosen[-1]['end'])
        text=' '.join(s['text'].strip() for s in chosen).strip()
        if b-a<15 or len(text.split())<15: continue
        score = min(len(text.split())/(b-a),3) + bool(re.search(r'[.!?]$',text))
        results.append(dict(start=a,end=b,text=text,score=score))
    selected=[]
    for item in sorted(results,key=lambda x:x['score'],reverse=True):
        if all(item['end']<=s['start'] or item['start']>=s['end'] for s in selected):
            selected.append(item)
        if len(selected)>=limit: break
    return sorted(selected,key=lambda x:x['start'])


_MODELS={}


def whisper(model):
    """One loaded speech model per process, using every CPU core."""
    import os
    from faster_whisper import WhisperModel
    key=(model,id(WhisperModel))
    if key not in _MODELS:
        _MODELS[key]=WhisperModel(model,device='cpu',compute_type='int8',cpu_threads=os.cpu_count() or 4)
    return _MODELS[key]


def prepare(source, source_url, count='auto', model='base', captions=False, editor='basic', editor_model='qwen2.5:7b', progress=None):
    source=Path(source).resolve()
    receipt=source.parent/'source.json'
    record={}
    if receipt.exists():
        record=p.read(receipt)
        decision=policy.screen(record)
        if not decision['eligible']: raise ValueError(decision['reason'])
    key=p.digest(source)[:16]
    transcript=p.DATA/'transcripts'/(key+('-words-'+model+'-v3' if editor=='semantic' else '')+'.json')
    language_path=transcript.with_suffix('.language.json')
    def english_check():
        if language_path.exists():
            language=p.read(language_path)
            if language.get('language')!='en' and language.get('probability',0)>=.8:
                raise ValueError('English dialogue required for automatic editing. For visual dance, choose a manual cut and review any dialogue.')
    if not transcript.exists():
        # Segments are generated lazily: the detected language is known before any
        # transcription work, so a non-English source stops in seconds, not minutes.
        segments,language_info=whisper(model).transcribe(
            str(source),vad_filter=True,word_timestamps=True,beam_size=1,condition_on_previous_text=False)
        p.write(language_path,dict(language=language_info.language,probability=language_info.language_probability))
        english_check()
        total=float(getattr(language_info,'duration',0) or 0); rows=[]
        for s in segments:
            rows.append(dict(start=s.start,end=s.end,text=s.text.strip(),
                             words=[dict(start=w.start,end=w.end,word=w.word) for w in (s.words or [])]))
            if progress and total and len(rows)%20==0:
                progress(15+int(40*min(1,s.end/total)),f'Transcribing — {int(s.end//60)} of {int(total//60)+1} minutes done')
        p.write(transcript,rows)
    english_check()
    if progress: progress(58, 'Transcript ready — selecting the strongest complete scenes')
    if count in (None,'auto'):
        spoken=p.read(transcript)
        minutes=(float(spoken[-1]['end']) if spoken else 0)/60
        count=min(5,max(1,round(minutes/6)))
    if editor=='semantic':
        import editorial
        metadata={}
        if (source.parent/'source.json').exists():
            record=p.read(source.parent/'source.json')
            metadata={k:record.get(k,'') for k in ['title','creator','source_url']}
        report=editorial.select_scenes(p.read(transcript),count,editor_model,metadata)
        p.write(p.DATA/'editorial'/(key+'-'+editorial.VERSION+'.json'),report)
        candidates=report['scenes']
    else:
        candidates=windows(p.read(transcript),count)
    if progress: progress(72, f'{len(candidates)} coherent moments selected — rendering previews')
    if not candidates:
        raise ValueError('Not enough continuous speech for suggestions. Use the manual clip form for silent/action videos.')
    jobs=[]
    for item in candidates:
        burned=bool(captions and p.caption_capability()['supported'])
        ident=(('story-v3-'+('sub-' if burned else 'srt-')) if editor=='semantic' else 'draft-en60-')+key+'-'+str(round(item['start']*1000))
        if editor=='semantic': ident+='-'+str(round(item['end']*1000))+'-'+model
        dest=p.DATA/'jobs'/(ident+'.json')
        if dest.exists():
            old=p.read(dest)
            p.validate(old)
            if not (p.output(old)/'clip.mp4').exists(): p.render(old)
            jobs.append(old); continue
        title=item.get('title') or re.split(r'(?<=[.!?])\s',item['text'])[0][:95].strip()
        job=dict(id=ident,input=str(source),source_url=source_url,start=item['start'],end=item['end'],
                 title=title,description='',layout='fit',made_for_kids=False,privacy='public',
                 needs_editorial_review=True,transcript_excerpt=item['text'])
        job['clearance_reference']=record.get('clearance_reference','')
        job['caption_source']=str(transcript)
        job['caption_status']='English subtitles burned in' if burned else 'English SRT available; subtitles not burned in'
        job['caption_timing']='word timestamps' if any(x.get('words') for x in p.read(transcript)) else 'segment timestamps'
        if editor=='semantic':
            job['editorial']={k:v for k,v in item.items() if k not in ('start','end','text','title')}
        if burned: job['transcript']=str(transcript)
        p.validate(job)
        p.write(dest,job)
        p.render(job)
        if progress: progress(min(96, 72 + int(24*len(jobs)/max(1,len(candidates)))), f'Rendered clip {len(jobs)} of {len(candidates)}')
        jobs.append(job)
    return jobs


def source_catalog():
    """Stable display numbers; never rename source files or existing clip jobs."""
    catalog_path=p.DATA/'source-catalog.json'
    with p.lock():
        catalog=p.read(catalog_path) if catalog_path.exists() else {}
        receipts=sorted((p.DATA/'imports').glob('*/source.json'),key=lambda x:(x.stat().st_mtime,x.parent.name))
        next_number=max((x['number'] for x in catalog.values()),default=0)+1
        for receipt in receipts:
            key=receipt.parent.name
            if key not in catalog:
                catalog[key]={'number':next_number}
                next_number+=1
        p.write(catalog_path,catalog)
    sources=[]
    for receipt in receipts:
        record=p.read(receipt)
        path=Path(record['input'])
        if not path.is_file(): continue
        number=catalog[receipt.parent.name]['number']
        title=record.get('title','').strip() or receipt.parent.name
        sources.append(dict(path=path,number=number,label=f'Import {number:03d} — {title}',
                            title=title,creator=record.get('creator',''),url=record['source_url']))
    sources.sort(key=lambda x:x['number'])
    for path in sorted((p.DATA/'inbox').glob('*')):
        if path.suffix.lower() in ('.mp4','.mov','.mkv','.webm'):
            sources.append(dict(path=path,number=None,label='Local file — '+path.name,
                                title=path.name,creator='',url='Local file: '+path.name))
    return sources


def caption_visual(job, model='small', burn=True):
    """Try English captions on just the chosen visual cut; keep source audio unchanged."""
    audio=p.DATA/'transcripts'/(job['id']+'-audio.wav')
    transcript=audio.with_suffix('.json')
    audio.parent.mkdir(parents=True,exist_ok=True)
    try:
        p.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(job['start']),
               '-i',str(p.material(job)),'-t',str(job['end']-job['start']),
               '-vn','-ac','1','-ar','16000',str(audio)])
        segments,info=whisper(model).transcribe(
            str(audio),vad_filter=True,word_timestamps=True,beam_size=5)
        segments=list(segments)
        if info.language!='en' or info.language_probability<.8 or not segments:
            job['caption_status']='No confident English speech detected; subtitles omitted'
            return job
        offset=float(job['start'])
        p.write(transcript,[dict(start=offset+s.start,end=offset+s.end,text=s.text.strip(),
            words=[dict(start=offset+w.start,end=offset+w.end,word=w.word) for w in (s.words or [])]) for s in segments])
        job.update(caption_source=str(transcript),caption_timing='word timestamps')
        if burn and p.caption_capability()['supported']:
            job.update(transcript=str(transcript),caption_status='English subtitles burned in')
        else: job['caption_status']='English SRT available; subtitles not burned in'
    except Exception as exc:
        print('Visual subtitle preparation failed: '+str(exc),flush=True)
        job['caption_status']='English subtitles unavailable: '+str(exc)[:200]
    finally: audio.unlink(missing_ok=True)
    return job
