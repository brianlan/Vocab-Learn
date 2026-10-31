# V1 reviewer feedback assessment: round two

Reviewed on 2026-10-31 after rereading the updated feedback input (local-only reference: `/home/rlan/Downloads/reviewer-feedback.md`) and the current [acceptance draft](../planning/v1/issues/11-acceptance-and-handoff.md), revision reviewer-follow-up-1. Input SHA-256: 0adab9ea5b4efc0c0538ff2a2ebaab30528024148ad307cabb3a910dfabfa49f. The input path is mutable; this digest distinguishes this round from the earlier assessment.

This is an evaluation, not an automatic rewrite of the acceptance rules. The first review's adopted changes remain in force. The current feedback identifies useful local acceptance improvements and one already-decided grading goal; it does not justify reopening the architecture or expanding V1.

Follow-up disposition: the user subsequently authorized applying these recommendations. The [acceptance draft](../planning/v1/issues/11-acceptance-and-handoff.md) is now reviewer-follow-up-2 with 45 named cases, and the related upstream contracts have been synchronized. The original assessment below is retained as the reasoning for that revision. The accepted Generic outcome remains C; the semantic-only alternative was not adopted.

## Recommended disposition

| Round-two suggestion | Decision recommendation | Reason and scope |
| --- | --- | --- |
| PAIR-LOCK-RACE | Adopt with high priority. | The current lifecycle already prevents activation over a locked question, but the acceptance case must also prove that storing/receiving a candidate cannot make a correct answer to that locked question stale. This is stronger than checking that the screen did not change. |
| Split CSV duplicate and rollback cases | Adopt; this is a real test-design defect. | Existing F-V1/F-V2 records might be skipped before the invalid row, letting a row-by-row importer pass with zero new writes. Rollback must use valid sources absent from an independent test deck and assert no new sources or executable generation intent remain. |
| Mixed queue and study-run lifecycle | Adopt. | The [scheduling decision](../planning/v1/issues/07-review-policy.md) defines due-only tiers and run-only deferral, but the case needs explicit selection and restart expectations. Clarify when a run is resumed, finished and explicitly restarted; do not auto-open another run when deferrals exhaust the current one. |
| Generator never-started/crash/replay recovery | Adopt using the existing worker design. | [Architecture](../planning/v1/issues/10-architecture-and-storage.md) has durable preparation intent and claims. Tests still need source-plus-intent atomicity, unclaimed-work discovery, stale-claim recovery, and idempotent pair persistence. A 120-second provider-call limit alone cannot recover a generation job that never starts. |
| Timeout must return local worker capacity | Adopt as execution evidence. | Invalidating a database claim only fences off effects. It does not prove that blocked calls/children/connections release their bounded slots. Exhaust configured capacity, expire the work, and prove a normal queued job completes through the recovered worker system. No new broker is implied. |
| Clarify Generic cancel versus call off | Adopt the clarification; keep C for this fixture. | The upstream Generic rubric explicitly makes a suitable alternative expression C regardless of speed, and its decisive examples already use call off versus cancel. Changing this fixture to D/E would change an accepted user choice. Make the goal visible in the standalone handoff and real Judge prompt. |
| Narrow rotation invariants instead of entire L equality | Adopt. | L includes rotation intent, while valid activation may consume that intent. Enumerate the stable scored/progress fields and the permitted pair/intent transitions instead of asserting that every field of L remains equal. |
| Restore with the actual delivered backup procedure | Adopt. | Test-generated perfect snapshots cannot certify the operator instructions. Use the same delivered cold-backup command/steps and exclusions in restore tests; online backup remains unnecessary. |

The review's positive ASR-spec check is consistent with the public [MiniMax guide](https://platform.minimax.io/docs/guides/speech-to-text) and [domestic API reference](https://platform.minimax.cn/docs/api-reference/speech-to-text): asr-1.0, the selected languages and the 500-second/50-MB ceilings need no change from this review. Actual account access and short-word accuracy still belong to the early implementation probe.

## Important implementation distinctions

### A locked old pair remains a valid question

Add a controlled order: an authorized prior E starts preparation; the next eligible presentation locks the old valid pair because the replacement is not ready; then the candidate arrives; finally the learner submits a correct response to the displayed old pair.

The simple intended policy is to retain the locked question/reference/direction/clock and park or discard the candidate under the existing lifecycle. The current presentation must not become stale solely because background rotation metadata or a parent active-pair pointer changed. Source edits, another committed review, archive and genuinely invalid claims must still invalidate stale work. Do not solve this by removing revision checks wholesale or withholding all due questions until generation succeeds.

[Example lifecycle](../planning/v1/issues/15-vocabulary-example-lifecycle.md) already requires activation only before a new question and retention of a displayed fallback. This recommendation adds a precise case and guards against the wrong example-revision comparison, rather than a new learning behavior.

### Rollback needs an input that would otherwise write

Use independent preconditions:

- Duplicate case: a deck already contains F-V1/F-V2; repeat them and verify skip/no overwrite.
- Atomicity case: another deck contains only a known existing source Z. Its incoming valid A/B are absent; a later invalid C fails validation. Assert A/B are absent afterwards, Z is unchanged, and no runnable generation work/provider call arose from the failed batch.

The importer may validate everything before opening the write transaction or roll back attempted source writes. The observable requirement is no partial import or post-failure generation intent, not a particular internal ordering.

### Queue behavior is more than rejecting an early score

Add a fixed-clock QUEUE-RUN with due Forgot A, due previously reviewed Normal B, future card C, unprepared Vocabulary D, archived E, and a ready unseen Normal F. Select A before B before F; never select C/D/E. Include a future Forgot card so its collection alone cannot make it eligible, and a within-tier due/tie-break variant when testing stable order.

Run Skip and closed-unassessed branches independently. The deferred card is excluded only from run R1, with saved progress/cue/direction intact. Refresh/resume retains R1's deferrals. A finished/no-selectable-card view does not automatically create R2 and repeat the skipped word. Explicitly starting a new run R2 permits eligible deferred cards again. This is a clarification of the promised run lifecycle, not a daily quota or new scheduling algorithm.

### Generator recovery and worker capacity are separate properties

Persist initial source and preparation intent together, or use the persisted Preparing source itself as discoverable work. An in-memory post-commit enqueue alone is insufficient. Cover three separate boundaries:

1. Source/intent saved, before dispatch: restart can discover it, or a bounded status/retry path makes it recoverable.
2. Claimed, before a valid pair commits: expired claims are fenced off, recovery is bounded, and uncertain billed work is not silently retried.
3. Pair committed, before acknowledgment: replay returns/reuses the saved pair without another active revision or duplicate source. Old source versions cannot mark a new source Ready.

Give unclaimed and crashed preparation a concrete recovery/status route as well as the existing 120-second call timeout. Reuse bounded claims, current revisions, status endpoints and worker scanning; no second task infrastructure is necessary.

For capacity, a meaningful test must use one slot or block every configured slot. Marking a future timed out is insufficient if another free slot makes the following normal job pass. Verify real cleanup/reaping/transport closure or bounded automatic replacement, then successful normal-job completion without manual intervention or unbounded extra pools. Keep late-result fencing intact throughout. [Primary-source worker findings](../research/v1-review-round2-worker-evidence.md).

## Generic grading: preserve the established goal

The original [Generic grading resolution](../planning/v1/issues/06-grading-feedback.md) explicitly states that a different suitable synonym is C, even when fluent and grammatically correct. Its decisive example is target call off, response cancel, C at both 2 and 60 seconds. [Goal-aware grading](../planning/v1/issues/16-vocabulary-grading.md) preserves that Generic rubric while permitting complete native meaning during Vocabulary Recognition.

Therefore F-G2 remains an expression-recall fixture: cancel forms a sensible English sentence, while C indicates incomplete recall of the authored target expression call off. The acceptance file should state that task goal explicitly. Do not confuse this with strict transcript equality: genuinely equivalent spelling, appropriate forms and complete sentences are already allowed. Nor should the clarification turn every freeform answer into character-by-character recitation.

The reviewer is correct about the fake-provider limitation. Separate two tests: offline mapping of a supplied partial outcome to C, and real Judge classification of the frozen answer under an explicit expression-recall rubric. A fake returning partial proves only the first. If the live Judge marks cancel complete despite that explicit goal, investigate prompt/model alignment; do not treat the fixture as a language claim that cancel is ungrammatical or meaningless. The reviewer's semantic-only alternative is a possible future product choice, not the current accepted rule.

## Wording and delivery corrections

Keep L useful for failed/closed-attempt invariants, including the prohibition on late rotation eligibility. For authorized pair activation, explicitly preserve FSRS memory, due, collection, streak, direction position, scored reviews and scored statistics; allow the active example revision and rotation intent to change according to the lifecycle. Do not use an undifferentiated row/metadata change to invalidate a locked presentation.

Run every restore scenario from an artifact produced by the exact operator-facing cold-backup command or steps. Record the procedure/application versions, excluded audio, restored durable data/CA identity and recovery result. If only cold backup is delivered, test cold backup; a separate online-backup feature is not required.

## What to keep unchanged or avoid expanding

- Keep the selected Django/SQLite/same-image-worker/private-LAN stack, model profiles and learning modes.
- Keep the accepted Generic target-expression outcome C; clarify and test it rather than reopening that choice because the reviewer did not receive upstream documents.
- Keep the distinction between fake mapping evidence and live semantic evidence; do not count a prelabelled fake as proof of grading quality.
- Keep a bounded set of discriminating cases. Add the missing orders/preconditions; do not require every language/action/failure combination to be enumerated.
- Keep the delivered backup method cold unless a separate need for online backup emerges. Use existing durable preparation mechanisms rather than adding infrastructure solely to satisfy these tests.

None of the substantial correctness recommendations should be discarded. The main qualification is the Generic branch: adopt the request for clarity and evidence, not a silent change to semantic-only scoring. This is a final local hardening pass, followed by implementation and the early real-capability probe, not a reason to enlarge V1 planning.

## Status and evidence

The authorized document revision implements the recommended disposition: independent duplicate/rollback inputs, mixed queue/run behavior, locked-pair race, four generation recovery cases, capacity/resource recovery, explicit Generic goal/live classification, narrow rotation invariants and delivered-procedure restore evidence. Upstream scheduling, lifecycle, architecture, configuration, grading and completion contracts plus the glossary/brief/map are synchronized. Initial generation execution and cleanup defaults are 300 and 10 seconds respectively; these engineering budgets still require implementation evidence.

The user subsequently confirmed reviewer approval of the final handoff, revision reviewer-follow-up-2. Its ticket and the decision map are now resolved; this is planning approval, not runtime acceptance. Primary-source worker verification was committed on research/review-round2-worker-evidence at a9ed2ba81b4175a4441f25288c0f4566e680e0aa. No application, worker, provider, browser, cancellation or restore test was executed during this documentation follow-up.

Before reviewer approval, document checks passed: 185 local links across 34 Markdown files; 19 acyclic decision tickets with 18 resolved and only handoff 11 claimed; 45 unique acceptance IDs with valid reviewer-table case/fixture references; independent provider settings and distinct execution/call/cleanup budgets. The exact handoff Markdown fixture renders only blanks 1 and 2 through the existing experimental parser, and its timing examples are coherent. English narrative, whitespace/newlines and the reviewed-input digest were also checked. These checks certify document consistency and the stated fixture behavior, not application acceptance.
