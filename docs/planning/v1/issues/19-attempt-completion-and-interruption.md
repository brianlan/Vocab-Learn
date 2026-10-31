# Finalize Attempt Completion and Interruption Semantics

Id: 19
Parent: [Vocab-Learn Browser V1 Decision Map](../map.md)
Type: grilling
Labels: wayfinder:grilling
Mode: HITL
Status: resolved
Assignee: /root
Blocked by: 09, 10

## Question

The [reviewer assessment](../../../reviews/v1-reviewer-feedback-assessment.md) identifies precise completion/interruption questions to settle before final handoff. Preserve the accepted stack, fixed submissions, per-attempt feedback, neutral technical failures, scored-only direction advancement, and independent model profiles.

Define the terminal outcome when an explicit Proceed unassessed races with delayed judgment. The recommended invariant is first atomically committed terminal outcome wins: exit-first blocks all later scored side effects, while grade-first returns the stored result rather than a contradictory unassessed state. Distinguish retryable failure from terminal closed-unassessed and specify which attempts can still be retried.

Define a bounded whole-attempt waiting/recovery path, including an unclaimed task or unavailable worker, rather than relying only on per-provider timeouts and leases. State how web/status requests permit exit and how late claims/results are invalidated without repeating billed calls automatically.

Clarify timer identity across refresh of the same unsubmitted presentation versus a genuinely new review. The existing architecture allows a new presentation after interruption; preserve legitimate new-review clocks without silently treating a same-presentation refresh as new Quick recall evidence. Decide recovery when elapsed/permission-blocked time cannot be reliably restored. Keep submitted timing frozen and Cancel's established behavior unchanged.

Specify cancellable UI for an indefinitely pending getUserMedia request: invalidate obsolete request identity on Cancel/navigation, discard late rejection, and stop all tracks if an obsolete stream eventually resolves. App cancellation does not claim to cancel the browser's native permission request. External API facts are in [review-feedback evidence](../../../research/v1-review-feedback-evidence.md).

The rules above are recommendations to decide, not already accepted behavioral changes. Add corresponding focused cases to the final acceptance ticket and amend upstream wording only after the disposition is agreed. No implementation or live-provider test is required to resolve the policy.

## Comments

The user asked to implement the recommended reviewer-driven document revisions and prepare the final handoff for another review. This authorizes the recommended lifecycle clarifications. The numeric execution budget below is an initial engineering default, not a separately supplied user preference. No application implementation or live test is authorized by this documentation task.

## Answer

Resolved on 2026-10-31 under the user's instruction to revise the documents according to the reviewer assessment. This supplements the existing immutable-submission, shared-progress, and neutral-failure contracts; it does not change the stack or the selected learning modes.

### Presentation, attempt, and execution identity

A presentation is one display of a frozen question, direction, source/example revision, expected progress version, and response clock. Its accepted front action is unique: Skip, Forgot, or a submitted spoken response. Repeated/conflicting requests for that presentation return its existing action/result; they cannot create a second action or replace submitted audio.

A spoken attempt retains that immutable submission and frozen timing. Processing it may have multiple executions after explicit Retry, each with a distinct claim/execution revision. A new execution changes neither the recording, source/reference, original submission timestamp, nor audio expiry. Dispatch snapshots the actual task configuration for that execution; secrets are not stored in the snapshot. An already dispatched call uses that snapshot; queued work uses the configuration when dispatched, and a later explicit Retry may use the then-current configuration. Existing cached ASR text retains its own provenance. Model changes never rewrite completed results or accepted examples.

### Attempt state and terminal outcomes

| State | Meaning and permitted transitions |
| --- | --- |
| `submitted` / `processing` | Fixed spoken input is waiting/running under one current execution. It can become assessed, fail retryably, or close unassessed under the recovery rules. |
| `failed` | A technical failure or elapsed execution deadline ended the current execution. Invalidate its claim. Retryability is separate error metadata: explicit Retry creates a new execution when permitted and required inputs exist; Proceed unassessed can close the attempt. |
| `assessed` | Terminal A-E outcome and all scored effects committed. Direct Forgot commits A without provider calls. Only read/replay of that stored result remains. |
| `closed_unassessed` | Terminal explicit exit or stale/ineligible attempt. No later assessment or same-attempt Retry is permitted. A later eligible review is a new attempt. |
| `skipped` | Terminal Skip action for its presentation. It has no A-E result or direction-slot advancement. |

Nonretryable configuration failures can offer an unassessed exit and Retry after the deployer corrects configuration; they do not become a wrong-answer grade. The failure message and whether immediate Retry is useful remain stage-specific. A retryable failure is not itself an irreversible unassessed exit.

### Atomic finalization and late results

The first successfully committed terminal outcome wins. Both assessment and exit compare the current attempt state/execution claim and relevant source/example/progress revisions in a short transaction:

- If Proceed unassessed commits first, set `closed_unassessed`, invalidate pending claims, and preserve learning state. A later response may be logged as discarded operational metadata but cannot write a grade, FSRS state/due time, collection/streak, direction slot, rotation eligibility, or scored statistics.
- If assessment commits first, a racing exit returns the saved assessment and committed Next review. The UI restores that result; it does not claim that the attempt ended unassessed.
- If two distinct attempts compete for the same progress version, at most one consumes it. The loser becomes explicitly stale/unassessed without a scored review or another slot/streak increment. Same-attempt idempotency alone is insufficient.
- A source edit, archive, or invalidated presentation/claim prevents old work from updating current learning state. An archive closes/invalidate active attempts so restoring it cannot revive a pre-archive execution. Prior completed history remains intact.

Learning state here comprises progress version/FSRS memory, due time, collection, streak, direction position, rotation intent, scored review rows and accuracy counts. Operational attempt/error/transcript metadata may change without becoming a learning update. Apply all scored effects together once, using the established conditional-update/short-transaction strategy.

An exit is confirmed only by the server's terminal response. A lost response is recovered by reading/repeating the idempotent operation. If the server cannot be reached, the UI shows an unconfirmed outcome and reconnect/status recovery, not an invented successful unassessed exit. Closing a tab, cancelling a fetch, or losing connectivity without a committed exit does not by itself close the server attempt; an eligible execution can still finish until its deadline.

Healthy checking retains the existing disabled-Next behavior. Offer the explicit unassessed exit after a reported processing/status-communication failure or the bounded waiting deadline. A stale UI can therefore offer recovery while the original Judge execution is still valid; the grade/exit transaction order remains authoritative. A local communication error does not by itself invalidate or finalize the server's attempt.

### Bounded processing and recovery

Add `ASSESSMENT_TIMEOUT_SECONDS`, initially 300 seconds per execution. This is a configurable engineering budget, not a latency guarantee. The initial execution starts at accepted durable submission; an explicit Retry starts a new execution deadline. Include queue waiting, conversion, ASR, and judging. Keep the existing ASR 60-second and Judge 120-second limits, each capped by remaining whole-execution time; conversion is also bounded by the remaining budget. Generator calls retain their separate configured deadline.

The [generation lifecycle](15-vocabulary-example-lifecycle.md) separately bounds unclaimed/crashed preparation executions at an initial 300 seconds, with a 120-second call cap. Both workflows follow the [worker capacity contract](10-architecture-and-storage.md): claim invalidation fences results, while actual resource cleanup/recovery must restore bounded capacity within the initial 10-second grace. These are separate properties to verify.

Web status/retry/exit routes and worker claim/result routes evaluate the saved execution deadline, even when a worker never claimed the attempt. At or after expiry, an unfinished execution becomes a visible technical failure, its claim is invalidated, and Retry/Proceed unassessed is available. Next cannot remain disabled forever merely because a worker died or no response arrived. A worker result cannot commit at/after its execution deadline; a result already committed before expiry remains terminal and is returned.

An execution that times out is not silently retried, and a late response from it cannot satisfy a newer execution. Claim recovery does not promise exactly one paid provider invocation. A new explicit Retry preserves the original submission/action time, response duration, and `audio_expires_at = submitted_at + 24 hours`; it does not grant another 24-hour window. A durable transcript permits judge-only Retry when ASR audio is no longer needed, but a terminal closed attempt cannot be revived by the existence of that transcript.

### Timing across refresh and new reviews

Keep presentation identity stable across refresh of an unsubmitted question. Restore its valid elapsed clock and completed permission-wait exclusions; include the refresh/interruption gap in that same presentation rather than resetting to zero. Do not directly subtract unrelated performance.now origins across navigations. Cancel within the same presentation still preserves thinking/rerecording time and excludes actual permission-blocked intervals.

If the clock or permission-wait history cannot be reliably restored, mark the old unsubmitted presentation interrupted/unscored and show that timing was interrupted. Offer an explicit Restart question or Skip/Forgot path with the same retained cue/direction. Only that explicit restart creates a new presentation/display clock; refresh alone does not silently grant one. It supplies no A-E result and no direction advancement. A genuine later review after Skip or closed-unassessed also has a new presentation/clock. A submitted attempt always resumes its frozen duration and immutable input; Restart question cannot replace its recording after reveal.

Recall duration ends at the browser's Stop & check event. Upload, ASR, judging and retries cannot change it. Scheduling uses a separate server UTC submission/action receipt timestamp, fixed when the complete immutable submission/action is accepted. It never uses later worker completion. Thus changing upload delay may change the server receipt anchor while leaving the grade unchanged; changing only post-submission model delay changes neither the frozen duration nor that anchor. Forgot step due times are exactly anchor + 24 hours for its first/second complete successes.

### Pending microphone permission

The waiting-for-permission UI immediately offers Cancel and an accessible route back to the question. It does not wait for getUserMedia to resolve/reject before becoming usable. A browser permission prompt has no guaranteed response deadline; no arbitrary automatic permission timeout is required for V1.

Each acquisition has a request identity/liveness flag. Cancel, navigation, or an optional application timeout invalidates it and ends that permission-blocked interval. A stale grant stops every track in the resulting stream without starting recording or changing the new UI. A stale rejection cannot replace a newer request's state. Clear owned wait timers and release owned streams on every completion/navigation path. Logical cancellation does not claim to dismiss the native permission prompt or use an undocumented AbortSignal argument. [Verified capture semantics](../../../research/v1-review-feedback-evidence.md).

### Persistence, expiry, and evidence

Persist a successful transcript before relying on it for judge-only recovery. Keep the only recording until the scored result commits or the original audio expiry applies; ASR merely returning is not a deletion trigger. Deletion after an assessed commit and the 24-hour original expiry remain as agreed. Restart/restore do not rewrite submission or expiry timestamps. Missing restored audio with no transcript becomes a technical failure; a saved transcript permits judge-only recovery if the attempt remains nonterminal; an already committed result is replayed without another score.

The [revised acceptance handoff](11-acceptance-and-handoff.md) provides fixed race orders, input/clock fixtures, recovery stages and evidence requirements. These are documentary decisions only; no model, microphone, container, or application concurrency test was run to resolve this ticket.
