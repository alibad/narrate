# Language-first local voice setup

Open the real HTML microphone studio first. Its flow is **Languages → Model →
Setup → Your voice → Audition**. Preserve existing recordings. Do not substitute
a preset or a static playback page for this workflow.

## Start locally

Reuse a compatible Apple Silicon environment when present. The tested runtime
is Python 3.12 and MLX-Audio 0.5.1. For a new machine, create an isolated Python
3.12 environment and install `mlx-audio==0.5.1`, `huggingface-hub` and the core
Pillow requirement there; make FFmpeg/ffprobe available. Never alter a working
speech environment. These bundled adapters require Apple Silicon macOS.

Start with private data storage and offline inference:

```sh
NARRATE_VIDEO_DATA=/chosen/private/studio-data \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
python scripts/voice-studio/studio.py
```

The agent opens `http://127.0.0.1:8765` in a microphone-capable browser.
`VOICE_STUDIO_PORT` changes the port. If OmniVoice already exists, set
`NARRATE_VIDEO_MODEL_DIR` to that model folder before starting. Other models
live under the private data folder. No model weights are bundled.

## Complete setup in the browser

1. Choose narration languages. The list offers 32 documented languages and
   varieties, up to 12 per profile. Existing same-language recordings remain.
2. Review eligible cloning models and the recommendation. Language coverage
   comes first, followed by the chosen preference: reuse an installed model
   (favoring the current one) or the smallest total download. The user can
   override the recommendation among eligible choices.
3. Start setup. Only that model and its required components download, at pinned
   revisions. Progress distinguishes downloading from loading/verification.
   A download is not marked ready until its model loads. No cloud fallback.
4. Record English once, stop, listen and choose **Use this one**. That committed
   English recording is automatically selected for other languages that have no
   explicit choice or their own saved recording. Existing own-language references
   and explicit saved choices are preserved. Cross-language references can carry
   accents; the user still auditions each target language. To replace one
   language, record it or preview a saved reference, then choose **Use this one**.
   Stopping a recording or browsing the selector never commits a replacement.
   Aim for 5–10 seconds; the accepted range is 3–35 seconds. Existing longer
   references are preserved. Re-recording retains the previous WAV and transcript
   under private `voice-history`. No microphone starts automatically. Replacing
   English stales auditions that used the prior English audio, while an unchanged
   language-specific reference retains its approval. Selecting the already-active
   recording is a no-op for readiness. No audition is accepted automatically.
5. Generate, listen to and accept an audition in every selected language. Click
   **Save my voice profile**. The user's listening approval determines quality;
   recommendation scores do not measure audio quality.

## Model policy and evidence

| Model | Coverage in this studio | Total model data | Selection notes |
|---|---|---:|---|
| OmniVoice | All 32 offered languages/varieties | ~1.64 GB | Broad coverage, including offered Arabic varieties |
| Chatterbox Multilingual | 23 languages | ~1.43 GB | Includes ~495 MB required S3 speech tokenizer |
| Qwen3-TTS Base 1.7B | 10 languages | ~4.54 GB | Cloning checkpoint; excludes Arabic |

These are pinned MLX conversions. See `scripts/voice-studio/catalog.py` for exact
repositories, revisions, dependencies and the eligibility policy. The Qwen
CustomVoice checkpoint is not offered as a cloning model. Coverage is a
capability filter, not a guarantee of pronunciation or dialect quality.

Primary references: [OmniVoice](https://github.com/k2-fsa/OmniVoice), its
[language list](https://github.com/k2-fsa/OmniVoice/blob/master/docs/languages.md),
[Chatterbox MLX](https://huggingface.co/mlx-community/chatterbox-8bit),
[upstream Chatterbox](https://huggingface.co/ResembleAI/chatterbox), and
[Qwen3-TTS Base](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base).
Recheck upstream coverage before updating this catalog; do not invent quality
rankings. Review conversion and upstream licenses before redistribution.

## Generate narration with the saved profile

```sh
python scripts/studio_speech.py phrase.txt new-phrase.wav --language en
```

The client follows the selected model and language, requires accepted auditions,
checks the model/language/reference identity, validates audio and refuses output
overwrites. Model or recording changes require fresh auditions. Pass the WAVs to
`voice.py compose`, then `render.py`. Missing references fail explicitly.

Recordings, transcripts, configuration, accepted takes, models and setup logs
stay in private storage. Inference uses offline loading; the selected setup
worker temporarily enables network access for model downloads. The local server
binds only to loopback and rejects foreign origins. It snapshots references per
request and serializes model loading/inference on a single MLX worker thread.
Keep private data, weights and generated personal audio outside public packages.
