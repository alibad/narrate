import hashlib,zipfile,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];skill=ROOT/'skill/narrate-video'
files=sorted(p for p in skill.rglob('*')if p.is_file()and '__pycache__'not in p.parts and p.name!='FILES.sha256')
# A Windows checkout has CRLF text and no executable bits; package git's LF text and recorded modes on every platform.
def content(p):
 data=p.read_bytes();return data if b'\0' in data else data.replace(b'\r\n',b'\n')
try:modes={line.split('\t')[1]:line.split()[0]for line in subprocess.run(['git','ls-files','-s','--',str(skill)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',check=True).stdout.splitlines()}
except(OSError,subprocess.CalledProcessError):modes={}
def executable(p):
 mode=modes.get(p.relative_to(ROOT).as_posix());return mode=='100755'if mode else bool(p.stat().st_mode&0o111)
for p in files:
 if p.suffix in('.wav','.mp3','.mp4','.pyc','.safetensors'):raise ValueError('Private media or weights in skill package')
 if re.search(r'(?:/Users/|/home/|[A-Za-z]:\\\\?Users\\\\?)[^/\\\s]+[/\\]',content(p).decode('utf-8')):raise ValueError('Private absolute path in skill package')
(skill/'FILES.sha256').write_text(''.join(f'{hashlib.sha256(content(p)).hexdigest()}  {p.relative_to(skill).as_posix()}\n'for p in files),encoding='utf-8',newline='\n')
dest=ROOT/'site/downloads';dest.mkdir(exist_ok=True)
with zipfile.ZipFile(dest/'narrate-video.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9)as out:
 for p in sorted(files+[skill/'FILES.sha256']):
  info=zipfile.ZipInfo((Path('narrate-video')/p.relative_to(skill)).as_posix(),date_time=(1980,1,1,0,0,0))
  info.compress_type=zipfile.ZIP_DEFLATED;info.create_system=3
  info.external_attr=(0o100755 if executable(p) else 0o100644)<<16
  out.writestr(info,content(p),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
print('Portable skill packaged without reference audio, weights or private paths.')
