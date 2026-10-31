# Decide the Spoken-Answer Flow and Visual Direction

Id: 05
Parent: [Vocab-Learn Browser V1 Decision Map](../map.md)
Type: prototype
Labels: wayfinder:prototype
Mode: HITL
Status: resolved
Assignee: /root
Blocked by: 01, 02, 04
Prototype branch: prototype/spoken-card-ui
Prototype commit: a3fe7b400fff94264c6550c3f5aaa94d9bd9b2dd
Visual direction: A - Fieldnotes (selected by the user)

## Question

Given that only Speak can lead to a correct answer and all three actions lead to the back, what is the minimum flow through question display, recording, stopping, transcription, judging, reveal, and the next card? Discuss a disposable interaction prototype with the user instead of implementing the production application.

Expose the choices around click-to-record versus hold-to-record, answer reveal timing, re-recording before reveal, transcript visibility, microphone denial, ASR/judge failures, and duplicate clicks or interrupted sessions. Distinguish revealing immediately on pressing Speak from revealing after the spoken answer, while preserving the requirement that every action ultimately shows the answer.

Identify fair timing boundaries that exclude model waiting; leave thresholds to the feedback decision. Do not silently treat technical failures as wrong answers. Use English-only interface copy and desktop Chrome/Edge scope. Link the prototype asset and resolve through real user feedback.

Use the settled card model: one or more blanks, one spoken response for the whole card, unrestricted text answers, and one reference answer. Include a multi-blank example without deciding partial-credit rules in the prototype.

The user requires an attractive frontend. Compare three structurally distinct visual directions on one disposable route, with deliberate typography, spacing, color, navigation, card hierarchy, and recording/result states. Show enough surrounding deck/progress context to judge the interface as an application. Keep text legible and controls accessible; interface copy is English.

Use simulated transcription and grading for this design exercise, explicitly label those results as examples, and expose the current interaction state. The prototype does not select a production framework, validate a real model, or settle mastery labels or intervals. Ask the user for concrete visual and interaction feedback before resolving this ticket.

## Prototype assets

- Interactive HTML prototype (local-only reference: `/tmp/vocab-learn-prototype-card-ui/docs/prototypes/card-review-prototype/index.html`), with three layouts selected by the bottom arrows or the variant query parameter. It opens directly as a local file.
- Run instructions and verification limits (local-only reference: `/tmp/vocab-learn-prototype-card-ui/docs/prototypes/card-review-prototype/README.md`).
- A — Fieldnotes (local-only reference: `/tmp/vocab-learn-prototype-card-ui/docs/prototypes/card-review-prototype/previews/fieldnotes.png`): a warm dashboard with sidebar navigation and a daily progress rail.
- B — Studio (local-only reference: `/tmp/vocab-learn-prototype-card-ui/docs/prototypes/card-review-prototype/previews/studio.png`): a dark, focused canvas with a large prompt and minimal surrounding information.
- C — Atlas (local-only reference: `/tmp/vocab-learn-prototype-card-ui/docs/prototypes/card-review-prototype/previews/atlas.png`): an editorial split layout with a study queue and a separate practice page.
- Fieldnotes answer side (local-only reference: `/tmp/vocab-learn-prototype-card-ui/docs/prototypes/card-review-prototype/previews/fieldnotes-back.png`).
- Fieldnotes while checking (local-only reference: `/tmp/vocab-learn-prototype-card-ui/docs/prototypes/card-review-prototype/previews/fieldnotes-checking.png`): the reference is already visible while transcription and judging are pending.

The complete prototype and previews are captured at the branch and commit above. Local paths are review conveniences; the Git reference retains the primary source independently of the temporary worktree.

## Comments

2026-10-30: Prepared a styled prototype after resolving the learning-unit decision and recording the user's frontend-quality requirement. The proposed flow is click Speak to start, Stop & check to submit, then reveal after simulated transcription/judging; cancellation, retry, and unassessed reveal can also be explored. This is a proposal awaiting user feedback, not a closed interaction decision.

Headless Chromium checks passed for variant URLs, keyboard/form handling, multi-blank and sentence examples, Skip/Forgot reveal, complete/partial mock responses, transcription/judge failure recovery, cancellation, local-file switching, and desktop layouts. Real microphone capture, MiniMax calls, Edge, and production behavior were not exercised.

2026-10-31: The user explicitly selected A — Fieldnotes. This settles the visual direction; it does not imply approval of the recording, reveal, transcript, or recovery behavior. The selection is captured on the prototype branch at the commit above.

The user also accepted the Chrome-based automation path and confirmed that one working browser-control approach is sufficient. CDP already exercised the prototype's navigation, DOM interaction, state checks, and screenshots. Continue QA with that verified path; a separate Playwright MCP repair or installation is not needed. No Playwright configuration was changed or represented as tested.

2026-10-31: The user accepted the recommended recording and reveal choices, followed by cancellation, readonly transcript display, and processing/failure navigation. The updated prototype and CDP checks reflect these choices; the final resolution follows.

## Answer

Resolved through the user's explicit selection of A and answers to interaction questions Q1-Q5 on 2026-10-31.

- **Visual direction:** A — Fieldnotes, with its warm light palette, sidebar, study card, and daily progress rail. Keep all system copy in English and learning content language-independent.
- **Question:** Skip and Forgot reveal the answer immediately. Speak begins one recording for the whole card, including all blanks.
- **Before submission:** Cancel discards the current recording and returns to the question, allowing another recording. It does not reveal the reference. Click Stop & check to stop and commit the spoken response.
- **Submission and reveal:** Fix the recording for this attempt before releasing the reference answer. Immediately show the answer and explanation; transcription and judging continue while the user reads the back. Upload and model delays must not become user response time.
- **Transcript:** Display the ASR text as readonly Your response when available. Do not accept manual transcript edits as a replacement scored answer.
- **Navigation:** Keep Next card unavailable while checking. Enable it after assessment. Duplicate stop/submit actions must not create multiple scored attempts.
- **Technical failures:** Offer retry of the same submitted recording while the attempt remains nonterminal, or a server-confirmed unassessed exit. The first committed terminal result wins; late work cannot grade an exited attempt. [Completion/interruption rules](19-attempt-completion-and-interruption.md) specify bounded waiting and result races. A failed service call is not evidence of a wrong answer. After reveal, a fresh recording cannot overwrite this attempt.
- **Microphone failures:** Expose permission/device problems and allow recovery without a grade penalty. Waiting for permission itself offers Cancel; obsolete grants stop all returned tracks, and obsolete rejections cannot overwrite newer state. Logical cancellation does not dismiss the browser's native permission prompt. Actual hardware behavior requires implementation validation.

The disposable prototype is captured on `prototype/spoken-card-ui` at `a3fe7b400fff94264c6550c3f5aaa94d9bd9b2dd`. CDP assertions covered immediate reveal before ASR, a fixed submission, pre-submission cancellation, processing navigation restrictions, readonly text, duplicate actions, mock success/partial outcomes, both service failures, retry, unassessed continuation, and the shared layouts. No real microphone or paid model request was used.

Handoff: [Define Grading, Five-Level Feedback, and Response Timing](06-grading-feedback.md) owns feedback labels, timing thresholds, partial answers, Skip semantics, and grading uncertainty. [Decide Replaceable ASR and Judge Boundaries](09-provider-configuration.md) and [Decide the Application, Persistence, and Compose Boundaries](10-architecture-and-storage.md) own the production contracts, immutable submission, interruption handling, and atomic result application. This UI prototype is not production code.
