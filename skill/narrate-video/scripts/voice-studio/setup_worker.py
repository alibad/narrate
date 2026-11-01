"""Download only the selected, pinned local model; launched by the setup job."""
import sys,os
from pathlib import Path
from catalog import MODELS
if __name__=='__main__':
 from huggingface_hub import snapshot_download
 name,path=sys.argv[1:];m=MODELS[name]
 snapshot_download(m['repo'],revision=m['revision'],local_dir=Path(path),max_workers=4)
 for dep in m.get('dependencies',[]):
  cache=Path(os.environ['HF_HUB_CACHE']);snapshot_download(dep['repo'],revision=dep['revision'],cache_dir=cache,allow_patterns=['config.json','model.safetensors'])
  # The upstream loader asks for main. Pin that alias inside this private model cache.
  refs=cache/('models--'+dep['repo'].replace('/','--'))/'refs';refs.mkdir(parents=True,exist_ok=True);(refs/'main').write_text(dep['revision'],encoding='utf-8')
