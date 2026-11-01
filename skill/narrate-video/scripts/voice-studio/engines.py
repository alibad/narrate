"""Explicit local voice-cloning engines. One loaded model and no provider fallback."""
import gc,threading,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from catalog import MODELS,LANGUAGES,model_path,installed
_lock=threading.RLock();_loaded={}
# MLX streams are thread-bound: setup and inference share one persistent worker.
_worker=ThreadPoolExecutor(max_workers=1,thread_name_prefix="voice-inference")

def _load(name,data):
 if name not in MODELS:raise ValueError('Choose a supported model.')
 if not installed(name,data):raise ValueError('Set up this model before generating speech.')
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

def _speak(name,lang,text,out,ref_audio,ref_text,data):
 if name not in MODELS or lang not in MODELS[name]['languages']:raise ValueError('The selected model does not support this language. Choose another model; none is substituted.')
 if not ref_audio or not Path(ref_audio).is_file():raise ValueError('Save or choose a voice recording first.')
 if not ref_text or not ref_text.strip():raise ValueError('The recording needs the text that was read.')
 import numpy as np
 from mlx_audio.audio_io import write as audio_write
 with _lock:
  model=_load(name,data);start=time.time()
  kw=dict(ref_audio=ref_audio,verbose=False)
  if name=='omnivoice':kw.update(language=LANGUAGES[lang]['omni_id'],ref_text=ref_text,ref_audio_max_duration_s=35.0)
  elif name=='chatterbox':kw.update(lang_code=lang)
  else:kw.update(language={'zh':'Chinese','en':'English','ja':'Japanese','ko':'Korean','de':'German','fr':'French','ru':'Russian','pt':'Portuguese','es':'Spanish','it':'Italian'}[lang],ref_text=ref_text)
  parts=[];rate=None
  for part in model.generate(text=text,**kw):parts.append(np.asarray(part.audio).reshape(-1));rate=part.sample_rate
  if not parts:raise RuntimeError('The selected model returned no speech.')
  audio=np.concatenate(parts)
  if not np.isfinite(audio).all()or np.max(np.abs(audio))<.001:raise RuntimeError('The selected model returned invalid or silent speech.')
  audio_write(out,audio,rate)
  return dict(engine=name,label=MODELS[name]['label'],model=MODELS[name]['repo'],revision=MODELS[name]['revision'],seconds=round(len(audio)/rate,2),took=round(time.time()-start,2),cloned=True,provider='local',fallback=False,language=lang)
