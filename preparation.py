"""On-demand source import and draft batches; never uploads or approves content."""
import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import pipeline as p
import content_policy as policy


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


def import_video(url, clearance):
    url = video_url(url)
    if not clearance.strip():
        raise ValueError('Record the reference from your separate content-clearance process')
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
    folder.mkdir(parents=True, exist_ok=True)
    opts = dict(noplaylist=True, outtmpl=str(folder/'source.%(ext)s'),
                format='bv[height<=1080]+ba/b[height<=1080]', merge_output_format='mp4',
                socket_timeout=30, retries=2, fragment_retries=2, quiet=True,
                max_filesize=2_000_000_000)
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url,download=False)
        if info.get('is_live') or not info.get('duration') or info['duration']>3*3600:
            raise ValueError('Use a finished video shorter than three hours')
        decision=policy.screen(dict(title=info.get('title',''),creator=info.get('uploader',''),
                                    description=info.get('description',''),audio_language=info.get('language',''),
                                    categoryId='10' if 'Music' in (info.get('categories') or []) else ''))
        if not decision['eligible']: raise ValueError(decision['reason'])
        info = ydl.extract_info(url, download=True)
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


def prepare(source, source_url, count=3, model='base', captions=False, editor='basic', editor_model='qwen2.5:7b'):
    if captions: p.require_captions()
    source=Path(source).resolve()
    receipt=source.parent/'source.json'
    if receipt.exists():
        decision=policy.screen(p.read(receipt))
        if not decision['eligible']: raise ValueError(decision['reason'])
    key=p.digest(source)[:16]
    transcript=p.DATA/'transcripts'/(key+'.json')
    if not transcript.exists():
        from faster_whisper import WhisperModel
        segments,language_info=WhisperModel(model,device='cpu',compute_type='int8').transcribe(str(source),vad_filter=True)
        p.write(transcript,[dict(start=s.start,end=s.end,text=s.text.strip()) for s in segments])
        p.write(transcript.with_suffix('.language.json'),dict(language=language_info.language,
                probability=language_info.language_probability))
    language_path=transcript.with_suffix('.language.json')
    if language_path.exists():
        language=p.read(language_path)
        if language.get('language')!='en' and language.get('probability',0)>=.8:
            raise ValueError('English dialogue required for automatic editing. For visual dance, choose a manual cut and review any dialogue.')
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
    if not candidates:
        raise ValueError('Not enough continuous speech for suggestions. Use the manual clip form for silent/action videos.')
    jobs=[]
    for item in candidates:
        ident=('story-en60-v2-' if editor=='semantic' else 'draft-en60-')+key+'-'+str(round(item['start']*1000))
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
        if editor=='semantic':
            job['editorial']={k:v for k,v in item.items() if k not in ('start','end','text','title')}
        if captions: job['transcript']=str(transcript)
        p.validate(job)
        p.write(dest,job)
        p.render(job)
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
