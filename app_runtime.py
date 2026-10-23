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
                stage('Searching across topics'); scouting.discover_broad()
                stage('Ranking sources'); scouting.refresh()
            elif action=='prepare':
                import preparation as prep
                if data.get('url'):
                    stage('Downloading source'); source=prep.import_video(data['url'],data['clearance']); path=source['input']; url=source['source_url']
                else: path=data['path']; url=data['source_url']
                stage('Transcribing and selecting complete scenes — this can take several minutes')
                prep.prepare(path,url,data.get('count',3),'base',data.get('captions',False),'semantic','qwen2.5:7b')
            elif action=='publish':
                for ident in data['ids']:
                    stage('Publishing '+ident)
                    job=p.read(p.DATA/'exports'/ident/'job.json')
                    p.upload(job)
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
        subprocess.run([sys.executable,'-m','unittest','discover','-s','tests'],cwd=p.ROOT,check=True)
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
