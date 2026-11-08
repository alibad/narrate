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
 def test_committed_english_is_an_automatic_nonwriting_default(self):
  (server.VOICES/'en.wav').write_bytes(b'fixture');server.save_config({'languages':['en','ar','es']})
  before=server.CONFIG.read_bytes();status,data=self.request('/api/status')
  self.assertEqual(status,200);self.assertEqual(data['effectiveReferences'],{'en':'en','ar':'en','es':'en'})
  self.assertEqual(server.CONFIG.read_bytes(),before);self.assertEqual(data['config']['references'],{})
  self.assertEqual(server.selected_reference('ar',{},server.config()),'en')
 def test_no_arbitrary_nonenglish_fallback_or_preset(self):
  (server.VOICES/'fr.wav').write_bytes(b'fixture');server.save_config({'languages':['ar'],'setupReady':True,'setupModel':'omnivoice'})
  status,data=self.request('/api/generate',{'engine':'omnivoice','lang':'ar','text':'test'})
  self.assertEqual(status,400);self.assertIn('Record English once',data['error'])
 def test_explicit_reference_overrides_default_and_missing_choice_refuses(self):
  for code in ['en','fr','ar']:(server.VOICES/(code+'.wav')).write_bytes(code.encode())
  server.save_config({'languages':['en','ar'],'references':{'ar':'fr'}})
  self.assertEqual(server.selected_reference('ar',{},server.config()),'fr')
  self.assertEqual(server.selected_reference('ar',{'reference':'en'},server.config()),'en')
  server.save_config({'references':{'ar':'de'}})
  with self.assertRaises(ValueError):server.selected_reference('ar',{},server.config())
 def test_own_legacy_recording_is_preserved_instead_of_english_default(self):
  for code in ['en','ar']:(server.VOICES/(code+'.wav')).write_bytes(code.encode())
  self.assertEqual(server.selected_reference('ar',{},server.config()),'ar')
 def test_reselecting_effective_reference_keeps_approved_profile(self):
  (server.VOICES/'en.wav').write_bytes(b'fixture')
  approved={'ar':{'id':'already-listened','engine':'omnivoice','referenceSha256':'fixture'}}
  server.save_config({'languages':['en','ar'],'accepted':approved,'profileReady':True})
  status,data=self.request('/api/reference-choice',{'language':'ar','reference':'en'})
  self.assertEqual(status,200);self.assertTrue(data['config']['profileReady']);self.assertEqual(data['config']['accepted'],approved)
 def test_explicit_override_changes_only_target_without_accepting_auditions(self):
  for code in ['en','ar']:(server.VOICES/(code+'.wav')).write_bytes(code.encode())
  approved={'en':{'id':'already-listened','engine':'omnivoice'}}
  server.save_config({'languages':['en','ar','es'],'references':{'ar':'en'},'accepted':approved,'profileReady':True})
  status,data=self.request('/api/reference-choice',{'language':'ar','reference':'ar'})
  self.assertEqual(status,200);self.assertEqual(data['effectiveReferences'],{'en':'en','ar':'ar','es':'en'})
  self.assertEqual(data['config']['accepted'],approved);self.assertFalse(data['config']['profileReady'])
  self.assertEqual(data['config']['languages'],['en','ar','es']);self.assertEqual(data['config']['engine'],'omnivoice')
 def test_replaced_english_stales_followers_but_preserves_own_override(self):
  for code in ['en','ar']:(server.VOICES/(code+'.wav')).write_bytes(('before-'+code).encode())
  en_hash=server.sha(server.VOICES/'en.wav');ar_hash=server.sha(server.VOICES/'ar.wav')
  accepted={code:{'id':code+'-listened','engine':'omnivoice','referenceSha256':ar_hash if code=='ar' else en_hash} for code in ['en','ar','es']}
  server.save_config({'languages':['en','ar','es'],'references':{'ar':'ar'},'accepted':accepted,'profileReady':True})
  (server.VOICES/'en.wav').write_bytes(b'after-English');server.save_config({'profileReady':False})
  status,data=self.request('/api/finish',{});self.assertEqual(status,400)
  self.assertEqual(server.config()['accepted'],accepted)
  self.assertEqual(server.sha(server.VOICES/'ar.wav'),ar_hash)
  self.assertEqual(server.selected_reference('ar',{},server.config()),'ar')
  current=server.sha(server.VOICES/'en.wav')
  for code in ['en','es']:accepted[code]={**accepted[code],'id':'newly-listened-'+code,'referenceSha256':current}
  server.save_config({'accepted':accepted})
  self.assertEqual(self.request('/api/finish',{})[0],200)
  self.assertEqual(server.config()['accepted']['ar']['referenceSha256'],ar_hash)
 def test_recording_replacement_preserves_previous_audio(self):
  from io import BytesIO
  def audio(freq):
   buf=BytesIO()
   with wave.open(buf,'wb')as w:
    w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b''.join(struct.pack('<h',int(5000*math.sin(2*math.pi*freq*i/24000)))for i in range(24000*4)))
   return buf.getvalue()
  def upload(freq,lang='en'):
   req=urllib.request.Request(self.url+f'/api/reference?lang={lang}&text=Synthetic%20test%20fixture',data=audio(freq),headers={'Content-Type':'audio/wav'})
   with urllib.request.urlopen(req)as r:return json.load(r)
  server.save_config({'languages':['en','ar','es'],'accepted':{'es':{'id':'existing-approval'}}})
  upload(300);self.assertEqual(server.selected_reference('ar',{},server.config()),'en');old=server.sha(server.VOICES/'en.wav');upload(450);self.assertNotEqual(server.sha(server.VOICES/'en.wav'),old)
  history=list((self.root/'voice-history').rglob('en.wav'));self.assertEqual(len(history),1);self.assertEqual(server.sha(history[0]),old)
  self.assertEqual(server.selected_reference('ar',{},server.config()),'en')
  self.assertEqual(server.config()['accepted'],{'es':{'id':'existing-approval'}})
  upload(600,'ar');self.assertEqual(server.selected_reference('ar',{},server.config()),'ar')
  self.assertEqual(server.selected_reference('es',{},server.config()),'en')
  self.assertEqual(server.config()['references'],{'en':'en','ar':'ar'})
  self.assertEqual(server.config()['languages'],['en','ar','es'])

if __name__=='__main__':unittest.main()
