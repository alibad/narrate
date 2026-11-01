"""Behavioral setup-policy and local HTTP tests. No model download or GPU generation."""
import importlib.util,json,os,sys,tempfile,threading,unittest,urllib.request,urllib.error,wave,math,struct,hashlib
from pathlib import Path
SCRIPTS=Path(__file__).resolve().parents[1]/'scripts/voice-studio';sys.path.insert(0,str(SCRIPTS))
from catalog import recommend,validate_languages,MODELS,LANGUAGES,installed
spec=importlib.util.spec_from_file_location('setup_server',SCRIPTS/'studio.py');server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)

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
    p=self.root/'models'/name;p.mkdir(parents=True);(p/'config.json').write_text('{}');(p/'model.safetensors').write_bytes(b'fixture')
    if name=='omnivoice':(p/'audio_tokenizer').mkdir();(p/'audio_tokenizer/model.safetensors').write_bytes(b'fixture')
    else:
     d=MODELS[name]['dependencies'][0];cache=self.root/'model-hub'/('models--'+d['repo'].replace('/','--'));snap=cache/'snapshots'/d['revision'];snap.mkdir(parents=True);(snap/'model.safetensors').write_bytes(b'fixture');(cache/'refs').mkdir();(cache/'refs/main').write_text(d['revision'])
   self.assertEqual(recommend(['en','ar'],self.root,'reuse','omnivoice')['recommended'],'omnivoice')
  finally:
   if old is not None:os.environ['NARRATE_VIDEO_MODEL_DIR']=old
 def test_chatterbox_requires_its_separate_tokenizer(self):
  p=self.root/'models/chatterbox';p.mkdir(parents=True);(p/'config.json').write_text('{}');(p/'model.safetensors').write_bytes(b'fixture')
  self.assertFalse(installed('chatterbox',self.root))
  d=MODELS['chatterbox']['dependencies'][0];cache=self.root/'model-hub'/('models--'+d['repo'].replace('/','--'));snapshot=cache/'snapshots'/d['revision'];snapshot.mkdir(parents=True);(snapshot/'model.safetensors').write_bytes(b'fixture');(cache/'refs').mkdir();(cache/'refs/main').write_text(d['revision'])
  self.assertTrue(installed('chatterbox',self.root))
 def test_qwen_requires_its_speech_tokenizer(self):
  p=self.root/'models/qwen3-base';p.mkdir(parents=True);(p/'config.json').write_text('{}');(p/'model.safetensors').write_bytes(b'fixture');self.assertFalse(installed('qwen3-base',self.root))
 def test_invalid_language_and_empty_selection_fail(self):
  for codes in [[],['made-up'],['en']*13]:
   with self.assertRaises(ValueError):validate_languages(codes)
 def test_only_cloning_models_are_offered(self):self.assertTrue(all(m['cloning']for m in MODELS.values()))

class HttpTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);server.DATA=self.root;server.VOICES=self.root/'voices/me';server.OUT=self.root/'out/studio';server.CONFIG=self.root/'config.json'
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
