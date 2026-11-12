# Explicit speech and auditions

Start with [local studio](local-studio.md) for the standard record-your-voice
language-first workflow. The command/preset adapter and static audition page below are
optional alternatives, used only when explicitly chosen by the user.

The core needs Python 3.12+, Pillow with RAQM for Arabic, FFmpeg and ffprobe.
On Windows, Pillow's wheels include RAQM but not the FriBiDi library it loads;
put a FriBiDi DLL on `PATH` and confirm `PIL.features.check("raqm")` before
rendering Arabic captions.
Use an isolated existing environment or explicitly install `requirements.txt`.
The studio downloads only a selected pinned model after setup is started. Core rendering does not install or download dependencies. Audio can be recorded by a human
or supplied by any reviewed synthesis tool.

The optional `scripts/voice.py synthesize CONFIG TEXT OUTPUT --language en --voice NAME`
adapter executes a deliberately supplied command as an argv array, without a
shell. The agent creates CONFIG in the private production folder. It contains:

```json
{
  "provider": "chosen-local-tool",
  "model": "exact-model-name",
  "revision": "exact-installed-revision",
  "network": "none",
  "languages": ["en", "ar"],
  "voices": ["narrator"],
  "command": ["/absolute/path/to/chosen-tool", "--input", "{input}", "--output", "{output}", "--voice", "{voice}", "--language", "{language}"]
}
```

This is an adapter contract, not an installed provider. Inspect the selected
command before invoking it. `network: none` is a declaration, not a network
sandbox. For cloud speech, use `network: explicit` only when that provider and
transmission are authorized. Keep credentials in the provider's secure store
or environment; never put them in commands, this package or the manifest.
There is no automatic provider selection, fallback, or generation cache.
Each invocation uses a unique temporary output, validates audio and records
the identity/config hash before promoting a new file. Existing files are refused.

The optional command adapter supports presets and rejects cloning settings.
The bundled recording studio handles the selected compatible model and the user’s recorded voice.
Other cloning integrations need explicit speaker permission,
reference audio and transcript content hashes, and output identity proving which
reference/model/language were actually used. Do not silently fall back to a preset
or cross-language reference. The bundled recording studio supplies microphone collection.

For auditions, the agent writes a spec with `takes`, each containing `audio`
(relative local path), `name`, `provider`, `model`, `revision`, `language`, and
the spoken `text`. Run `python scripts/studio.py SPEC NEW_FOLDER`. The generated
page contains local audio players and a selectable voice identity that the user
can save. It generates no speech, loads no remote fonts and has no server/API.
Selection changes only that page; it does not configure the speech provider.

For close caption alignment, generate one natural short phrase per file. Keep
clauses intact so synthesis remains conversational. After transcribing each
phrase (never play it aloud; see [QA](qa.md) for the transcription command), write:

```json
{"phrases": [{"audio": "phrase.wav", "text": "The exact spoken phrase."}]}
```

Compose once per scene: `python scripts/voice.py compose scene-1-phrases.json
narration/scene-1`. That scene's `audio` is the folder's `narration.wav`, and its
`say` and `captions` come from `captions.json`. Caption edges follow audio file durations
at 48 kHz; silence within a file is still included, so a phrase with leading
silence shows its caption early. Check this silently before composing: measure
each phrase's leading and trailing silence with
`ffmpeg -i phrase.wav -af silencedetect=noise=-45dB:d=0.25 -f null -` (a
`silence_start: 0` line means the file opens silent; its `silence_end` is when
speech starts). Trim or regenerate a phrase whose speech starts more than about
0.3 s in, or whose trailing silence would leave a long gap. Transcribe each
phrase to catch overlaps or lost words. Broken prosody and the exact feel of
caption timing need ears: leave them pending for the user's listen at delivery,
never report them as checked. These are phrase timings, not automatic word alignment. A provider's forced alignment
may give finer timings, but still requires review against the final audio.

English and Arabic are independent acceptance paths. Check supported language,
voice and dialect explicitly; no bundled model guarantees either. Keep Arabic
text logically ordered in UTF-8. Do not reverse strings or normalize away letter
distinctions to make transcript comparison pass.
