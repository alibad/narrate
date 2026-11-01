# Narrate

Good explanations speak your language.

[Narrate](https://narrate.humanquest.net) is a standalone Human Quest project:
a local voice/video skill and a public gallery of ten narrated, source-linked
explorations. It is separate from Walkthrough Studio.

## The local skill

`skill/narrate-video/` contains the actual microphone studio, pinned model setup,
narration client, capture adapter, renderer and media QA.

**Languages → Model → Setup → Your voice → Audition**

Choose languages first. The studio explains compatible cloning models, downloads
and verifies the chosen model, then records or reuses your voice. Listen to an
audition in each selected language before saving the profile. The refreshed
interface has a dark editing-suite layout, live recording bars that build as you
speak, saved-audio waveforms, playback cursors, clear reference labels and motion
that respects reduced-motion settings.

The voice studio runs on Apple Silicon macOS (Python 3.12 with MLX-Audio 0.5.1:
OmniVoice, Chatterbox Multilingual and Qwen3-TTS Base) or on Windows and Linux
with an NVIDIA GPU (CUDA PyTorch with chatterbox-tts: Chatterbox Multilingual).
Both need FFmpeg. The core renderer runs anywhere with Python, Pillow and
FFmpeg, and also accepts supplied audio. Weights download separately. No cloud
speech key is required. See the bundled `references/local-studio.md` for the
agent's environment setup procedure.

In Claude Code, install the skill at `~/.claude/skills/narrate-video` and start
with `/narrate-video`; in Codex, use `$narrate-video`.

```sh
PYTHON=/path/to/audio-python sh skill/narrate-video/scripts/verify.sh
```

## The website

Node 22 and Python 3 build and preview the static website. No npm dependencies.

```sh
npm run build
npm run verify
npm run dev
# http://127.0.0.1:8770/
```

The site has a real language/model explorer, a setup guide, a portable skill ZIP
and ten H.264/AAC preview films with captions and source links. Every film and
the studio helper have a crawlable watch page with a transcript and video
structured data; the sitemap includes their video URLs. Footer links connect
Narrate to Human Quest and the AI Patterns collection. The public site
never accesses a microphone or automatically connects to a private local API.
Actual recording and inference happen in the installed local skill.

The build packages `skill/narrate-video/` into the download, excluding personal
recordings, weights, private paths and caches. Raw production, reference audio,
transcripts and QA receipts remain under ignored `production/`.

## First collection

English, Mandarin Chinese, Hindi, Spanish, Modern Standard Arabic, French,
Bengali, Portuguese, Indonesian and Urdu follow the 2026 total-speaker selection
(first- and second-language speakers), with methodology linked in the gallery.
Each film is one editorial choice, not a definition of a language's cultures.
The edit uses real screenshots of observed article states, not continuous click
recordings. `content/gallery.json` contains scripts, article URLs and credits.

The creator authorized the cloned voice for public examples. Arabic uses the
saved Arabic reference; the other languages use the English reference. Eight
are cross-language references. The films are published as review cuts: fluent
pronunciation and cultural-context review remain open. Installed Qwen ASR covers
eight collection languages; Bengali and Urdu need a separate fluent review.

## Local verification and release

`npm run verify` checks selection policy, navigation, assets, real video streams,
captions and the absence of hosted workflows. The bundled skill has 45 local
behavioral tests, including CJK wrapping, caption sizing, missing-glyph checks,
reference preservation, partial model downloads, the NVIDIA model catalog,
crossfade timing and local stylesheet delivery. On Windows the symlink test
skips unless the account may create symlinks.

Deploy local build output through the configured Vercel project; no GitHub
Actions or automatic Git deployment is used. Set `PUBLIC_SITE_URL` only to a
verified HTTPS origin before the final public build. Reference audio and model
weights must remain outside any public deployment or repository.

```sh
PUBLIC_SITE_URL=https://narrate.humanquest.net vercel build --prod
vercel deploy --prebuilt --prod
```

Code: [MIT](LICENSE). Model and media terms: [NOTICE.md](NOTICE.md).
