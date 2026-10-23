"""Local, original-audio Shorts production. Python 3.11+, FFmpeg required."""
import argparse
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
import urllib.parse
import urllib.request
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
    return subprocess.run(args, check=True, **kwargs)

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def probe(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)]))

def validate(job):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', job['id']):
        raise ValueError('id must contain only letters, digits, underscores and hyphens')
    a, b = float(job['start']), float(job['end'])
    if not all(map(math.isfinite, [a, b])) or a < 0 or not 1 <= b - a <= 180:
        raise ValueError('Clip must last 1–180 seconds; start must be nonnegative')
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
        a, b = max(start, float(s['start'])), min(end, float(s['end']))
        if b > a and s['text'].strip():
            # Strip markup/control characters from model or supplied transcript.
            text = re.sub(r'<[^>]*>|\{[^}]*\}', '', s['text']).replace('\r', ' ').replace('\n', ' ')
            lines.append(f'{len(lines)+1}\n{stamp(a-start)} --> {stamp(b-start)}\n{text.strip()}\n')
    return '\n'.join(lines)

def render(job):
    validate(job)
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
    if job.get('transcript'):
        srt = subtitles(read(job['transcript']), job['start'], job['end'])
        if not srt:
            raise ValueError('No transcript text overlaps this clip')
        (dest / 'captions.srt').write_text(srt)
        vf += ",subtitles=captions.srt:force_style='FontSize=18,Outline=2,MarginV=100'"
    tmp = dest / 'clip.partial.mp4'
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(job['start']), '-i', str(src),
         '-t', str(job['end']-job['start']), '-map', '0:v:0', '-map', '0:a:0', '-vf', vf,
         '-r', '30', '-c:v', 'libx264', '-preset', 'fast', '-crf', '21', '-pix_fmt', 'yuv420p',
         '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(tmp.resolve())], cwd=dest)
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

def approve(job, reference):
    validate(job)
    if job.get('needs_editorial_review'):
        raise ValueError('Review draft title and audience settings before approval')
    dest = output(job)
    if read(dest/'job.json') != job:
        raise ValueError('Job changed since rendering; render again')
    if not reference.strip():
        raise ValueError('Provide your external clearance reference')
    write(dest/'approval.json', {'job_sha': fingerprint(job), 'video_sha': digest(dest/'clip.mp4'),
          'clearance_reference': reference, 'approved_at': dt.datetime.now(dt.timezone.utc).isoformat()})
    print('Approved this exact video and metadata')

def check_approval(job):
    validate(job)
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
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise RuntimeError('Worker already running, or stale data/worker.lock; inspect before removing')
    try:
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)

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


def upload(job):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    check_approval(job)
    dest = output(job)
    # Durable reservation BEFORE network call: ambiguous failures must not cause duplicate uploads.
    receipt = dest/'upload.json'
    if receipt.exists():
        raise ValueError('Upload already attempted. Inspect upload.json and YouTube Studio before any retry')
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
                        'categoryId': '24'}, 'status': status}
    write(receipt, {'state': 'uploading', 'day': today, 'job_sha': fingerprint(job)})
    request = service.videos().insert(part='snippet,status', body=body,
        media_body=MediaFileUpload(str(dest/'clip.mp4'), mimetype='video/mp4', resumable=True, chunksize=8*1024*1024))
    response = None
    while response is None:
        _, response = request.next_chunk()
    write(receipt, {'state': 'uploaded', 'day': today, 'video_id': response['id'], 'job_sha': fingerprint(job)})
    print('https://www.youtube.com/watch?v=' + response['id'])

def discover():
    settings = read(ROOT/'config'/'sources.json')
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA/'discovery.sqlite3')
    db.execute('CREATE TABLE IF NOT EXISTS candidates (id TEXT PRIMARY KEY, title TEXT, url TEXT, published TEXT, source TEXT)')
    errors = []
    for source in settings:
        try:
            channel = source['channel_id']
            if not re.fullmatch(r'UC[\w-]{22}', channel):
                raise ValueError('Invalid YouTube channel ID')
            url = 'https://www.youtube.com/feeds/videos.xml?channel_id=' + channel
            req = urllib.request.Request(url, headers={'User-Agent':'ShortsPipeline/0.1'})
            with urllib.request.urlopen(req, timeout=30) as f:
                root = ET.fromstring(f.read(2_000_000))
            ns = {'a':'http://www.w3.org/2005/Atom','yt':'http://www.youtube.com/xml/schemas/2015'}
            for e in root.findall('a:entry', ns):
                vid = e.findtext('yt:videoId', namespaces=ns)
                db.execute('INSERT OR IGNORE INTO candidates VALUES (?,?,?,?,?)',
                    (vid, e.findtext('a:title', namespaces=ns), 'https://www.youtube.com/watch?v='+vid,
                     e.findtext('a:published', namespaces=ns), source['name']))
        except Exception as exc:
            errors.append(f"{source.get('name','source')}: {exc}")
    db.commit()
    rows = db.execute('SELECT id,title,url,published,source FROM candidates ORDER BY published DESC LIMIT 100').fetchall()
    db.close()
    write(DATA/'candidates.json', [dict(zip(['id','title','url','published','source'], r)) for r in rows])
    print(f'{len(rows)} recent candidates saved; discovery is not rights clearance or a virality forecast')
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        raise RuntimeError('Some source feeds failed; other results were saved')

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
