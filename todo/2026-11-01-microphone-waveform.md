# Restore the live microphone waveform

User clarification: fix the wave while recording, not the playback wave. The recording view now uses the earlier scrolling bars built from actual microphone peak samples, instead of the instantaneous line. Sampling runs at a stable cadence; the canvas scales to its displayed size and pixel density, follows Arabic direction, and shows a quiet baseline before recording.

The previous playback renderer and saved/new-take controls are restored unchanged. The local running studio and portable skill use the same recording renderer. No microphone capture or replacement of reference recordings was performed for verification; an isolated, visibly labelled synthetic-audio fixture exercised recording and stopping. The source package excludes that fixture and private voice data.
