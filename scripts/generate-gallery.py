"""Generate private review speech with the skill's selected, explicit voice adapter."""
import hashlib,json,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];ENDPOINT='http://127.0.0.1:8768'
def post(path,body):
 req=urllib.request.Request(ENDPOINT+path,json.dumps(body,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
 try:return json.load(urllib.request.urlopen(req,timeout=600))
 except urllib.error.HTTPError as e:raise RuntimeError(e.read().decode())
items=json.loads((ROOT/'content/gallery.json').read_text(encoding='utf-8'))
post('/api/setup',dict(model='omnivoice',languages=[x['id']for x in items],preference='reuse'))
for _ in range(180):
 s=json.load(urllib.request.urlopen(ENDPOINT+'/api/status'))['setup']
 if s['state']=='ready':break
 if s['state']=='failed':raise RuntimeError(s['message'])
 time.sleep(1)
else:raise RuntimeError('Local model setup did not finish')
for item in items:
 code=item['id'];folder=ROOT/'production'/code/'speech'
 for n,text in enumerate(item['narration'],1):
  wav=folder/f'{n:02}.wav';receipt=folder/f'{n:02}.identity.json'
  if wav.exists()and receipt.exists():continue
  ref=code if code in('en','ar')else'en'
  result=post('/api/generate',dict(lang=code,text=text,reference=ref,engine='omnivoice',mine=True))
  assert result['engine']=='omnivoice'and result['cloned']and result['from_recording']==ref and result['language']==code
  audio=urllib.request.urlopen(ENDPOINT+result['url']).read();wav.write_bytes(audio)
  result.update(audioSha256=hashlib.sha256(audio).hexdigest(),review='private draft; listening approval pending',crossLanguageReference=ref!=code)
  receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(code,n,result['seconds'],flush=True)
print('All thirty speech phrases generated for private review.',flush=True)
