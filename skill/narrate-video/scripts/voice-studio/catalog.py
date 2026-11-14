"""Language eligibility and explicit, source-backed local model recommendations."""
import functools,importlib.util,json,os,platform
from pathlib import Path
HERE=Path(__file__).parent
LANGUAGES={x['code']:x for x in json.loads((HERE/'languages.json').read_text(encoding='utf-8'))}
RUNTIMES={'mlx':'Apple Silicon · MLX','cuda':'NVIDIA GPU · CUDA'}
MODELS={
 'omnivoice':dict(label='OmniVoice',tagline='One voice across many languages',repo='mlx-community/OmniVoice-bf16',revision='8fb0b754cad788aaefec690cd55c207e8a628f85',bytes=1639492513,languages=list(LANGUAGES),cloning=True,source='https://github.com/k2-fsa/OmniVoice',details='Broad language coverage, including the Arabic varieties offered here. Already used locally with voice references. The weights are licensed for non-commercial use (CC BY-NC 4.0); check that before publishing. Audition each selected language.',verification='Reference-conditioned generation tested locally',
  # The upstream PyTorch checkpoint, loaded by the omnivoice package (it needs transformers 5.3 or newer).
  cuda=dict(tagline='One voice across many languages, on NVIDIA GPUs',repo='k2-fsa/OmniVoice',revision='c5fdb5ccb189668d56333f77ba2629f4cd7535f4',bytes=3267452573,files=['config.json','model.safetensors','tokenizer.json','tokenizer_config.json','chat_template.jinja','audio_tokenizer/config.json','audio_tokenizer/model.safetensors','audio_tokenizer/preprocessor_config.json','audio_tokenizer/LICENSE'],module='omnivoice',package='omnivoice==0.2.1',source='https://huggingface.co/k2-fsa/OmniVoice',details='The upstream PyTorch checkpoint with the same language coverage, including the Arabic varieties offered here. Runs through the omnivoice package on CUDA and uses the text you read with your recording. The weights are licensed for non-commercial use (CC BY-NC 4.0); its audio tokenizer has the Boson Higgs Audio 2 community licence. Check both before publishing. Audition each selected language.',verification='English reference-conditioned speech generated locally on an NVIDIA GPU; listening approval is yours')),
 'chatterbox':dict(label='Chatterbox Multilingual',tagline='A smaller multilingual alternative',repo='mlx-community/chatterbox-8bit',revision='9617d61b596a03d1bed766a28c341680e993a1b9',bytes=1427734984,dependencies=[dict(repo='mlx-community/S3TokenizerV2',revision='e0c9886f0e1c35ae85b1f27277416fb19fc72bec',bytes=494869110)],languages='ar da de el en es fi fr he hi it ja ko ms nl no pl pt ru sv sw tr zh'.split(),cloning=True,source='https://huggingface.co/mlx-community/chatterbox-8bit',details='23 declared languages and reference-voice conditioning. Includes its required speech tokenizer in the setup size. Compare an audition before choosing.',verification='English and Arabic reference-conditioned speech generated locally; listening approval is yours',
  # The upstream PyTorch checkpoint; the files are the ones chatterbox-tts 0.1.x loads for the multilingual model.
  cuda=dict(tagline='Multilingual cloning on NVIDIA GPUs',repo='ResembleAI/chatterbox',revision='5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18',bytes=3208951748,files=['ve.pt','t3_mtl23ls_v2.safetensors','s3gen.pt','grapheme_mtl_merged_expanded_v1.json','conds.pt','Cangjie5_TC.json'],module='chatterbox',package='chatterbox-tts==0.1.7',source='https://huggingface.co/ResembleAI/chatterbox',details='The upstream PyTorch checkpoint with 23 declared languages and reference-voice conditioning. Runs through the chatterbox-tts package on CUDA. Compare an audition before choosing.',verification='English and Arabic reference-conditioned speech generated locally on an NVIDIA GPU; listening approval is yours')),
 'qwen3-base':dict(label='Qwen3-TTS Base',tagline='Voice cloning for ten languages',repo='mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16',revision='a6eb4f68e4b056f1215157bb696209bc82a6db48',bytes=4544212739,languages='zh en ja ko de fr ru pt es it'.split(),cloning=True,source='https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base',details='The Base checkpoint supports cloning with reference audio and its transcript. Does not support Arabic. This is not the preset-only CustomVoice checkpoint.',verification='English reference-conditioned speech generated locally; listening approval is yours')}

@functools.cache
def _cuda():
 try:
  import torch
  return bool(torch.cuda.is_available())
 except Exception:return False

def runtime():
 """mlx on Apple Silicon, cuda where PyTorch sees an NVIDIA GPU, else none. NARRATE_VIDEO_RUNTIME overrides detection."""
 forced=os.environ.get('NARRATE_VIDEO_RUNTIME')
 if forced:return forced if forced in RUNTIMES else 'none'
 if platform.system()=='Darwin' and platform.machine()=='arm64':return 'mlx'
 return 'cuda' if _cuda() else 'none'

def variant(name):
 """The build of a model this computer runs. A model without a CUDA build is unavailable on NVIDIA; none is substituted."""
 m={k:v for k,v in MODELS[name].items() if k!='cuda'}
 if runtime()!='cuda':return {**m,'available':True}
 return {**m,**MODELS[name]['cuda'],'available':True} if 'cuda' in MODELS[name] else {**m,'available':False}

def _importable(module):return importlib.util.find_spec(module)is not None

def missing_package(name):
 """The package a CUDA build needs when the Python running the studio cannot import it, else None.
 Builds can need conflicting versions of shared libraries, so each may run from its own environment."""
 c=MODELS[name].get('cuda')
 if runtime()!='cuda' or not c:return None
 return None if _importable(c['module']) else c['package']

def hub(data):
 return Path(os.environ.get('HF_HUB_CACHE') or data/'model-hub')

def validate_languages(codes):
 if not isinstance(codes,list) or not 1<=len(codes)<=12 or any(not isinstance(c,str)or c not in LANGUAGES for c in codes):raise ValueError('Choose 1 to 12 languages from the list.')
 return list(dict.fromkeys(codes))

def model_path(name,data):
 if name not in MODELS:raise ValueError('Unknown model.')
 if runtime()=='cuda' and 'cuda' in MODELS[name]:
  c=MODELS[name]['cuda'];return hub(data)/('models--'+c['repo'].replace('/','--'))/'snapshots'/c['revision']
 # WALKTHROUGH_VIDEO_* are the names from before the rename; they keep earlier setups working.
 if name=='omnivoice' and (os.environ.get('NARRATE_VIDEO_MODEL_DIR')or os.environ.get('WALKTHROUGH_VIDEO_MODEL_DIR')):return Path(os.environ.get('NARRATE_VIDEO_MODEL_DIR')or os.environ['WALKTHROUGH_VIDEO_MODEL_DIR']).resolve()
 return data/'models'/name

def download_dirs(name,data):
 """Folders that grow while the selected model downloads, for the setup progress bar."""
 if runtime()=='cuda':return [hub(data)/('models--'+MODELS[name]['cuda']['repo'].replace('/','--'))]
 return [model_path(name,data)]+[data/'model-hub'/('models--'+d['repo'].replace('/','--'))for d in MODELS[name].get('dependencies',[])]

def installed(name,data):
 p=model_path(name,data)
 if runtime()=='cuda':return 'cuda' in MODELS[name] and all((p/f).is_file() for f in MODELS[name]['cuda']['files'])
 core=(p/'config.json').is_file() and any(p.glob('*.safetensors')) and (name!='omnivoice' or (p/'audio_tokenizer/model.safetensors').is_file())
 if name=='qwen3-base':core=core and(p/'speech_tokenizer/model.safetensors').is_file()and(p/'speech_tokenizer/config.json').is_file()
 if name=='chatterbox':
  dep=MODELS[name]['dependencies'][0];cache=data/'model-hub'/('models--'+dep['repo'].replace('/','--'));core=core and(cache/'snapshots'/dep['revision']/'model.safetensors').is_file()and(cache/'refs/main').is_file()
 return bool(core)

def recommend(codes,data,preference='reuse',current='omnivoice'):
 codes=validate_languages(codes)
 if preference not in ('reuse','compact'):raise ValueError('Unknown setup preference.')
 rt=runtime();result=[]
 for key in MODELS:
  m=variant(key);missing=[c for c in codes if c not in m['languages']];present=installed(key,data)
  needs=missing_package(key) if m['available'] else None
  if not m['available']:reason=f"Not available for {RUNTIMES[rt]} yet; it runs on an Apple Silicon Mac."
  elif missing:reason='Does not cover '+', '.join(LANGUAGES[c]['name']for c in missing)+'.'
  elif needs:reason=f"Needs the {needs} package in the Python that runs this studio. See the local studio guide."
  else:reason=f"Covers all {len(codes)} selected language{'s' if len(codes)>1 else ''} and supports your recorded voice."
  score=(200 if present and key==current else 100 if present else 0)-(m['bytes']/1e9) if preference=='reuse' else -m['bytes']/1e9
  result.append(dict(id=key,**m,eligible=m['available'] and not missing and not needs,missing=missing,needs=needs,installed=present,downloadBytes=0 if present else m['bytes'],reason=reason,score=score))
 result.sort(key=lambda m:(m['eligible'],m['score']),reverse=True)
 eligible=[x for x in result if x['eligible']]
 return dict(languages=codes,recommended=eligible[0]['id'] if eligible else None,models=result,preference=preference,policy='Filter by language coverage, voice cloning and this computer\'s runtime; then prefer an installed model or the smallest model, as selected. Auditions decide voice quality.',runtime=dict(system=platform.system(),architecture=platform.machine(),runtime=rt,label=RUNTIMES.get(rt,'No supported local runtime'),supported=rt!='none'))
