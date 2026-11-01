"""Behavioral setup-policy and local HTTP tests. No model download or GPU generation."""
import importlib.util,json,os,sys,tempfile,threading,unittest,urllib.request,urllib.error,wave,math,struct,hashlib
from pathlib import Path
SCRIPTS=Path(__file__).resolve().parents[1]/'scripts/voice-studio';sys.path.insert(0,str(SCRIPTS))
# The policy tests describe the Apple Silicon catalog unless a test chooses another runtime.
os.environ['NARRATE_VIDEO_RUNTIME']='mlx'
from catalog import recommend,validate_languages,MODELS,LANGUAGES,installed
spec=importlib.util.spec_from_file_location('setup_server',SCRIPTS/'studio.py');server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)

class CudaPolicyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.saved={k:os.environ.get(k)for k in('NARRATE_VIDEO_RUNTIME','HF_HUB_CACHE')}
  os.environ.update(NARRATE_VIDEO_RUNTIME='cuda',HF_HUB_CACHE=str(self.root/'hub'))
 def tearDown(self):
  for k,v in self.saved.items():
   if v is None:os.environ.pop(k,None)
   else:os.environ[k]=v
  self.tmp.cleanup()
 def test_nvidia_offers_only_models_with_a_cuda_build(self):
  plan=recommend(['en','ar'],self.root);self.assertEqual(plan['recommended'],'chatterbox');self.assertEqual(plan['runtime']['label'],'NVIDIA GPU · CUDA')
  c=next(x for x in plan['models']if x['id']=='chatterbox');self.assertEqual(c['repo'],'ResembleAI/chatterbox');self.assertEqual(c['bytes'],MODELS['chatterbox']['cuda']['bytes'])
  o=next(x for x in plan['models']if x['id']=='omnivoice');self.assertFalse(o['eligible']);self.assertIn('Apple Silicon',o['reason'])
 def test_gulf_arabic_has_no_nvidia_model_yet(self):self.assertIsNone(recommend(['afb'],self.root)['recommended'])
 def test_nvidia_chatterbox_is_found_complete_in_the_hugging_face_cache(self):
  c=MODELS['chatterbox']['cuda'];snap=self.root/'hub'/('models--'+c['repo'].replace('/','--'))/'snapshots'/c['revision'];snap.mkdir(parents=True)
  for f in c['files'][:-1]:(snap/f).write_bytes(b'fixture')
  self.assertFalse(installed('chatterbox',self.root))
  (snap/c['files'][-1]).write_bytes(b'fixture');self.assertTrue(installed('chatterbox',self.root))
  self.assertEqual(next(x for x in recommend(['en'],self.root)['models']if x['id']=='chatterbox')['downloadBytes'],0)

class PolicyTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def test_arabic_excludes_qwen_base(self):
  plan=recommend(['en','ar'],self.root)
  q=next(x for x in plan['models']if x['id']=='qwen3-base');self.assertFalse(q['eligible']);self.assertEqual(q['missing'],['ar'])
 def test_english_allows_qwen_cloning_checkpoint(self):
  q=next(x for x in recommend(['en'],self.root)['models']if x['id']=='qwen3-base');self.assertTrue(q['eligible']);self.assertTrue(q['cloning']);self.assertIn('Base',q['repo'])
 def test_gulf_arabic_coverage_changes_available_models(self):
  p=recommend(['afb'],self.root,'compact');self.assertEqual(p['recommended'],'omnivoice');self.assertEqual([x['id']for x in p['models']if x['eligible']],['omnivoice'])
 def test_compact_prefers_smaller_model_when_languages_fit(self):self.assertEqual(recommend(['en','ar'],self.root,'compact')['recommended'],'chatterbox')
 def test_current_installed_model_is_preferred_for_reuse(self):
  old=os.environ.pop('NARRATE_VIDEO_MODEL_DIR',None)
  try:
   for name in ['chatterbox','omnivoice']:
    p=self.root/'models'/name;p.mkdir(parents=True);(p/'config.json').write_text('{}',encoding='utf-8');(p/'model.safetensors').write_bytes(b'fixture')
    if name=='omnivoice':(p/'audio_tokenizer').mkdir();(p/'audio_tokenizer/model.safetensors').write_bytes(b'fixture')
    else:
     d=MODELS[name]['dependencies'][0];cache=self.root/'model-hub'/('models--'+d['repo'].replace('/','--'));snap=cache/'snapshots'/d['revision'];snap.mkdir(parents=True);(snap/'model.safetensors').write_bytes(b'fixture');(cache/'refs').mkdir();(cache/'refs/main').write_text(d['revision'],encoding='utf-8')
   self.assertEqual(recommend(['en','ar'],self.root,'reuse','omnivoice')['recommended'],'omnivoice')
  finally:
   if old is not None:os.environ['NARRATE_VIDEO_MODEL_DIR']=old
 def test_chatterbox_requires_its_separate_tokenizer(self):
  p=self.root/'models/chatterbox';p.mkdir(parents=True);(p/'config.json').write_text('{}',encoding='utf-8');(p/'model.safetensors').write_bytes(b'fixture')
  self.assertFalse(installed('chatterbox',self.root))
  d=MODELS['chatterbox']['dependencies'][0];cache=self.root/'model-hub'/('models--'+d['repo'].replace('/','--'));snapshot=cache/'snapshots'/d['revision'];snapshot.mkdir(parents=True);(snapshot/'model.safetensors').write_bytes(b'fixture');(cache/'refs').mkdir();(cache/'refs/main').write_text(d['revision'],encoding='utf-8')
  self.assertTrue(installed('chatterbox',self.root))
 def test_qwen_requires_its_speech_tokenizer(self):
  p=self.root/'models/qwen3-base';p.mkdir(parents=True);(p/'config.json').write_text('{}',encoding='utf-8');(p/'model.safetensors').write_bytes(b'fixture');self.assertFalse(installed('qwen3-base',self.root))
 def test_invalid_language_and_empty_selection_fail(self):
  for codes in [[],['made-up'],['en']*13]:
   with self.assertRaises(ValueError):validate_languages(codes)
 def test_only_cloning_models_are_offered(self):self.assertTrue(all(m['cloning']for m in MODELS.values()))
 def test_every_language_has_a_bundled_flag(self):
  for l in LANGUAGES.values():self.assertTrue((SCRIPTS/'flags'/f"{l['flag']}.svg").is_file(),l['code'])

class HttpTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);server.DATA=self.root;server.VOICES=self.root/'voices/me';server.OUT=self.root/'out/studio';server.GUIDE=self.root/'out/guide';server.CONFIG=self.root/'config.json'
  for p in(server.VOICES,server.OUT):p.mkdir(parents=True)
  self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);server.PORT=self.http.server_address[1];self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start();self.url=f'http://127.0.0.1:{server.PORT}'
 def tearDown(self):self.http.shutdown();self.http.server_close();self.tmp.cleanup()
 def request(self,path,data=None,headers=None):
  payload=json.dumps(data).encode()if data is not None else None
  req=urllib.request.Request(self.url+path,data=payload,headers={'Content-Type':'application/json',**(headers or{})})
  try:
   with urllib.request.urlopen(req)as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:
   raw=e.read().decode()
   try:raw=json.loads(raw)
   except ValueError:pass
   return e.code,raw
 def test_preferences_persist_user_languages_without_model_swap(self):
  status,data=self.request('/api/preferences',{'languages':['en','ar'],'preference':'compact'});self.assertEqual(status,200);self.assertEqual(data['config']['engine'],'omnivoice');self.assertEqual(data['plan']['recommended'],'chatterbox')
 def test_studio_stylesheet_is_served_with_css_content_type(self):
  with urllib.request.urlopen(self.url+'/studio.css')as response:
   self.assertEqual(response.status,200);self.assertEqual(response.headers.get_content_type(),'text/css');self.assertIn(b'--coral',response.read())
 def test_private_status_rejects_foreign_origin(self):self.assertEqual(self.request('/api/status',headers={'Origin':'https://foreign.example'})[0],403)
 def test_invalid_setup_cannot_start_download(self):
  status,_=self.request('/api/setup',{'languages':['ar'],'model':'qwen3-base'});self.assertEqual(status,400);self.assertFalse((self.root/'models').exists())
 def test_setup_names_the_supported_runtimes_and_never_substitutes(self):
  try:
   os.environ['NARRATE_VIDEO_RUNTIME']='none'
   status,data=self.request('/api/setup',{'languages':['en'],'model':'chatterbox'});self.assertEqual(status,400);self.assertIn('Apple Silicon Mac, or an NVIDIA GPU',data['error'])
   os.environ['NARRATE_VIDEO_RUNTIME']='cuda'
   status,data=self.request('/api/setup',{'languages':['en'],'model':'omnivoice'});self.assertEqual(status,400);self.assertIn('not available for NVIDIA',data['error'])
  finally:os.environ['NARRATE_VIDEO_RUNTIME']='mlx'
  self.assertFalse((self.root/'models').exists())
 def test_every_language_flag_is_served_and_paths_cannot_escape(self):
  for code in {l['flag']for l in LANGUAGES.values()}:
   with urllib.request.urlopen(self.url+f'/flags/{code}.svg')as r:self.assertEqual(r.headers.get_content_type(),'image/svg+xml');self.assertIn(b'<svg',r.read(200))
  for path in('/flags/..%2Fstudio.py','/flags/gb.py','/guide/..%2F..%2Fconfig.json'):self.assertEqual(self.request(path)[0],404)
 def test_guide_needs_setup_and_a_saved_recording_and_is_never_an_audition(self):
  status,data=self.request('/api/guide',{'lang':'en','text':'Hello.'});self.assertEqual(status,400);self.assertIn('Complete setup',data['error'])
  server.save_config({'engine':'chatterbox','languages':['en','zh'],'setupReady':True,'setupModel':'chatterbox'})
  status,data=self.request('/api/guide',{'lang':'zh','text':'你好。'});self.assertEqual(status,400);self.assertIn('Save one recording',data['error'])
  status,data=self.request('/api/guide',{'lang':'fr','text':'Bonjour.'});self.assertEqual(status,400);self.assertIn('selected language',data['error'])
  self.assertEqual(list(server.OUT.glob('*')),[])
 def test_finish_requires_accepted_auditions(self):self.assertEqual(self.request('/api/finish',{})[0],400)
 def test_missing_same_language_reference_never_falls_back(self):
  (server.VOICES/'en.wav').write_bytes(b'fixture');server.save_config({'languages':['ar'],'setupReady':True,'setupModel':'omnivoice'})
  status,data=self.request('/api/generate',{'engine':'omnivoice','lang':'ar','text':'test'});self.assertEqual(status,400);self.assertIn('explicitly choose',data['error'])
 def test_recording_replacement_preserves_previous_audio(self):
  from io import BytesIO
  def audio(freq):
   buf=BytesIO()
   with wave.open(buf,'wb')as w:
    w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b''.join(struct.pack('<h',int(5000*math.sin(2*math.pi*freq*i/24000)))for i in range(24000*4)))
   return buf.getvalue()
  def upload(freq):
   req=urllib.request.Request(self.url+'/api/reference?lang=en&text=Synthetic%20test%20fixture',data=audio(freq),headers={'Content-Type':'audio/wav'})
   with urllib.request.urlopen(req)as r:return json.load(r)
  upload(300);old=server.sha(server.VOICES/'en.wav');upload(450);self.assertNotEqual(server.sha(server.VOICES/'en.wav'),old)
  history=list((self.root/'voice-history').rglob('en.wav'));self.assertEqual(len(history),1);self.assertEqual(server.sha(history[0]),old)

if __name__=='__main__':unittest.main()
