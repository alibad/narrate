---
name: narrate-video
description: Create narrated product videos using a language-first local recording studio in the user's own voice, stable screenshots, real action clips, captions, and playback QA.
---

# Narrate

Create a video the audience can follow and the visible evidence can support.
Work in a local production folder. The agent writes scripts, capture entries and
edit manifests; ask the user for audience or voice preferences only when they
materially change the result. Do not make the user configure JSON.

## Choose a small story

Start with the useful result, then the few steps needed to understand it. Use
the requested length and format; otherwise make a short first cut. Write one
idea per scene, in spoken language. Check product claims against the running
application. A screenshot explains a state; a continuous action clip shows how
the state changes. Editorial cards must be identified as editorial material.

Keep authenticated product setup outside the portable skill. Capture only
authorized records and actions. A rehearsal can perform writes: do not replay
it automatically. Keep incidental loading and preparation outside takes.
Do not modify a product to manufacture a successful demonstration.

## Establish the narrator

**Open the recording studio first.** Follow [local studio](references/local-studio.md).
The user chooses languages, reviews compatible cloning models, starts local
setup, records or reuses their voice, and accepts an audition in every selected
language. Recommendations filter documented coverage and cloning capability,
then honor the user's installed-model or download-size preference. Explain the
reason and permit eligible overrides. Use the resulting accepted voice profile.
Do not replace this workflow with a static audition page or another preset.
Reuse saved recordings where appropriate. While recording or listening approval
is pending, prepare scripts and captures; do not finish with a substitute voice.

Read [speech and auditions](references/speech.md) when generating or comparing
voices. Use supplied speech or a different adapter when the user explicitly chooses it.
No provider, endpoint, credentials, model download or fallback is implicit.
State the actual provider, model/revision, preset or authorized voice reference,
language and delivery settings. Never describe a preset as the user's voice.

Generate a short audition with the intended text. Use `scripts/studio.py` to
make a local comparison page when there are multiple takes. Let the user hear
the choices when preference matters; otherwise select a clear take and state
the choice. Listen and transcribe for omissions, invented endings, numbers and
negations. Regenerate a bad phrase before assembling the film.

For English/Arabic or mixed-language work, confirm each selected model supports
the requested language and dialect. Unsupported languages fail rather than
change the narrator. Arabic needs a font with the required glyphs, RAQM shaping,
and a reader competent in the language. The studio filters model choices for Arabic;
model weights are downloaded separately. Do not infer dialect quality from an English test.

## Capture and emphasize

Read [capture](references/capture.md) for the optional browser adapter, target
readiness, geometry checks, cards and highlights. Use supported native capture
tools for native applications, passing their files to the same renderer.

Use a stable screenshot while explaining. For behavior, prepare the page,
confirm visible targets/fonts/images and repeated pixel stability, then start
and stop a bounded take around the actual action and result. Preserve speed.
Capture readiness is separate from proving a recorder has no missing edges or
flashes. Never hide an unexplained strip or imply stills repair a recorder.

Use a highlight only to direct attention; it must not obscure the evidence.
Use deliberate detail crops or a portrait composition for phones, retaining
the originals and recording the crop. Inspect at the intended viewing size.

## Assemble and review

Read [edit format](references/edit-format.md). The offline renderer accepts local
images, clips and speech, keeps caption space outside the UI, preserves action
speed, holds the final clip frame and exports MP4, SRT, narration and a receipt.

```sh
python scripts/render.py production/plan.json --check
python scripts/render.py production/plan.json production/new-cut
python scripts/qa.py production/new-cut/walkthrough.mp4 production/new-cut/evidence.json production/new-qa
```

Use measured phrase-audio boundaries or reviewed alignment data for captions.
`voice.py compose` derives phrase cues from the separate audio files. It does
not estimate word positions or establish precise word alignment. Captions and
SRT share the same output-frame boundaries. A silent storyboard requires
`--silent-preview`; it is never a finished narrated video.

Follow [QA](references/qa.md): decode, final-audio transcription and ordered
comparison, loudness measurement, cut-boundary inspection, small-screen review
and complete normal-speed playback with sound. Missing checks remain pending.
Keep synthetic tests distinct from observed behavior in the actual product.

Deliver the local video and the concise evidence needed to assess it. Say what
it shows and any material verification gap. Uploading, publishing or sending
requires authorization for that action. Before redistribution, separately
review every file and spoken sample for private content, establish ownership
or redistribution rights and choose a license. See [publication](references/publication.md).
