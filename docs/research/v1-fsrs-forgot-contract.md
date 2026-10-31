# FSRS state under the Forgot review policy

Checked on 2026-10-31 for **Verify FSRS State Under the Forgot Review Policy**. The selected implementation is `fsrs==6.3.2`; learning content remains language-agnostic.

## Result

**The proposed contract is compatible with the tested default scheduler.** Map A/B/C to Again, D to Good, and E to Easy. Pass every assessed, eligible review through FSRS once, then override only the returned card's due time while the application keeps it in Forgot. The third qualifying success uses FSRS's returned due time without resetting or reconstructing memory.

All 192 fixed-clock graduation cases passed. Every third D/E success was already in FSRS `State.Review` with `step=None`; no private method, forced state transition, custom weights, retention change, disabled fuzzing, or optimizer was needed. This establishes API/state compatibility, not an empirical claim about recall accuracy under forced intervals or AI-assigned ratings.

## Library facts and application policy

The publisher documents default retention of 0.9, learning steps of one and ten minutes, a ten-minute relearning step, and enabled interval fuzzing. These defaults were retained and asserted against the installed package. [Versioned package documentation](https://pypi.org/project/fsrs/6.3.2/).

In the inspected implementation, Good advances a learning step and exits at the final step; Easy exits learning immediately. Default relearning has one step, so Good or Easy exits it. Again resets the applicable step. Consequently, an initial failed card needs at most two Good successes to reach Review, while a lapsed mature card needs one; business membership can still remain Forgot until success three. [Maintainer scheduler source](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/fsrs/scheduler.py#L253-L472).

Keep these two concepts separate:

| Concern | Agreed application policy |
| --- | --- |
| A/B in Normal | Enter Forgot, reset its streak, and persist a due time one minute after the actual review. |
| C in Normal | Stay Normal. It still maps to Again because the target was not recalled; keep the returned FSRS due time. This may put the library card into Relearning without entering the business Forgot collection. |
| A/B/C already in Forgot | Reset the streak; keep the returned memory/state update but set due to actual review time plus one minute. |
| First or second eligible D/E in Forgot | Increment the streak; preserve the returned memory/state update and set due to actual review time plus 24 hours. |
| Third eligible D/E in Forgot | Graduate to Normal and retain the complete returned FSRS card, including its due time. |
| Skip or Not assessed | No scheduler call, rating, review log, memory update, or streak change. |

D is Good rather than Hard: elapsed time alone does not define a difficult-recall rating, and Hard would not advance the default learning step. The mapping above is the selected product interpretation, not a mapping inferred by the library.

The check confirms that changing the input due time, with all memory fields, actual review timestamp, rating, and random state held equal, produces the same FSRS result. Thus a due-only override does not erase prior memory. Preserve `stability`, `difficulty`, `state`, `step`, `last_review`, and card identity exactly as returned; do not fabricate timestamps or recreate the card on graduation.

## Reproducible investigation

Run the adjacent [assert-based check](v1-fsrs-forgot-check.py) with:

```sh
/home/rlan/anaconda3/envs/mykik_py311/bin/python docs/research/v1-fsrs-forgot-check.py
```

The installed package was checked at `/home/rlan/anaconda3/envs/mykik_py311/lib/python3.11/site-packages/fsrs/scheduler.py`. Public imports and methods only were used: `Scheduler`, `Card`, `Rating`, `State`, `ReviewLog`, `review_card`, and JSON/dictionary serialization. Card fixtures are built through real public review calls rather than injected stability/difficulty values.

The 192 paths combine:

- Three entry states: initial Learning, mature Review, and existing Relearning.
- All eight D/E triples.
- No intervening reset, or A/B/C after an initial success.
- On-time reviews, or actual reviews delayed by three days and five hours.

The check also verifies A/B entry, neutral interactions, preservation of input cards, positive finite memory values, UTC requirements, exact one-minute/24-hour overrides, and unchanged raw due time on graduation. Card and ReviewLog are round-tripped after every assessment; Scheduler configuration is round-tripped too. The public serialization contracts include due and last-review timestamps. [Card serialization](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/fsrs/card.py#L88-L156), [ReviewLog serialization](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/fsrs/review_log.py#L48-L109).

**Test-only randomness:** the script seeds Python's random generator with `20261031` for reproducibility and separately uses seeds 0–7 to demonstrate active default fuzzing. No seed is proposed for production. Exact examples depend on the fixture, prior reviews, and random draws; they are not an interval table.

### Observed normal-review examples

These are offsets from the actual review time in one reproducible run. The mature fixture has two earlier successful reviews and a correspondingly different memory state.

| Starting library state | Grade / rating | Raw FSRS offset | Persisted policy offset |
| --- | --- | --- | --- |
| Initial Learning | A / Again | 1 minute | 1 minute; enters Forgot |
| Initial Learning | C / Again | 1 minute | 1 minute; stays Normal |
| Initial Learning | D / Good | 10 minutes | 10 minutes |
| Initial Learning | E / Easy | 8 days | 8 days |
| Mature Review | A / Again | 10 minutes | 1 minute; enters Forgot |
| Mature Review | C / Again | 10 minutes | 10 minutes; stays Normal |
| Mature Review | D / Good | 180 days | 180 days |
| Mature Review | E / Easy | 292 days | 292 days |

### Observed third-success examples

For an initially failed Learning card, with no reset or missed review, these are the unmodified FSRS offsets after success three:

| Successful route | Offset after third success |
| --- | --- |
| DDD | 5 days |
| DDE | 8 days |
| DED | 10 days |
| DEE | 10 days |
| EDD | 7 days |
| EDE | 8 days |
| EED | 10 days |
| EEE | 12 days |

Across the entire case matrix, observed graduation offsets ranged from 2–37 days for initial Learning, 3–42 for mature Review, and 2–17 for existing Relearning. These are sample ranges, not guaranteed bounds. In the separate same-state Good fuzzing probe, seeds 0–7 produced offsets of 137, 138, 139, 140, 146, 149, 150, and 152 days; this confirms the test did not silently disable default randomness.

## Constraints for the implementation decision

- Supply actual timezone-aware UTC review timestamps. The library rejects naive and non-UTC review times; normalizing a local offset with `astimezone(timezone.utc)` passed. The inspected scheduler uses elapsed whole days for relevant memory calculations. [Timestamp handling](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/fsrs/scheduler.py#L219-L251).
- The library accepts a review before its due time. Eligibility and the three-success rule therefore belong to the application. The research helper rejects early scored reviews to model the agreed due queue; it does not implement an optional early-practice feature. Extra same-day practice must not increment the graduation streak.
- A missed day does not itself update or reset a streak. Use the actual delayed review time for FSRS and for the next one-minute/24-hour delay. The check explicitly covers these delays.
- Persist the returned card, effective due time, application collection/streak, and review log together. Repeating the scheduler call to redisplay or retry a completed assessment can draw a different fuzzed interval; reuse the persisted result.
- A 0.9 desired retention is a model target, not a guarantee for this app's users. ASR/AI grading accuracy and whether this custom policy is well calibrated require later evidence. Changing library version, learning steps, parameters, or the D/E mapping requires revisiting this check.

No production adapter was written. No optimizer, credentials, paid API calls, browser behavior, or real-user retention were tested. Context7 was not exposed in this worker's tool list; the investigation used versioned publisher documentation, pinned maintainer source, installed-source inspection, and runtime assertions.
