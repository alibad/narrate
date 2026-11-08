"""Nonaudible pronunciation examples from installed macOS system voices.

These synthetic language examples never read or change a user's voice reference,
model, profile or auditions. The browser chooses whether to play their audio.
"""
import functools
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
import unicodedata
import wave
from pathlib import Path

SAY = '/usr/bin/say'
LOCK = threading.Lock()
PREFERRED = {
    'en-gb': 'Daniel', 'en-us': 'Samantha (English (US))',
    'ar-001': 'Majed', 'de-de': 'Anna', 'es-es': 'Mónica',
    'fr-fr': 'Thomas', 'it-it': 'Alice', 'pt-pt': 'Joana',
    'pt-br': 'Luciana', 'zh-cn': 'Tingting', 'ja-jp': 'Kyoko',
    'ko-kr': 'Yuna', 'hi-in': 'Lekha', 'ru-ru': 'Milena',
    'tr-tr': 'Yelda', 'nl-nl': 'Xander', 'pl-pl': 'Zosia',
    'sv-se': 'Alva', 'da-dk': 'Sara', 'fi-fi': 'Satu',
    'nb-no': 'Nora', 'el-gr': 'Melina', 'he-il': 'Carmit',
    'ms-my': 'Amira', 'id-id': 'Damayanti', 'bn-in': 'Piya',
    'ta-in': 'Vani', 'vi-vn': 'Linh', 'th-th': 'Kanya', 'uk-ua': 'Lesya',
}
# Avoid comic/effect voices even if no preferred voice is installed.
NOVELTY = {'albert', 'bad news', 'bahh', 'bells', 'boing', 'bubbles',
           'cellos', 'good news', 'jester', 'junior', 'organ', 'ralph',
           'superstar', 'trinoids', 'whisper', 'wobble', 'zarvox'}


def locale_key(value):
    return str(value or '').replace('_', '-').lower()


def parse_inventory(text):
    """The voice name can contain spaces, parentheses and accented characters."""
    result = []
    for line in text.splitlines():
        match = re.fullmatch(r'(.+?)\s+([a-z]{2,3}_[A-Za-z0-9]+)\s+#.*', line.strip())
        if match:
            name, locale = match.groups()
            if name.casefold() not in NOVELTY:
                result.append({'voice': name, 'locale': locale.replace('_', '-')})
    return result


@functools.lru_cache(maxsize=1)
def inventory():
    if platform.system() != 'Darwin' or not Path(SAY).is_file():
        return []
    try:
        result = subprocess.run([SAY, '-v', '?'], capture_output=True,
                                text=True, encoding='utf-8', errors='replace',
                                check=True, timeout=10)
        return parse_inventory(result.stdout)
    except (OSError, subprocess.SubprocessError):
        return []


def capability(language, voices=None):
    requested = locale_key(language.get('speechLocale'))
    base = {'available': False, 'provider': 'macos-system', 'voice': None,
            'locale': language.get('speechLocale'), 'cloned': False}
    if not requested:
        return {**base, 'reason': 'No matching system example is configured for this language or dialect.'}
    matches = [v for v in (inventory() if voices is None else voices)
               if locale_key(v['locale']) == requested]
    if not matches:
        return {**base, 'reason': 'A matching installed macOS system voice is unavailable. No other accent or language is substituted.'}
    preferred = PREFERRED.get(requested)
    def identity(name):
        # macOS may decorate the same installed name with language/region labels.
        return unicodedata.normalize('NFC', name.split(' (', 1)[0]).casefold()
    choices = [voice for voice in matches if preferred and identity(voice['voice']) == identity(preferred)]
    if not choices:
        return {**base, 'reason': 'The preferred pronunciation voice is not installed. A basic or novelty voice is not substituted.'}
    selected = sorted(choices, key=lambda v: v['voice'].casefold())[0]
    return {**base, **selected, 'available': True, 'reason': None,
            'quality': 'basic-system',
            'qualityNote': 'Basic system speech, not a native-speaker recording or a pronunciation-quality approval.'}


def capabilities(languages, selected):
    voices = inventory()
    return {code: capability(languages[code], voices) for code in selected if code in languages}


def synthesize(request, languages, selected, destination):
    if not isinstance(request, dict):
        raise ValueError('Choose a selected language and enter its passage.')
    code, text = request.get('lang'), request.get('text')
    if not isinstance(code, str) or code not in selected or code not in languages:
        raise ValueError('Choose a selected language for the pronunciation example.')
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 600 or '\0' in text:
        raise ValueError('Keep the passage between 1 and 600 characters.')
    choice = capability(languages[code])
    if not choice['available']:
        raise ValueError(choice['reason'])
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise ValueError('FFmpeg is required to prepare the system pronunciation example.')
    if not LOCK.acquire(blocking=False):
        raise ValueError('Another pronunciation example is being prepared. Let it finish first.')
    try:
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix='system-example-', dir=destination) as directory:
            aiff, wav = Path(directory)/'example.aiff', Path(directory)/'example.wav'
            # No message argument: say reads only this stdin. -- ends option parsing.
            # -o always writes a file; this command never plays through speakers.
            subprocess.run([SAY, '-v', choice['voice'], '-r', '165', '-o', str(aiff), '--'],
                           input=text.strip(), text=True, encoding='utf-8',
                           capture_output=True, check=True, timeout=60)
            subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-i', str(aiff),
                            '-ac', '1', '-ar', '24000', '-c:a', 'pcm_s16le', str(wav)],
                           stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=60)
            with wave.open(str(wav), 'rb') as audio:
                seconds = audio.getnframes()/audio.getframerate()
                if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or not .05 <= seconds <= 180:
                    raise ValueError('The pronunciation example did not produce usable speech audio.')
            filename = f'{uuid.uuid4().hex}-{code}.wav'
            target = destination/filename
            with target.open('xb') as output, wav.open('rb') as source:
                shutil.copyfileobj(source, output)
            target.chmod(0o600)
        return {'url': f'/pronunciation/{filename}', 'seconds': round(seconds, 2),
                'language': code, 'provider': 'macos-system', 'voice': choice['voice'],
                'locale': choice['locale'], 'quality': choice['quality'], 'cloned': False, 'synthetic': True, 'audition': False}
    except (OSError, subprocess.SubprocessError, wave.Error) as error:
        raise ValueError('The installed system voice could not prepare this example. No fallback or voice-profile change was made.') from error
    finally:
        LOCK.release()
