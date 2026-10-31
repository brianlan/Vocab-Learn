# Decide Normal and Forgot Scheduling and Graduation

Id: 07
Parent: [Vocab-Learn Browser V1 Decision Map](../map.md)
Type: grilling
Labels: wayfinder:grilling
Mode: HITL
Status: resolved
Assignee: /root
Blocked by: 03, 06, 12
Prototype branch: prototype/spoken-card-ui
Prototype commit: bc5a68947472e8f284e7e465584b98aa4f912b2d

## Question

Scope note: the resolved policy is the existing learning-unit baseline. The vocabulary extension uses a shared card schedule and goal-specific grading; [Define Vocabulary-Direction Grading and Timing](16-vocabulary-grading.md) defines its outcome mapping, and [Define Vocabulary Example Pairs and Rotation](15-vocabulary-example-lifecycle.md) decides when new examples become active.

Which regular scheduling algorithm should V1 use, and how exactly should Forgot items follow short intervals and graduate after three consecutive correct answers? Preserve the requested behavior, use the research and settled grading contract, and discuss a concrete timeline and state transitions with the user.

Cover first learning, A/B entering or remaining in Forgot, what returning soon on the same day means, which C/D/E outcomes count as success, resetting on a wrong answer, Skip's effect on due time and streak, whether same-day repetitions can complete all three successes, missed days and time zones, and the Normal state after graduation.

Establish Forgot priority relative to overdue Normal items and new cards, avoiding immediate loops when only one item is available. Convert the user's next-day examples into explicit date/time semantics. The decision should be verifiable with fixed-clock examples; this ticket decides policy rather than implementing a scheduler.

Return a concrete next due time for the back's Next review display. The user wants an approximate relative value such as 1 min, 1 day, 4 days, or 1 month; these examples are not an interval table already selected. Distinguish a due time from a promise that the card appears while the user is away. Skip preserves collection and streak and does not count toward accuracy; decide its queue behavior without inventing a graded review.

## Comments

2026-10-31: The user accepted FSRS with default parameters, without personalization/optimizer work. The agreed Forgot policy is: retry after about one minute; D/E alone count toward graduation, with 24 hours after success one and again after success two; success three returns to Normal. A/B/C inside Forgot reset its streak and schedule one minute later. Skip/unassessed leave the streak unchanged. Missed days do not reset it; future delays start from the actual review time. Extra same-day practice does not satisfy all three successes, and only due cards have queue priority.

The newly specified library-state integration question is tracked in [Verify FSRS State Under the Forgot Review Policy](12-fsrs-forgot-contract.md) before finalizing the adapter policy and examples.

## Answer

Resolved on 2026-10-31 through the user's acceptance of default FSRS and the proposed Forgot timeline. The technical state contract was subsequently verified in [Verify FSRS State Under the Forgot Review Policy](12-fsrs-forgot-contract.md).

### Regular scheduling and rating mapping

Use `fsrs==6.3.2`, whose public API was exercised in the requested Python 3.11 environment. Retain its default parameters, desired retention 0.9, learning steps of 1 and 10 minutes, 10-minute relearning step, and enabled fuzzing. No optimizer or personalized training is part of V1. The retention setting is a model target, not a promised user outcome.

| Application feedback | FSRS rating | Interpretation |
| --- | --- | --- |
| A / B / C | Again | The current review goal was not completely met. Generic substitutes and Vocabulary partial results remain C. |
| D | Good | The current review goal was completely met. Elapsed time alone does not establish the separate Hard rating. |
| E | Easy | The current review goal was completely met quickly under the agreed response budget. |
| Skip / Not assessed | No rating or scheduler call | No FSRS review log or memory update. |

Application collection membership and FSRS Learning/Review/Relearning are separate concepts. In particular, C in Normal stays Normal, even if the library moves it into Relearning. Only A/B enter the business Forgot collection.

[Define Vocabulary-Direction Grading and Timing](16-vocabulary-grading.md) defines complete success for the two Vocabulary directions. Their shared-card use changes the interpretation of the review goal, not these ratings or state transitions.

### Effective next due time

Use the authoritative, timezone-aware UTC submission timestamp as the review time; a direct Forgot action uses its recorded action timestamp. Convert local timestamps to UTC before calling FSRS. Do not substitute the later ASR/LLM completion time. One day below means exactly 24 elapsed hours, not midnight or a calendar-date boundary.

[Completion/interruption semantics](19-attempt-completion-and-interruption.md) fixes that anchor once at server acceptance of the complete submission/action. Browser Stop duration is a separate grading field. Post-submission model delay changes neither value; upload delay may move the server receipt anchor without changing the frozen response duration. Retry/replay do not replace the original anchor.

For each eligible, assessed interaction, run FSRS once with the actual review time and mapped rating. Retain the complete returned memory/state and review log. Change only the returned due time when the following policy requires it:

| Starting collection / result | Resulting collection and streak | Effective due time |
| --- | --- | --- |
| Either collection, A/B | Forgot, streak 0 | Review time + 1 minute |
| Normal, C/D/E | Normal; no active Forgot streak progression | Unmodified FSRS due time |
| Forgot, C | Forgot, streak 0 | Review time + 1 minute |
| Forgot, first or second qualifying D/E | Forgot, streak +1 | Review time + 24 hours |
| Forgot, third qualifying D/E | Normal, graduation recorded at streak 3 | Unmodified FSRS due time from this third success |
| Either collection, Skip/Not assessed | Unchanged | Preserve existing due time |

Do not reset or recreate stability, difficulty, state, learning step, or last-review time at graduation. The runtime check verified that all tested D/E sequences already reach FSRS Review by success three under the default learning steps. The streak is relevant only inside Forgot; a later A/B starts a fresh streak at zero.

Missed days neither increment nor reset a streak. Evaluate a delayed answer at its actual submission time, and start its next one-minute/24-hour delay from that time. A/B/C inside Forgot do reset it. Skip and technical failures do neither.

### Queue and eligibility

Only due cards are eligible for scored scheduling updates. FSRS itself accepts early calls, so enforce eligibility in the application and prevent duplicate/stale applications against the same card schedule. Extra practice before the next due time cannot call the scheduler or award another graduation success.

Choose due Forgot cards first, then due previously reviewed Normal cards, then unseen Normal cards. Within a tier, use earliest due time and a stable card-identity tie-breaker. New cards are eligible immediately. Do not bring a future card forward merely because it is in Forgot or the queue is otherwise empty.

After Skip or an explicit unassessed exit, set that card aside for the remainder of the current study run without changing its stored due time, collection, memory, or streak. It can return in a new run. If every remaining card is future-due or set aside, show a caught-up state and the next future due estimate rather than immediately repeating a card. An already due card set aside in this run can be labelled Due now with that session context.

### Study-run lifecycle

An explicit Start review/Start new run action creates a stable, user-owned run identity. Refresh, reconnect, or Resume reuses that run and its saved deferrals. Leaving the review page does not silently reset the deferral set. Multiple tabs retain their explicit run identities and the existing per-card progress-version checks still prevent double scoring.

An active run selects only currently eligible, nondeferred cards using the tiers above; a new due time can make a card eligible again if it was not deferred in this run. When none are selectable, finish/show the run summary and next future-due information. If due cards were set aside, distinguish Finished this run from globally having no due cards. Do not automatically create a new run when the queue is empty, the summary is refreshed, or a tab reconnects. Only an explicit new-run action creates an empty deferral set and permits still-due skipped/closed-unassessed cards again. That action does not change saved learning state, cue/direction, or existing attempt outcomes.

### Persistence and Next review

Commit the returned FSRS card with its effective due time, application collection/streak, and review log together, once per assessed attempt. Reuse the stored result on retry or redisplay; rerunning a completed review can change the fuzzed interval. Do not seed randomness in production.

Next review formats this persisted effective due time using the relative-time display agreed in the grading ticket. While judging is pending, it says After checking. After Skip/unassessed it reflects the unchanged schedule. A due time describes eligibility when the user studies, not a promise of an automatic notification or immediate presentation while the app is closed.

### Fixed-clock examples

| Review | Result | Next state / due |
| --- | --- | --- |
| Day 0, 15:00 UTC | A or B | Forgot 0; due 15:01 |
| Day 0, 15:01 UTC | D | Forgot 1; due Day 1, 15:01 |
| Day 1, 15:01 UTC | D | Forgot 2; due Day 2, 15:01 |
| Day 2, 15:01 UTC | D | Normal; due from the returned FSRS result |
| Instead, second review is delayed until Day 4, 18:00 | D | Keep progression to Forgot 2; due Day 5, 18:00 |
| Instead, a due Forgot review is C | C | Reset to Forgot 0; due one minute after that review |
| A repeat before the next due time | Not eligible for another scored review | No new memory update or streak increment |
| Skip or technical failure | No score | Preserve schedule and streak; set aside only for this run |

In one seeded initial-card trace, DDD graduated with a 5-day normal interval and EEE with 12 days. A new Normal card's D review produced 10 minutes, and E produced 8 days. These are state-dependent examples, not fixed grade intervals or guaranteed bounds; prior history and default fuzzing matter.

### Evidence and handoff

The [research report](../../../research/v1-fsrs-forgot-contract.md) and [reproducible check](../../../research/v1-fsrs-forgot-check.py) cover 192 paths across three entry states, all eight D/E triples, failure resets, and delayed reviews, plus neutral actions, early-review rejection, UTC requirements, and serialization. The research is captured at `research/fsrs-forgot-contract`, commit `2d6089f668203af7e1217daa63580f6c6a6c31cb`.

The UI prototype (local-only reference: `/tmp/vocab-learn-prototype-card-ui/docs/prototypes/card-review-prototype/index.html`) now uses documented seeded new-card offsets as explicitly labelled examples; snapshot `prototype/spoken-card-ui` at `bc5a68947472e8f284e7e465584b98aa4f912b2d`. It still has no persistent scheduling backend.

The persistence ticket owns production transactions, interruption handling, and duplicate/stale requests. The statistics ticket owns study-run presentation and calendar reporting. Runtime compatibility is verified; real-user retention, live ASR/LLM outcomes, and production persistence were not tested.
