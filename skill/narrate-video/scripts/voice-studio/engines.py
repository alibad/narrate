"""Explicit local voice-cloning engines. One loaded model and no provider fallback."""
import gc,re,threading,time,wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from catalog import MODELS,LANGUAGES,model_path,installed,runtime,variant
_lock=threading.RLock();_loaded={}
# MLX streams are thread-bound: setup and inference share one persistent worker.
_worker=ThreadPoolExecutor(max_workers=1,thread_name_prefix="voice-inference")

def _load(name,data):
 if name not in MODELS:raise ValueError('Choose a supported model.')
 if not installed(name,data):raise ValueError('Set up this model before generating speech.')
 if name not in _loaded and runtime()=='cuda':
  from chatterbox.mtl_tts import ChatterboxMultilingualTTS
  import torch
  _loaded.clear();gc.collect();torch.cuda.empty_cache()
  _loaded[name]=ChatterboxMultilingualTTS.from_local(model_path(name,data),'cuda')
 if name not in _loaded:
  from mlx_audio.tts.utils import load_model
  _loaded.clear();gc.collect()
  import mlx.core as mx
  mx.clear_cache()
  model=load_model(str(model_path(name,data)))
  if name=='omnivoice' and (getattr(model,'audio_tokenizer',None)is None or getattr(model,'text_tokenizer',None)is None):raise RuntimeError('OmniVoice tokenizers did not load.')
  if name=='qwen3-base' and getattr(getattr(model,'config',None),'tts_model_type',None) not in ('base',None):raise RuntimeError('Voice cloning requires the Qwen Base checkpoint.')
  _loaded[name]=model
 return _loaded[name]

def prepare(name,data):
 return _worker.submit(_prepare,name,data).result()

def _prepare(name,data):
 with _lock:
  model=_load(name,data)
  return dict(model=name,loaded=True)

def speak(name,lang,text,out,ref_audio,ref_text,data):
 return _worker.submit(_speak,name,lang,text,out,ref_audio,ref_text,data).result()

def _sentences(text,limit=300):
 # PyTorch Chatterbox drifts on long inputs: speak sentence-sized pieces and join them.
 parts,current=[],''
 for piece in re.split(r'(?<=[.!?。！？؟])\s+',text.strip()):
  if current and len(current)+1+len(piece)>limit:parts.append(current);current=piece
  else:current=(current+' '+piece).strip()
 return parts+[current] if current else parts

def _write_wav(path,audio,rate):
 import numpy as np
 with wave.open(str(path),'wb')as w:
  w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes((np.clip(audio,-1,1)*32767).astype('<i2').tobytes())

def _speak(name,lang,text,out,ref_audio,ref_text,data):
 if name not in MODELS or lang not in MODELS[name]['languages']:raise ValueError('The selected model does not support this language. Choose another model; none is substituted.')
 if not ref_audio or not Path(ref_audio).is_file():raise ValueError('Save or choose a voice recording first.')
 if not ref_text or not ref_text.strip():raise ValueError('The recording needs the text that was read.')
 import numpy as np
 with _lock:
  model=_load(name,data);start=time.time();cuda=runtime()=='cuda'
  if cuda:
   parts=[model.generate(piece,language_id=lang,audio_prompt_path=ref_audio).squeeze(0).cpu().numpy().reshape(-1) for piece in _sentences(text)];rate=model.sr
  else:
   kw=dict(ref_audio=ref_audio,verbose=False)
   if name=='omnivoice':kw.update(language=LANGUAGES[lang]['omni_id'],ref_text=ref_text,ref_audio_max_duration_s=35.0)
   elif name=='chatterbox':kw.update(lang_code=lang)
   else:kw.update(language={'zh':'Chinese','en':'English','ja':'Japanese','ko':'Korean','de':'German','fr':'French','ru':'Russian','pt':'Portuguese','es':'Spanish','it':'Italian'}[lang],ref_text=ref_text)
   parts=[];rate=None
   for part in model.generate(text=text,**kw):parts.append(np.asarray(part.audio).reshape(-1));rate=part.sample_rate
  if not parts:raise RuntimeError('The selected model returned no speech.')
  audio=np.concatenate(parts)
  if not np.isfinite(audio).all()or np.max(np.abs(audio))<.001:raise RuntimeError('The selected model returned invalid or silent speech.')
  if cuda:_write_wav(out,audio,rate)
  else:
   from mlx_audio.audio_io import write as audio_write
   audio_write(out,audio,rate)
  v=variant(name)
  return dict(engine=name,label=v['label'],model=v['repo'],revision=v['revision'],seconds=round(len(audio)/rate,2),took=round(time.time()-start,2),cloned=True,provider='local',fallback=False,language=lang)
