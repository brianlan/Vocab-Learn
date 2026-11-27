"""Issue #27: collapsible Practice illustrations and the inline Card detail image."""
import tempfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from learning import authoring, review, work
from learning.models import Attempt, Card, Deck, ExamplePair, ExampleIllustration
from learning.tests.test_learning import GENERIC, PAIR, VOCAB


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PracticeIllustrationTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        override = override_settings(ILLUSTRATIONS_DIR=Path(directory.name))
        override.enable()
        self.addCleanup(override.disable)
        self.user = get_user_model().objects.create_user("scene-learner", password="test-password")
        self.other = get_user_model().objects.create_user("scene-other", password="test-password")
        self.deck = Deck.objects.create(owner=self.user, name="Scenes")
        self.client.force_login(self.user)

    def prepared_card(self):
        card = authoring.save_card(self.deck, "vocabulary", VOCAB)
        job = card.generation_jobs.get(mode="initial")
        job.state = "processing"; job.started_at = timezone.now(); job.deadline = job.started_at+timedelta(seconds=300); job.save()
        work.save_pair(job.pk, job.claim, PAIR, {"model": "test"})
        card.refresh_from_db()
        return card

    def publish(self, pair, image=b"scene-bytes"):
        """Force a done illustration with a stored artifact, bypassing the worker."""
        row, _ = ExampleIllustration.objects.get_or_create(pair=pair)
        ExampleIllustration.objects.filter(pk=row.pk).update(state="done", file=f"{row.pk}.scene.webp")
        (Path(settings.ILLUSTRATIONS_DIR)/f"{row.pk}.scene.webp").write_bytes(image)
        return reverse("illustration_image", args=[pair.pk])

    def present(self, card, direction="recognition"):
        Card.objects.filter(pk=card.pk).update(due=timezone.now()-timedelta(seconds=1), deferred_until=None,
            direction_block=[direction, "production" if direction == "recognition" else "recognition"],
            direction_index=0, cue_pair=card.active_pair_id, cue_direction=direction)
        return review.next_question(self.user, self.deck)

    def rotated_pair(self, card):
        return ExamplePair.objects.create(card=card, source_version=card.source_version,
            target_sentence=PAIR["target_sentence"]+" Again.", target_highlight=PAIR["target_highlight"],
            target_highlight_start=PAIR["target_highlight_start"], native_sentence=PAIR["native_sentence"],
            native_highlight=PAIR["native_highlight"], native_highlight_start=PAIR["native_highlight_start"])

    def assert_disclosure(self, markup, url, figure_id="back-illustration-figure"):
        self.assertIn(f'data-illustration-src="{url}"', markup)
        self.assertIn('data-illustration-toggle aria-expanded="false"', markup)
        self.assertIn(f'aria-controls="{figure_id}"', markup)
        self.assertIn("Show illustration", markup)
        # Collapsed by default: the image element carries no source, so nothing is fetched yet.
        self.assertIn(f'<figure class="illustration-figure" data-illustration-figure id="{figure_id}" hidden>', markup)
        self.assertIn('<img data-illustration-image alt="Illustration of the example scene">', markup)

    def test_question_and_answer_share_one_collapsed_disclosure_for_the_frozen_pair(self):
        card = self.prepared_card()
        url = self.publish(card.active_pair)
        for direction in ("recognition", "production"):
            p = self.present(card, direction)
            page = self.client.get(reverse("presentation", args=[p.pk])).content.decode()
            self.assert_disclosure(page, url, figure_id="front-illustration-figure")
            review.submit(p, "skip")
            back = self.client.get(reverse("status", args=[p.pk])).json()["back_html"]
            self.assert_disclosure(back, url)

    def test_voice_reveal_while_checking_keeps_the_disclosure_available(self):
        card = self.prepared_card()
        url = self.publish(card.active_pair)
        p = self.present(card, "recognition")
        # A real spoken submission: the deadline defaults to the full assessment window.
        review.submit(p, "speak", duration=2.0, audio_name="response.webm")
        data = self.client.get(reverse("status", args=[p.pk])).json()
        self.assertEqual(data["state"], "submitted")  # still Checking, not expired to failed
        self.assert_disclosure(data["back_html"], url)

    def test_forgot_reveals_a_collapsed_disclosure_on_a_fresh_presentation(self):
        card = self.prepared_card()
        url = self.publish(card.active_pair)
        p = self.present(card, "recognition")
        review.submit(p, "forgot")
        attempt = Attempt.objects.get(presentation=p)
        self.assertEqual((attempt.action, attempt.state, attempt.grade), ("forgot", "assessed", "A"))
        back = self.client.get(reverse("status", args=[p.pk])).json()["back_html"]
        self.assert_disclosure(back, url)

    def test_frozen_question_keeps_its_image_after_a_rotation(self):
        card = self.prepared_card()
        frozen_url = self.publish(card.active_pair)
        p = self.present(card, "recognition")
        rotated = self.rotated_pair(card)
        card.active_pair = rotated
        card.save(update_fields=["active_pair"])
        rotated_url = self.publish(rotated)
        page = self.client.get(reverse("presentation", args=[p.pk])).content.decode()
        self.assertIn(f'data-illustration-src="{frozen_url}"', page)
        self.assertNotIn(rotated_url, page)
        detail = self.client.get(reverse("card", args=[card.pk])).content.decode()
        self.assertIn(f'class="card-illustration" src="{rotated_url}"', detail)
        self.assertNotIn(frozen_url, detail)

    def test_card_detail_shows_only_a_ready_current_image(self):
        card = self.prepared_card()
        plain = self.client.get(reverse("card", args=[card.pk])).content.decode()
        self.assertNotIn("card-illustration", plain)
        url = self.publish(card.active_pair)
        detail = self.client.get(reverse("card", args=[card.pk])).content.decode()
        self.assertInHTML(f'<img class="card-illustration" src="{url}" alt="Illustration of the current example scene">', detail)

    def test_generic_cards_have_no_illustration_anywhere(self):
        card = authoring.save_card(self.deck, "generic", GENERIC)
        card.ready = True
        card.save(update_fields=["ready"])
        p = self.present(card)
        page = self.client.get(reverse("presentation", args=[p.pk])).content.decode()
        self.assertNotIn("data-illustration", page)
        review.submit(p, "skip")
        back = self.client.get(reverse("status", args=[p.pk])).json()["back_html"]
        self.assertNotIn("data-illustration", back)
        self.assertNotIn("card-illustration", self.client.get(reverse("card", args=[card.pk])).content.decode())

    def test_missing_artifact_renders_no_control(self):
        card = self.prepared_card()
        url = self.publish(card.active_pair)
        row = ExampleIllustration.objects.get(pair=card.active_pair)
        (Path(settings.ILLUSTRATIONS_DIR)/row.file).unlink()  # delete the stored artifact by its own name
        p = self.present(card, "recognition")
        page = self.client.get(reverse("presentation", args=[p.pk])).content.decode()
        self.assertNotIn("data-illustration", page)
        self.assertNotIn(url, page)
        review.submit(p, "skip")
        self.assertNotIn("data-illustration", self.client.get(reverse("status", args=[p.pk])).json()["back_html"])

    def test_a_completed_review_is_history_without_controls(self):
        card = self.prepared_card()
        url = self.publish(card.active_pair)
        p = self.present(card, "recognition")
        review.submit(p, "skip")  # a skipped attempt is already terminal
        page = self.client.get(reverse("presentation", args=[p.pk])).content.decode()
        self.assertNotIn("data-illustration", page)
        self.assertNotIn(url, page)

    def test_another_learner_sees_no_scene_of_someone_elses_card(self):
        card = self.prepared_card()
        url = self.publish(card.active_pair)
        self.client.force_login(self.other)
        other_deck = Deck.objects.create(owner=self.other, name="Private")
        other_card = authoring.save_card(other_deck, "vocabulary", VOCAB)
        self.assertNotIn(url, self.client.get(reverse("card", args=[other_card.pk])).content.decode())
