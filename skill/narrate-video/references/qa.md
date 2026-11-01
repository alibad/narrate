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

Transcribe the final decoded audio with a selected transcription tool, never
substitute the planned text as a transcript. The optional transcript comparison
preserves word order, repetitions, numbers and negations. A difference is a
review item, not proof that synthesis or ASR was wrong. Correct material errors
and document pronunciation/ASR ambiguities. Missing transcription remains pending.

Listen to the entire final track and play the complete film at normal speed
with sound. Inspect the first/middle/last frames and every cut at full resolution.
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
