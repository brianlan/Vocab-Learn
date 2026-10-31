# V1 reviewer feedback assessment

Reviewed on 2026-10-31 against the supplied feedback (local-only reference: `/home/rlan/Downloads/reviewer-feedback.md`), the [acceptance draft](../planning/v1/issues/11-acceptance-and-handoff.md), and its upstream decisions. This records recommendations, not user acceptance of new behavior. No application code or accepted product rule was changed by this assessment.

Source-version note: the Downloads input has since been replaced by a second reviewer pass. This document records the earlier feedback, not the current contents of that mutable path. See the [round-two assessment](v1-reviewer-feedback-assessment-round2.md) for the current input digest and recommendations.

Follow-up disposition: the user subsequently authorized applying the recommended document revisions. [Attempt completion and interruption](../planning/v1/issues/19-attempt-completion-and-interruption.md) is resolved, related contracts are synchronized, and [the acceptance draft](../planning/v1/issues/11-acceptance-and-handoff.md) now contains fixed inputs, explicit race orders, processing deadlines, timing/expiry anchors, restore stages, and a reviewer-topic coverage table. The original assessment below is retained as the pre-revision record. No application/runtime implementation was performed by that follow-up.

## Overall recommendation

Accept most of the review. The final acceptance table compressed several explicit requirements too far, and should make those obligations observable. Most are already specified upstream and need acceptance examples rather than a product redesign. The reviewer explicitly did not receive those upstream files, so its qualifications are appropriate.

The substantive clarifications are attempt finalization after an unassessed exit, a recovery route when processing never completes, and presentation/timer semantics across interruption. Ignored microphone permission also needs an explicit cancellable lifecycle. Preserve the selected Django/SQLite/worker/private-LAN architecture and independent ASR/Judge/Generator configurations.

## Disposition of the six priority findings

| Reviewer finding | Recommendation | Assessment against the full plan |
| --- | --- | --- |
| Initial example generation failure | Adopt as an explicit acceptance case. | Already defined in [Example lifecycle](../planning/v1/issues/15-vocabulary-example-lifecycle.md), Source creation and first preparation: save valid sources, expose preparation failure/retry, exclude unready cards from study/Due now. This is distinct from rotation fallback and must appear separately in the final table. |
| Unassessed exit versus late judgment | Adopt; clarify one atomic terminal outcome before handoff. | [Architecture](../planning/v1/issues/10-architecture-and-storage.md) specifies claims, idempotent commits and stale-revision checks, but does not explicitly state which outcome wins an exit/grade race. At-most-once scoring alone is insufficient. Recommend first committed terminal outcome wins, with all learning/statistical effects conditional on it. |
| Two different concurrent attempts and edits during judgment | Adopt concrete race tests, retaining the existing architecture. | Architecture already checks expected progress/source/example revisions, including two tabs, and marks unapplied stale work unassessed. Test two distinct attempt identities against one progress version, not just duplicate delivery of one identity; test a source edit before the old result arrives. |
| Same vocabulary in independent cards | Adopt an explicit isolation case. | [Learning units](../planning/v1/issues/14-generic-and-vocabulary-units.md) already makes progress per card instance, while Recognition/Production share progress only within one Vocabulary Card. Lifecycle identity includes meaning/languages, not a global word key. Test two valid distinct sources without bypassing the duplicate rules. |
| Displayed blanks equal judged units | Adopt exact set/identity assertions and both missing-unit cases. | [Source/rendering contract](../planning/v1/issues/08-private-decks-and-stats.md) derives projections from one parsed representation. [Grading](../planning/v1/issues/16-vocabulary-grading.md) explicitly distinguishes a learner's unanswered blank (B after valid judgment) from malformed provider output missing a unit (Not assessed). The final compressed table should preserve both. |
| Refresh and asynchronous timing | Adopt boundary/delay tests; clarify refresh by presentation identity. | Grading already ends recall time at Stop and excludes upload/permission/provider waits. Scheduling uses the recorded server UTC submission/action time, not model completion. Architecture currently permits a fresh unsubmitted presentation after interruption. That is a real policy distinction the reviewer could not see, but automatically using refresh to obtain a fresh clock risks misleading E results. Clarify it rather than applying one timer across every later review. |

### Recommended finalization clarification

Distinguish retryable failure from an explicitly closed-unassessed attempt. The latter is terminal, with no later grading, scheduling, direction-slot, rotation, or scored-statistics effects. If exit commits first, a delayed judge result is unapplied. If assessment commits first, an exit request returns that stored assessment rather than pretending it was unassessed. Gate both by the attempt state/claim and card revisions in the same short transaction.

Cover waiting before a worker starts as well as an already executing provider call. Existing 60/120-second stage limits do not themselves bound a job that is never claimed. Provide a bounded whole-attempt wait/recovery path that works through the web/status route even if the worker is unavailable; its exact configured budget belongs in the follow-up decision. Do not extend that deadline or revive a terminal attempt merely because a late result arrives.

### Recommended interruption clarification

A refresh that resumes the same presentation should not silently reset its valid elapsed time. A genuinely new review after Skip/unassessed exit has a fresh clock while retaining the chosen direction as already agreed. When an interrupted clock cannot be reconstructed reliably, treat the old presentation as an unscored interruption and make a new presentation explicit; do not fabricate a duration or claim a silent reload proves Quick recall. Preserve same-page Cancel/permission exclusions and already frozen submitted durations.

Do not interpret the reviewer as requiring one timer to keep running across every later study session or until a word is mastered. That would penalize returning learners and contradict the per-attempt feedback model. The goal is consistent presentation lifecycle, not a new anti-cheat subsystem.

## Other acceptance additions

Adopt all six additional examples as acceptance bindings to existing rules:

- Next review must show the saved scheduler due time, including Due now, never a prototype interval table.
- Restore retains a card's progress, due time and examples; overdue restored ready cards re-enter the due queue.
- Changing Judge/Generator settings does not rewrite completed grades/examples. Each in-flight execution records the configuration actually used; a completed or already dispatched call is not retroactively assigned a new model.
- The three action paths are Skip, Speak, and Forgot. They are separate coverage dimensions from English/Chinese, English/Spanish, and Spanish/Chinese language pairs and from Recognition/Production.
- Keep a Recognition partial-meaning case and a contextually unsuitable listed-synonym case distinct.
- Keep one spoken response covering multiple actual blanks and one zero-blank Generic whole-answer case.

These do not reopen user choices or require copying all business rules into multiple specifications. Point each case at its canonical decision and expected state changes.

## Implementation and recovery suggestions

### Early real-provider probe: adopt in the implementation phase

Move a small real-capability probe ahead of broad UI/CRUD construction, alongside the first fake-provider vertical slice. Use real target-browser audio, normalization and ASR, a complete default Judge response, and one valid Generator pair for each supported language pairing. Use the actual selected effort, token cap and deadlines. This exposes core feasibility risks before substantial application work.

The MiniMax reminder is technically sound. However, [the actual provider contract](../planning/v1/issues/09-provider-configuration.md) already configures independent 8192-token completion budgets including reasoning, 120-second LLM deadlines, and empty/truncated-output failure handling. New calls use max_completion_tokens. The review supplies no evidence that these exact defaults are too small or too short. Benchmark them; do not blindly raise budgets, change models, or add a fallback layer.

This recommendation does not authorize paid calls during the current planning/review task. Define the probe and its pass/fail examples now; execute it when implementation begins. Retain the full live acceptance pass before declaring the application usable. [Primary-source verification](../research/v1-review-feedback-evidence.md).

### Interrupted restore and recording deletion: adopt

Extend restore tests beyond completed jobs. The existing architecture already excludes audio from backups and allows cached-transcript judge retry, but the exact cases need evidence:

- Missing restored audio with no saved transcript becomes a clear technical/unassessed state, never permanent Pending or B.
- A durable transcript with unfinished judgment permits judge-only retry under the selected attempt-finalization rules.
- A committed grade with an unacknowledged task returns that same result without a second review/slot/schedule update.

Delete successful audio only after the relevant durable result commit, as architecture already requires. An ASR return by itself is not a deletion trigger. Preserve the original submitted-at/expiry across retries/restart/restore; none creates another 24-hour window. Audio cleanup and CA persistence are separate policies.

### Fixed cases and permission waiting: adopt proportionately

Use a small set of named, controlled scenario fixtures with before state, input/fault/clock, expected UI/data changes, and implementation evidence. The proposed cases below are sufficient starting groups; they are not executed tests or a demand to enumerate every Cartesian combination. Live-language cases need pre-agreed expected meanings/labels rather than an invented numeric accuracy promise.

The ignored-permission claim is supported by MDN and the W3C algorithm. The interface needs an explicit Cancel/leave route while acquisition is pending. Logical cancellation invalidates the request; a late stream must have every track stopped and must not activate recording or overwrite a newer request. A timeout alone does not cancel the browser permission request. [Verified API facts](../research/v1-review-feedback-evidence.md).

## Proposed focused case groups

All entries are proposed acceptance groups, not reports of passing implementation tests. Each future evidence record should include its source/prompt revisions, direction, progress version, exact clock/fault, expected state changes, and implementation revision.

| Case group | Controlled situation | Essential observable result |
| --- | --- | --- |
| PREP-INITIAL | Valid source import; first generation fails | Source persists; visible retry; no study/Due now eligibility until valid pair commits |
| EXIT-FIRST | Closed-unassessed commits before delayed judgment | No later score, schedule, streak, direction, rotation, or scored-statistics change |
| GRADE-FIRST | Judgment commits before exit request | Stored assessment wins and is shown consistently |
| NEVER-STARTED | Worker never claims submitted work | Bounded recovery/exit; no permanently disabled Next |
| TWO-ATTEMPTS | Different attempts compete for one progress version | At most one consumes that version/slot; the other is stale |
| SOURCE-EDIT | Learning content changes during old judgment | New progress stays fresh; old result cannot update it |
| SAME-WORD | Independent valid card instances target the same word | Reviewing one leaves the other's progress/examples/history unchanged |
| UNIT-IDENTITY | Formatted/literal/fake cloze inputs and missing-answer versus missing-output faults | Visible and judged unit identities match; B versus Not assessed remain distinct |
| CLOCK-LIFECYCLE | Same-presentation refresh/Cancel, new review, and T-epsilon/T/T+epsilon | The selected presentation policy is explicit and D/E boundaries remain stable |
| DELAY-ANCHOR | Same response duration, varied upload/ASR/Judge delays | Same grade; due uses the recorded submission/action anchor and saved Next review |
| PERMISSION-PENDING | Ignored prompt; Cancel; late grant/rejection | Usable UI, no stale recorder, all obsolete tracks released |
| RESTORE-STAGES | Missing audio; saved transcript; committed but unacknowledged result | Correct recovery in all three states, with no duplicate grading |
| AUDIO-TTL | Retry/restart/restore near original expiry | Expiry is not extended; deletion follows durable state; history remains |
| DISPLAY-ISOLATION | Model changes, archive/restore, paired action/language/direction examples | Existing results remain stable and UI reflects actual saved state |

## What needs no immediate change

- The selected framework/database/worker/TLS topology: the review identifies acceptance/lifecycle work, not evidence requiring replacement infrastructure.
- Already decided grading, scheduling, duplicate identity, and ownership policy: add the missing cases instead of redesigning those rules.
- Completion budgets/model selection: the documented reasoning risk justifies an early probe, not an unmeasured parameter increase.
- Cross-session timing: preserve new-attempt semantics; do not carry one clock indefinitely merely to satisfy a blanket reading of refresh persistence.
- Full live execution during this assessment: retain the planning/implementation split and verify those capabilities early during implementation.

## Tracking and verification

The precise follow-up decision, [Finalize Attempt Completion and Interruption Semantics](../planning/v1/issues/19-attempt-completion-and-interruption.md), resolves the terminal/deadline/presentation/capture-lifecycle questions. The other recommendations were integrated as acceptance cases without changing the chosen stack or learning modes. Following the second-review revisions, the user confirmed reviewer approval of the final handoff and the decision map was resolved; runtime validation remains an implementation task.

External-claim evidence was produced on research/review-feedback-evidence at 7fa1fde1c194d105aaecf571322dc9ee726390d0. Source links and documentary limits are in the note. This assessment did not run models, browsers, containers, restoration, or new application tests, and did not amend accepted behavioral rules on the user's behalf.
