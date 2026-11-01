"""Language eligibility and explicit, source-backed local model recommendations."""
import json,os,platform
from pathlib import Path
HERE=Path(__file__).parent
LANGUAGES={x['code']:x for x in json.loads((HERE/'languages.json').read_text())}
MODELS={
 'omnivoice':dict(label='OmniVoice',tagline='One voice across many languages',repo='mlx-community/OmniVoice-bf16',revision='8fb0b754cad788aaefec690cd55c207e8a628f85',bytes=1639492513,languages=list(LANGUAGES),cloning=True,source='https://github.com/k2-fsa/OmniVoice',details='Broad language coverage, including the Arabic varieties offered here. Already used locally with voice references. Audition each selected language.',verification='Reference-conditioned generation tested locally'),
 'chatterbox':dict(label='Chatterbox Multilingual',tagline='A smaller multilingual alternative',repo='mlx-community/chatterbox-8bit',revision='9617d61b596a03d1bed766a28c341680e993a1b9',bytes=1427734984,dependencies=[dict(repo='mlx-community/S3TokenizerV2',revision='e0c9886f0e1c35ae85b1f27277416fb19fc72bec',bytes=494869110)],languages='ar da de el en es fi fr he hi it ja ko ms nl no pl pt ru sv sw tr zh'.split(),cloning=True,source='https://huggingface.co/mlx-community/chatterbox-8bit',details='23 declared languages and reference-voice conditioning. Includes its required speech tokenizer in the setup size. Compare an audition before choosing.',verification='English and Arabic reference-conditioned speech generated locally; listening approval is yours'),
 'qwen3-base':dict(label='Qwen3-TTS Base',tagline='Voice cloning for ten languages',repo='mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16',revision='a6eb4f68e4b056f1215157bb696209bc82a6db48',bytes=4544212739,languages='zh en ja ko de fr ru pt es it'.split(),cloning=True,source='https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base',details='The Base checkpoint supports cloning with reference audio and its transcript. Does not support Arabic. This is not the preset-only CustomVoice checkpoint.',verification='English reference-conditioned speech generated locally; listening approval is yours')}

def validate_languages(codes):
 if not isinstance(codes,list) or not 1<=len(codes)<=12 or any(not isinstance(c,str)or c not in LANGUAGES for c in codes):raise ValueError('Choose 1 to 12 languages from the list.')
 return list(dict.fromkeys(codes))

def model_path(name,data):
 if name not in MODELS:raise ValueError('Unknown model.')
 if name=='omnivoice' and (os.environ.get('NARRATE_VIDEO_MODEL_DIR')or os.environ.get('WALKTHROUGH_VIDEO_MODEL_DIR')):return Path(os.environ.get('NARRATE_VIDEO_MODEL_DIR')or os.environ['WALKTHROUGH_VIDEO_MODEL_DIR']).resolve()
 return data/'models'/name

def installed(name,data):
 p=model_path(name,data)
 core=(p/'config.json').is_file() and any(p.glob('*.safetensors')) and (name!='omnivoice' or (p/'audio_tokenizer/model.safetensors').is_file())
 if name=='qwen3-base':core=core and(p/'speech_tokenizer/model.safetensors').is_file()and(p/'speech_tokenizer/config.json').is_file()
 if name=='chatterbox':
  dep=MODELS[name]['dependencies'][0];cache=data/'model-hub'/('models--'+dep['repo'].replace('/','--'));core=core and(cache/'snapshots'/dep['revision']/'model.safetensors').is_file()and(cache/'refs/main').is_file()
 return bool(core)

def recommend(codes,data,preference='reuse',current='omnivoice'):
 codes=validate_languages(codes)
 if preference not in ('reuse','compact'):raise ValueError('Unknown setup preference.')
 result=[]
 for key,m in MODELS.items():
  missing=[c for c in codes if c not in m['languages']];present=installed(key,data)
  reason=(f"Covers all {len(codes)} selected language{'s' if len(codes)>1 else ''} and supports your recorded voice.") if not missing else 'Does not cover '+', '.join(LANGUAGES[c]['name']for c in missing)+'.'
  score=(200 if present and key==current else 100 if present else 0)-(m['bytes']/1e9) if preference=='reuse' else -m['bytes']/1e9
  result.append(dict(id=key,**m,eligible=not missing,missing=missing,installed=present,downloadBytes=0 if present else m['bytes'],reason=reason,score=score))
 result.sort(key=lambda m:(m['eligible'],m['score']),reverse=True)
 eligible=[x for x in result if x['eligible']]
 return dict(languages=codes,recommended=eligible[0]['id'] if eligible else None,models=result,preference=preference,policy='Filter by language coverage and voice cloning; then prefer an installed model or the smallest model, as selected. Auditions decide voice quality.',runtime=dict(system=platform.system(),architecture=platform.machine(),supported=platform.system()=='Darwin' and platform.machine()=='arm64'))
