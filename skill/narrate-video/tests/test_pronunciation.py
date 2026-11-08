"""Bounded system-example tests. Synthetic WAV fixtures do not prove pronunciation."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
import wave
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts/voice-studio'
sys.path.insert(0, str(SCRIPTS))
import pronunciation

spec = importlib.util.spec_from_file_location('pronunciation_server', SCRIPTS/'studio.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def tone_fixture(path):
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b'\0\0'*12000)


class PronunciationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.languages = {'en': {'speechLocale': 'en-GB'}, 'ar': {'speechLocale': 'ar-001'},
                          'afb': {'speechLocale': None}, 'fr': {'speechLocale': 'fr-FR'}}
        self.voices = [{'voice': 'Daniel', 'locale': 'en-GB'}, {'voice': 'Majed', 'locale': 'ar-001'}]
        self.inventory = patch.object(pronunciation, 'inventory', return_value=self.voices)
        self.inventory.start()

    def tearDown(self):
        self.inventory.stop()
        self.tmp.cleanup()

    def fake_run(self, argv, **kwargs):
        if argv[0] == pronunciation.SAY:
            self.assertEqual(argv[-1], '--')
            self.assertEqual(kwargs['input'], self.text)
            self.assertNotIn(self.text, argv)
            Path(argv[argv.index('-o')+1]).write_bytes(b'synthetic-aiff-fixture')
        else:
            self.assertIn('-nostdin', argv)
            tone_fixture(argv[-1])
        self.assertEqual(kwargs['timeout'], 60)
        return subprocess.CompletedProcess(argv, 0)

    def test_inventory_parses_spaces_accents_and_excludes_effect_voices(self):
        result = pronunciation.parse_inventory('Daniel en_GB # Hello\nBad News en_US # Hello\nMónica es_ES # Hola\nSamantha (English (US)) en_US # Hello\ninvalid')
        self.assertEqual(result, [{'voice': 'Daniel', 'locale': 'en-GB'}, {'voice': 'Mónica', 'locale': 'es-ES'}, {'voice': 'Samantha (English (US))', 'locale': 'en-US'}])

    def test_exact_locale_and_dialect_do_not_fall_back_to_other_arabic(self):
        self.assertTrue(pronunciation.capability(self.languages['ar'])['available'])
        self.assertFalse(pronunciation.capability(self.languages['afb'])['available'])
        self.assertFalse(pronunciation.capability({'speechLocale': 'ar-EG'})['available'])
        self.assertFalse(pronunciation.capability({'speechLocale': 'en-US'})['available'])

    def test_preferred_voice_is_deterministic_and_locale_is_normalized(self):
        voices = [{'voice': 'Sandy', 'locale': 'en_GB'}, {'voice': 'Daniel', 'locale': 'en-GB'}]
        self.assertEqual(pronunciation.capability({'speechLocale': 'en_GB'}, voices)['voice'], 'Daniel')
        self.assertEqual(pronunciation.capability({'speechLocale': 'en_GB'}, list(reversed(voices)))['voice'], 'Daniel')

    def test_invalid_or_unselected_passage_refuses_before_output_or_process(self):
        for request in [None, [], {'lang': 'fr', 'text': 'hello'}, {'lang': ['en'], 'text': 'hello'}, {'lang': 'en', 'text': []}, {'lang': 'en', 'text': ''}, {'lang': 'en', 'text': 'x'*601}, {'lang': 'en', 'text': 'x\0y'}]:
            with patch.object(pronunciation.subprocess, 'run') as run:
                with self.assertRaises(ValueError):
                    pronunciation.synthesize(request, self.languages, ['en'], self.root/'out')
                run.assert_not_called()
                self.assertFalse((self.root/'out').exists())

    def test_unsupported_and_busy_examples_do_not_start_process_or_create_output(self):
        with patch.object(pronunciation.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                pronunciation.synthesize({'lang': 'afb', 'text': 'test'}, self.languages, ['afb'], self.root/'out')
            with pronunciation.LOCK, patch.object(pronunciation.shutil, 'which', return_value='ffmpeg'):
                with self.assertRaisesRegex(ValueError, 'Another pronunciation'):
                    pronunciation.synthesize({'lang': 'en', 'text': 'test'}, self.languages, ['en'], self.root/'out')
            run.assert_not_called()
            self.assertFalse((self.root/'out').exists())

    def test_synthesis_uses_stdin_private_unique_output_and_no_voice_clone(self):
        self.text = '--voice other; $(do-not-run) café'
        with patch.object(pronunciation.subprocess, 'run', side_effect=self.fake_run), patch.object(pronunciation.shutil, 'which', return_value='ffmpeg'):
            first = pronunciation.synthesize({'lang': 'en', 'text': self.text}, self.languages, ['en'], self.root/'out')
            second = pronunciation.synthesize({'lang': 'en', 'text': self.text}, self.languages, ['en'], self.root/'out')
        self.assertNotEqual(first['url'], second['url'])
        self.assertEqual(first['provider'], 'macos-system')
        self.assertFalse(first['cloned'])
        self.assertFalse(first['audition'])
        self.assertEqual(first['voice'], 'Daniel')
        self.assertEqual(first['seconds'], .5)
        self.assertEqual(len(list((self.root/'out').iterdir())), 2)
        self.assertEqual((self.root/'out'/Path(first['url']).name).stat().st_mode & 0o777, 0o600)

    def test_failed_process_leaves_no_final_output_and_releases_lock(self):
        with patch.object(pronunciation.subprocess, 'run', side_effect=subprocess.TimeoutExpired('say', 60)), patch.object(pronunciation.shutil, 'which', return_value='ffmpeg'):
            with self.assertRaisesRegex(ValueError, 'No fallback'):
                pronunciation.synthesize({'lang': 'en', 'text': 'test'}, self.languages, ['en'], self.root/'out')
        self.assertEqual(list((self.root/'out').iterdir()), [])
        self.assertTrue(pronunciation.LOCK.acquire(blocking=False))
        pronunciation.LOCK.release()

    def test_status_capabilities_and_http_example_preserve_profile_and_references(self):
        saved = {key: getattr(server, key) for key in ['DATA', 'VOICES', 'OUT', 'GUIDE', 'CONFIG', 'PORT']}
        server.DATA = self.root
        server.VOICES = self.root/'voices/me'
        server.OUT = self.root/'out/studio'
        server.GUIDE = self.root/'out/guide'
        server.CONFIG = self.root/'config.json'
        server.VOICES.mkdir(parents=True)
        reference = server.VOICES/'en.wav'
        reference.write_bytes(b'unchanged-private-reference-fixture')
        (server.VOICES/'en.txt').write_text('unchanged fixture', encoding='utf-8')
        server.save_config({'languages': ['en'], 'references': {'en': 'en'}, 'accepted': {'en': {'id': 'unchanged-acceptance'}}, 'profileReady': True})
        before_config = server.CONFIG.read_bytes()
        before_reference = reference.read_bytes()
        http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        server.PORT = http.server_address[1]
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        self.text = 'A synthetic example.'
        try:
            with patch.dict(server.LANGUAGES, {'en': {'speechLocale': 'en-GB'}}), patch.object(pronunciation.subprocess, 'run', side_effect=self.fake_run), patch.object(pronunciation.shutil, 'which', return_value='ffmpeg'), patch.object(server, 'references', return_value={}), patch.object(server, 'recommend', return_value={}):
                base = f'http://127.0.0.1:{server.PORT}'
                with urllib.request.urlopen(base+'/api/status') as response:
                    status = json.load(response)
                self.assertTrue(status['pronunciation']['en']['available'])
                request = urllib.request.Request(base+'/api/pronunciation', data=json.dumps({'lang': 'en', 'text': self.text}).encode(), headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(request) as response:
                    receipt = json.load(response)
                with urllib.request.urlopen(base+receipt['url']) as response:
                    self.assertEqual(response.headers['Content-Type'], 'audio/wav')
                    self.assertTrue(response.read().startswith(b'RIFF'))
            self.assertEqual(server.CONFIG.read_bytes(), before_config)
            self.assertEqual(reference.read_bytes(), before_reference)
            self.assertEqual((server.VOICES/'en.txt').read_text(encoding='utf-8'), 'unchanged fixture')
            self.assertEqual(list(server.OUT.glob('*.json')), [])
        finally:
            http.shutdown()
            http.server_close()
            for key, value in saved.items():
                setattr(server, key, value)


if __name__ == '__main__':
    unittest.main()
