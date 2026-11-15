"""Deck progress metric: cumulative current-source D/E qualification per deck tile."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from learning import authoring, review, views, work
from learning.models import Attempt, Card, Deck, Presentation, ScoredReview
from .test_learning import GENERIC, PAIR, VOCAB


class DeckProgressTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("progress", password="x")
        self.other = get_user_model().objects.create_user("other", password="x")
        self.deck = Deck.objects.create(owner=self.user, name="Progress deck")

    def generic(self, deck=None, tag=None, **overrides):
        tag = tag or f"card-{Card.objects.count() + 1}"
        return authoring.save_card(deck or self.deck, "generic", {**GENERIC, "answer": f"Answer for {tag}.", **overrides})

    def vocabulary(self, deck=None, **overrides):
        return authoring.save_card(deck or self.deck, "vocabulary", {**VOCAB, **overrides})

    def ready(self, card):
        job = card.generation_jobs.get(mode="initial")
        job.state = "processing"
        job.started_at = timezone.now()
        job.deadline = job.started_at + timedelta(seconds=300)
        job.save()
        work.save_pair(job.pk, job.claim, PAIR, {})
        card.refresh_from_db()
        return card

    def review_of(self, card, grade, user=None, direction=None):
        """One committed review fixture whose frozen snapshot carries the card's current source version."""
        user = user or card.deck.owner
        snapshot = {"source_version": card.source_version}
        if direction:
            snapshot["direction"] = direction
        p = Presentation.objects.create(user=user, scope_deck=card.deck, card=card,
            source_version=card.source_version, progress_version=card.progress_version,
            snapshot={**snapshot, "kind": card.kind}, budget=60)
        a = Attempt.objects.create(presentation=p, action="speak", state="assessed", submitted_at=timezone.now(),
            duration=2, grade=grade, reason="Fixture review.")
        return ScoredReview.objects.create(attempt=a, card=card, user=user, grade=grade, reviewed_at=timezone.now(),
            next_due=card.due, snapshot=snapshot, fsrs_log={}, duration=2, budget=60)

    def progress(self, decks, user=None):
        return views.deck_progress(user or self.user, decks if isinstance(decks, list) else [decks])

    def test_qualification_rules_and_deduplication(self):
        empty = Deck.objects.create(owner=self.user, name="Empty deck")
        self.assertEqual(self.progress([empty]), {empty.pk: {"total": 0, "qualified": 0, "percent": None}})
        unseen = self.generic(tag="unseen")
        a_card, b_card, c_card = (self.generic(tag=tag) for tag in ["a-only", "b-only", "c-only"])
        self.review_of(a_card, "A"); self.review_of(b_card, "B"); self.review_of(c_card, "C")
        d_card, e_card = self.generic(tag="d-card"), self.generic(tag="e-card")
        self.review_of(d_card, "D"); self.review_of(e_card, "E")
        kept = self.generic(tag="kept-after-lows")
        self.review_of(kept, "E"); self.review_of(kept, "A"); self.review_of(kept, "B"); self.review_of(kept, "C")
        repeated = self.generic(tag="repeated")
        self.review_of(repeated, "D"); self.review_of(repeated, "D"); self.review_of(repeated, "E")
        vocab = self.ready(self.vocabulary())
        self.review_of(vocab, "D", direction="recognition")     # both directions of the same card...
        self.review_of(vocab, "E", direction="production")      # ...still count one distinct card
        result = self.progress(self.deck)
        # C alone never qualifies; D/E followed by A/B/C stays qualified; repeats count one card; kinds both count.
        self.assertEqual(result[self.deck.pk], {"total": 9, "qualified": 5, "percent": 55})
        self.assertEqual(ScoredReview.objects.filter(card=kept).count(), 4)
        self.assertEqual(ScoredReview.objects.filter(card=vocab).count(), 2)
        self.assertIsNotNone(unseen)

    def test_denominator_includes_all_active_cards(self):
        seen = self.generic(tag="seen")
        self.review_of(seen, "D")
        preparing = self.vocabulary(word="preparing")            # ready=False, still counted
        failed = self.vocabulary(word="failed-source")           # preparation failed, still counted
        job = failed.generation_jobs.get(mode="initial")
        job.state = "failed"; job.error = "no key"; job.save()
        future = self.generic(tag="future"); future.due = timezone.now() + timedelta(days=30); future.save()
        forgot = self.generic(tag="forgot"); forgot.collection = "Forgot"; forgot.save()
        deferred = self.generic(tag="deferred"); deferred.deferred_until = timezone.now() + timedelta(hours=1); deferred.save()
        archived = self.generic(tag="archived")
        self.review_of(archived, "D")
        authoring.archive_card(archived, True)
        result = self.progress(self.deck)
        self.assertEqual((result[self.deck.pk]["total"], result[self.deck.pk]["qualified"], result[self.deck.pk]["percent"]),
                         (6, 1, 16))
        # An archived deck's tile computes identically when that tab is selected.
        archived_deck = Deck.objects.create(owner=self.user, name="Archived deck")
        inside = self.generic(archived_deck, tag="inside")
        self.review_of(inside, "E")
        authoring.archive_deck(archived_deck, True)
        self.assertEqual(self.progress([self.deck, archived_deck])[archived_deck.pk],
                         {"total": 1, "qualified": 1, "percent": 100})
        self.assertIsNotNone(preparing)

    def test_unfinished_work_never_qualifies(self):
        # Attempt states the real flows produce, none of which commit a ScoredReview.
        for tag, state, action in [("cancelled", None, "speak"), ("pending", "submitted", "speak"),
                                   ("processing", "processing", "speak"), ("failed-attempt", "failed", "speak"),
                                   ("skipped", "skipped", "skip"), ("exited", "closed_unassessed", "speak")]:
            card = self.generic(tag=tag)
            p = Presentation.objects.create(user=self.user, scope_deck=self.deck, card=card,
                source_version=card.source_version, progress_version=card.progress_version,
                snapshot={"source_version": card.source_version}, budget=60)
            if state:
                Attempt.objects.create(presentation=p, action=action, state=state, submitted_at=timezone.now(),
                    duration=None if action == "skip" else 2, error_stage="timing" if state == "failed" else "")
        self.assertEqual(ScoredReview.objects.count(), 0)
        self.assertEqual(self.progress(self.deck)[self.deck.pk], {"total": 6, "qualified": 0, "percent": 0})

    def test_counts_come_from_one_snapshot_and_stay_coherent(self):
        seen = self.generic(tag="coherent-seen")
        self.review_of(seen, "D")
        archived = self.generic(tag="coherent-archived")
        self.review_of(archived, "D")
        authoring.archive_card(archived, True)
        self.generic(tag="coherent-unseen")
        with CaptureQueriesContext(connection) as ctx:
            row = self.progress(self.deck)[self.deck.pk]
        self.assertEqual(len(ctx), 1)                       # both counts are one grouped SELECT: no interleaving
        self.assertEqual((row["total"], row["qualified"], row["percent"]), (2, 1, 50))
        self.assertTrue(0 <= row["qualified"] <= row["total"])
        authoring.archive_card(archived, False)             # the restore that used to race the separate reads
        row = self.progress(self.deck)[self.deck.pk]
        self.assertEqual((row["total"], row["qualified"], row["percent"]), (3, 2, 66))
        self.assertTrue(0 <= row["qualified"] <= row["total"])

    def test_current_source_lifecycle(self):
        card = self.generic(tag="lifecycle")
        self.review_of(card, "D")
        authoring.save_card(self.deck, "generic", {**GENERIC, "answer": f"Answer for {card.answer}", "question": "What is seven times six?"}, card)
        card.refresh_from_db()
        self.assertGreater(card.source_version, 1)
        self.assertEqual(self.progress(self.deck)[self.deck.pk]["qualified"], 0)  # old-source history does not qualify
        self.review_of(card, "E")                                                 # new source qualifies again
        self.assertEqual(self.progress(self.deck)[self.deck.pk]["qualified"], 1)
        # A real presentation-only Markdown change preserves the source version and qualification.
        version_before = card.source_version
        authoring.save_card(self.deck, "generic", {**GENERIC, "answer": card.answer,
                                                   "question": "**What is seven times six?**"}, card)
        card.refresh_from_db()
        self.assertEqual(card.question, "**What is seven times six?**")
        self.assertEqual(card.source_version, version_before)
        self.assertEqual(self.progress(self.deck)[self.deck.pk]["qualified"], 1)
        # Example correction and deck metadata changes do not reset qualification.
        vocab = self.ready(self.vocabulary())
        self.review_of(vocab, "D")
        work.save_corrected_pair(vocab.pk, vocab.source_version, vocab.active_pair_id,
                                 {**PAIR, "native_sentence": "那次误会很小。", "native_highlight_start": 2}, {})
        self.deck.name = "Renamed deck"; self.deck.save(update_fields=["name"])
        self.assertEqual(self.progress([self.deck])[self.deck.pk]["qualified"], 2)
        # Automatic rotation installs a new active pair without touching the source or qualification.
        Card.objects.filter(pk=card.pk).update(due=timezone.now() + timedelta(days=1))
        p = review.next_question(self.user, self.deck)
        self.assertEqual(p.card_id, vocab.pk)
        a = review.submit(p, "speak", 2)
        self.assertEqual(review.commit_grade(a.pk, a.claim, "E", [], "Automatic rotation fixture.").state, "assessed")
        vocab.refresh_from_db()
        version_before, old_pair = vocab.source_version, vocab.active_pair_id
        rotation = vocab.generation_jobs.get(mode="rotation", state="queued")
        rotation.state = "processing"; rotation.started_at = timezone.now()
        rotation.deadline = rotation.started_at + timedelta(seconds=300); rotation.save()
        rotated = work.save_pair(rotation.pk, rotation.claim,
            {**PAIR, "target_sentence": "A quiet misunderstanding delayed the meeting.",
             "native_sentence": "那次误会推迟了会议。", "native_highlight_start": 2}, {})
        self.assertIsNotNone(rotated)
        self.assertNotEqual(old_pair, rotated.pk)
        self.assertEqual(self.progress(self.deck)[self.deck.pk]["qualified"], 2)
        Card.objects.filter(pk=card.pk).update(due=vocab.due + timedelta(days=1))
        with patch("learning.review.timezone.now", return_value=vocab.due + timedelta(seconds=1)):
            presented = review.next_question(self.user, self.deck)   # activate only at the next eligible review
        self.assertEqual(presented.snapshot["pair_id"], rotated.pk)
        vocab.refresh_from_db()
        self.assertEqual(vocab.active_pair_id, rotated.pk)
        self.assertIsNone(vocab.rotation_token)
        self.assertEqual(vocab.source_version, version_before)
        result = self.progress([self.deck])
        self.assertEqual(result[self.deck.pk]["qualified"], 2)

    def test_archive_restore_and_neutral_actions(self):
        card = self.generic(tag="restorable")
        self.review_of(card, "D")
        skip_p = Presentation.objects.create(user=self.user, scope_deck=self.deck, card=card,
            source_version=card.source_version, progress_version=card.progress_version,
            snapshot={"source_version": card.source_version}, budget=60)
        Attempt.objects.create(presentation=skip_p, action="skip", state="skipped", submitted_at=timezone.now())
        self.assertEqual(ScoredReview.objects.count(), 1)  # skip invents no qualifying score
        authoring.archive_card(card, True)
        self.assertEqual(self.progress(self.deck)[self.deck.pk], {"total": 0, "qualified": 0, "percent": None})
        authoring.archive_card(card, False)                # restore uses retained current-source history
        self.assertEqual(self.progress(self.deck)[self.deck.pk]["qualified"], 1)
        self.review_of(card, "A")                          # explicit Forgot after D/E retains qualification
        self.assertEqual(self.progress(self.deck)[self.deck.pk]["qualified"], 1)

    def test_ownership_and_deck_separation(self):
        other_deck = Deck.objects.create(owner=self.other, name="Other deck")
        mine = self.generic(tag="mine")
        theirs = self.generic(other_deck, tag="theirs")
        self.review_of(mine, "D", user=self.other)         # another user's review never qualifies my deck
        self.review_of(theirs, "E", user=self.other)
        result = self.progress([self.deck, other_deck])
        self.assertEqual(result[self.deck.pk], {"total": 1, "qualified": 0, "percent": 0})
        self.assertEqual(result[other_deck.pk], {"total": 0, "qualified": 0, "percent": None})  # no cross-owner data
        other_result = self.progress([other_deck], user=self.other)
        self.assertEqual(other_result[other_deck.pk], {"total": 1, "qualified": 1, "percent": 100})
        self.review_of(mine, "E")                          # my own review qualifies
        self.assertEqual(self.progress(self.deck)[self.deck.pk]["percent"], 100)

    def test_rounding_and_rendering(self):
        third, almost, full = (Deck.objects.create(owner=self.user, name=name) for name in ["Third", "Almost", "Full"])
        for deck, count, graded in [(third, 3, 1), (almost, 1000, 999), (full, 2, 2)]:
            cards = [self.generic(deck, tag=f"{deck.pk}-{index}") for index in range(count)]
            for card in cards[:graded]:
                self.review_of(card, "D")
        self.assertEqual(self.progress(third)[third.pk]["percent"], 33)
        self.assertEqual(self.progress(almost)[almost.pk]["percent"], 99)
        self.assertEqual(self.progress(full)[full.pk]["percent"], 100)
        empty = Deck.objects.create(owner=self.user, name="No cards")
        self.client.force_login(self.user)
        html = self.client.get(reverse("library")).content.decode()
        self.assertIn("LEARNING PROGRESS", html)
        self.assertIn("33%", html)
        self.assertIn("1 / 3 active cards", html)
        self.assertIn("Cards with at least one D/E on their current content.", html)
        self.assertIn('max="3" value="1"', html)
        self.assertIn("99%", html)
        self.assertIn("100%", html)
        self.assertIn("No active cards", html)
        self.assertIn('aria-label="Learning progress: no active cards"', html)
        self.assertIn("&ndash;", html)
        archived_empty = Deck.objects.create(owner=self.user, name="Archived empty", archived=True)
        self.assertIn("No active cards", self.client.get(reverse("library") + "?archived=1").content.decode())
        long_name = Deck.objects.create(owner=self.user, name="A very long deck name " * 6)
        self.generic(long_name, tag="longname-card")
        self.assertIn("A very long deck name", self.client.get(reverse("library")).content.decode())

    def test_bounded_queries_and_readonly_rendering(self):
        def fresh_decks(count, prefix):
            decks = [Deck.objects.create(owner=self.user, name=f"{prefix}-{index}") for index in range(count)]
            for deck in decks:
                card = self.generic(deck, tag=f"{prefix}-{deck.pk}")
                attempt = review.submit(review.next_question(self.user, deck), "speak", 2)
                self.assertEqual(review.commit_grade(attempt.pk, attempt.claim, "D", [], "Read-only fixture.").state, "assessed")
                Card.objects.filter(pk=card.pk).update(deferred_until=timezone.now() + timedelta(minutes=30))
            return decks

        def saved_state():
            return (list(Card.objects.order_by("pk").values()), list(ScoredReview.objects.order_by("pk").values()))

        one = fresh_decks(1, "single")
        with CaptureQueriesContext(connection) as ctx_one:
            views.deck_progress(self.user, one)
        helper_queries_one = len(ctx_one)
        self.client.force_login(self.user)
        before = saved_state()
        with CaptureQueriesContext(connection) as ctx_page_one:
            first = self.client.get(reverse("library")).content.decode()
        page_queries_one = len(ctx_page_one)
        self.assertEqual(saved_state(), before)
        many = fresh_decks(6, "many")
        authoring.archive_deck(many[0], True)      # both tabs now render populated decks
        with CaptureQueriesContext(connection) as ctx_many:
            views.deck_progress(self.user, one + many)
        helper_queries_many = len(ctx_many)
        before = saved_state()
        with CaptureQueriesContext(connection) as ctx_page_many:
            self.client.get(reverse("library"))
        page_queries_many = len(ctx_page_many)
        self.assertContains(self.client.get(reverse("library") + "?archived=1"), "1 / 1 active cards")
        self.assertEqual((helper_queries_one, helper_queries_many), (1, 1))  # helper: one vs seven decks
        self.assertEqual(page_queries_many, page_queries_one)  # populated page: one vs six active decks
        self.assertEqual(saved_state(), before)
        # the nonempty bar's accessible name and value are rendered alongside the visible count
        self.assertIn('aria-label="Learning progress: 1 of 1 active cards"', first)
        self.assertIn('<progress max="1" value="1"', first)
