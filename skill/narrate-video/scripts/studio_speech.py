#!/usr/bin/env python3
"""Narrate with the user's accepted local voice profile, without voice fallback.

  studio_speech.py status --start --open [--language en ...] [--wait SECONDS]
      start the studio server in the background if needed, then report whether the profile is
      ready; with --open, a profile that is not ready opens the studio in the user's default
      browser. Exit 0 ready, 1 waiting on the user, 3 studio not running.
  studio_speech.py phrase.txt out.wav --language en    narrate one phrase (starts the server too)
  studio_speech.py stop      stop the background server after delivery, freeing the loaded model's memory

The voice profile is saved, so a ready profile needs no browser at all: the server runs headless.
Only when status is not ready does the user get the studio page, in their own default browser, to
record and approve their voice. The agent never drives that page; it uses this command line."""
import argparse,json,os,signal,subprocess,sys,tempfile,time,urllib.parse,urllib.request,webbrowser
from pathlib import Path
from render import command,digest,audio_peak

ENDPOINT='http://127.0.0.1:8765'
STUDIO=Path(__file__).resolve().parent/'voice-studio/studio.py'
DATA=Path(os.environ.get('NARRATE_VIDEO_DATA',os.environ.get('WALKTHROUGH_VIDEO_DATA',Path.home()/'.local/share/narrate-video')))

def runs(python):
    """Whether this interpreter starts. A failed `-m venv` leaves bin/python without a usable standard library."""
    try:return subprocess.run([str(python),'-c',''],stdin=subprocess.DEVNULL,capture_output=True,timeout=30).returncode==0
    except(OSError,subprocess.TimeoutExpired):return False

def studio_python():
    """The Python that runs the studio: NARRATE_VIDEO_PYTHON, else the documented audio-env, else this one."""
    if os.environ.get('NARRATE_VIDEO_PYTHON'):return os.path.abspath(os.environ['NARRATE_VIDEO_PYTHON'])
    for env in(DATA/'audio-env/bin/python',Path.home()/'.local/share/narrate-video/audio-env/bin/python'):
        if env.exists():
            if not runs(env):raise RuntimeError(f'{env} does not start; delete {env.parent.parent} and create it again (README, First run)')
            return str(env.absolute())
    return sys.executable

def local(endpoint):
    url=urllib.parse.urlparse(endpoint)
    if url.scheme!='http' or url.hostname not in ('localhost','127.0.0.1') or url.username or url.password:
        raise ValueError('Use the selected local studio; this client has no cloud endpoint')

def fetch_status(endpoint):
    local(endpoint)
    with urllib.request.urlopen(endpoint+'/api/status',timeout=10)as r:return json.load(r)

def start_server(endpoint=ENDPOINT,timeout=60):
    """The studio's status, starting its server in the background first if it is not running. No browser opens."""
    local(endpoint)
    try:return fetch_status(endpoint)
    except OSError:pass
    DATA.mkdir(parents=True,exist_ok=True);log=DATA/'studio.log'
    port=str(urllib.parse.urlparse(endpoint).port or 80)
    with open(log,'ab')as out:
        # The caller's working directory and an absolute data folder: a relative NARRATE_VIDEO_DATA means the same
        # folder as a manual launch from here, so the saved profile is found.
        subprocess.Popen([studio_python(),str(STUDIO)],env={**os.environ,'VOICE_STUDIO_PORT':port,'NARRATE_VIDEO_DATA':str(DATA.absolute())},
            stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
    deadline=time.monotonic()+timeout
    while True:
        try:return fetch_status(endpoint)
        except OSError:
            if time.monotonic()>=deadline:raise RuntimeError(f'The studio did not start; see {log}')
            time.sleep(.5)

def accepted(status,language):
    c=status['config']
    reference=status.get('effectiveReferences',{}).get(language) or c.get('references',{}).get(language) or language
    saved=status.get('mine',{}).get(reference);approval=c.get('accepted',{}).get(language,{})
    grant=c.get('sharedEnglishApproval',{});english=c.get('accepted',{}).get('en',{})
    if reference=='en' and saved and grant.get('mode')=='english-reference' and grant.get('engine')==c.get('engine') and grant.get('referenceSha256')==saved['sha256'] and grant.get('acceptedEnglishId') and grant.get('acceptedEnglishId')==english.get('id'):
        approval=english
    return bool(saved) and approval.get('engine')==c.get('engine') and approval.get('referenceSha256')==saved['sha256'],reference,saved

def profile(status,language):
    """The engine, reference and saved recording for an accepted language, or ValueError saying what the user must do."""
    c=status['config'];engine=c.get('engine');models=status.get('engines',{})
    setup='Complete language/model setup and accept your voice auditions in the studio first'
    if engine not in models or c.get('voice')!='mine':raise ValueError(setup)
    if not c.get('profileReady'):
        langs=c.get('languages',[])
        if langs and all(accepted(status,l)[0] for l in langs):
            raise ValueError('Every audition is accepted; click Save my voice profile in the studio to finish')
        raise ValueError(setup)
    if language not in c.get('languages',[]) or language not in models[engine]['langs']:
        raise ValueError('Add this language to your voice profile first; no language substitution')
    ok,reference,saved=accepted(status,language)
    if not ok:raise ValueError('The model or reference changed. Accept a fresh audition or reuse a current explicit shared-reference approval first')
    return engine,reference,saved

def open_studio(endpoint):
    """Show the studio in the user's default browser (open, start or xdg-open), never a browser the agent controls.
    Linux without a display (SSH, containers, CI) would fall back to a console browser that blocks: give the link instead."""
    if sys.platform.startswith('linux') and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):return False
    try:return bool(webbrowser.open(endpoint,new=2))
    except webbrowser.Error:return False

def status(languages=None,endpoint=ENDPOINT,wait=0,poll=5,start=False,show=False):
    """Whether the voice profile is ready for these languages (default: the profile's own), polling up to `wait` seconds.
    With start, a stopped server is started in the background first. With show, a profile that is not ready
    opens the studio once in the user's default browser."""
    local(endpoint);deadline=time.monotonic()+wait;opened=None;start_error=None
    if start:
        try:start_server(endpoint)
        except RuntimeError as e:start_error=str(e)
    while True:
        try:st=fetch_status(endpoint)
        except OSError:st=None
        if st is None:
            report=dict(studio=endpoint,running=False,ready=False,languages={},
                next=start_error or f'Run status --start; if the studio still does not start, see {DATA/"studio.log"}')
        else:
            langs={}
            for lang in languages or st['config'].get('languages',[]):
                try:profile(st,lang);langs[lang]=dict(ready=True)
                except ValueError as e:langs[lang]=dict(ready=False,reason=str(e))
            ready=bool(langs) and all(v['ready'] for v in langs.values())
            # The config names a default model before the user picks one: report it only once it is set up.
            c=st['config'];chosen=c.get('profileReady') or (c.get('setupReady') and c.get('setupModel')==c.get('engine'))
            report=dict(studio=endpoint,running=True,ready=ready,engine=c.get('engine') if chosen else None,
                languages=langs,next='Narrate with this command line; the user need not open the studio')
            if not chosen:report['recommended']=(st.get('plan') or {}).get('recommended')
            if show and not ready and opened is None:opened=open_studio(endpoint)
            if opened is not None:report['opened']=opened
            if not ready:report['next']=(f'Tell the user the studio is open in their browser at {endpoint} and what to finish there' if opened
                else f'Give the user the studio link {endpoint} to open in their own browser')+', then check again with --wait; do not operate the page yourself'
        left=deadline-time.monotonic()
        if report['ready'] or left<=0:return report
        time.sleep(min(poll,left))

def is_studio(pid):
    """Whether this process runs this skill's studio.py, so stop never signals another program that answers on the port.
    Windows has no ps to check the command line, so stop refuses there."""
    if os.name=='nt':return False
    try:out=subprocess.run(['ps','-ww','-p',str(pid),'-o','command='],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=10).stdout
    except(OSError,subprocess.TimeoutExpired):return False
    return str(STUDIO) in out

def stop(endpoint=ENDPOINT,timeout=10):
    """Stop the studio server that --start and narration leave running in the background. Refuses during model setup."""
    local(endpoint)
    try:st=fetch_status(endpoint)
    except OSError:return dict(studio=endpoint,running=False,stopped=False,next='The studio is not running')
    if(st.get('setup')or{}).get('state')in('checking','downloading','verifying'):
        raise ValueError('Model setup is running in the studio; stop it after setup finishes')
    pid=st.get('pid')
    if not isinstance(pid,int) or isinstance(pid,bool) or pid<=0 or not is_studio(pid):
        raise ValueError(f'The server at {endpoint} is not a voice studio this command can stop; stop it where it was started')
    os.kill(pid,signal.SIGTERM);deadline=time.monotonic()+timeout
    while True:
        try:fetch_status(endpoint)
        except OSError:return dict(studio=endpoint,running=False,stopped=True,next='Stopped; status --start or narration starts it again')
        if time.monotonic()>=deadline:raise RuntimeError(f'The studio (pid {pid}) did not stop within {timeout:g} s')
        time.sleep(.2)

def generate(text_path,output,language='en',endpoint=ENDPOINT):
    url=urllib.parse.urlparse(endpoint)
    if url.scheme!='http' or url.hostname not in ('localhost','127.0.0.1') or url.username or url.password:
        raise ValueError('Use the selected local studio; this client has no cloud endpoint')
    if output.exists():raise ValueError('Narration output exists')
    text=text_path.read_text(encoding='utf-8').strip()
    if not 1<=len(text)<=2400:raise ValueError('Keep each narration request within 2400 characters')
    status=start_server(endpoint)
    c=status['config'];engine=c.get('engine');models=status.get('engines',{})
    if engine not in models or c.get('voice')!='mine' or not c.get('profileReady'):
        raise ValueError('Complete language/model setup and accept your voice auditions in the studio first')
    if language not in c.get('languages',[]) or language not in models[engine]['langs']:
        raise ValueError('Add this language to your voice profile first; no language substitution')
    reference=status.get('effectiveReferences',{}).get(language) or c.get('references',{}).get(language) or language
    saved=status.get('mine',{}).get(reference);accepted=c.get('accepted',{}).get(language,{})
    grant=c.get('sharedEnglishApproval',{});english=c.get('accepted',{}).get('en',{});approval_scope='language'
    if reference=='en' and grant.get('mode')=='english-reference' and grant.get('engine')==engine and saved and grant.get('referenceSha256')==saved['sha256'] and grant.get('acceptedEnglishId') and grant.get('acceptedEnglishId')==english.get('id'):
        accepted=english;approval_scope='english-reference'
    if not saved or accepted.get('engine')!=engine or accepted.get('referenceSha256')!=saved['sha256']:
        raise ValueError('The model or reference changed. Accept a fresh audition first')
    output.parent.mkdir(parents=True,exist_ok=True)
    req=urllib.request.Request(endpoint+'/v1/audio/speech',data=json.dumps({'input':text,'language':language,'engine':engine,'mine':True}).encode(),headers={'Content-Type':'application/json'})
    with tempfile.TemporaryDirectory(prefix='local-voice-',dir=output.parent)as td:
        work=Path(td)
        with urllib.request.urlopen(req,timeout=600)as response:
            if response.headers.get('X-Voice')!=f'{engine}; cloned=True; lang={language}':
                raise ValueError('Studio did not confirm the selected model, language and recorded voice')
            reference_hash=response.headers.get('X-Voice-Reference-SHA256')
            if reference_hash!=saved['sha256'] or response.headers.get('X-Voice-Reference-Language')!=reference:
                raise ValueError('The reference changed during generation. Review it in the studio first')
            (work/'speech.mp3').write_bytes(response.read())
        command(['ffmpeg','-v','error','-i',work/'speech.mp3','-ar','48000','-ac','1',work/'speech.wav'])
        if audio_peak(work/'speech.wav') < -55:raise ValueError('Local voice output is silent')
        model_info=next(m for m in status['plan']['models'] if m['id']==engine)
        receipt=dict(approvalScope=approval_scope,provider='local-voice-studio',engine=engine,model=model_info['repo'],revision=model_info['revision'],voice='saved-user-recording',referenceLanguage=reference,referenceSha256=reference_hash,language=language,cloned=True,fallback=False,audioSha256=digest(work/'speech.wav'),textSha256=digest(text_path),review='pending')
        (work/'identity.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        os.link(work/'identity.json',output.with_suffix('.identity.json'))
        try:os.link(work/'speech.wav',output)
        except Exception:
            output.with_suffix('.identity.json').unlink();raise
    return receipt

if __name__=='__main__':
    if sys.argv[1:2]==['status']:
        p=argparse.ArgumentParser(prog='studio_speech.py status',description='Report whether the voice profile is ready.')
        p.add_argument('--language',action='append',help='repeat for each language; default: the profile\'s languages')
        p.add_argument('--wait',type=float,default=0,help='poll up to this many seconds for the user to finish')
        p.add_argument('--start',action='store_true',help='start the studio server in the background if it is not running')
        p.add_argument('--open',action='store_true',help="open the studio in the user's default browser when the profile is not ready")
        p.add_argument('--endpoint',default=ENDPOINT)
        a=p.parse_args(sys.argv[2:]);r=status(a.language,a.endpoint,a.wait,start=a.start,show=a.open)
        print(json.dumps(r,indent=2));sys.exit(0 if r['ready'] else 1 if r['running'] else 3)
    if sys.argv[1:2]==['stop']:
        p=argparse.ArgumentParser(prog='studio_speech.py stop',description='Stop the background studio server.')
        p.add_argument('--endpoint',default=ENDPOINT);a=p.parse_args(sys.argv[2:])
        try:print(json.dumps(stop(a.endpoint),indent=2));sys.exit(0)
        except(ValueError,RuntimeError)as e:print(json.dumps(dict(studio=a.endpoint,stopped=False,next=str(e)),indent=2));sys.exit(1)
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter);p.add_argument('text',type=Path);p.add_argument('output',type=Path);p.add_argument('--language',default='en');p.add_argument('--endpoint',default=ENDPOINT)
    a=p.parse_args();print(json.dumps(generate(a.text,a.output,a.language,a.endpoint),indent=2))
