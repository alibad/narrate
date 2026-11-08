---
name: narrate-video
description: Make narrated explainer, demo and product videos from real screens and footage, in the user's own recorded or cloned voice, with audio-timed captions, evidence labels and playback QA. Use when the user wants a narrated video, voiceover, screen walkthrough, demo or explainer film, wants to record or clone their voice for narration, or wants one video in several languages. The voice studio runs locally on Apple Silicon Macs or NVIDIA GPUs; rendering runs anywhere with Python, Pillow and FFmpeg.
---

# Narrate

Make a video the audience can follow and the visible evidence supports. Work in
a local production folder. You write the scripts, capture entries and edit
plans; ask the user only about audience or voice choices that change the
result. Never make the user edit JSON.

## Where it runs

- **Voice studio** (record, clone, audition): an Apple Silicon Mac (OmniVoice,
  Chatterbox Multilingual, Qwen3-TTS Base) or Windows/Linux with an NVIDIA GPU
  (Chatterbox Multilingual). See [local studio](references/local-studio.md).
- **Renderer and QA**: any system with Python 3.12+, Pillow and FFmpeg.
- With neither studio runtime, use speech the user supplies or a voice tool the
  user chooses ([speech and auditions](references/speech.md)), and say so.

## Choose a small story

Start with the useful result, then the few steps needed to understand it. Use
the requested length and format; otherwise make a short first cut. One idea per
scene, in spoken language. Check product claims against the running
application. A screenshot explains a state; an action clip shows how it
changes. Identify editorial cards as editorial.

Keep authenticated product setup outside this skill and capture only authorized
records and actions. A rehearsal can write data: never replay it automatically.
Keep loading and preparation outside takes. Never change a product to fake a
successful demonstration.

## Establish the narrator

**Open the recording studio first** ([local studio](references/local-studio.md)).
The user chooses languages, reviews compatible cloning models, starts setup,
records or reuses their voice, and accepts an audition in every selected
language. Explain the recommendation and allow eligible overrides. Use the
accepted voice profile. Do not replace this with a static audition page or a
preset. The first committed English recording supplies other languages unless
an explicit or language-specific recording exists. New takes and reference
choices remain previews until **Use this one**; only that language changes.
Replacing English invalidates inherited auditions, never separate language
approvals. Pronunciation practice shows a Latin-letter guide and a language example from
the selected model. OmniVoice can generate the independent example without a
user reference; the separate own-voice guide uses that model with the saved
recording. Neither action accepts an audition or changes the narrator. Missing
independent adapters fail explicitly; never substitute OS speech or another
model. Synthetic examples still need listening review for pronunciation quality.
While recording or listening approval is pending, prepare scripts and
captures, but do not finish with a substitute voice.

Supplied speech or another adapter is used only when the user chooses it
([speech and auditions](references/speech.md)). Nothing is implicit: no
provider, endpoint, credentials, model download or fallback. State the actual
provider, model and revision, voice reference or preset, language and delivery
settings. Never call a preset the user's voice.

Generate a short audition with the intended text; `scripts/studio.py` builds a
local comparison page for several takes. Let the user listen when preference
matters; otherwise pick a clear take and say which. Transcribe every phrase and
check for omissions, invented endings, numbers and negations. Cloned voices
often misread acronyms such as "AI": spell them out ("A I,") or reword, then
check again. Regenerate a bad phrase before assembling the film.

For English/Arabic or mixed-language work, confirm each model supports the
language and dialect; an unsupported language fails rather than changing the
narrator. Arabic needs a font with the glyphs, Pillow with RAQM shaping, and a
reader who knows the language. Do not judge dialect quality from an English test.

## Capture and emphasize

Read [capture](references/capture.md) for the optional browser adapter,
readiness, geometry checks, cards and highlights. For native applications use
their own capture tools and pass the files to the same renderer.

Hold a stable screenshot while explaining. For behavior, prepare the page,
confirm targets, fonts, images and repeated pixel stability, then record a
bounded take around the action and its result at real speed. Readiness does not
prove a recorder has no missing edges or flashes; never hide an unexplained
strip or use stills to cover a recorder fault.

A highlight only directs attention and must not hide the evidence. For phones,
use deliberate detail crops or a portrait composition, keep the originals and
record the crop. Check everything at the size people will watch it.

## Assemble and review

Read [edit format](references/edit-format.md). The offline renderer takes local
images, clips and speech, keeps captions outside the picture, keeps action speed,
holds a clip's last frame and exports MP4, SRT, narration and a receipt. For a
finished film it can also set a frame colour, hide the label header, push in
slowly on stills and crossfade between scenes, without moving any timing.

```sh
python scripts/render.py production/plan.json --check
python scripts/render.py production/plan.json production/new-cut
python scripts/qa.py production/new-cut/walkthrough.mp4 production/new-cut/evidence.json production/new-qa --transcript production/final-transcript.txt
```

Time captions from measured phrase audio or reviewed alignment data.
`voice.py compose` derives phrase cues from separate audio files; it does not
estimate word positions. Captions and SRT share the same frame boundaries. A
silent storyboard needs `--silent-preview` and is never a finished video.

Follow [QA](references/qa.md): decode, transcribe the final audio and compare it
in order, measure loudness, inspect every cut, review at phone size and play the
whole film at normal speed with sound. Checks you could not do stay pending.
Keep synthetic tests separate from behavior observed in the real product.

## Deliver

Deliver the local video with the short evidence needed to judge it: what it
shows and any material gap in verification. Uploading, publishing or sending
needs authorization for that action. Before redistributing, review every file
and spoken sample for private content and establish the rights to everything in
it. See [publication](references/publication.md).
