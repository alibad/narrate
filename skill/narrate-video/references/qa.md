# Verification and honest completion

Run the local regression command before changing the helpers:

```sh
sh scripts/verify.sh
```

Synthetic fixtures exercise mechanics; they do not establish behavior in a
particular product, deployment or device. Capture a small authorized journey
and verify its result separately before claiming production readiness.
Set `PYTHON` to a chosen environment when needed. To include the optional local
browser fixture, append the installed Playwright module entry and browser
executable to `verify.sh`. The fixture tests readiness, a single action and
geometry. It neither installs a browser nor touches a product.

`scripts/qa.py VIDEO EVIDENCE NEW_QA [--transcript FINAL_TRANSCRIPT]` verifies the
video's receipt hash, decodes through the end, probes streams, measures loudness
and extracts first/middle/last frames and both sides of every scene boundary.
Its contact sheet is a review aid. It leaves visual, caption and playback review
pending because those are not established by a probe.

Transcribe the final decoded audio, never substitute the planned text as a
transcript. The optional transcript comparison
preserves word order, repetitions, numbers and negations. A difference is a
review item, not proof that synthesis or ASR was wrong. Correct material errors
and document pronunciation/ASR ambiguities. Missing transcription remains pending.

## Transcription

Use whisper.cpp (`whisper-cli`) with `ggml-large-v3-turbo-q5_0.bin` from
`huggingface.co/ggerganov/whisper.cpp` at revision
`5359861c739e955e79d9a303bcbc70fb988958b1` (SHA-256
`394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2`); the
plugin README's First run downloads it to `asr/` in the data folder and
checks that hash. It runs
offline. Convert to 16 kHz mono, set `-l` to the narration language and keep
timestamps on: `-nt` drops words near the 30-second window edges.

```sh
ffmpeg -v error -i phrase.wav -ar 16000 -ac 1 phrase-16k.wav
whisper-cli -m ~/.local/share/narrate-video/asr/ggml-large-v3-turbo-q5_0.bin -l en -np -otxt -of phrase-heard -f phrase-16k.wav
```

`phrase-heard.txt` holds the transcript. For the film, extract its audio the
same way (`ffmpeg -v error -i walkthrough.mp4 -vn -ar 16000 -ac 1 final-16k.wav`)
and pass the text file to `qa.py --transcript`. The mlx-community Whisper
conversions lack the tokenizer files MLX-Audio needs (`Processor not found`).
When a difference is a run of words missing at the end or near a 30-second mark,
transcribe that stretch alone before regenerating speech.

Everything the agent checks is silent; it never plays audio through the
speakers. Listening to the entire final track and watching the complete film at
normal speed with sound is the user's check: give them the file and list it as
pending. Inspect the first/middle/last frames and every cut at full resolution.
Check clipping, loading frames, unexpected flashes, caption transitions and
actual action results. Review a phone-sized rendering for readable UI and captions;
crop deliberately or recompose if the essential detail is too small.

Record the MP4 SHA-256, reviewer, date, actual checks and limitations in a
separate QA note. Include final-audio transcription, caption timing assessment,
measured LUFS/true peak, boundary inspection and playback duration/ended state.
Do not automatically mark these checks passed after encoding. Automated playback
completion proves player traversal, not that a human heard intelligible speech.

An export is complete only when the requested verification has been performed
or an explicit limitation is reported. Publication and device/user acceptance
are distinct from a successful local render.
