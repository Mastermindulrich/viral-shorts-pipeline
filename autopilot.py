"""Unattended daily posting: find, cut and publish clips on a schedule with no clicks.

Owner request (2026-11-22): post at least three clips every day without intervening.
launchd starts `app_runtime.py autopilot-tick` every hour. Each tick publishes the clips
that are due by now (default slots 11:00, 16:00 and 20:00 local time), prepares more
clips when the ready queue is short, and retries anything that failed on the next tick.

Everything else stays enforced: 15–180 s coherent English cuts chosen by the local
editor (with its score thresholds), source screening, music exclusions, the channel
guard, the daily upload cap and the cross-job duplicate guard. Autopilot only ever
publishes clips it prepared itself; drafts already waiting in Review are left alone.
"""
import datetime as dt
import subprocess
import sys
import time
import traceback
from pathlib import Path
import pipeline as p
import content_policy as policy

SETTINGS=p.DATA/'autopilot-settings.json'
STATE=p.DATA/'autopilot.json'
QUEUE=p.DATA/'autopilot-queue.json'
LABEL='com.viralmomentclips.autopilot'
# daily_target is a minimum (owner 2026-11-22: "post as many as you have"). Extra ready clips go out
# one per hourly tick between extra_start and extra_end local time, so they are spread over the day.
DEFAULTS=dict(enabled=True,daily_target=3,slots=[11,16,20],max_rounds=3,focus_only=False,
              post_extra=True,extra_start=9,extra_end=23)
AUTH_HINTS=('authorization expired','run auth','invalid_grant','reauthorize','token has been expired','refresh_token')
YTDLP_HINTS=('unable to extract','nsig','signature','http error 403','sign in to confirm','failed to extract','player response')


def settings():
    path=SETTINGS
    result=dict(DEFAULTS,**(p.read(path) if path.exists() else {}))
    result['daily_target']=max(1,min(20,int(result['daily_target'])))
    result['slots']=sorted({int(h) for h in result['slots'] if 0<=int(h)<=23}) or list(DEFAULTS['slots'])
    result['max_rounds']=max(1,min(6,int(result['max_rounds'])))
    return result


def save_settings(values):
    result=dict(settings(),**values)
    p.write(SETTINGS,result)
    return settings()


def local_now(now=None):
    import studio
    from zoneinfo import ZoneInfo
    tz=ZoneInfo(studio.preferences()['timezone'])
    return (now or dt.datetime.now(dt.timezone.utc)).astimezone(tz)


def due_by(local, cfg):
    """How many posts should exist by this local time. After the last slot the full target is due."""
    passed=sum(1 for h in cfg['slots'] if h<=local.hour)
    if passed>=len(cfg['slots']): return cfg['daily_target']
    return min(cfg['daily_target'],passed)


def published_on(day, timezone):
    import studio
    count=0
    for path in (p.DATA/'exports').glob('*/upload.json'):
        try: record=p.read(path)
        except (OSError,ValueError): continue
        if record.get('state')!='uploaded': continue
        if studio.publication_time(record,timezone)[0]==day: count+=1
    return count


def queue():
    return p.read(QUEUE) if QUEUE.exists() else dict(ready=[],skipped={})


def save_queue(value):
    p.write(QUEUE,value)


def ready():
    """Autopilot-prepared clips that are rendered and not yet attempted, oldest first."""
    q=queue(); keep=[]
    for ident in q['ready']:
        dest=p.DATA/'exports'/ident
        if ident in q['skipped'] or (dest/'upload.json').exists(): continue
        if (dest/'job.json').exists() and (dest/'clip.mp4').exists(): keep.append(ident)
    if keep!=q['ready']: q['ready']=keep; save_queue(q)
    return keep


def enqueue(jobs):
    q=queue()
    for job in jobs:
        ident=job['id']; dest=p.DATA/'exports'/ident
        if ident in q['ready'] or ident in q['skipped'] or (dest/'upload.json').exists(): continue
        q['ready'].append(ident)
    save_queue(q)


def skip(ident, reason):
    q=queue(); q['skipped'][ident]=str(reason)[:300]
    q['ready']=[x for x in q['ready'] if x!=ident]; save_queue(q)


def credit(job):
    """Credit the original creator and link the source (upload() appends the link)."""
    record={}
    source=Path(job['input']).parent/'source.json'
    if source.exists():
        try: record=p.read(source)
        except (OSError,ValueError): record={}
    creator=(record.get('creator') or '').strip()
    gta=policy.is_focus(dict(title=record.get('title','')+' '+job['title'],description=record.get('description','')))
    lines=[]
    if creator: lines.append(f'Original video by {creator}. All credit to the creator; full video linked below.')
    lines.append('#GTA6 #GTAVI #Shorts' if gta else '#Shorts')
    return '\n'.join(lines), gta


def publish(ident):
    dest=p.DATA/'exports'/ident
    job=p.read(dest/'job.json')
    description,gta=credit(job)
    job.update(description=description,privacy='public',needs_editorial_review=False,made_for_kids=False,autopilot=True)
    if gta: job['category_id']='20'
    job.pop('publish_at',None)
    p.write(dest/'job.json',job); p.write(p.DATA/'jobs'/(ident+'.json'),job)
    p.approve(job)
    p.upload(job)
    return p.read(dest/'upload.json').get('video_id')


def ensure_editor(model, sleep=time.sleep):
    """Start Ollama if it is not running, so a closed app never stops the day's posts."""
    import editorial
    try: return editorial.require_model(model)
    except Exception as first:
        if 'is not installed' in str(first):
            # Model missing: download it once (stays local).
            subprocess.run(['ollama','pull',model],capture_output=True,timeout=3600)
        else:
            for command in (['open','-a','Ollama'],['ollama','serve']):
                try:
                    if command[0]=='open': subprocess.run(command,capture_output=True,timeout=30)
                    else: subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
                except (OSError,subprocess.SubprocessError): continue
                for _ in range(20):
                    sleep(3)
                    try: return editorial.require_model(model)
                    except Exception: pass
    return editorial.require_model(model)


def upgrade_downloader():
    """yt-dlp breaks whenever YouTube changes; refresh it at most once a day."""
    marker=p.DATA/'autopilot-ytdlp-upgrade.txt'
    today=dt.date.today().isoformat()
    if marker.exists() and marker.read_text().strip()==today: return False
    marker.parent.mkdir(parents=True,exist_ok=True); marker.write_text(today)
    result=subprocess.run([sys.executable,'-m','pip','install','-q','-U','yt-dlp'],capture_output=True,text=True,timeout=600)
    print('yt-dlp upgrade: '+('ok' if result.returncode==0 else (result.stderr or '')[-300:]),flush=True)
    return result.returncode==0


def candidates(cfg, stage):
    import app_runtime as rt
    import scouting
    used=rt.used_sources()
    choices=rt.fresh_choices(scouting,used)
    if not choices:
        stage('Autopilot: searching for fresh GTA 6 gameplay and other topics')
        result=rt.retry(scouting.discover_broad,'Search')
        for warning in result.get('warnings',[]): print('Discovery warning: '+warning,flush=True)
        ranked=rt.retry(scouting.refresh,'Ranking')
        choices=[x for x in scouting.shortlist(scouting.visible_ranked(ranked)) if x['url'] not in used]
    if cfg['focus_only']: choices=[x for x in choices if x.get('focus')]
    # Focus videos first, then the rest by score; visible_ranked already sorts by display score.
    return sorted(choices,key=lambda x:not x.get('focus'))


def prepare_round(cfg, stage):
    """Turn the best unused video into ready clips. Tries up to three videos; returns the jobs made."""
    import app_runtime as rt
    import scouting
    import studio
    import preparation as prep
    defaults=studio.preferences()
    ensure_editor(defaults['editor_model'])
    errors=[]
    for number,item in enumerate(candidates(cfg,stage)[:3],1):
        try:
            stage(f'Autopilot: cutting clips from “{item["title"][:70]}”',20)
            source=rt.import_source(item['url'],defaults.get('clearance',''),item.get('title',''))
            jobs=rt.retry(lambda:prep.prepare(source['input'],source['source_url'],defaults['count'],defaults['transcription_model'],
                                              defaults['captions'],'semantic',defaults['editor_model'],
                                              progress=lambda n,m: stage('Autopilot: '+m,n)),'Scene selection')
            fresh=[j for j in jobs if not (p.DATA/'exports'/j['id']/'upload.json').exists()]
            if fresh:
                enqueue(fresh); return fresh,errors
            errors.append(f'{item["title"][:50]}: no new clips')
        except Exception as exc:
            traceback.print_exc(); errors.append(f'{item["title"][:50]}: {exc}')
        try: scouting.hide_video(item)
        except Exception: pass
    return [],errors


def notify(message):
    """A macOS notification; never required for the run to succeed."""
    if sys.platform!='darwin': return
    text=message.replace('\\','').replace('"','\'')[:220]
    try: subprocess.run(['osascript','-e',f'display notification "{text}" with title "Viral Moment Clips autopilot"'],capture_output=True,timeout=10)
    except (OSError,subprocess.SubprocessError): pass


def extra_allowed(local, cfg):
    return bool(cfg.get('post_extra')) and int(cfg.get('extra_start',9))<=local.hour<=int(cfg.get('extra_end',23))


def publish_due(cfg, today, timezone, local, stage, errors, published, extra=0):
    """Publish what is due by now, plus `extra` more ready clips beyond the schedule."""
    import app_runtime as rt
    done=published_on(today,timezone)
    due=due_by(local,cfg)
    limit=max(due,done+extra)
    for ident in ready():
        if done>=limit: break
        stage(f'Autopilot: publishing clip {done+1} for today (minimum {cfg["daily_target"]})',90)
        try:
            video=publish(ident); done+=1
            published.append(dict(id=ident,video_id=video))
            print(f'Autopilot published {ident}: https://youtu.be/{video}',flush=True)
        except Exception as exc:
            traceback.print_exc()
            text=str(exc)
            if any(h in text.lower() for h in AUTH_HINTS): raise
            if 'daily upload cap' in text.lower():
                errors.append(text); break
            if rt.transient(exc) and not (p.DATA/'exports'/ident/'upload.json').exists():
                errors.append(f'{ident}: {text} (will retry next hour)'); break
            skip(ident,text); errors.append(f'{ident}: {text}')
    return done,due


def run(stage=print, now=None):
    cfg=settings()
    if not cfg['enabled']: return dict(status='off')
    import studio
    timezone=studio.preferences()['timezone']
    local=local_now(now); today=local.date()
    errors=[]; published=[]
    try: p.reconcile_receipts()
    except Exception as exc: print(f'Receipt check skipped: {exc}',flush=True)
    try:
        done,due=publish_due(cfg,today,timezone,local,stage,errors,published)
        rounds=0
        while rounds<cfg['max_rounds'] and len(ready())<max(1,cfg['daily_target']-done):
            rounds+=1
            jobs,problems=prepare_round(cfg,stage)
            errors.extend(problems)
            if not jobs:
                if any(h in ' '.join(problems).lower() for h in YTDLP_HINTS) and upgrade_downloader(): continue
                break
            done,due=publish_due(cfg,today,timezone,local,stage,errors,published)
        done,due=publish_due(cfg,today,timezone,local,stage,errors,published)
        if extra_allowed(local,cfg) and not errors:
            # Surplus clips: one extra post per hourly tick so the day's posts stay spread out.
            done,due=publish_due(cfg,today,timezone,local,stage,errors,published,extra=1)
    except Exception as exc:
        text=str(exc)
        record=dict(last_run=dt.datetime.now(dt.timezone.utc).isoformat(),day=today.isoformat(),
                    published_today=published_on(today,timezone),target=cfg['daily_target'],
                    ready=len(ready()),published=published,errors=(errors+[text])[-10:],blocked=True)
        p.write(STATE,record)
        if any(h in text.lower() for h in AUTH_HINTS):
            notify('YouTube sign-in expired. Run: .venv/bin/python pipeline.py auth')
        raise
    record=dict(last_run=dt.datetime.now(dt.timezone.utc).isoformat(),day=today.isoformat(),
                published_today=done,due_now=due,target=cfg['daily_target'],ready=len(ready()),
                published=published,errors=errors[-10:],blocked=False)
    p.write(STATE,record)
    if done<due:
        message=f'Behind schedule: {done} of {due} clips due by now are posted. Retrying automatically next hour.'
        if local.hour>=max(cfg['slots'])+2: notify(message)
        raise RuntimeError(message+(' Last problems: '+' | '.join(errors[-3:]) if errors else ''))
    return record


def status():
    return p.read(STATE) if STATE.exists() else {}


def plist(root=None, python=None):
    """launchd job: every hour at :07, kept awake while it runs."""
    root=Path(root or p.ROOT)
    python=str(python or root/'.venv'/'bin'/'python')
    log=str(root/'data'/'logs'/'autopilot.log')
    return dict(Label=LABEL,
                ProgramArguments=['/usr/bin/caffeinate','-i',python,str(root/'app_runtime.py'),'autopilot-tick'],
                WorkingDirectory=str(root),StartCalendarInterval=[dict(Minute=7)],RunAtLoad=True,
                AbandonProcessGroup=True,StandardOutPath=log,StandardErrorPath=log,
                EnvironmentVariables={'PATH':'/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'})


def install():
    import os
    import plistlib
    if sys.platform!='darwin': raise RuntimeError('Autopilot scheduling must be installed on your Mac.')
    folder=Path.home()/'Library'/'LaunchAgents'; folder.mkdir(parents=True,exist_ok=True)
    (p.DATA/'logs').mkdir(parents=True,exist_ok=True)
    path=folder/(LABEL+'.plist')
    path.write_bytes(plistlib.dumps(plist()))
    target=f'gui/{os.getuid()}'
    subprocess.run(['launchctl','bootout',target,str(path)],capture_output=True)
    subprocess.run(['launchctl','bootstrap',target,str(path)],check=True)
    save_settings(dict(enabled=True))
    print('Autopilot installed: runs every hour at :07 and posts '+str(settings()['daily_target'])+' clips a day.')


def uninstall():
    import os
    path=Path.home()/'Library'/'LaunchAgents'/(LABEL+'.plist')
    subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}',str(path)],capture_output=True)
    path.unlink(missing_ok=True)
    save_settings(dict(enabled=False))
    print('Autopilot removed.')
