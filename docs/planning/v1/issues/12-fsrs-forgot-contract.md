# Verify FSRS State Under the Forgot Review Policy

Id: 12
Parent: [Vocab-Learn Browser V1 Decision Map](../map.md)
Type: research
Labels: wayfinder:research
Mode: AFK
Status: resolved
Assignee: /root/research_scheduling
Blocked by: 03, 06
Research branch: research/fsrs-forgot-contract
Research commit: 2d6089f668203af7e1217daa63580f6c6a6c31cb

## Question

Using the selected Py-FSRS 6.3.2 implementation, can the agreed one-minute/24-hour Forgot policy preserve meaningful default FSRS state and return a valid normal interval after the third target-recall success?

Inspect primary documentation and the installed implementation, then run a small fixed-clock, assert-based investigation. Test the proposed mapping A/B/C to Again, D to Good, and E to Easy; Hard is not inferred from response time alone. In Normal, C stays in the Normal collection despite its failed-target rating. In Forgot, override the returned due time with one minute after A/B/C and 24 hours after the first two D/E successes; keep stability, difficulty, and last-review data rather than resetting on graduation. The third qualifying D/E should use FSRS's returned interval.

Investigate all D/E success combinations and lapse/reset paths, whether default learning/relearning states can remain stuck, actual timezone/datetime requirements, serialization, default retention/fuzzing, and the minimum API surface needed. Distinguish library facts from application policy. Do not use private APIs or silently choose altered model parameters to make the experiment pass.

Retain an English research note and a small reproducible check on the `research/fsrs-forgot-contract` branch. No production application, credentials, paid model requests, or changes to the main tracker from the research worker.

## Answer

Resolved on 2026-10-31 by the assigned research worker. All 192 fixed-clock cases passed under installed `fsrs==6.3.2` with the default scheduler. The proposed rating mapping and due-only Forgot overrides retain the library's memory state; every third target-recall success reached Review without resetting memory or using private APIs.

See the [research report](../../../research/v1-fsrs-forgot-contract.md) and [reproducible assert-based check](../../../research/v1-fsrs-forgot-check.py) for source citations, actual fixture-dependent intervals, serialization/UTC checks, default fuzzing, and eligibility constraints. The application must enforce due eligibility and reuse persisted results rather than rerun fuzzed scheduling. This verifies the integration contract, not learning efficacy.

Provenance: `research/fsrs-forgot-contract` at `2d6089f668203af7e1217daa63580f6c6a6c31cb`. The repository assets match that research commit. No production adapter, credentials, model calls, or optimizer was used.
