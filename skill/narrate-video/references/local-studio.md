# Language-first local voice setup

Open the real HTML microphone studio first. Its flow is **Languages → Model →
Setup → Your voice → Audition**. Preserve existing recordings. Do not substitute
a preset or a static playback page for this workflow.

## Start locally

The studio picks its runtime from the computer it runs on:

- **Apple Silicon Mac (MLX):** all three models. The tested runtime is Python
  3.12 and MLX-Audio 0.5.1. For a new machine, create an isolated Python 3.12
  environment and install `mlx-audio==0.5.1`, `huggingface-hub` and the core
  Pillow requirement there.
- **Windows or Linux with an NVIDIA GPU (CUDA):** Chatterbox Multilingual from
  the upstream PyTorch checkpoint. Use a Python whose PyTorch reports
  `torch.cuda.is_available()`, with `chatterbox-tts` and `huggingface-hub`
  installed. Tested with chatterbox-tts 0.1.7 and torch 2.11 (CUDA 12.8) on an
  RTX 5090. chatterbox-tts pins an older torch that has no kernels for the
  newest cards, so on those install it into a virtual environment built with
  `--system-site-packages` over a working CUDA torch instead of letting it
  downgrade torch. OmniVoice and Qwen3-TTS Base have no CUDA build here yet; the
  studio shows them as not available rather than substituting.

Make FFmpeg/ffprobe available in either case. Never alter a working speech
environment. `NARRATE_VIDEO_RUNTIME=mlx|cuda|none` overrides detection, for
tests only.

Start with private data storage and offline inference:

```sh
NARRATE_VIDEO_DATA=/chosen/private/studio-data \
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
python scripts/voice-studio/studio.py
```

On Windows PowerShell, set each variable with `$env:NAME = "value"` first.

The agent opens `http://127.0.0.1:8765` in a microphone-capable browser.
`VOICE_STUDIO_PORT` changes the port. If OmniVoice already exists, set
`NARRATE_VIDEO_MODEL_DIR` to that model folder before starting. MLX models live
under the private data folder. The CUDA build downloads into the Hugging Face
cache (`HF_HUB_CACHE`, by default inside the private data folder); point
`HF_HUB_CACHE` at an existing cache that already holds the pinned revision and
setup only loads it. No model weights are bundled.

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
4. Reuse a recording or click **Record my voice**. Read the displayed passage,
   stop, listen and **Save this take**. Aim for 5–10 seconds; the accepted range
   is 3–35 seconds. Existing longer references are preserved. Re-recording
   retains the previous WAV and transcript under private `voice-history`.
   No microphone starts automatically. Other saved languages require an explicit
   reference choice; explain that cross-language references can carry accents.
5. Generate, listen to and accept an audition in every selected language. Click
   **Save my voice profile**. The user's listening approval determines quality;
   recommendation scores do not measure audio quality.

## Model policy and evidence

| Model | Coverage in this studio | Total model data | Runs on | Selection notes |
|---|---|---:|---|---|
| OmniVoice | All 32 offered languages/varieties | ~1.64 GB | Mac | Broad coverage, including offered Arabic varieties |
| Chatterbox Multilingual | 23 languages | ~1.43 GB (Mac) / ~3.21 GB (NVIDIA) | Mac, NVIDIA | Mac size includes the ~495 MB S3 speech tokenizer |
| Qwen3-TTS Base 1.7B | 10 languages | ~4.54 GB | Mac | Cloning checkpoint; excludes Arabic |

The Mac builds are pinned MLX conversions; the NVIDIA build is the upstream
ResembleAI checkpoint at a pinned revision. See `scripts/voice-studio/catalog.py`
for exact repositories, revisions, dependencies and the eligibility policy. The Qwen
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
request and serializes model loading/inference on a single worker thread.
Keep private data, weights and generated personal audio outside public packages.
