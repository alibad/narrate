"""Pronunciation examples use the selected local model. No OS/cloud fallback."""
import tempfile
import threading
import uuid
import wave
from pathlib import Path
from catalog import variant,installed,runtime
from engines import speak_example

LOCK=threading.Lock()

def capability(language,config,data):
 name=config.get('engine');code=language['code']
 base=dict(available=False,provider='local',engine=name,voice=None,
           locale=language.get('omni_id',code),cloned=False,model=None,revision=None)
 if name!='omnivoice' or runtime()!='mlx':
  return {**base,'reason':'The selected model has no independent language-example adapter. Use its own-voice guide or choose a supported model; no other engine is substituted.'}
 v=variant(name);base.update(model=v['repo'],revision=v['revision'],voice=v['label']+' language example')
 if not config.get('setupReady')or config.get('setupModel')!=name or not installed(name,data):
  return {**base,'reason':'Complete setup for the selected model first.'}
 if code not in v['languages']:
  return {**base,'reason':'The selected model does not support this language.'}
 return {**base,'available':True,'reason':None,'label':v['label']}

def capabilities(languages,config,data):
 return {code:capability(languages[code],config,data) for code in config['languages'] if code in languages}

def synthesize(request,languages,config,data,destination):
 if not isinstance(request,dict):raise ValueError('Choose a selected language and enter its passage.')
 code,text=request.get('lang'),request.get('text')
 if not isinstance(code,str)or code not in config['languages']or code not in languages:
  raise ValueError('Choose a selected language for the pronunciation example.')
 if not isinstance(text,str)or not 1<=len(text.strip())<=600 or '\0'in text:
  raise ValueError('Keep the passage between 1 and 600 characters.')
 name=config['engine']
 if request.get('engine',name)!=name:raise ValueError('The selected model changed. Refresh the studio before generating the example.')
 choice=capability(languages[code],config,data)
 if not choice['available']:raise ValueError(choice['reason'])
 if not LOCK.acquire(blocking=False):raise ValueError('Another pronunciation example is being prepared. Let it finish first.')
 try:
  destination=Path(destination);destination.mkdir(parents=True,exist_ok=True,mode=0o700)
  with tempfile.TemporaryDirectory(prefix='model-example-',dir=destination)as directory:
   wav=Path(directory)/'example.wav'
   result=speak_example(name,code,text.strip(),str(wav),data)
   if result.get('engine')!=name or result.get('model')!=choice['model']or result.get('revision')!=choice['revision']or result.get('cloned')is not False or result.get('fallback')is not False:
    raise ValueError('The pronunciation response did not match the selected model.')
   with wave.open(str(wav),'rb')as audio:
    seconds=audio.getnframes()/audio.getframerate()
    if audio.getnchannels()!=1 or audio.getsampwidth()!=2 or not .05<=seconds<=180:
     raise ValueError('The selected model did not produce usable pronunciation audio.')
   filename=f'{uuid.uuid4().hex}-{code}.wav';target=destination/filename
   with target.open('xb')as output:output.write(wav.read_bytes())
   target.chmod(0o600)
  return {**result,'url':f'/pronunciation/{filename}','seconds':round(seconds,2),
          'voice':choice['voice'],'locale':choice['locale'],'synthetic':True,'audition':False}
 finally:LOCK.release()
