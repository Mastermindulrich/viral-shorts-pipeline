"""Durable local tasks, diagnostics and macOS service lifecycle."""
import contextlib
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
import pipeline as p

STATE=p.DATA/'activity.json'
LOG=p.DATA/'logs'/'activity.log'
LABEL='com.viralmomentclips.dashboard'

def active():
    if not STATE.exists(): return {}
    state=p.read(STATE)
    if state.get('status')=='running':
        try: os.kill(state['pid'],0)
        except (ProcessLookupError,KeyError):
            state.update(status='interrupted',error='Task stopped. See diagnostics before retrying an upload.')
    return state

def start(action, payload=None):
    import fcntl
    p.DATA.mkdir(parents=True,exist_ok=True)
    with (p.DATA/'submission.lock').open('a+') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        return _start(action,payload)

def _start(action, payload=None):
    if active().get('status')=='running': raise RuntimeError('A task is already running. Follow its progress in Activity.')
    ident=str(time.time_ns())
    request=p.DATA/'tasks'/(ident+'.json')
    p.write(request,dict(action=action,payload=payload or {}))
    LOG.parent.mkdir(parents=True,exist_ok=True)
    with LOG.open('a') as log:
        child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'task',str(request)],cwd=p.ROOT,stdout=log,stderr=log,start_new_session=True)
    p.write(STATE,dict(status='running',action=action,pid=child.pid,started=dt.datetime.now().isoformat(),request=ident))
    return ident

def stage(message):
    print(message,flush=True)
    state=p.read(STATE) if STATE.exists() else {}
    state['stage']=message
    p.write(STATE,state)

def execute(request):
    # Parent writes the state before this worker begins updating it.
    for _ in range(100):
        if STATE.exists() and p.read(STATE).get('pid')==os.getpid(): break
        time.sleep(.05)
    spec=p.read(request); data=spec['payload']; action=spec['action']
    try:
        if action=='update':
            with p.lock(): update()
            return
        with p.lock():
            if action=='scout':
                import scouting
                stage('Searching recent events and selected topics'); result=scouting.discover_broad()
                for warning in result.get('warnings',[]): print('Discovery warning: '+warning,flush=True)
                stage('Ranking sources'); scouting.refresh()
            elif action=='rescreen':
                import scouting
                stage('Rechecking saved videos with current music and language filters')
                scouting.refresh()
            elif action=='sync_history':
                import studio
                stage('Reading exact publication dates from YouTube')
                count=studio.sync_publication_dates()
                print(f'Updated {count} publication timestamps.',flush=True)
            elif action=='import':
                import preparation as prep
                stage('Importing source for visual selection')
                prep.import_video(data['url'],data['clearance'])
            elif action=='prepare':
                import preparation as prep
                import editorial
                import studio
                stage('Checking the local AI editor')
                editorial.require_model(studio.preferences()['editor_model'])
                if data.get('url'):
                    stage('Downloading source'); source=prep.import_video(data['url'],data['clearance']); path=source['input']; url=source['source_url']
                else: path=data['path']; url=data['source_url']
                stage('Transcribing and selecting complete scenes — this can take several minutes')
                defaults=studio.preferences()
                prep.prepare(path,url,data.get('count',defaults['count']),
                             data.get('transcription_model',defaults['transcription_model']),data.get('captions',defaults['captions']),
                             'semantic',defaults['editor_model'])
            elif action=='visual':
                import uuid
                import preparation as prep
                import studio
                stage('Rendering visual clip — maximum 60 seconds')
                job=dict(id='visual-'+uuid.uuid4().hex[:12],input=data['path'],source_url=data['source_url'],
                         start=float(data['start']),end=float(data['end']),title=data['title'],description='',
                         layout='fit',made_for_kids=False,privacy='public',needs_editorial_review=True)
                p.validate(job)
                source_record=Path(job['input']).parent/'source.json'
                if source_record.exists(): job['clearance_reference']=p.read(source_record).get('clearance_reference','')
                defaults=studio.preferences()
                if defaults['captions']:
                    stage('Preparing English subtitles for the selected visual moment')
                    prep.caption_visual(job,defaults['transcription_model'])
                p.write(p.DATA/'jobs'/(job['id']+'.json'),job)
                p.render(job)
            elif action=='publish':
                # Each clip has its own durable receipt, so one blocked clip need not stop the batch.
                failures=[]
                for ident in data['ids']:
                    stage('Publishing '+ident)
                    try: p.upload(p.read(p.DATA/'exports'/ident/'job.json'))
                    except Exception as exc:
                        print(f'Publish failed for {ident}: {exc}',flush=True)
                        failures.append(f'{ident}: {exc}')
                if failures: raise RuntimeError(f'{len(failures)} of {len(data["ids"])} clips not published. '+' | '.join(failures))
            else: raise ValueError('Unknown task')
        state=p.read(STATE); state.update(status='complete',stage='Finished'); p.write(STATE,state)
    except Exception as exc:
        traceback.print_exc()
        state=p.read(STATE); state.update(status='failed',error=str(exc)); p.write(STATE,state)

def diagnostics():
    text=LOG.read_text(errors='replace')[-24000:] if LOG.exists() else 'No activity logs yet.'
    text=re.sub(r'(?i)(access_token|refresh_token|client_secret|authorization)([\s"\x27:=]+)[^\s,}\n]+',r'\1\2[REDACTED]',text)
    text=re.sub(r'ya29\.[\w.-]+','[REDACTED]',text)
    version=subprocess.run(['git','rev-parse','--short','HEAD'],cwd=p.ROOT,capture_output=True,text=True).stdout.strip()
    return json.dumps(dict(version=version,python=sys.version.split()[0],activity=active()),indent=2)+'\n'+text

PACKAGES=[('streamlit','requirements.txt'),('googleapiclient','requirements.txt'),('google_auth_oauthlib','requirements.txt'),
          ('yt_dlp','requirements-preparation.txt'),('faster_whisper','requirements-preparation.txt')]

def readiness(editor_model=None):
    """Local setup checks. Reports only whether credentials exist, never their contents."""
    import importlib.util
    import shutil
    import editorial
    import studio
    model=editor_model or studio.preferences()['editor_model']
    install='.venv/bin/python -m pip install -r requirements.txt -r requirements-preparation.txt'
    checks=[]
    def check(name,ok,detail,fix='',required=True):
        checks.append(dict(name=name,ok=bool(ok),detail=detail,fix='' if ok else fix,required=required))
    version='.'.join(map(str,sys.version_info[:3]))
    check('Python 3.11+',sys.version_info>=(3,11),'Python '+version,'brew install python@3.12')
    check('Project virtual environment',(p.ROOT/'.venv'/'bin'/'python').exists(),'.venv',
          'python3 -m venv .venv && '+install)
    missing=sorted({req for module,req in PACKAGES if importlib.util.find_spec(module) is None})
    check('Python packages',not missing,'Missing from '+', '.join(missing) if missing else 'Installed',install)
    for tool in ('ffmpeg','ffprobe'):
        path=shutil.which(p.media_tool(tool))
        check(tool.upper() if tool=='ffmpeg' else 'ffprobe',path,path or 'Not found','brew install ffmpeg-full')
    captions=p.caption_capability()
    check('Burned-in English subtitles',captions['supported'],captions['reason'],'brew install ffmpeg-full',required=False)
    try:
        names=editorial.installed_models()
        check('Ollama running',True,editorial.OLLAMA)
        check('Local AI editor model',model in names or model+':latest' in names,model,'ollama pull '+model)
    except Exception:
        check('Ollama running',False,'Not reachable at '+editorial.OLLAMA,'brew install ollama && open -a Ollama  (or: ollama serve)')
        check('Local AI editor model',False,model+' (cannot check while Ollama is stopped)','ollama pull '+model)
    check('YouTube authorization',(p.DATA/'secrets'/'token.json').exists(),'Saved locally' if (p.DATA/'secrets'/'token.json').exists() else 'Not set up',
          '.venv/bin/python pipeline.py auth   (sign in through the browser; never paste tokens anywhere)')
    return checks

def readiness_report(checks):
    lines=[]
    for x in checks:
        mark='OK' if x['ok'] else ('MISSING' if x['required'] else 'OPTIONAL')
        lines.append(f"[{mark:<8}] {x['name']}: {x['detail']}"+(f"\n           Fix: {x['fix']}" if x['fix'] else ''))
    return '\n'.join(lines)

def install():
    import plistlib
    if sys.platform!='darwin': raise RuntimeError('Mac installation must run on your Mac.')
    folder=Path.home()/'Library'/'LaunchAgents'; folder.mkdir(parents=True,exist_ok=True)
    LOG.parent.mkdir(parents=True,exist_ok=True)
    plist=folder/(LABEL+'.plist')
    config=dict(Label=LABEL,ProgramArguments=[str(p.ROOT/'.venv/bin/python'),'-m','streamlit','run',str(p.ROOT/'dashboard.py'),'--server.address','127.0.0.1','--server.port','8501','--server.headless','true','--browser.gatherUsageStats','false'],WorkingDirectory=str(p.ROOT),RunAtLoad=True,KeepAlive=True,StandardOutPath=str(LOG),StandardErrorPath=str(LOG),EnvironmentVariables={'PATH':'/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin'})
    plist.write_bytes(plistlib.dumps(config))
    target=f'gui/{os.getuid()}'
    subprocess.run(['launchctl','bootout',target,str(plist)],capture_output=True)
    subprocess.run(['launchctl','bootstrap',target,str(plist)],check=True)
    # Finder application opens the service dashboard without a visible terminal.
    app=Path.home()/'Applications'/'Viral Moment Clips.app'; app.parent.mkdir(exist_ok=True)
    subprocess.run(['osacompile','-o',str(app),'-e','open location "http://127.0.0.1:8501"'],check=True)
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health',timeout=1)
            break
        except Exception: time.sleep(.5)
    else: raise RuntimeError('Service installed but startup failed. Open '+str(LOG))
    subprocess.run(['open',str(app)],check=True)
    print('Installed. Open ~/Applications/Viral Moment Clips.app. Logs: '+str(LOG))

def run_update_checks():
    stage('Validating update')
    result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],
                          cwd=p.ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    output=result.stdout or ''
    LOG.parent.mkdir(parents=True,exist_ok=True)
    (LOG.parent/'update-checks.log').write_text(output)
    print(output,flush=True)
    if result.returncode:
        names=[line for line in output.splitlines() if line.startswith(('ERROR:','FAIL:'))]
        detail='; '.join(names) or output[-1500:]
        raise RuntimeError('Update validation failed: '+detail+
                           '. See Activity diagnostics or data/logs/update-checks.log for details.')


def update():
    stage('Checking for updates')
    if not (Path.home()/'Library/LaunchAgents'/(LABEL+'.plist')).exists(): raise RuntimeError('Install the Mac launcher before using Update app.')
    dirty=subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=p.ROOT,text=True)
    # Local config is intentionally preserved and never overwritten.
    changed=[line[3:] for line in dirty.splitlines() if not line[3:].startswith('config/')]
    if changed: raise RuntimeError('Local code changes detected; update stopped to preserve your work: '+', '.join(changed))
    old=subprocess.check_output(['git','rev-parse','HEAD'],cwd=p.ROOT,text=True).strip()
    subprocess.run(['git','fetch','origin'],cwd=p.ROOT,check=True)
    remote=subprocess.check_output(['git','rev-parse','@{upstream}'],cwd=p.ROOT,text=True).strip()
    if old==remote:
        state=p.read(STATE); state.update(status='complete',stage='Already up to date'); p.write(STATE,state); return
    subprocess.run(['git','merge-base','--is-ancestor',old,remote],cwd=p.ROOT,check=True)
    config={x:x.read_bytes() for x in (p.ROOT/'config').glob('*.json')}
    stash=False
    try:
        if dirty.strip():
            subprocess.run(['git','stash','push','-m','VMC updater local configuration','--','config'],cwd=p.ROOT,check=True); stash=True
        stage('Installing update')
        subprocess.run(['git','merge','--ff-only',remote],cwd=p.ROOT,check=True)
        subprocess.run([sys.executable,'-m','pip','install','-r','requirements.txt','-r','requirements-preparation.txt'],cwd=p.ROOT,check=True)
        run_update_checks()
    except Exception:
        subprocess.run(['git','reset','--hard',old],cwd=p.ROOT,check=True)
        raise
    finally:
        for path,content in config.items(): path.write_bytes(content)
        if stash: print('Original configuration also retained in git stash.',flush=True)
    state=p.read(STATE); state.update(status='complete',stage='Updated; dashboard restarting'); p.write(STATE,state)
    subprocess.run(['launchctl','kickstart','-k',f'gui/{os.getuid()}/{LABEL}'],check=True)

if __name__=='__main__':
    if sys.argv[1]=='install': install()
    elif sys.argv[1]=='task': execute(sys.argv[2])
    elif sys.argv[1]=='doctor':
        checks=readiness(); print(readiness_report(checks))
        sys.exit(any(x['required'] and not x['ok'] for x in checks))
