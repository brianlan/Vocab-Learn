"""Deck progress metric: cumulative current-source D/E qualification per deck tile."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from learning import authoring, views, work
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

    def review_of(self, card, grade, user=None):
        """One committed review fixture whose frozen snapshot carries the card's current source version."""
        user = user or card.deck.owner
        p = Presentation.objects.create(user=user, scope_deck=card.deck, card=card,
            source_version=card.source_version, progress_version=card.progress_version,
            snapshot={"kind": card.kind, "source_version": card.source_version}, budget=60)
        a = Attempt.objects.create(presentation=p, action="speak", state="assessed", submitted_at=timezone.now(),
            duration=2, grade=grade, reason="Fixture review.")
        return ScoredReview.objects.create(attempt=a, card=card, user=user, grade=grade, reviewed_at=timezone.now(),
            next_due=card.due, snapshot={"source_version": card.source_version}, fsrs_log={}, duration=2, budget=60)

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
        self.review_of(kept, "E"); self.review_of(kept, "A"); self.review_of(kept, "C")
        repeated = self.generic(tag="repeated")
        self.review_of(repeated, "D"); self.review_of(repeated, "D"); self.review_of(repeated, "E")
        vocab = self.ready(self.vocabulary())
        self.review_of(vocab, "D")
        result = self.progress(self.deck)
        # C alone never qualifies; D/E followed by A/B/C stays qualified; repeats count one card; kinds both count.
        self.assertEqual(result[self.deck.pk], {"total": 9, "qualified": 5, "percent": 55})
        self.assertEqual(ScoredReview.objects.filter(card=kept).count(), 3)
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

    def test_current_source_lifecycle(self):
        card = self.generic(tag="lifecycle")
        self.review_of(card, "D")
        authoring.save_card(self.deck, "generic", {**GENERIC, "answer": f"Answer for {card.answer}", "question": "What is seven times six?"}, card)
        card.refresh_from_db()
        self.assertGreater(card.source_version, 1)
        self.assertEqual(self.progress(self.deck)[self.deck.pk]["qualified"], 0)  # old-source history does not qualify
        self.review_of(card, "E")                                                 # new source qualifies again
        self.assertEqual(self.progress(self.deck)[self.deck.pk]["qualified"], 1)
        # A content-identical resubmission preserves the source version and qualification.
        authoring.save_card(self.deck, "generic", {**GENERIC, "answer": card.answer,
                                                   "question": "What is seven times six?"}, card)
        card.refresh_from_db()
        self.assertEqual(self.progress(self.deck)[self.deck.pk]["qualified"], 1)
        # Example correction and deck metadata changes do not reset qualification.
        vocab = self.ready(self.vocabulary())
        self.review_of(vocab, "D")
        work.save_corrected_pair(vocab.pk, vocab.source_version, vocab.active_pair_id,
                                 {**PAIR, "native_sentence": "那次误会很小。", "native_highlight_start": 2}, {})
        self.deck.name = "Renamed deck"; self.deck.save(update_fields=["name"])
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
                self.review_of(card, "D")
            return decks

        one = fresh_decks(1, "single")
        with CaptureQueriesContext(connection) as ctx_one:
            views.deck_progress(self.user, one)
        self.client.force_login(self.user)
        with CaptureQueriesContext(connection) as ctx_page_one:
            self.client.get(reverse("library"))
        many = fresh_decks(6, "many")
        with CaptureQueriesContext(connection) as ctx_many:
            views.deck_progress(self.user, many)
        with CaptureQueriesContext(connection) as ctx_page_many:
            self.client.get(reverse("library"))
        self.assertEqual(len(ctx_many), len(ctx_one))                     # aggregation does not grow per deck
        self.assertLessEqual(len(ctx_page_many) - len(ctx_page_one), 3)   # page rendering stays bounded
        before = [(c.pk, c.source_version, c.fsrs, c.due, c.collection, c.review_count) for c in Card.objects.all()]
        reviews = ScoredReview.objects.count()
        self.client.get(reverse("library") + "?archived=1")
        self.assertEqual([(c.pk, c.source_version, c.fsrs, c.due, c.collection, c.review_count) for c in Card.objects.all()], before)
        self.assertEqual(ScoredReview.objects.count(), reviews)
