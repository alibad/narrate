"""Local behavioral tests: tone fixtures establish timing/failure semantics, not speech quality."""
import importlib.util
import json
import math
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
from voice import synthesize,compose
from qa import compare
from studio import build
from render import prepare,render,probe


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        for i,seconds in enumerate([.4,.7]):
            with wave.open(str(self.root/f'{i}.wav'),'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(48000)
                w.writeframes(b''.join(struct.pack('<h',round(5000*math.sin(n*2*math.pi*300/48000)))for n in range(round(seconds*48000))))
        self.text=self.root/'text.txt';self.text.write_text('Exact test phrase.',encoding='utf-8')
        self.cfg=self.root/'config.json'

    def tearDown(self):self.tmp.cleanup()

    def config(self,command):
        cfg=dict(provider='synthetic-test',model='tone-fixture',revision='1',network='none',languages=['en'],voices=['fixture'],command=command)
        self.cfg.write_text(json.dumps(cfg),encoding='utf-8');return cfg

    def test_unsupported_language_never_invokes_provider(self):
        marker=self.root/'invoked'
        self.config([sys.executable,'-c',f"open({str(marker)!r},'w').write('bad')",'{input}','{output}'])
        with self.assertRaisesRegex(ValueError,'unsupported'):synthesize(self.cfg,self.text,self.root/'out.wav','ar','fixture')
        self.assertFalse(marker.exists())

    def test_provider_failure_has_no_fallback_or_partial_output(self):
        self.config([sys.executable,'-c','raise SystemExit(9)','{input}','{output}'])
        with self.assertRaisesRegex(ValueError,'no fallback'):synthesize(self.cfg,self.text,self.root/'out.wav','en','fixture')
        self.assertFalse((self.root/'out.wav').exists())

    def test_explicit_provider_audio_and_identity_no_overwrite(self):
        self.config([sys.executable,'-c',f"import shutil,sys;shutil.copyfile({str(self.root/'0.wav')!r},sys.argv[2])",'{input}','{output}'])
        out=self.root/'out.wav';receipt=synthesize(self.cfg,self.text,out,'en','fixture')
        self.assertEqual(receipt['voice'],'fixture');self.assertEqual(receipt['language'],'en')
        self.assertEqual(out.read_bytes(),(self.root/'0.wav').read_bytes())
        with self.assertRaisesRegex(ValueError,'exists'):synthesize(self.cfg,self.text,out,'en','fixture')

    def test_phrase_boundaries_follow_audio_duration(self):
        spec=self.root/'phrases.json';spec.write_text(json.dumps({'phrases':[{'audio':'0.wav','text':'First phrase.'},{'audio':'1.wav','text':'Second phrase.'}]}),encoding='utf-8')
        result=compose(spec,self.root/'composed')
        self.assertAlmostEqual(result['captions'][1]['start'],.4,places=5)
        self.assertAlmostEqual(result['captions'][1]['end'],1.1,places=5)
        self.assertAlmostEqual(float(probe(self.root/'composed/narration.wav')['format']['duration']),1.1,places=4)

    def test_order_negations_numbers_and_duplicates_are_not_lost(self):
        for a,b in [('Do not send it.','Do send it.'),('Send two files.','Send three files.'),('Click save then close.','Click close then save.'),('Go go now.','Go now.')]:
            self.assertFalse(compare(a,b)['exactOrderedMatch'])
        self.assertTrue(compare('Save the file.','save the file!')['exactOrderedMatch'])

    def test_audition_escapes_content_and_keeps_audio(self):
        spec=self.root/'audition.json';spec.write_text(json.dumps({'takes':[dict(name='<unsafe>',provider='test',model='tone',revision='1',language='en',text='Synthetic tone, not speech.',audio='0.wav')]}),encoding='utf-8')
        out=self.root/'studio';build(spec,out)
        text=(out/'index.html').read_text(encoding='utf-8')
        self.assertIn('&lt;unsafe&gt;',text);self.assertNotIn('<unsafe>',text)
        self.assertEqual((out/'take-0.wav').read_bytes(),(self.root/'0.wav').read_bytes())


if __name__=='__main__':unittest.main()
