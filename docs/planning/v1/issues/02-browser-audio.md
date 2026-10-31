# Verify Desktop Recording and ASR Audio Paths

Id: 02
Parent: [Vocab-Learn Browser V1 Decision Map](../map.md)
Type: research
Labels: wayfinder:research
Mode: AFK
Status: resolved
Assignee: /root/research_audio
Blocked by: none
Research branch: research/browser-audio
Research commit: dd291a9ca16975d6b608ae6d17208160318aae2e

## Question

What is the smallest viable path from desktop Chrome/Edge recording to audio accepted by MiniMax ASR? Use platform specifications, first-party browser documentation, and official ASR documentation to verify secure contexts, microphone permissions, format detection, WebM/Opus or WAV compatibility, conversion requirements and deployment cost, empty/silent recordings, cancellation, and observable failure states.

Identify browser timing points that can separate user thinking/speaking time from network, ASR, and LLM latency. Do not choose the final timing policy or interaction, and do not claim real browser testing from documentation alone.

Do not assume English learning content, read credentials, or make paid calls. Produce an English document with primary-source citations and retain a `research/browser-audio` branch reference.

## Answer

Resolved on 2026-10-30 by the assigned research agent.

The platform and format investigation is complete. Native recording is available, but documented Opus support does not establish acceptance of browser WebM containers. The research asset distinguishes direct-upload and conversion candidates, secure-context requirements, observable timing, and the real-browser checks still needed. No recording path or interaction policy was selected or executed.

Asset: [English research findings](../../../research/v1-browser-audio.md).

Provenance: `research/browser-audio` at `dd291a9ca16975d6b608ae6d17208160318aae2e`. The repository asset matches that research commit. No credentials, paid model calls, or application changes were used.
