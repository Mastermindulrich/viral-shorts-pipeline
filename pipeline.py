"""Local, original-audio Shorts production. Python 3.11+, FFmpeg required."""
import argparse
from content_policy import MAX_CLIP_SECONDS
import contextlib
import datetime as dt
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import textwrap
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'

def read(path):
    return json.loads(Path(path).read_text())

def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False))
    temp.replace(path)

def run(args, **kwargs):
    if args[0] in ('ffmpeg','ffprobe'): args=[media_tool(args[0]),*args[1:]]
    return subprocess.run(args, check=True, **kwargs)

def media_tool(name):
    # Homebrew's caption-capable alternate build is keg-only; no global relinking needed.
    for prefix in ('/opt/homebrew/opt/ffmpeg-full/bin','/usr/local/opt/ffmpeg-full/bin'):
        path=Path(prefix)/name
        if path.is_file(): return str(path)
    return name

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def probe(path):
    return json.loads(subprocess.check_output([media_tool('ffprobe'), '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)]))

def caption_capability():
    """Inspect the installed executable; captions are an optional libass feature."""
    try:
        result=subprocess.run([media_tool('ffmpeg'),'-hide_banner','-filters'],capture_output=True,text=True,timeout=10)
    except (OSError,subprocess.TimeoutExpired):
        return {'supported':False,'reason':'Cannot inspect FFmpeg. Check the local FFmpeg installation.'}
    if result.returncode:
        return {'supported':False,'reason':'FFmpeg could not list its filters. Check the local FFmpeg installation.'}
    supported=any(len(parts:=line.split())>=3 and parts[1]=='subtitles'
                  for line in result.stdout.splitlines())
    return {'supported':supported,'reason':
            'Burned-in captions available.' if supported else
            'Burned-in captions unavailable: subtitles/libass missing. English SRT files still work. On Mac, install ffmpeg-full, then restart the app.'}


def require_captions():
    capability=caption_capability()
    if not capability['supported']:
        raise ValueError(capability['reason'])


def validate(job):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', job['id']):
        raise ValueError('id must contain only letters, digits, underscores and hyphens')
    a, b = float(job['start']), float(job['end'])
    if not all(map(math.isfinite, [a, b])) or a < 0 or not 1 <= b - a <= MAX_CLIP_SECONDS:
        raise ValueError(f'Clip must last 1–{MAX_CLIP_SECONDS} seconds; start must be nonnegative')
    if not 1 <= len(job['title'].strip()) <= 100:
        raise ValueError('Title must contain 1–100 characters')
    if len(job.get('description', '')) > 4500:
        raise ValueError('Description is too long')
    if job.get('layout', 'fit') not in ('fit', 'crop'):
        raise ValueError('layout must be fit or crop')
    if not job.get('source_url'):
        raise ValueError('Record a source_url or provenance reference')
    if not isinstance(job.get('made_for_kids'), bool):
        raise ValueError('Set made_for_kids explicitly to true or false')
    if job.get('privacy', 'private') not in ('private', 'unlisted', 'public'):
        raise ValueError('Unsupported privacy')

def output(job):
    return DATA / 'exports' / job['id']

def material(job):
    path = Path(job['input']).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f'Missing local input: {path}')
    return path

def stamp(seconds):
    ms = max(0, round(seconds * 1000))
    return f'{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}'

def subtitles(segments, start, end):
    lines = []
    for s in segments:
        words=s.get('words') or []
        cues=[]
        if words:
            group=[]
            for word in words:
                if group and (len(group)>=7 or float(word['end'])-float(group[0]['start'])>3.5):
                    cues.append(dict(start=group[0]['start'],end=group[-1]['end'],text=''.join(x['word'] for x in group)))
                    group=[]
                group.append(word)
            if group: cues.append(dict(start=group[0]['start'],end=group[-1]['end'],text=''.join(x['word'] for x in group)))
        else:
            # Legacy transcripts have segment timing only; label that limitation in the UI.
            cues=[s]
        for cue in cues:
            a, b = max(start, float(cue['start'])), min(end, float(cue['end']))
            if b<=a or not cue['text'].strip(): continue
            # Strip markup/control characters from model or supplied transcript.
            text = re.sub(r'<[^>]*>|\{[^}]*\}', '', cue['text'])
            text=' '.join(''.join(c if c.isprintable() else ' ' for c in text).split())
            text='\n'.join(textwrap.wrap(text,width=34,break_long_words=False))
            lines.append(f'{len(lines)+1}\n{stamp(a-start)} --> {stamp(b-start)}\n{text}\n')
    return '\n'.join(lines)

def render(job):
    validate(job)
    if job.get('transcript'): require_captions()
    src = material(job)
    meta = probe(src)
    duration = float(meta['format']['duration'])
    if job['end'] > duration + .05:
        raise ValueError('Clip ends after source video')
    if not any(s['codec_type'] == 'audio' for s in meta['streams']):
        raise ValueError('Source has no audio; original sound is required')
    dest = output(job)
    dest.mkdir(parents=True, exist_ok=True)
    # Remove old approval before changing any export. Re-render requires reapproval.
    (dest / 'approval.json').unlink(missing_ok=True)
    if job.get('layout', 'fit') == 'crop':
        vf = 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1'
    else:
        vf = 'scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1'
    caption_source=job.get('transcript') or job.get('caption_source')
    if caption_source:
        srt = subtitles(read(caption_source), job['start'], job['end'])
        if not srt:
            raise ValueError('No transcript text overlaps this clip')
        (dest / 'captions.srt').write_text(srt)
        if job.get('transcript'):
            vf += ",subtitles=filename=captions.srt:force_style='FontName=Arial,FontSize=18,Bold=1,Outline=2,MarginV=55'"
    tmp = dest / 'clip.partial.mp4'
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(job['start']), '-i', str(src),
         '-t', str(job['end']-job['start']), '-map', '0:v:0', '-map', '0:a:0', '-vf', vf,
         '-r', '30', '-c:v', 'libx264', '-preset', 'fast', '-crf', '21', '-pix_fmt', 'yuv420p',
         '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(tmp.resolve())], cwd=dest)
    validate_export_duration(tmp)
    tmp.replace(dest / 'clip.mp4')
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str((dest/'clip.mp4').resolve()),
         '-frames:v', '1', str((dest/'cover.jpg').resolve())])
    write(dest / 'job.json', job)
    (dest / 'review.html').write_text(f'''<!doctype html><meta charset="utf-8"><title>Clip review</title>
<style>body{{background:#10121b;color:white;font:18px system-ui;max-width:850px;margin:40px auto}}video{{max-height:70vh;max-width:100%}}pre{{white-space:pre-wrap}}</style>
<h1>{html.escape(job['title'])}</h1><video controls src="clip.mp4"></video>
<pre>{html.escape(job.get('description',''))}</pre><p>Source: {html.escape(job['source_url'])}</p>
<p>Review the full clip, framing, captions and context before approving.</p>''')
    print(dest / 'review.html')

def fingerprint(job):
    return hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()

def validate_export_duration(path):
    duration=float(probe(path)['format']['duration'])
    if not math.isfinite(duration) or duration<=0 or duration>MAX_CLIP_SECONDS:
        raise ValueError(f'Rendered clip exceeds the {MAX_CLIP_SECONDS}-second limit or has an invalid duration. Re-cut it before publishing.')


def approve(job, reference):
    validate(job)
    if job.get('needs_editorial_review'):
        raise ValueError('Review draft title and audience settings before approval')
    dest = output(job)
    if read(dest/'job.json') != job:
        raise ValueError('Job changed since rendering; render again')
    if not reference.strip():
        raise ValueError('Provide your external clearance reference')
    validate_export_duration(dest/'clip.mp4')
    write(dest/'approval.json', {'job_sha': fingerprint(job), 'video_sha': digest(dest/'clip.mp4'),
          'clearance_reference': reference, 'approved_at': dt.datetime.now(dt.timezone.utc).isoformat()})
    print('Approved this exact video and metadata')

def check_approval(job):
    validate(job)
    validate_export_duration(output(job)/'clip.mp4')
    approval = read(output(job)/'approval.json')
    if approval['job_sha'] != fingerprint(job) or approval['video_sha'] != digest(output(job)/'clip.mp4'):
        raise ValueError('Video or metadata changed after approval')
    if not approval.get('clearance_reference', '').strip():
        raise ValueError('Missing external clearance reference')

SCOPES = ['https://www.googleapis.com/auth/youtube.upload',
          'https://www.googleapis.com/auth/youtube.readonly']

def credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    path = DATA/'secrets'/'token.json'
    saved = read(path)
    if not set(SCOPES).issubset(set(saved.get('scopes', []))):
        raise ValueError('Channel verification needs read-only permission. Run: python pipeline.py auth')
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        write(path, json.loads(creds.to_json()))
        path.chmod(0o600)
    if not creds.valid:
        raise ValueError('Authorization expired; run auth again')
    return creds

def auth():
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(str(DATA/'secrets'/'client_secret.json'), SCOPES)
    creds = flow.run_local_server(port=0, prompt='consent select_account')
    path = DATA/'secrets'/'token.json'
    write(path, json.loads(creds.to_json()))
    path.chmod(0o600)
    print('YouTube authorization saved locally')

@contextlib.contextmanager
def lock():
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA/'worker.lock'
    import fcntl
    with path.open('a+') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another task is running. Check Activity.')
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def verify_channel(service, expected):
    if not expected:
        raise ValueError('Set expected_channel_id before uploading')
    items = service.channels().list(part='snippet', mine=True).execute().get('items', [])
    if len(items) != 1 or items[0]['id'] != expected:
        names = ', '.join(x.get('snippet', {}).get('title', x['id']) for x in items)
        raise ValueError(f'Upload blocked: connected to {names or "no channel"}. Reauthorize the intended channel.')
    return {'id': items[0]['id'], 'name': items[0]['snippet']['title']}


def channel():
    from googleapiclient.discovery import build
    service = build('youtube', 'v3', credentials=credentials(), cache_discovery=False)
    result = verify_channel(service, read(ROOT/'config'/'settings.json').get('expected_channel_id'))
    print(json.dumps(result))
    return result


def overlap_ratio(a, b):
    """Shared seconds as a fraction of the shorter clip."""
    shared = min(float(a['end']), float(b['end'])) - max(float(a['start']), float(b['start']))
    shortest = min(float(a['end']) - float(a['start']), float(b['end']) - float(b['start']))
    return max(0., shared) / shortest if shortest > 0 else 0.


def upload_conflicts(job, check_video=True):
    """Earlier upload attempts of the same moment under another job ID.

    Regenerated batches use new IDs, so the per-job receipt alone cannot stop a
    repeat of an already published moment. Uncertain attempts count too."""
    dest = output(job)
    video_sha = None
    conflicts = []
    for receipt in sorted((DATA/'exports').glob('*/upload.json')):
        if receipt.parent == dest: continue
        try:
            record = read(receipt)
        except (OSError, ValueError):
            continue
        try:
            other = read(receipt.parent/'job.json')
        except (OSError, ValueError):
            # New receipts also carry the uploaded moment.
            other = record
        reason = None
        try:
            if other.get('source_url') == job['source_url'] and overlap_ratio(job, other) >= .5:
                reason = 'same source moment'
        except (KeyError, TypeError, ValueError):
            pass
        approval = receipt.parent/'approval.json'
        if not reason and check_video and approval.exists() and (dest/'clip.mp4').exists():
            video_sha = video_sha or digest(dest/'clip.mp4')
            try:
                if read(approval).get('video_sha') == video_sha: reason = 'identical video'
            except (OSError, ValueError):
                pass
        if reason:
            conflicts.append(dict(id=receipt.parent.name, title=other.get('title', receipt.parent.name),
                                  video_id=record.get('video_id'), reason=reason))
    return conflicts


def describe_conflicts(conflicts):
    return '; '.join(f'"{x["title"]}" ' + (f'(youtu.be/{x["video_id"]})' if x['video_id'] else '(uncertain upload attempt)')
                     for x in conflicts)


def upload(job):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    check_approval(job)
    dest = output(job)
    # Durable reservation BEFORE network call: ambiguous failures must not cause duplicate uploads.
    receipt = dest/'upload.json'
    if receipt.exists():
        raise ValueError('Upload already attempted. Inspect upload.json and YouTube Studio before any retry')
    conflicts = upload_conflicts(job)
    if conflicts:
        raise ValueError('Duplicate upload blocked: this clip repeats ' + describe_conflicts(conflicts) +
                         '. Choose a different moment.')
    settings = read(ROOT/'config'/'settings.json')
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    attempts = [read(p) for p in (DATA/'exports').glob('*/upload.json')]
    if sum(x.get('day') == today for x in attempts) >= settings['max_uploads_per_day']:
        raise ValueError('Daily upload cap reached (UTC)')
    service = build('youtube', 'v3', credentials=credentials(), cache_discovery=False)
    verify_channel(service, settings.get('expected_channel_id'))
    status = {'privacyStatus': job.get('privacy', 'private'), 'selfDeclaredMadeForKids': job['made_for_kids']}
    if job.get('publish_at'):
        when = dt.datetime.fromisoformat(job['publish_at'].replace('Z', '+00:00'))
        if when.tzinfo is None or when <= dt.datetime.now(dt.timezone.utc):
            raise ValueError('publish_at must be a future ISO time with timezone')
        if status['privacyStatus'] != 'private':
            raise ValueError('Scheduled videos must use private privacy')
        status['publishAt'] = job['publish_at']
    body = {'snippet': {'title': job['title'], 'description': job.get('description','') + '\n\nSource: ' + job['source_url'],
                        'categoryId': '24', 'defaultLanguage': 'en'}, 'status': status}
    write(receipt, {'state': 'uploading', 'day': today, 'attempted_at':dt.datetime.now(dt.timezone.utc).isoformat(), 'job_sha': fingerprint(job),
                    'source_url': job['source_url'], 'start': job['start'], 'end': job['end']})
    request = service.videos().insert(part='snippet,status', body=body,
        media_body=MediaFileUpload(str(dest/'clip.mp4'), mimetype='video/mp4', resumable=True, chunksize=8*1024*1024))
    response = None
    while response is None:
        _, response = request.next_chunk()
    write(receipt, {'state': 'uploaded', 'day': today, 'uploaded_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                    'published_at':response.get('snippet',{}).get('publishedAt'),
                    'video_id': response['id'], 'privacy':status['privacyStatus'], 'job_sha': fingerprint(job),
                    'source_url': job['source_url'], 'start': job['start'], 'end': job['end']})
    print('https://www.youtube.com/watch?v=' + response['id'])

def api_recent_uploads(channel_id, service=None):
    if service is None:
        from googleapiclient.discovery import build
        service = build('youtube', 'v3', credentials=credentials(), cache_discovery=False)
    channels = service.channels().list(part='contentDetails', id=channel_id).execute().get('items', [])
    if not channels:
        raise ValueError('YouTube API did not find this channel')
    uploads = channels[0]['contentDetails']['relatedPlaylists']['uploads']
    items = service.playlistItems().list(part='snippet,contentDetails', playlistId=uploads, maxResults=15).execute().get('items', [])
    return [dict(id=x['contentDetails']['videoId'], title=x['snippet']['title'],
                 published=x['contentDetails'].get('videoPublishedAt', x['snippet'].get('publishedAt','')))
            for x in items if x.get('contentDetails', {}).get('videoId')]


def recent_uploads(channel_id):
    url = 'https://www.youtube.com/feeds/videos.xml?channel_id=' + channel_id
    req = urllib.request.Request(url, headers={'User-Agent':'ShortsPipeline/0.2'})
    try:
        with urllib.request.urlopen(req, timeout=30) as f:
            root = ET.fromstring(f.read(2_000_000))
        ns = {'a':'http://www.w3.org/2005/Atom','yt':'http://www.youtube.com/xml/schemas/2015'}
        entries = [dict(id=e.findtext('yt:videoId', namespaces=ns), title=e.findtext('a:title', namespaces=ns),
                        published=e.findtext('a:published', namespaces=ns)) for e in root.findall('a:entry', ns)]
        if not entries:
            return api_recent_uploads(channel_id)
        return entries
    except (urllib.error.URLError, TimeoutError, ET.ParseError) as exc:
        print(f'RSS unavailable for {channel_id}: {exc}. Trying YouTube API.')
        try:
            return api_recent_uploads(channel_id)
        except Exception as api_error:
            raise RuntimeError(f'RSS: {exc}; API fallback: {api_error}') from api_error


def discover():
    settings = read(ROOT/'config'/'sources.json')
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA/'discovery.sqlite3')
    db.execute('CREATE TABLE IF NOT EXISTS candidates (id TEXT PRIMARY KEY, title TEXT, url TEXT, published TEXT, source TEXT)')
    errors = []
    try:
        for source in settings:
            try:
                channel_id = source['channel_id']
                if not re.fullmatch(r'UC[\w-]{22}', channel_id):
                    raise ValueError('Invalid YouTube channel ID')
                for item in recent_uploads(channel_id):
                    if not item.get('id'):
                        continue
                    db.execute('INSERT OR IGNORE INTO candidates VALUES (?,?,?,?,?)',
                               (item['id'], item['title'], 'https://www.youtube.com/watch?v='+item['id'],
                                item['published'], source['name']))
            except Exception as exc:
                errors.append(f"{source.get('name','source')}: {exc}")
        db.commit()
        rows = db.execute('SELECT id,title,url,published,source FROM candidates ORDER BY published DESC LIMIT 100').fetchall()
    finally:
        db.close()
    write(DATA/'candidates.json', [dict(zip(['id','title','url','published','source'], r)) for r in rows])
    print(f'{len(rows)} recent candidates saved; discovery is not rights clearance or a virality forecast')
    if errors:
        raise RuntimeError('Some sources failed; other results were saved. ' + ' | '.join(errors))


def transcribe(path, model):
    from faster_whisper import WhisperModel
    segments, _ = WhisperModel(model, device='cpu', compute_type='int8').transcribe(str(path), vad_filter=True)
    out = DATA/'transcripts'/(Path(path).stem+'.json')
    write(out, [{'start':s.start, 'end':s.end, 'text':s.text.strip()} for s in segments])
    print(out)

def suggest(path):
    # Cheap heuristic only: sentence-aligned speech windows, never advertised as AI virality scoring.
    segments = read(path)
    candidates = []
    previous_end = -1
    for i, first in enumerate(segments):
        if first['start'] < previous_end:
            continue
        chosen = []
        for s in segments[i:]:
            if s['end'] - first['start'] > 50:
                break
            chosen.append(s)
        if chosen and chosen[-1]['end'] - first['start'] >= 20:
            text = ' '.join(s['text'] for s in chosen)
            candidates.append({'start':first['start'], 'end':chosen[-1]['end'], 'transcript':text,
                               'suggested_title':text.split('.')[0][:95], 'requires_editorial_review':True})
            previous_end = chosen[-1]['end']
    out = DATA/'suggestions.json'
    write(out, candidates)
    print(out)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for name in ['render', 'approve', 'upload']:
        sp = sub.add_parser(name)
        sp.add_argument('job')
        if name == 'approve':
            sp.add_argument('--clearance-ref', required=True)
    sub.add_parser('discover')
    sub.add_parser('auth')
    sub.add_parser('channel')
    sp = sub.add_parser('transcribe')
    sp.add_argument('input'); sp.add_argument('--model', default='base')
    sp = sub.add_parser('suggest'); sp.add_argument('transcript')
    sp = sub.add_parser('batch'); sp.add_argument('folder')
    args = p.parse_args()
    with lock():
        if args.command in ('render','approve','upload'):
            job = read(args.job)
            if args.command == 'approve': approve(job, args.clearance_ref)
            elif args.command == 'render': render(job)
            else: upload(job)
        elif args.command == 'batch':
            for path in sorted(Path(args.folder).glob('*.json')):
                render(read(path))
        elif args.command == 'discover': discover()
        elif args.command == 'auth': auth()
        elif args.command == 'channel': channel()
        elif args.command == 'transcribe': transcribe(args.input, args.model)
        elif args.command == 'suggest': suggest(args.transcript)

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(1)
