# Narrate launch — 1 November 2026

Confirmed identity: Narrate at https://narrate.humanquest.net, separate from
Walkthrough. Confirmed public narration: the creator's cloned voice. Selected
mark: exploration 03, the ribbon passing through a frame.

The local studio visual refresh preserves the existing five-step flow, original
English/Arabic recordings, chosen model and latest audition. The site includes
a functional language/model explorer and ten captioned review films.

Media review: all ten films decode and have measured loudness and caption files.
Eight have local ASR comparisons; Bengali and Urdu are outside installed Qwen
ASR coverage. Fluent pronunciation/context review remains pending and is stated
in the public gallery. Screen stills are identified as stills. No personal
microphone references or model weights are in the public package.

The repository and deployment use local verification commands. GitHub Actions
must stay disabled; there is no automatic Git deployment integration. The
Human Quest AI Patterns entry is published from an isolated checkout, preserving
unrelated edits in its main working tree. Its production HTML and sitemap were
verified after a local Next.js build and explicit prebuilt deployment.

The Vercel project is prj_t6h2A7635TU7lkXUiR5pttsVTYk7 under the existing Human
Quest team. The custom domain is assigned to that project. Authoritative DNS
lives at GreenGeeks. The new `narrate` CNAME points to `cname.vercel-dns.com`,
with no existing record replaced. Both authoritative nameservers report it;
Vercel reports no DNS conflict or misconfiguration, and the issued TLS certificate
serves HTTP 200. The public domain was also opened successfully in a browser.

Public source: https://github.com/alibad/narrate

Public showcase: https://narrate.humanquest.net

Published pattern: https://www.humanquest.net/ai-patterns#narrate

The 38.6-second studio helper completed normal-speed, unmuted browser playback
without a media error. The gallery films passed full decode and stream checks;
these technical checks do not establish fluent pronunciation approval.
