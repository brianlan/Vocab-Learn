# Scheduling evidence for Vocab-Learn v1

Reviewed on 2026-10-30. This note supplies facts for **Verify Regular and Reinforcement Scheduling Options**; it does not select an algorithm or settle product rules. Learning content remains language-agnostic.

## Findings

All three options can support a first version. None turns an AI answer judgment and elapsed seconds into the project's five feedback categories automatically. The custom Forgot collection also needs an explicit policy; it is not another name for an algorithm's built-in relearning state. These are integration conclusions from the contracts below, not measured learning outcomes.

| Option | Minimum scheduling state | Initial data and implementation cost | Important limitation |
| --- | --- | --- | --- |
| Fixed increasing intervals | A stage, its interval table, and the next due time; progress/reset rules are application policy. | No personal history or dependency is necessary. This describes a possible application rule, not a named or validated memory model. | Any particular intervals, success mapping, and handling of missed days must be chosen; it provides no inferred recall probability by itself. |
| SM-2 | Repetition count, previous interval, and an item-specific easiness factor, plus application timestamps. | The original algorithm starts with an easiness factor of 2.5 and first intervals of one and six days, then multiplies by the factor. It takes a 0–5 answer-quality grade. No training history is required. | A grade below 3 restarts the repetition sequence. The original also calls for same-day repetitions of grades below 4; these are not a specified ten-minute queue or the requested three-success exit rule. [Original author specification](https://super-memory.org/archive/english/ol/sm2.htm). |
| FSRS using Py-FSRS | Card state and learning step, stability, difficulty, due time, last-review time, and scheduler parameters. Review logs support later fitting and replay. | A new scheduler has default parameters; a new card can be reviewed immediately. Training is optional. The API returns an updated card and review log. [Card representation](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/fsrs/card.py), [maintainer quickstart and optional optimizer](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/README.md). | Its four ratings and three states are distinct from the project's five feedback categories and two collections. [Rating enum](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/fsrs/rating.py), [state enum](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/fsrs/state.py). |

The fixed-interval row is a definition of the candidate under discussion. It makes no scientific efficacy claim. The SM-2 and FSRS rows describe published algorithms or implementations, not evidence that one will outperform the others for spoken cloze answers.

## Python 3.11 and dependency facts

- PyPI lists `fsrs` **6.3.2**, released August 9, 2026, requiring Python **>=3.10**. Python 3.11 satisfies that declared requirement; this research did not install or execute the package. [Publisher's package metadata](https://pypi.org/project/fsrs/).
- The inspected Py-FSRS source identifies version 6.3.2. The ordinary scheduler depends on `typing-extensions`; the optional optimizer adds `torch`, `numpy`, `pandas`, and `tqdm`. An optimizer is therefore not required merely to schedule reviews with defaults. [Project metadata](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/pyproject.toml).
- A maintained SM-2 candidate exists in the same organization. Its inspected metadata identifies `sm-2` 0.3.0, Python **>=3.10**, and no runtime dependencies. This establishes a candidate's declared Python 3.11 compatibility, not a decision to add it or proof of runtime behavior. [SM-2 project metadata](https://github.com/open-spaced-repetition/sm-2/blob/b6272adbdef4a743aaf43e425b182bc47d208842/pyproject.toml).
- No claim about a universal minimum review count for personalization is needed: the relevant distinction for v1 is that default scheduling works without personal training, while fitting needs review logs. The Py-FSRS maintainer also cautions that its optimizer and Anki's implementation can produce different results. [Optional optimizer contract](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/README.md#optimizer-optional).

The Py-FSRS source snapshot was checked at commit `9446cb06605c597a063aeee49f7d188d42e34dc2`; the SM-2 snapshot at `b6272adbdef4a743aaf43e425b182bc47d208842`. Pin and verify a selected package version during implementation.

## Five feedback categories are a product mapping

SM-2's 0–5 grades distinguish complete failure, different unsuccessful recall experiences, and successful recall with varying difficulty. Five project categories cannot be assumed to be those six grades unchanged. [Original grading definitions](https://super-memory.org/archive/english/ol/sm2.htm).

FSRS uses Again, Hard, Good, and Easy. Anki explicitly defines Hard as **successful recall with difficulty**; using it for forgotten answers misrepresents the outcome. [Anki's FSRS guidance](https://docs.ankiweb.net/manual/deck-options#fsrs).

| Project feedback intent | Decision still required |
| --- | --- |
| A: user chooses Forgot | Whether to record a failed-recall scheduler rating, and which SM-2 grade if SM-2 is selected. |
| B: clearly wrong spoken answer | Whether A and B share scheduler input while retaining separate feedback for the user. |
| C: only an approximate meaning or synonym | Whether the target was actually recalled. This cannot become FSRS Hard merely because it sits between B and D. |
| D: fully correct but slow | Which successful rating applies, after response timing and difficulty rules are defined. |
| E: fully correct and fast | Which successful rating applies; elapsed time alone is not the scheduler's rating contract. |
| Skip, ASR failure, or invalid grading output | Whether a review occurred at all. Neither four-rating FSRS nor six-grade SM-2 provides a built-in Skip or technical-failure result. |

Py-FSRS accepts `review_duration`, but inspection of `review_card` shows that duration is stored in the review log rather than used to choose the next interval. The application must define any timing-to-rating conversion. Its review timestamp must be timezone-aware UTC. [Scheduling implementation](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/fsrs/scheduler.py), [duration field semantics](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/fsrs/review_log.py).

## Connecting the custom Forgot collection

Py-FSRS defaults to one- and ten-minute learning steps and a ten-minute relearning step. Again resets a step; Good advances it; Easy can leave learning or relearning immediately. This does **not** enforce three consecutive correct answers. Short-interval reviews update its memory state too, so overriding only the due time is not equivalent to leaving algorithm state untouched. [Scheduler transitions](https://github.com/open-spaced-repetition/py-fsrs/blob/9446cb06605c597a063aeee49f7d188d42e34dc2/fsrs/scheduler.py).

Anki recommends steps shorter than a day when using FSRS. The user's requirement to keep successful Forgot cards close on following days is a deliberate custom policy, not a guarantee supplied by standard FSRS settings. This observation does not invalidate that requirement. [Anki learning and relearning guidance](https://docs.ankiweb.net/manual/deck-options#learning-and-relearning-steps).

The following questions belong to the product decision ticket:

1. Which of C, D, and E count toward the three-success streak? What resets it, and can multiple same-day answers satisfy it?
2. Does “next day” mean a calendar date in the user's timezone or at least 24 elapsed hours? What happens after missed days?
3. Does each valid Forgot review update normal-algorithm state while the application controls its next due time, or is that state reset/reconstructed on exit? How is the third success recorded exactly once?
4. On exit, what normal interval or state applies? Resuming an old long interval and beginning afresh are different behaviors.
5. How do due Forgot cards rank against overdue normal cards and new cards, without making one remaining card repeat immediately forever?

These are integration obligations, not proposed answers. Regardless of algorithm, retaining actual review times and separating collection membership, streak, and scheduling state makes the eventual rule explainable; the exact persistence model remains undecided.

## Verification limits

Only first-party documentation, package metadata, and source were inspected. No dependencies were installed, no scheduler was executed, and no comparison with this application's real users was performed. This research does not validate any response-time threshold, success mapping, interval policy, or promised retention rate.
