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
import health
import learning

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


def source_risk(ident):
    """Copyright reason to hold back a queued clip, checked again just before posting."""
    try:
        job=p.read(p.DATA/'exports'/ident/'job.json')
        source=Path(job['input']).parent/'source.json'
        record=p.read(source) if source.exists() else {}
    except (OSError,ValueError,KeyError): return ''
    return policy.copyright_risk(dict(record,title=record.get('title',''),source=record.get('creator','')))


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
    """yt-dlp breaks whenever YouTube changes; refresh it at most once a day (see health.upgrade_downloader)."""
    return health.upgrade_downloader()


def vary_niches(items, recent=()):
    """Reorder so consecutive picks come from different niches, starting away from what was just posted.
    Scores still decide the order inside each niche (owner 2026-11-24: shorts in many niches)."""
    queues={}
    for item in items: queues.setdefault(item.get('niche') or policy.niche(item),[]).append(item)
    order=[]; last=list(recent)[-1:] 
    while any(queues.values()):
        names=[n for n,q in queues.items() if q]
        # Best remaining item whose niche differs from the previous pick (if any differ).
        fresh=[n for n in names if n not in last] or names
        best=max(fresh,key=lambda n:(queues[n][0].get('display_score',0)))
        order.append(queues[best].pop(0)); last=[best]
    return order


def recent_niches(limit=3):
    rows=[]
    for path in (p.DATA/'exports').glob('*/upload.json'):
        try:
            receipt=p.read(path)
            if receipt.get('state')=='uploaded': rows.append((receipt.get('uploaded_at') or '',p.read(path.parent/'job.json').get('title','')))
        except (OSError,ValueError): continue
    return [policy.niche(dict(title=t)) for _,t in sorted(rows)[-limit:]]


def candidates(cfg, stage):
    import app_runtime as rt
    import scouting
    used=rt.used_sources()
    choices=rt.fresh_choices(scouting,used)
    if not choices:
        stage('Autopilot: searching for today\'s viral moments')
        result=rt.retry(scouting.discover_broad,'Search')
        for warning in result.get('warnings',[]): print('Discovery warning: '+warning,flush=True)
        ranked=rt.retry(scouting.refresh,'Ranking')
        choices=[x for x in scouting.shortlist(scouting.visible_ranked(ranked)) if x['url'] not in used]
    if cfg['focus_only']: choices=[x for x in choices if x.get('focus')]
    # visible_ranked already sorts by display score (trending and GTA get a boost).
    if cfg['focus_only']: return choices
    # Footage of today's biggest news stories (newsdesk) alternates with the usual picks.
    news=news_footage(stage,used)
    picked=[x for x in choices if x['url'] not in {n['url'] for n in news}]
    mixed=[]
    for index in range(max(len(news),len(picked))):
        mixed.extend(x for x in (news[index:index+1]+picked[index:index+1]))
    return mixed


def news_footage(stage, used):
    """Screened videos of the stories making the buzz right now. Never stops a round when it fails."""
    try:
        import newsdesk
        import scouting
        if not newsdesk.settings()['enabled']: return []
        stage('Autopilot: checking the news, Google Trends, X and Reddit for footage of today\'s buzz')
        added=newsdesk.footage(log=lambda m:print(m,flush=True))
        ranked=p.read(p.DATA/'ranked-candidates.json') if (p.DATA/'ranked-candidates.json').exists() else []
        if added: ranked=scouting.refresh()
        return newsdesk.footage_candidates(scouting.visible_ranked(ranked),used)
    except Exception as exc:
        print(f'News footage skipped: {str(exc)[:200]}',flush=True)
        return []


SOURCE_PROBLEMS={'no_complete_scene','not_english','too_little_speech','source_refused','copyright','music_release',
                 'media_broken','bot_check','downloader_outdated'}
SYSTEM_STOP={'disk_full','media_tools_missing','youtube_signin','wrong_channel','out_of_memory','editor_down','editor_missing'}


def make_clips(item, defaults, stage, attempt=None):
    """Download and cut one video. Each failure is diagnosed; where a better approach exists
    (upgrade the downloader, restart the editor, free disk, ask for the single best moment,
    use the lighter transcription model) it is applied and the same video is retried once."""
    import app_runtime as rt
    import preparation as prep
    attempt=attempt or dict(count=defaults['count'],model=defaults['transcription_model'],tries=0)
    try:
        stage(f'Autopilot: downloading “{item["title"][:70]}”',20)
        source=rt.import_source(item['url'],defaults.get('clearance',''),item.get('title',''))
        stage(f'Autopilot: cutting clips from “{item["title"][:70]}”',30)
        return rt.retry(lambda:prep.prepare(source['input'],source['source_url'],attempt['count'],attempt['model'],
                                            defaults['captions'],'semantic',defaults['editor_model'],
                                            progress=lambda n,m: stage('Autopilot: '+m,n)),'Scene selection')
    except Exception as exc:
        diagnosis=health.record('clip-making',exc,item)
        if attempt['tries']>=1 or diagnosis['strategy']!=health.RETRY_BETTER: raise
        better=dict(attempt,tries=attempt['tries']+1)
        if diagnosis['id']=='no_complete_scene':
            if str(attempt['count'])=='1': raise
            better['count']=1
            health.note('editor','No complete scene: asking the editor again for the single best moment (transcript reused)')
        elif diagnosis['id']=='out_of_memory':
            health.repair(diagnosis); better['model']='base'
            health.note('memory','Retrying with the lighter base transcription model')
        elif not health.repair(diagnosis): raise
        stage('Autopilot: retrying the same video with a better approach',25)
        return make_clips(item,defaults,stage,better)


def prepare_round(cfg, stage):
    """Turn the best unused video into ready clips. Tries up to three videos; returns the jobs made.

    A video is hidden (and its channel ranked lower) only when the video itself was the problem.
    When the Mac is the problem (disk, FFmpeg, sign-in, editor) the round stops instead of
    burning good videos, and the diagnosis says what was done about it."""
    import scouting
    import studio
    defaults=studio.preferences()
    ensure_editor(defaults['editor_model'])
    errors=[]
    picks=vary_niches(candidates(cfg,stage),recent_niches())
    for number,item in enumerate(picks[:3],1):
        try:
            jobs=make_clips(item,defaults,stage)
            fresh=[j for j in jobs if not (p.DATA/'exports'/j['id']/'upload.json').exists()]
            if fresh:
                enqueue(fresh); learning.record_source(item,True); health.resolved(*SOURCE_PROBLEMS,*SYSTEM_STOP)
                return fresh,errors
            errors.append(f'{item["title"][:50]}: no new clips')
        except Exception as exc:
            traceback.print_exc(); errors.append(f'{item["title"][:50]}: {exc}')
            diagnosis=health.diagnose(exc)
            if diagnosis['id'] in SYSTEM_STOP or diagnosis['strategy']==health.OWNER:
                errors.append(f'Stopped this round: {diagnosis["title"]}. {diagnosis["fix"]}')
                break
            if diagnosis['strategy']==health.LATER: continue  # a network blip says nothing about the video
            if diagnosis['id'] in SOURCE_PROBLEMS: learning.record_source(item,False,diagnosis['title'])
        try: scouting.hide_video(item)
        except Exception: pass
    return [],errors


def news_images(stage):
    """Headline images for today's buzz (newsdesk). Failures are logged and never block clips."""
    try:
        import newsdesk
        cfg=newsdesk.settings()
        if not (cfg['enabled'] and cfg['images_per_day']): return []
        if not health.allowed('news-images'): return []
        # Spread over the day: at most two new images per hourly tick.
        return newsdesk.make_images(min(2,max(0,cfg['images_per_day']-newsdesk.images_made_today(local_now().date()))),cfg,stage)
    except Exception as exc:
        print(f'News images skipped: {str(exc)[:200]}',flush=True)
        health.failure('news-images',exc)
        return []


def community_posts(local):
    """Post one pending headline image to the channel's Posts tab per tick (9:00-23:00). Never blocks clips."""
    try:
        import newsdesk
        if not newsdesk.settings()['enabled'] or not 9<=local.hour<=23: return []
        if not health.allowed('community'): return []
        import community
        if not community.pending(): return []
        try: import playwright  # noqa: F401
        except ImportError:
            subprocess.run([sys.executable,'-m','pip','install','-q','playwright'],capture_output=True,timeout=900)
        try: return community.post_next(1)
        except Exception as exc:
            if 'Executable' in str(exc) or 'playwright install' in str(exc):
                # Neither Google Chrome nor Playwright's Chromium is installed yet: fetch Chromium once.
                subprocess.run([sys.executable,'-m','playwright','install','chromium'],capture_output=True,timeout=1800)
                return community.post_next(1)
            raise
    except PermissionError as exc:
        print(f'Community posts paused: {exc}',flush=True)
        health.record('posts-tab',exc); health.pause('community',6,exc)
        marker=p.DATA/'newsdesk'/'community-signin-notice.txt'
        today=dt.date.today().isoformat()
        if not (marker.exists() and marker.read_text().strip()==today):
            marker.parent.mkdir(parents=True,exist_ok=True); marker.write_text(today)
            notify('Sign in once so images can post: .venv/bin/python community.py login')
        return []
    except Exception as exc:
        print(f'Community posts skipped: {str(exc)[:200]}',flush=True)
        diagnosis=health.record('posts-tab',exc)
        if diagnosis['id']=='posts_tab': health.pause('community',24,exc)
        else: health.failure('community',exc)
        return []


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
        risk=source_risk(ident)
        if risk:
            skip(ident,risk); print(f'Autopilot held back {ident}: {risk}',flush=True); continue
        stage(f'Autopilot: publishing clip {done+1} for today (minimum {cfg["daily_target"]})',90)
        try:
            video=publish(ident); done+=1
            published.append(dict(id=ident,video_id=video))
            print(f'Autopilot published {ident}: https://youtu.be/{video}',flush=True)
        except Exception as exc:
            traceback.print_exc()
            text=str(exc)
            diagnosis=health.record('publishing',exc,dict(title=ident))
            if any(h in text.lower() for h in AUTH_HINTS) or diagnosis['id'] in ('youtube_signin','wrong_channel'): raise
            if p.quota_refusal(exc):
                # Quota or daily cap: the clip is fine, keep it for the next tick or tomorrow.
                errors.append(f'{ident}: {text} (kept; will retry later)'); break
            if rt.transient(exc) and not (p.DATA/'exports'/ident/'upload.json').exists():
                errors.append(f'{ident}: {text} (will retry next hour)'); break
            if diagnosis['strategy']==health.LATER or rt.transient(exc):
                # The upload was cut off midway. Its receipt stays 'uploading' so it is never posted twice;
                # release_unconfirmed() checks the channel and gives the clip back if YouTube never got it.
                errors.append(f'{ident}: {text} (checking with YouTube before any retry)'); break
            skip(ident,text); errors.append(f'{ident}: {text}')
    return done,due


def run(stage=print, now=None):
    cfg=settings()
    if not cfg['enabled']: return dict(status='off')
    import studio
    timezone=studio.preferences()['timezone']
    local=local_now(now); today=local.date()
    errors=[]; published=[]
    checks=health.preflight(stage)
    for problem in checks: print('Health check: '+problem,flush=True)
    try: p.reconcile_receipts()
    except Exception as exc: print(f'Receipt check skipped: {exc}',flush=True)
    try:
        for ident in p.release_unconfirmed():
            q=queue(); q['skipped'].pop(ident,None); save_queue(q); enqueue([dict(id=ident)])
            health.note('publishing',f'{ident}: YouTube never received the interrupted upload, so it goes out again')
    except Exception as exc: print(f'Unconfirmed upload check skipped: {exc}',flush=True)
    try: learning.refresh_niches()
    except Exception as exc: print(f'Niche learning skipped: {str(exc)[:160]}',flush=True)
    try:
        done,due=publish_due(cfg,today,timezone,local,stage,errors,published)
        rounds=0
        while rounds<cfg['max_rounds'] and len(ready())<max(1,cfg['daily_target']-done):
            rounds+=1
            jobs,problems=prepare_round(cfg,stage)
            errors.extend(problems)
            if not jobs:
                break
            done,due=publish_due(cfg,today,timezone,local,stage,errors,published)
        done,due=publish_due(cfg,today,timezone,local,stage,errors,published)
        news_images(stage)
        community_posts(local)
        if extra_allowed(local,cfg) and not errors:
            # Surplus clips: one extra post per hourly tick so the day's posts stay spread out.
            done,due=publish_due(cfg,today,timezone,local,stage,errors,published,extra=1)
    except Exception as exc:
        text=str(exc)
        health.record('autopilot',exc)
        record=dict(last_run=dt.datetime.now(dt.timezone.utc).isoformat(),day=today.isoformat(),
                    published_today=published_on(today,timezone),target=cfg['daily_target'],
                    ready=len(ready()),published=published,errors=(errors+[text])[-10:],blocked=True)
        p.write(STATE,record)
        if any(h in text.lower() for h in AUTH_HINTS):
            notify('YouTube sign-in expired. Run: .venv/bin/python pipeline.py auth')
        raise
    record=dict(last_run=dt.datetime.now(dt.timezone.utc).isoformat(),day=today.isoformat(),
                published_today=done,due_now=due,target=cfg['daily_target'],ready=len(ready()),
                published=published,errors=errors[-10:],health_checks=checks,blocked=False)
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
