"""Local language-first voice setup, recording and auditions. No cloud speech."""
import gc,hashlib,json,os,platform,shutil,subprocess,sys,tempfile,threading,time,uuid
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs,unquote
from catalog import LANGUAGES,MODELS,recommend,validate_languages,model_path,installed
from engines import prepare,speak
HERE=Path(__file__).parent
DATA=Path(os.environ.get('NARRATE_VIDEO_DATA',os.environ.get('WALKTHROUGH_VIDEO_DATA',Path.home()/'.local/share/narrate-video')))
os.environ.setdefault('HF_HUB_CACHE',str(DATA/'model-hub'))
VOICES=DATA/'voices/me';OUT=DATA/'out/studio';CONFIG=DATA/'config.json';PORT=int(os.environ.get('VOICE_STUDIO_PORT','8765'))
LOCK=threading.RLock();JOB_LOCK=threading.Lock();JOB={'state':'idle'}

def now():return datetime.now(timezone.utc).isoformat()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def atomic_json(path,data):
 path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,path)
def config():
 try:c=json.loads(CONFIG.read_text(encoding='utf-8'))
 except(OSError,ValueError):c={}
 saved=[x.stem for x in VOICES.glob('*.wav')if x.stem in LANGUAGES]if VOICES.exists()else[]
 return {'engine':'omnivoice','languages':saved or ['en'],'preference':'reuse','references':{},'accepted':{},**c,'provider':'local','voice':'mine'}

def save_config(values):
 with LOCK:
  c=config();c.update(values);atomic_json(CONFIG,c);return c

def references():
 result={}
 with LOCK:
  for code in LANGUAGES:
   p=VOICES/f'{code}.wav';t=VOICES/f'{code}.txt'
   if p.is_file():
    try:secs=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(p)],stderr=subprocess.DEVNULL))
    except Exception:secs=0
    result[code]=dict(language=code,name=LANGUAGES[code]['name'],url=f'/me/{code}.wav?v={p.stat().st_mtime_ns}',text=t.read_text(encoding='utf-8')if t.exists()else'',seconds=round(secs,1),sha256=sha(p))
 return result

def state():
 c=config();plan=recommend(c['languages'],DATA,c.get('preference','reuse'),c.get('engine','omnivoice'))
 with LOCK:job=dict(JOB)
 auditions={}
 for path in sorted(OUT.glob('*.json'),key=lambda p:p.stat().st_mtime):
  try:
   a=json.loads(path.read_text(encoding='utf-8'))
   if a.get('id')and a.get('language')in c['languages']and a.get('engine')==c['engine']:auditions[a['language']]=a
  except (OSError,ValueError):pass
 return dict(version=2,config=c,languages=list(LANGUAGES.values()),mine=references(),plan=plan,setup=job,auditions=auditions,engines={k:dict(label=v['label'],repo=v['repo'],langs=v['languages'],clone=True)for k,v in MODELS.items()})

def set_job(**values):
 with LOCK:JOB.update(values);atomic_json(DATA/'setup-job.json',JOB)

def run_setup(name,languages,jobid):
 try:
  p=model_path(name,DATA)
  if not installed(name,DATA):
   if shutil.disk_usage(DATA).free<MODELS[name]['bytes']*1.3+1024**3:raise RuntimeError('Not enough free storage for this model.')
   p.mkdir(parents=True,exist_ok=True);set_job(state='downloading',message='Downloading the selected model',downloadedBytes=0,totalBytes=MODELS[name]['bytes'])
   env={**os.environ,'HF_HUB_OFFLINE':'0','TRANSFORMERS_OFFLINE':'0'}
   with (DATA/f'setup-{jobid}.log').open('w')as log:
    child=subprocess.Popen([sys.executable,str(HERE/'setup_worker.py'),name,str(p)],env=env,stdout=log,stderr=subprocess.STDOUT)
    start=time.monotonic()
    while child.poll()is None:
     seen=set();size=0
     for base in [p]+[DATA/'model-hub'/('models--'+d['repo'].replace('/','--'))for d in MODELS[name].get('dependencies',[])]:
      for f in base.rglob('*'):
       if f.is_file():
        st=f.stat();key=(st.st_dev,st.st_ino)
        if key not in seen:size+=st.st_size;seen.add(key)
     set_job(downloadedBytes=min(size,MODELS[name]['bytes']))
     if time.monotonic()-start>1800:child.terminate();child.wait();raise RuntimeError('Download timed out. Retry to resume it.')
     time.sleep(1)
    if child.returncode:raise RuntimeError('Model download failed. Check the local setup log and retry; no model was substituted.')
  set_job(state='verifying',message='Loading the model and checking its runtime')
  prepare(name,DATA)
  save_config(dict(engine=name,languages=languages,setupReady=True,setupModel=name,profileReady=False))
  set_job(state='ready',message='Model ready on this computer',completedAt=now(),downloadedBytes=MODELS[name]['bytes'],totalBytes=MODELS[name]['bytes'])
 except Exception as e:set_job(state='failed',message=str(e).replace(str(DATA),'private storage')[:350])
 finally:JOB_LOCK.release()

def start_setup(req):
 codes=validate_languages(req.get('languages'));name=req.get('model');pref=req.get('preference','reuse');recommend(codes,DATA,pref,config()['engine'])
 if name not in MODELS or any(c not in MODELS[name]['languages']for c in codes):raise ValueError('Choose a model that covers every selected language.')
 if platform.system()!='Darwin' or platform.machine()!='arm64':raise ValueError('These local MLX adapters need Apple Silicon. No cloud fallback is configured.')
 if not JOB_LOCK.acquire(blocking=False):raise ValueError('A model setup is already running. Let it finish before starting another.')
 save_config(dict(languages=codes,preference=pref,profileReady=False))
 jobid=uuid.uuid4().hex
 with LOCK:JOB.clear();JOB.update(id=jobid,model=name,languages=codes,state='checking',message='Checking the local installation',startedAt=now())
 threading.Thread(target=run_setup,args=(name,codes,jobid),daemon=True).start();return dict(JOB)

def selected_reference(lang,req,c):
 code=req.get('reference')or c.get('references',{}).get(lang)or(lang if(VOICES/f'{lang}.wav').exists()else None)
 if code not in LANGUAGES or not(VOICES/f'{code}.wav').is_file():raise ValueError('Record this language or explicitly choose a saved recording first.')
 return code

def generate(req):
 c=config();name=req.get('engine')or c['engine'];lang=req.get('lang')or req.get('language')or c['languages'][0];text=req.get('text',req.get('input','')).strip()
 if req.get('mine')is False:raise ValueError('This flow uses your recorded voice. A preset is not substituted.')
 if name not in MODELS or lang not in MODELS[name]['languages']:raise ValueError('The selected model does not support this language.')
 if lang not in c['languages']:raise ValueError('Add this narration language to your setup first.')
 if not c.get('setupReady')or c.get('setupModel')!=name:raise ValueError('Complete setup for the selected model first.')
 if not 1<=len(text)<=2400:raise ValueError('Enter between 1 and 2400 characters.')
 with tempfile.TemporaryDirectory(prefix='voice-request-',dir=OUT)as td:
  with LOCK:
   code=selected_reference(lang,req,c);source=VOICES/f'{code}.wav';ref=Path(td)/'reference.wav';shutil.copyfile(source,ref);reftext=(VOICES/f'{code}.txt').read_text(encoding='utf-8')
  token=uuid.uuid4().hex;out=OUT/f'{token}-{name}-{lang}.wav';result=speak(name,lang,text,str(out),str(ref),reftext,DATA)
  result.update(id=token,url=f'/out/{out.name}',file=out.name,from_recording=code,referenceSha256=sha(ref),text=text,createdAt=now())
  atomic_json(out.with_suffix('.json'),result)
  return result

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def trusted(self):
  own={f'localhost:{PORT}',f'127.0.0.1:{PORT}'};origin=self.headers.get('Origin')
  return self.headers.get('Host')in own and(origin is None or origin in {f'http://{h}'for h in own})and self.headers.get('Sec-Fetch-Site')in(None,'same-origin','none')
 def send(self,status,body,typ='application/json'):
  self.send_response(status);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
 def json(self,obj,status=200):self.send(status,json.dumps(obj,ensure_ascii=False).encode())
 def file(self,path):
  if not path.is_file():return self.send(404,b'not found','text/plain')
  self.send(200,path.read_bytes(),{'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.wav':'audio/wav','.mp3':'audio/mpeg','.json':'application/json'}.get(path.suffix,'application/octet-stream'))
 def do_GET(self):
  path=unquote(urlparse(self.path).path)
  if path in('/','/index.html')and self.headers.get('Host')in{f'localhost:{PORT}',f'127.0.0.1:{PORT}'}:return self.file(HERE/'studio.html')
  if not self.trusted():return self.send(403,b'local studio only','text/plain')
  if path=='/studio.css':return self.file(HERE/'studio.css')
  if path=='/api/status':return self.json(state())
  if path.startswith('/me/')and Path(path).name[:-4]in LANGUAGES and path.endswith('.wav'):return self.file(VOICES/Path(path).name)
  if path.startswith('/out/')and Path(path).suffix in('.wav','.mp3'):return self.file(OUT/Path(path).name)
  return self.send(404,b'not found','text/plain')
 def do_POST(self):
  if not self.trusted():return self.send(403,b'local studio only','text/plain')
  size=int(self.headers.get('Content-Length','0'))
  if not 0<size<=20*1024*1024:return self.json({'error':'Request is empty or too large.'},400)
  body=self.rfile.read(size);url=urlparse(self.path)
  try:
   if url.path=='/api/reference':
    q={k:v[0]for k,v in parse_qs(url.query).items()};lang=q.get('lang');text=q.get('text','').strip()
    if lang not in LANGUAGES or not text or len(text)>2400:raise ValueError('Choose a language and include the text you read.')
    with tempfile.TemporaryDirectory(prefix='recording-',dir=OUT)as td:
     source=Path(td)/'upload';source.write_bytes(body);wav=Path(td)/'voice.wav'
     subprocess.run(['ffmpeg','-v','error','-i',str(source),'-ac','1','-ar','24000','-af','loudnorm=I=-18:TP=-2',str(wav)],check=True,capture_output=True)
     seconds=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(wav)]))
     if not 3<=seconds<=35:raise ValueError('Record at least 3 seconds and no more than 35 seconds. Aim for 5–10 seconds.')
     with LOCK:
      target=VOICES/f'{lang}.wav'
      if target.exists():
       history=DATA/'voice-history'/str(time.time_ns());history.mkdir(parents=True);shutil.copyfile(target,history/target.name)
       old=VOICES/f'{lang}.txt'
       if old.exists():shutil.copyfile(old,history/old.name)
      pending=target.with_name(lang+'.'+uuid.uuid4().hex+'.wav');shutil.copyfile(wav,pending);(VOICES/f'{lang}.txt').write_text(text,encoding='utf-8');os.replace(pending,target)
      c=config();refs=c.get('references',{});refs[lang]=lang;save_config(dict(references=refs,profileReady=False))
    return self.json(dict(ok=True,seconds=round(seconds,1),reference=references()[lang]))
   req=json.loads(body)
   if url.path=='/api/preferences':
    codes=validate_languages(req.get('languages'));pref=req.get('preference','reuse');recommend(codes,DATA,pref);c=config();same=c.get('languages')==codes
    save_config(dict(languages=codes,preference=pref,profileReady=c.get('profileReady',False)if same else False));return self.json(state())
   if url.path=='/api/recommend':return self.json(recommend(req.get('languages'),DATA,req.get('preference','reuse'),config()['engine']))
   if url.path=='/api/setup':return self.json(start_setup(req))
   if url.path=='/api/reference-choice':
    lang=req.get('language');ref=req.get('reference')
    if lang not in config()['languages']or ref not in references():raise ValueError('Choose an existing saved recording.')
    c=config();refs=c.get('references',{});refs[lang]=ref;save_config(dict(references=refs,profileReady=False));return self.json(state())
   if url.path in('/api/generate','/v1/audio/speech'):
    result=generate(req)
    if url.path=='/api/generate':return self.json(result)
    wav=OUT/result['file'];mp3=wav.with_suffix('.mp3');subprocess.run(['ffmpeg','-v','error','-i',str(wav),'-ar','48000','-b:a','192k',str(mp3)],check=True)
    data=mp3.read_bytes();self.send_response(200);self.send_header('Content-Type','audio/mpeg');self.send_header('Content-Length',str(len(data)));self.send_header('X-Voice',f"{result['engine']}; cloned=True; lang={result['language']}");self.send_header('X-Voice-Reference-SHA256',result['referenceSha256']);self.send_header('X-Voice-Reference-Language',result['from_recording']);self.end_headers();self.wfile.write(data);return
   if url.path=='/api/accept':
    token=req.get('id');files=list(OUT.glob(f'{token}-*.json'))if isinstance(token,str)and len(token)==32 and all(c in'0123456789abcdef'for c in token)else[]
    if len(files)!=1:raise ValueError('Choose a generated audition first.')
    r=json.loads(files[0].read_text(encoding='utf-8'));c=config();lang=r['language'];ref=selected_reference(lang,{},c)
    if r['engine']!=c['engine']or r['referenceSha256']!=sha(VOICES/f'{ref}.wav'):raise ValueError('The model or recording changed. Generate a fresh audition.')
    accepted=c.get('accepted',{});accepted[lang]=dict(id=token,engine=r['engine'],referenceSha256=r['referenceSha256'],acceptedAt=now());save_config(dict(accepted=accepted));return self.json(state())
   if url.path=='/api/finish':
    c=config()
    for lang in c['languages']:
     a=c.get('accepted',{}).get(lang);ref=selected_reference(lang,{},c)
     if not a or a['engine']!=c['engine']or a['referenceSha256']!=sha(VOICES/f'{ref}.wav'):raise ValueError('Listen to and accept an audition in every selected language first.')
    save_config(dict(profileReady=True));return self.json(state())
   return self.send(404,b'not found','text/plain')
  except Exception as e:return self.json({'error':str(e).replace(str(DATA),'private storage')[:500]},400)

if __name__=='__main__':
 for p in(DATA,VOICES,OUT):p.mkdir(parents=True,exist_ok=True)
 print(f'Voice setup at http://127.0.0.1:{PORT}',flush=True)
 ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
