"""Self-diagnosis: classify every failure, find its likely cause, repair what can be repaired.

Owner request (2026-11-24): "a smart software that analyses every failure and finds causes and
corrects them", with zero intervention. Every failure the autopilot meets goes through
`record()`, which:

1. matches the error against CAUSES (known failure patterns seen on the owner's Mac and in the
   YouTube, yt-dlp, Ollama and FFmpeg error texts) and names the root cause in plain English;
2. picks a strategy: retry the same video a better way, move to the next video, keep the clip
   for later, or (only when nothing else can work) ask the owner;
3. saves the incident in data/health/incidents.json with counters per cause, so repeated
   problems are visible on the dashboard and in `app_runtime.py health`.

`repair()` runs the automatic fix for a cause (upgrade yt-dlp, restart the local editor, free
disk space, ...), each rate-limited so a broken fix never loops. `allowed()/failure()/success()`
are circuit breakers for optional extras (illustrations, the Posts tab, Reddit): after repeated
failures they pause instead of wasting minutes every hour. `preflight()` checks the Mac before
each run and fixes what it can. Nothing here relaxes a content, copyright or duplicate rule.
"""
import datetime as dt
import re
import shutil
import subprocess
import sys
import time
import pipeline as p

FOLDER='health'
MAX_INCIDENTS=400

# Strategies
RETRY_BETTER='retry_better'   # repair, then retry the same video once with a better approach
NEXT='next_video'             # the video was the problem: learn from it and move on
LATER='retry_later'           # temporary: keep everything and try again on the next tick
KEEP='keep_clip'              # the clip is fine; YouTube or the app limit says later
OWNER='needs_owner'           # only the owner can fix it (sign-in, a setting on YouTube)
SKIP='skip_clip'              # this clip can never be posted (duplicate, invalid)

CAUSES=[
    dict(id='youtube_signin',match=r'invalid_grant|token has been expired|expired or revoked|authorization expired|run auth|refresherror',
         title='YouTube sign-in expired',strategy=OWNER,repair=None,
         cause='Google stopped accepting the saved sign-in. Google Cloud projects whose OAuth consent screen is still in '
               '"Testing" expire sign-ins every 7 days; a password change or removed access does it too.',
         fix='Clips are kept and post automatically once you sign in again.',
         owner='Run: .venv/bin/python pipeline.py auth. To stop the weekly expiry, open Google Cloud Console, then '
               'APIs and Services, then OAuth consent screen, and press "Publish app" (Production).'),
    dict(id='wrong_channel',match=r'connected to .* expected|expected_channel|wrong channel|read-only permission',
         title='YouTube is signed in to the wrong channel',strategy=OWNER,repair=None,
         cause='The saved sign-in belongs to a different channel than Viral Moment Clips, or lacks permission.',
         fix='Nothing is uploaded to the wrong channel; clips are kept.',
         owner='Run: .venv/bin/python pipeline.py auth and choose the Viral Moment Clips channel.'),
    dict(id='youtube_quota',match=r'quotaexceeded|exceeded your quota|quota exceeded|uploadlimitexceeded|exceeded the number of videos',
         title='YouTube daily quota used up',strategy=KEEP,repair=None,
         cause='The YouTube Data API allows 10,000 units a day; one upload costs about 1,600 and a search about 100, '
               'so roughly 5 to 6 uploads fit. The quota resets at midnight Pacific time.',
         fix='The clip is kept and posts after the reset. Searches use yt-dlp where possible to save quota.',
         owner=None),
    dict(id='app_daily_cap',match=r'daily upload cap',title="The app's daily upload limit was reached",strategy=KEEP,repair=None,
         cause='config/settings.json max_uploads_per_day was reached for this UTC day.',
         fix='The clip is kept for the next UTC day.',owner=None),
    dict(id='duplicate',match=r'duplicate upload blocked|already published from this moment|upload already attempted',
         title='Clip would repeat an earlier upload',strategy=SKIP,repair=None,
         cause='The duplicate guard found an earlier upload of the same moment or the same video bytes.',
         fix='The clip is skipped so the channel never posts the same moment twice.',owner=None),
    dict(id='downloader_outdated',match=r'unable to extract|nsig|signature extraction|failed to extract|player response|'
                                       r'requested format is not available|unsupported url|precondition check failed|http error 403',
         title='YouTube changed its player and the downloader needs an update',strategy=RETRY_BETTER,repair='upgrade_downloader',
         cause='yt-dlp breaks every few weeks when YouTube changes its pages.',
         fix='yt-dlp is upgraded automatically (at most once a day) and the same video is retried.',owner=None),
    dict(id='bot_check',match=r'sign in to confirm|not a bot|confirm your age',
         title='YouTube asked the downloader to sign in',strategy=NEXT,repair='upgrade_downloader',
         cause='YouTube sometimes asks automated downloads to prove they are not a bot, or the video is age-gated.',
         fix='The downloader is upgraded and the next video is used; this one is not offered again.',owner=None),
    dict(id='source_refused',match=r'no longer than 20 minutes|finished video|still live|upcoming|age-restricted|will not provide this video|'
                                   r'private video|video unavailable|has been removed|not available in your country|members-only|'
                                   r'did not report a length|shorter than 30 seconds|copyright grounds',
         title='The video cannot be downloaded or is too long',strategy=NEXT,repair=None,
         cause='The video is live, too long, private, removed, region-blocked or restricted.',
         fix='It is remembered as unsupported and the next video is used.',owner=None),
    dict(id='copyright',match=r'rights-holder|avoid copyright claims|official studio, network',
         title='Official rights-holder material',strategy=NEXT,repair=None,
         cause='The video comes from a studio, network, label, league or publisher, or is their official cut.',
         fix='Skipped to avoid copyright claims; third-party footage is used instead.',owner=None),
    dict(id='music_release',match=r'standalone music video|music-category release',title='Music release',strategy=NEXT,repair=None,
         cause='Official music videos and audio are excluded by the channel rules.',fix='The next video is used.',owner=None),
    dict(id='not_english',match=r'english dialogue required|declared audio is not english',title='Not in English',strategy=NEXT,repair=None,
         cause='The speech is not English, so the editor cannot check the scene.',
         fix='The next video is used and this channel is ranked lower.',owner=None),
    dict(id='no_complete_scene',match=r'no complete scenes|no valid complete scenes|final context review|complete scenes',
         title='No complete, self-contained moment found',strategy=RETRY_BETTER,repair=None,
         cause='The local editor could not find a moment with a clear setup and payoff that passes the evidence checks. '
               'Common with montages, crosstalk, music-heavy videos and very short answers.',
         fix='The editor tries once more asking for the single best moment; if that also fails the next video is used.',owner=None),
    dict(id='too_little_speech',match=r'not enough continuous speech|transcript is empty|no speech',title='Too little speech',
         strategy=NEXT,repair=None,cause='The video is mostly music, action or silence.',fix='The next video is used.',owner=None),
    dict(id='editor_missing',match=r'is not installed|ollama pull',title='The local AI editor model is missing',
         strategy=RETRY_BETTER,repair='restart_editor',cause='The Ollama model was removed or never downloaded.',
         fix='The model is downloaded automatically (stays on your Mac).',owner=None),
    dict(id='editor_down',match=r'11434|ollama|local ai editor|model runner|llama runner|connection refused',
         title='The local AI editor stopped responding',strategy=RETRY_BETTER,repair='restart_editor',
         cause='Ollama was closed, crashed, or ran out of memory while thinking.',
         fix='Ollama is restarted and the same video is retried.',owner=None),
    dict(id='out_of_memory',match=r'cannot allocate memory|out of memory|memoryerror|killed: 9|resource exhausted',
         title='The Mac ran out of working memory',strategy=RETRY_BETTER,repair='restart_editor',
         cause='Transcription and the AI editor together needed more memory than was free.',
         fix='Ollama is restarted to free memory and the video is retried with the lighter transcription model.',owner=None),
    dict(id='disk_full',match=r'no space left|disk full|errno 28|not enough free space',title='The disk is full',
         strategy=RETRY_BETTER,repair='free_space',cause='Downloaded source videos filled the disk.',
         fix='Source videos that are no longer needed are deleted (never clips, receipts or sign-ins) and the step is retried.',
         owner=None),
    dict(id='media_tools_missing',match=r"no such file or directory: 'ffmpeg'|no such file or directory: 'ffprobe'|ffmpeg not found|ffprobe not found",
         title='FFmpeg is missing',strategy=OWNER,repair=None,cause='The video tools were uninstalled or are not on the PATH.',
         fix='Nothing can be rendered until FFmpeg is back.',owner='Run in Terminal: brew install ffmpeg-full'),
    dict(id='media_broken',match=r'invalid data found|moov atom|could not find codec|error while decoding|merged video|ffprobe|ffmpeg',
         title='The video file could not be processed',strategy=NEXT,repair=None,
         cause='The downloaded file is damaged or uses a format FFmpeg could not read.',fix='The next video is used.',owner=None),
    dict(id='upload_dropped',match=r'broken pipe|errno 32|connection reset|connection aborted|remote end closed|incompleteread',
         title='The internet connection dropped during a transfer',strategy=LATER,repair=None,
         cause='The Wi-Fi or the server closed the connection mid-transfer.',
         fix='Uploads resume where they stopped; an upload that cannot be confirmed is checked against the channel '
             'and released for a clean retry after two hours.',owner=None),
    dict(id='network',match=r'timed out|timeout|name resolution|nodename nor servname|temporarily|unreachable|network is down|'
                            r'http error 5\d\d|\b50[0234]\b|ssl|certificate|urlopen error',
         title='A service could not be reached',strategy=LATER,repair=None,
         cause='The internet connection or YouTube/Google was briefly unavailable.',
         fix='Retried automatically a few times, then again on the next hourly run.',owner=None),
    dict(id='busy',match=r'another task|already running|database is locked|resource temporarily unavailable',
         title='Another job was still running',strategy=LATER,repair=None,cause='Two jobs tried to run at once.',
         fix='The next hourly run continues.',owner=None),
    dict(id='posts_tab',match=r'create post|posts tab',title='The YouTube Posts tab is not available',strategy=OWNER,repair=None,
         cause='YouTube has not enabled posts for the channel yet, or changed the page.',
         fix='Image posts pause for a day instead of retrying every hour. Clips are not affected.',
         owner='Open YouTube Studio on the channel and check that "Create post" appears on the Posts tab.'),
    dict(id='posts_signed_out',match=r'not signed in|sign in once so images can post|signed out',title='The posting browser is signed out',
         strategy=OWNER,repair=None,cause='The saved browser sign-in for image posts expired.',
         fix='Image posts pause; clips are not affected.',owner='Run: .venv/bin/python community.py login'),
]
UNKNOWN=dict(id='unknown',title='An unexpected problem',strategy=LATER,repair=None,
             cause='This error does not match a known pattern yet.',
             fix='Everything is kept and the next hourly run tries again. The details are saved for diagnosis.',owner=None)


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _path(name):
    return p.DATA/FOLDER/name


def _load(name, default):
    try: return p.read(_path(name)) if _path(name).exists() else default
    except (OSError,ValueError): return default


def diagnose(error):
    """The cause entry for an exception or error text (a copy, so callers may annotate it)."""
    text=(type(error).__name__+': ' if isinstance(error,BaseException) else '')+str(error)
    lowered=text.lower()
    for cause in CAUSES:
        if re.search(cause['match'],lowered): return dict(cause)
    if isinstance(error,(ConnectionError,TimeoutError)): return dict(next(x for x in CAUSES if x['id']=='network'))
    return dict(UNKNOWN)


def signature(error):
    """A short, id-free form of the error so repeats of the same unknown problem are counted together."""
    text=str(error)[:300]
    text=re.sub(r'[0-9a-f]{8,}|\d+','#',text)
    return re.sub(r'\s+',' ',text).strip()[:160]


def record(where, error, item=None, outcome=''):
    """Diagnose and save one failure. Returns the diagnosis. Never raises."""
    diagnosis=diagnose(error)
    try:
        incidents=_load('incidents.json',[])
        entry=dict(at=_now().isoformat(),where=where,cause=diagnosis['id'],title=diagnosis['title'],
                   strategy=diagnosis['strategy'],error=re.sub(r'ya29\.[\w.-]+','[REDACTED]',str(error))[:400],
                   signature=signature(error),outcome=outcome)
        if item: entry['video']=dict(title=str(item.get('title',''))[:90],url=item.get('url',''),channel=item.get('source',''))
        incidents.append(entry)
        p.write(_path('incidents.json'),incidents[-MAX_INCIDENTS:])
        stats=_load('stats.json',{})
        row=stats.get(diagnosis['id'],dict(count=0,consecutive=0))
        row.update(count=row['count']+1,consecutive=row.get('consecutive',0)+1,last=entry['at'],title=diagnosis['title'])
        stats[diagnosis['id']]=row
        p.write(_path('stats.json'),stats)
        print(f"Diagnosis [{where}]: {diagnosis['title']}. Cause: {diagnosis['cause']} Action: {diagnosis['fix']}",flush=True)
    except Exception as exc:
        print(f'Health record skipped: {exc}',flush=True)
    return diagnosis


def resolved(*cause_ids):
    """A step succeeded: reset the consecutive count of the causes it could have hit."""
    try:
        stats=_load('stats.json',{})
        for ident in cause_ids or list(stats):
            if ident in stats: stats[ident]['consecutive']=0
        p.write(_path('stats.json'),stats)
    except Exception: pass


def note(where, message):
    """Record an automatic fix or decision (shown on the dashboard as 'fixed automatically')."""
    try:
        fixes=_load('fixes.json',[])
        fixes.append(dict(at=_now().isoformat(),where=where,message=str(message)[:300]))
        p.write(_path('fixes.json'),fixes[-200:])
        print(f'Self-repair [{where}]: {message}',flush=True)
    except Exception: pass


# ---------- automatic repairs ----------

def _cooldown_ok(name, minutes):
    marks=_load('repairs.json',{})
    try:
        last=dt.datetime.fromisoformat(marks[name])
        if (_now()-last).total_seconds()<minutes*60: return False
    except (KeyError,ValueError): pass
    marks[name]=_now().isoformat(); p.write(_path('repairs.json'),marks)
    return True


def upgrade_downloader():
    """Upgrade yt-dlp at most once a day (YouTube changes its player every few weeks)."""
    if not _cooldown_ok('upgrade_downloader',20*60): return False
    result=subprocess.run([sys.executable,'-m','pip','install','-q','-U','yt-dlp'],capture_output=True,text=True,timeout=600)
    ok=result.returncode==0
    note('downloader','yt-dlp upgraded' if ok else 'yt-dlp upgrade failed: '+(result.stderr or '')[-200:])
    if ok:
        # Reload so this process uses the new version without a restart.
        for name in [x for x in sys.modules if x=='yt_dlp' or x.startswith('yt_dlp.')]: sys.modules.pop(name,None)
    return ok


def restart_editor(sleep=time.sleep):
    """Restart Ollama (frees memory, recovers a crashed runner). At most every 10 minutes."""
    if not _cooldown_ok('restart_editor',10): return False
    import studio
    model=studio.preferences()['editor_model']
    if sys.platform=='darwin':
        subprocess.run(['osascript','-e','quit app "Ollama"'],capture_output=True,timeout=30)
        subprocess.run(['pkill','-f','ollama runner'],capture_output=True,timeout=30)
        sleep(3)
    import autopilot
    try:
        autopilot.ensure_editor(model,sleep=sleep)
        note('editor','Ollama restarted and the editor model answered')
        return True
    except Exception as exc:
        note('editor',f'Ollama restart did not help: {str(exc)[:160]}')
        return False


def free_gb(path=None):
    target=path or (p.DATA if p.DATA.exists() else p.ROOT)
    try: return shutil.disk_usage(target).free/1e9
    except OSError: return 99.0


def protected_inputs():
    """Source videos still needed: a clip that is ready, unposted or under review uses them."""
    keep=set()
    for job_path in (p.DATA/'jobs').glob('*.json'):
        try: job=p.read(job_path)
        except (OSError,ValueError): continue
        if not (p.DATA/'exports'/job.get('id','')/'upload.json').exists(): keep.add(str(p.Path(job.get('input','')).resolve()))
    return keep


def free_space(target_gb=8, min_age_hours=6):
    """Delete downloaded source videos that no unposted clip needs, oldest first, until target_gb is free.
    Never touches clips, jobs, receipts, transcripts, settings or sign-ins. Returns GB freed."""
    keep=protected_inputs(); freed=0.0
    sources=sorted((p.DATA/'imports').glob('*/source.mp4'),key=lambda x:x.stat().st_mtime)
    for source in sources:
        if free_gb()>=target_gb: break
        if str(source.resolve()) in keep: continue
        if (time.time()-source.stat().st_mtime)<min_age_hours*3600: continue
        size=source.stat().st_size/1e9
        source.unlink(missing_ok=True); freed+=size
    if freed: note('disk',f'Deleted {freed:.1f} GB of source videos no unposted clip needs')
    return freed


REPAIRS=dict(upgrade_downloader=upgrade_downloader,restart_editor=restart_editor,free_space=lambda:free_space()>0)


def repair(diagnosis):
    """Run the automatic fix for a diagnosis. True when something was fixed."""
    name=diagnosis.get('repair')
    if not name: return False
    try: return bool(REPAIRS[name]())
    except Exception as exc:
        note('repair',f'{name} failed: {str(exc)[:160]}')
        return False


# ---------- circuit breakers for optional extras ----------

def allowed(name, now=None):
    breakers=_load('breakers.json',{})
    row=breakers.get(name) or {}
    try: return not row.get('paused_until') or dt.datetime.fromisoformat(row['paused_until'])<=(now or _now())
    except ValueError: return True


def failure(name, error, threshold=3, hours=24):
    """Count a failure of an optional extra; after `threshold` in a row it pauses for `hours`."""
    breakers=_load('breakers.json',{})
    row=breakers.get(name,dict(failures=0))
    row['failures']=row.get('failures',0)+1; row['last_error']=str(error)[:300]
    if row['failures']>=threshold:
        row['paused_until']=(_now()+dt.timedelta(hours=hours)).isoformat(); row['failures']=0
        note(name,f'Paused for {hours} h after {threshold} failures in a row: {str(error)[:140]}')
    breakers[name]=row; p.write(_path('breakers.json'),breakers)


def pause(name, hours, reason):
    breakers=_load('breakers.json',{})
    breakers[name]=dict(failures=0,last_error=str(reason)[:300],paused_until=(_now()+dt.timedelta(hours=hours)).isoformat())
    p.write(_path('breakers.json'),breakers)
    note(name,f'Paused for {hours} h: {str(reason)[:160]}')


def success(name):
    breakers=_load('breakers.json',{})
    if name in breakers:
        breakers.pop(name); p.write(_path('breakers.json'),breakers)


# ---------- preflight ----------

def preflight(stage=print):
    """Checks before each autopilot run. Fixes what it can and returns the problems left (plain English)."""
    problems=[]
    if free_gb()<5:
        stage('Health check: low disk space, removing source videos that are no longer needed')
        free_space(target_gb=8,min_age_hours=1)
        if free_gb()<2: problems.append(f'Only {free_gb():.1f} GB free on the disk. Clips need about 2 GB of working space.')
    for tool in ('ffmpeg','ffprobe'):
        if not shutil.which(p.media_tool(tool)): problems.append(f'{tool} is missing. Run in Terminal: brew install ffmpeg-full')
    if not (p.DATA/'secrets'/'token.json').exists():
        problems.append('YouTube is not signed in. Run: .venv/bin/python pipeline.py auth')
    for path in (p.DATA/'tasks').glob('*.json'):
        # Old task request files pile up forever; keep two days of them.
        try:
            if time.time()-path.stat().st_mtime>2*86400: path.unlink()
        except OSError: pass
    return problems


# ---------- plain-English report ----------

def report(hours=24, now=None):
    """What happened recently, what the app fixed by itself and what (if anything) needs the owner."""
    now=now or _now(); since=(now-dt.timedelta(hours=hours)).isoformat()
    incidents=[x for x in _load('incidents.json',[]) if x.get('at','')>=since]
    fixes=[x for x in _load('fixes.json',[]) if x.get('at','')>=since]
    stats=_load('stats.json',{})
    by_cause={}
    for row in incidents: by_cause.setdefault(row['cause'],[]).append(row)
    lookup={x['id']:x for x in CAUSES}; lookup['unknown']=UNKNOWN
    needs=[]; handled=[]
    for ident,rows in sorted(by_cause.items(),key=lambda x:-len(x[1])):
        cause=lookup.get(ident,UNKNOWN)
        line=dict(cause=ident,title=cause['title'],times=len(rows),why=cause['cause'],action=cause['fix'],
                  last=rows[-1]['at'],example=rows[-1].get('video',{}).get('title') or rows[-1]['error'][:120])
        # An owner problem that has since succeeded (consecutive reset) no longer needs the owner.
        if cause['strategy']==OWNER and stats.get(ident,{}).get('consecutive',0)>0:
            needs.append(dict(line,owner=cause['owner']))
        else: handled.append(line)
    unknown=[x for x in incidents if x['cause']=='unknown']
    repeats={}
    for row in unknown: repeats[row['signature']]=repeats.get(row['signature'],0)+1
    for sig,count in repeats.items():
        if count>=3: needs.append(dict(cause='unknown',title='A new problem keeps repeating',times=count,why=sig,
                                       action='Share Settings → Activity and diagnostics so it can be added to the self-repair list.',
                                       owner='Share the diagnostics report.',last='',example=sig))
    breakers=_load('breakers.json',{})
    paused=[dict(name=k,until=v['paused_until'],reason=v.get('last_error','')) for k,v in breakers.items()
            if v.get('paused_until') and v['paused_until']>now.isoformat()]
    status='needs_you' if needs else ('fixed' if incidents else 'healthy')
    headline={'healthy':'Everything is running smoothly.',
              'fixed':f'{len(incidents)} problem(s) in the last {hours} h, all handled automatically.',
              'needs_you':f'{len(needs)} thing(s) need you. Everything else is handled automatically.'}[status]
    return dict(status=status,headline=headline,needs_you=needs,handled=handled,fixes=fixes[-10:],paused=paused,
                incidents=len(incidents))


def report_text(hours=24):
    r=report(hours)
    lines=[r['headline']]
    for x in r['needs_you']:
        lines.append(f"\nNEEDS YOU: {x['title']} ({x['times']}x)\n  Why: {x['why']}\n  Do this: {x['owner']}")
    for x in r['handled']:
        lines.append(f"\nHandled: {x['title']} ({x['times']}x)\n  Why: {x['why']}\n  What the app did: {x['action']}")
    for x in r['paused']:
        lines.append(f"\nPaused until {x['until'][:16]} UTC: {x['name']} ({x['reason'][:120]})")
    for x in r['fixes']:
        lines.append(f"\nFixed automatically {x['at'][:16]} UTC: {x['message']}")
    return '\n'.join(lines)
