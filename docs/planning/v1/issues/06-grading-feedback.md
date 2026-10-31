# Define Grading, Five-Level Feedback, and Response Timing

Id: 06
Parent: [Vocab-Learn Browser V1 Decision Map](../map.md)
Type: grilling
Labels: wayfinder:grilling
Mode: HITL
Status: resolved
Assignee: /root
Blocked by: 05
Prototype branch: prototype/spoken-card-ui
Prototype commit: 38f577fa9d4139f7f94a7ca16eaa658d65169728

## Question

Scope note: this resolved rubric is the Generic Card baseline. The subsequently requested recognition/production goals are addressed in [Define Vocabulary-Direction Grading and Timing](16-vocabulary-grading.md); a fully equivalent native-language meaning must not be automatically downgraded by applying the Generic synonym rule without that decision.

How should AI assessment of the transcript and observable user response time produce five understandable, humane mastery-feedback levels? Distinguish the result of one attempt from longer-term mastery, and establish which meaning the back of the card communicates.

Preserve the user's intended A forgotten, B substantially wrong, C approximate/incomplete, D slow fully correct, and E fast fully correct outcomes; discuss final English labels. Cover fast near-synonyms, inflections/spelling variants, full-sentence answers, different answer lengths, and uncertain ASR. Define the card's answer as the source of truth, the constrained fields returned by the judge, and rules enforced by the application. A prompt alone is not a complete boundary for untrusted answer text.

Cards may have multiple blanks addressed by one unrestricted spoken response and one reference answer. Explicitly decide how missing, swapped, or partly correct blanks produce the overall card result; scheduling and collection membership remain per card. Do not add a manually maintained list of accepted variants. AI evaluates alternative formulations, with its generated system feedback in English.

Decide timing start/stop points, testable V1 fast/slow thresholds, and treatment of re-recording or corrections. Network and model waiting must not silently affect mastery. Specify whether Skip has a grade or counts in attempts and accuracy. Record a small set of decisive examples. Scheduling remains a separate decision.

## Comments

2026-10-31: The user chose current-attempt feedback with an approximate Next review time. Synonym/paraphrase answers belong to C regardless of speed; any clearly wrong or missing blank makes the whole card B. Timing runs from the fully displayed question to submission, including thinking and rerecording but excluding permission, upload, and model waiting. Skip is neutral: outside A-E, no collection/streak change, and excluded from accuracy. Final English labels and the initial timing heuristic were delegated to the agent. The scheduling ticket owns actual intervals; the display must use its persisted due time.

## Answer

Resolved on 2026-10-31 through the user's answers to grading questions Q1-Q5, including the explicit clarification that C is independent of speed. English copy and the initial timing budget were delegated to the agent.

### Feedback and rubric

Use the heading **Your recall this time**. These levels describe this attempt, not a permanent or historically aggregated mastery score.

| Grade | English label | Rule |
| --- | --- | --- |
| A | Needs a refresh | The user chooses Forgot; ASR and AI judging are unnecessary. |
| B | Needs practice | A valid judged response has any clearly incorrect or unanswered blank. The whole card enters Forgot. |
| C | Meaning recalled | All blanks convey the intended meaning, but at least one uses a synonym/paraphrase instead of recalling its target expression. Speed never changes C. |
| D | Correct recall | Every blank recalls the target or a genuinely equivalent form, with response time above the initial fast budget. |
| E | Quick recall | Every blank recalls the target or a genuinely equivalent form, with response time at or below that budget. |

Later display-copy update: [Define Vocabulary-Direction Grading and Timing](16-vocabulary-grading.md) unifies C's label as Partial recall across card sources. The Generic C eligibility in this historical table remains unchanged.

A missing or wrong blank takes precedence over a synonym elsewhere: the result is B, not C. Equivalent spelling and contextually correct inflections can count as target recall. A completed sentence is acceptable; determine which answers it supplies rather than requiring a literal match of the whole transcript. A different synonym is meaning recall even if it is fluent and grammatically correct. The AI evaluates these distinctions against the single reference answer and context; there is no author-maintained accepted-variants list.

For an expression-recall Generic cloze such as reference call off, the benchmark includes that target expression: cancel conveys a suitable meaning but remains C. State that goal in the Judge input and handoff; C does not assert that the English sentence is ungrammatical. This is not literal whole-transcript matching: equivalent forms and complete spoken sentences remain accepted. Test the live Judge's interpretation separately from a fake's preselected outcome; the fake only verifies application mapping.

The judge supplies a constrained outcome for each blank: target recalled, meaning recalled, or incorrect/missing, with an English explanation. The application validates completeness and structure, applies the B-before-C precedence, and derives D/E from recorded time. It does not ask the LLM to invent a duration, select a schedule, or override the user's Forgot/Skip action. Treat card/transcript text as untrusted input and validate provider output; prompting alone is not sufficient enforcement. Wire protocol and failure parsing remain with the provider ticket.

### Neutral and unassessed interactions

- Skip shows **Skipped**, outside A-E. Preserve collection and success streak; exclude it from accuracy. The scheduling ticket decides its queue treatment without treating it as a scored failure.
- Capture/transcription/judge failures, empty unusable transcription, or invalid judge output are **Not assessed**, outside A-E. They cannot become B or an artificial correct answer. Keep the agreed same-recording retry/unassessed-exit flow.
- Cancel before submission produces no assessment and does not restart the question's response clock.
- Only D/E count as complete target recall. Statistics must distinguish this from C's correct approximate meaning; date windows and completion/view counters remain with the statistics ticket.

### Response clock and initial fast budget

Measure from the fully displayed question through Stop & check. Include thinking, recording, and cancelled recording/rerecording time. Subtract time blocked on microphone permission. Freeze the result at submission, before upload, transcription, judging, and retries; those waits cannot downgrade a response. Do not reset the clock on Cancel. Missing/invalid timing is a technical assessment problem, not evidence of poor recall.

The initial, deterministic budget in seconds is:

`T = max(12, ceil(5 * N + Q / 20 + R / 5))`

Here N is the number of blanks; Q is the number of non-whitespace Unicode code points in the displayed question excluding blank markers; R is the same count in the reference answer. E includes the exact boundary `response_seconds == T`; D starts above it. This modest complexity allowance supports longer questions, multi-blank cards, and sentence answers without adding a per-card settings field.

This is an initial heuristic, not an empirically established fluency model. Character counts approximate reading/speaking effort across languages; real review data must inform later calibration. Keep the measured duration and budget with the assessment so the decision is explainable and does not change when a card or policy is edited. Sample prototype budgets are 16 seconds for the two-blank English card, 12 for its single-blank card, and 16 for the two-blank Spanish card.

The later Markdown contract clarifies Q: derive visible text from the canonical parsed tokens and exclude actual cloze tokens. Formatting syntax does not increase the reading allowance; literal displayed code/text still does. This preserves the timing meaning when bold or underline is added.

The later [completion/interruption contract](19-attempt-completion-and-interruption.md) preserves valid timing for a same-presentation refresh. An unrecoverable clock produces an explicit unscored interruption, not a silent zero reset; a genuine new presentation has its own clock. Submitted durations remain fixed. Scheduling uses a separate server-recorded submission/action anchor rather than the browser duration or model completion time.

### Next review display

Show **Next review** near the feedback, using the scheduler's persisted next due time. Render an approximate relative value such as `~1 min`, `~1 day`, `~4 days`, or `~1 month`; these examples are not an interval table selected by this ticket. Use Due now for an already due item, minute/hour/day units for shorter intervals, and approximate month units from about 30 days. The canonical timestamp remains unchanged by display rounding.

While assessment is pending, show After checking rather than an invented new interval. After Skip or an unassessed exit, reflect the existing schedule. Final interval calculation, collection transitions beyond A/B entry, and streak eligibility belong to [Decide Normal and Forgot Scheduling and Graduation](07-review-policy.md). The production result should return feedback and the committed next due time together before Next card becomes available.

### Decisive examples and evidence

| Case | Expected result |
| --- | --- |
| Target call off; response cancel, with every other blank correct | C at both 2 seconds and 60 seconds |
| One correct blank and one missing or clearly incorrect blank | B, even when another blank is a valid synonym |
| Every target recalled at exactly T | E |
| Every target recalled just above T | D |
| A correctly completed sentence or genuinely equivalent spelling | D/E according to time |
| Skip | Skipped; no A-E grade or accuracy contribution |
| Empty/failed ASR or invalid judge result | Not assessed; no incorrect-answer grade |

The updated interactive prototype (local-only reference: `/tmp/vocab-learn-prototype-card-ui/docs/prototypes/card-review-prototype/index.html`), feedback preview (local-only reference: `/tmp/vocab-learn-prototype-card-ui/docs/prototypes/card-review-prototype/previews/fieldnotes-feedback.png`), and meaning-recall preview (local-only reference: `/tmp/vocab-learn-prototype-card-ui/docs/prototypes/card-review-prototype/previews/fieldnotes-meaning.png`) are captured on `prototype/spoken-card-ui` at `38f577fa9d4139f7f94a7ca16eaa658d65169728`.

CDP assertions passed for all five grades, C at fast/slow speeds, B precedence, the exact D/E boundary, Unicode budget counting, clock preservation across Cancel, frozen response time through service waits/retry, neutral Skip, labelled example intervals, and all three layouts. The Next review values in this prototype are explicitly examples until the scheduling policy is settled. Real ASR/LLM accuracy and hardware timing were not tested.
