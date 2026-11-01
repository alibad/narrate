import hashlib,zipfile,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];skill=ROOT/'skill/narrate-video'
files=sorted(p for p in skill.rglob('*')if p.is_file()and '__pycache__'not in p.parts and p.name!='FILES.sha256')
for p in files:
 if p.suffix in('.wav','.mp3','.mp4','.pyc','.safetensors'):raise ValueError('Private media or weights in skill package')
 if re.search(r'(?:/Users/|/home/)[^/\s]+/',p.read_text()):raise ValueError('Private absolute path in skill package')
(skill/'FILES.sha256').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(skill).as_posix()}\n'for p in files))
dest=ROOT/'site/downloads';dest.mkdir(exist_ok=True)
with zipfile.ZipFile(dest/'narrate-video.zip','w',zipfile.ZIP_DEFLATED)as out:
 for p in sorted(files+[skill/'FILES.sha256']):out.write(p,Path('narrate-video')/p.relative_to(skill))
print('Portable skill packaged without reference audio, weights or private paths.')
