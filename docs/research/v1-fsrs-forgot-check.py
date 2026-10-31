"""Research-only public-API check; run with Python containing fsrs==6.3.2."""

from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from itertools import product
import json
import math
import random

from fsrs import Card, Rating, ReviewLog, Scheduler, State


BASE = datetime(2026, 10, 31, 15, 0, tzinfo=timezone.utc)
MINUTE = timedelta(minutes=1)
DAY = timedelta(days=1)
RATINGS = {**dict.fromkeys("ABC", Rating.Again), "D": Rating.Good, "E": Rating.Easy}
scheduler = Scheduler()


def fixture(kind):
    card = Card(card_id=1, due=BASE)
    if kind != "learning":
        card, _ = scheduler.review_card(card, Rating.Easy, review_datetime=card.due)
        card, _ = scheduler.review_card(card, Rating.Good, review_datetime=card.due)
        assert card.state == State.Review
    if kind == "relearning":
        card, _ = scheduler.review_card(card, Rating.Again, review_datetime=card.due)
        assert card.state == State.Relearning
    return card


def assess(card, collection, streak, grade, when):
    """Simulate the agreed policy for due reviews, without a production adapter."""
    before = card.to_dict()
    if grade in ("Skip", "Not assessed"):
        return card, collection, streak, None, card.due
    # Eligibility is application policy: FSRS itself does not reject early reviews.
    if when < card.due:
        raise ValueError("This investigation only awards streaks to due reviews")
    updated, log = scheduler.review_card(
        card, RATINGS[grade], review_datetime=when, review_duration=15_000
    )
    assert card.to_dict() == before, "review_card returns a copy"
    library_due = updated.due
    memory = updated.to_dict()
    if grade in "AB" or collection == "Forgot":
        collection = "Forgot"
        streak = streak + 1 if grade in "DE" else 0
        if streak == 3:
            collection = "Normal"
        else:
            updated.due = when + (DAY if grade in "DE" else MINUTE)
    assert {k: v for k, v in updated.to_dict().items() if k != "due"} == {
        k: v for k, v in memory.items() if k != "due"
    }, "Only the library's returned due time may be overridden"
    assert updated.last_review == when == log.review_datetime
    assert log.rating == RATINGS[grade]
    assert math.isfinite(updated.stability) and updated.stability > 0
    assert math.isfinite(updated.difficulty) and 1 <= updated.difficulty <= 10
    assert ReviewLog.from_json(log.to_json()).to_dict() == log.to_dict()
    restored = Card.from_json(updated.to_json())
    assert restored.to_dict() == updated.to_dict()
    return restored, collection, streak, log, library_due


def main():
    assert version("fsrs") == "6.3.2"
    random.seed(20261031)  # Test-only reproducibility; default fuzzing remains enabled.
    assert scheduler.desired_retention == 0.9 and scheduler.enable_fuzzing
    assert len(scheduler.parameters) == 21
    assert scheduler.learning_steps == (MINUTE, 10 * MINUTE)
    assert scheduler.relearning_steps == (10 * MINUTE,)
    assert Scheduler.from_json(scheduler.to_json()).to_dict() == scheduler.to_dict()
    cases = 0
    graduation_days = {kind: [] for kind in ("learning", "mature", "relearning")}
    initial_graduation_days = {}

    for kind, route, reset, delay in product(
        graduation_days, product("DE", repeat=3), (None, "A", "B", "C"),
        (timedelta(0), timedelta(days=3, hours=5)),
    ):
        card = fixture(kind)
        entry_time = card.due
        entry_grade = "A" if reset is None else "B"
        card, collection, streak, _, _ = assess(card, "Normal", 0, entry_grade, entry_time)
        assert (collection, streak, card.due) == ("Forgot", 0, entry_time + MINUTE)
        if reset:
            card, collection, streak, _, _ = assess(card, collection, streak, "D", card.due)
            assert streak == 1
            reset_time = card.due + delay
            card, collection, streak, _, _ = assess(card, collection, streak, reset, reset_time)
            assert (collection, streak, card.due) == ("Forgot", 0, reset_time + MINUTE)
        for expected_streak, grade in enumerate(route, 1):
            when = card.due + (delay if expected_streak > 1 else timedelta(0))
            card, collection, streak, _, library_due = assess(card, collection, streak, grade, when)
            assert streak == expected_streak
            if expected_streak < 3:
                assert collection == "Forgot" and card.due == when + DAY
                snapshot = (card.to_dict(), collection, streak)
                for neutral in ("Skip", "Not assessed"):
                    same, same_collection, same_streak, log, _ = assess(
                        card, collection, streak, neutral, when
                    )
                    assert log is None and (same.to_dict(), same_collection, same_streak) == snapshot
                try:
                    assess(card, collection, streak, "E", when + timedelta(hours=1))
                except ValueError:
                    pass
                else:
                    raise AssertionError("Early extra practice must not award a streak")
                assert (card.to_dict(), collection, streak) == snapshot
            else:
                assert collection == "Normal" and card.state == State.Review and card.step is None
                assert card.due == library_due and card.due >= when + DAY
                graduation_days[kind].append((card.due - when).days)
                if kind == "learning" and reset is None and delay == timedelta(0):
                    initial_graduation_days["".join(route)] = (card.due - when).days
        cases += 1

    normal_offsets = {}
    for kind in ("learning", "mature"):
        normal_offsets[kind] = {}
        for grade in "ACDE":
            card = fixture(kind)
            when = card.due
            updated, collection, _, _, library_due = assess(card, "Normal", 0, grade, when)
            assert collection == ("Forgot" if grade == "A" else "Normal")
            if grade != "A":
                assert updated.due == library_due
            normal_offsets[kind][grade] = {
                "library_seconds": int((library_due - when).total_seconds()),
                "persisted_seconds": int((updated.due - when).total_seconds()),
            }

    card = fixture("mature")
    samples = set()
    for seed in range(8):
        random.seed(seed)
        updated, _ = scheduler.review_card(card, Rating.Good, review_datetime=card.due)
        samples.add((updated.due - card.due).days)
    assert len(samples) > 1, "Default fuzzing is active, not silently disabled"

    for invalid_time in (BASE.replace(tzinfo=None), BASE.astimezone(timezone(timedelta(hours=8)))):
        try:
            scheduler.review_card(Card(card_id=2, due=BASE), Rating.Good, review_datetime=invalid_time)
        except ValueError:
            pass
        else:
            raise AssertionError("Naive/non-UTC review timestamps must be normalized")
    early = Card(card_id=3, due=BASE + DAY)
    accepted, _ = scheduler.review_card(early, Rating.Good, review_datetime=BASE)
    assert accepted.last_review == BASE, "FSRS leaves due eligibility to the application"
    local_time = BASE.astimezone(timezone(timedelta(hours=8)))
    normalized, _ = scheduler.review_card(
        Card(card_id=4, due=BASE), Rating.Good,
        review_datetime=local_time.astimezone(timezone.utc),
    )
    assert normalized.last_review == BASE
    altered_due = Card.from_json(card.to_json())
    altered_due.due += 10 * DAY
    random_state = random.getstate()
    original_result, _ = scheduler.review_card(card, Rating.Good, review_datetime=card.due)
    random.setstate(random_state)
    altered_result, _ = scheduler.review_card(altered_due, Rating.Good, review_datetime=card.due)
    assert original_result.to_dict() == altered_result.to_dict(), "Input due is not a memory input"

    print(json.dumps({
        "fsrs_version": version("fsrs"), "test_seed": 20261031, "graduation_cases": cases,
        "graduation_days_min_max": {k: [min(v), max(v)] for k, v in graduation_days.items()},
        "initial_graduation_days": initial_graduation_days,
        "seeded_normal_examples": normal_offsets,
        "good_days_across_seeds_0_to_7": sorted(samples),
        "status": "all assertions passed",
    }, indent=2))


if __name__ == "__main__":
    main()
