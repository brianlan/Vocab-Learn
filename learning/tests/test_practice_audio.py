"""Issue #21: Practice audio delivery, autoplay preference and reveal-gated controls."""
import tempfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from learning import authoring, review, work
from learning.models import Card, Deck, ExamplePair, LearnerPreferences, SpeechClip
from learning.tests.test_learning import PAIR, VOCAB


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PracticeAudioTests(TestCase):
    def setUp(self):
        self.tts = tempfile.TemporaryDirectory()
        self.addCleanup(self.tts.cleanup)
        override = override_settings(TTS_DIR=Path(self.tts.name))
        override.enable()
        self.addCleanup(override.disable)
        self.user = get_user_model().objects.create_user("audio-learner", password="test-password")
        self.other = get_user_model().objects.create_user("audio-other", password="test-password")
        self.deck = Deck.objects.create(owner=self.user, name="Spoken")
        self.client.force_login(self.user)

    def prepared_card(self):
        card = authoring.save_card(self.deck, "vocabulary", VOCAB)
        job = card.generation_jobs.get(mode="initial")
        job.state = "processing"; job.started_at = timezone.now(); job.deadline = job.started_at+timedelta(seconds=300); job.save()
        work.save_pair(job.pk, job.claim, PAIR, {"model": "test"})
        card.refresh_from_db()
        return card

    def publish(self, pair, sound=b"clip-bytes"):
        """Force both sides done with a stored artifact, bypassing the worker."""
        for side in ("target", "native"):
            clip, _ = SpeechClip.objects.get_or_create(pair=pair, side=side, defaults={"language": ""})
            SpeechClip.objects.filter(pk=clip.pk).update(state="done", file=f"{pair.pk}.{side}.mp3")
            (Path(settings.TTS_DIR)/f"{pair.pk}.{side}.mp3").write_bytes(sound)

    def present(self, card, direction):
        Card.objects.filter(pk=card.pk).update(due=timezone.now()-timedelta(seconds=1), deferred_until=None,
            direction_block=[direction, "production" if direction == "recognition" else "recognition"],
            direction_index=0, cue_pair=card.active_pair_id, cue_direction=direction)
        return review.next_question(self.user, self.deck)

    def clip_url(self, p, side):
        return reverse("clip_audio", args=[p.pk, side])

    def test_front_serves_only_the_visible_side_for_both_directions(self):
        card = self.prepared_card()
        self.publish(card.active_pair)
        recognition = self.present(card, "recognition")
        response = self.client.get(self.clip_url(recognition, "target"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "audio/mpeg")
        self.assertEqual(set(response.headers["Cache-Control"].split(", ")), {"private", "no-store"})
        self.assertEqual(b"".join(response.streaming_content), b"clip-bytes")
        hidden = self.client.get(self.clip_url(recognition, "native"))
        self.assertEqual(hidden.status_code, 404)
        page = self.client.get(reverse("presentation", args=[recognition.pk])).content.decode()
        self.assertIn('data-play="target"', page)
        self.assertNotIn('data-play="native"', page)
        self.assertNotIn(self.clip_url(recognition, "native"), page)
        production = self.present(card, "production")
        self.assertEqual(self.client.get(self.clip_url(production, "native")).status_code, 200)
        self.assertEqual(self.client.get(self.clip_url(production, "target")).status_code, 404)
        page = self.client.get(reverse("presentation", args=[production.pk])).content.decode()
        self.assertIn('data-play="native"', page)
        self.assertNotIn('data-play="target"', page)

    def test_another_learner_is_denied_every_clip_route(self):
        card = self.prepared_card()
        self.publish(card.active_pair)
        p = self.present(card, "recognition")
        self.client.force_login(self.other)
        for side in ("target", "native"):
            self.assertEqual(self.client.get(self.clip_url(p, side)).status_code, 404)

    def test_a_committed_reveal_opens_both_sides_and_keeps_them_through_polling(self):
        card = self.prepared_card()
        self.publish(card.active_pair)
        p = self.present(card, "recognition")
        review.submit(p, "skip")
        for side in ("target", "native"):
            self.assertEqual(self.client.get(self.clip_url(p, side)).status_code, 200)
        back_html = self.client.get(reverse("status", args=[p.pk])).json()["back_html"]
        self.assertIn('data-play="target"', back_html)
        self.assertIn('data-play="native"', back_html)
        # A fresh load of a completed review is history: no playback controls anywhere.
        page = self.client.get(reverse("presentation", args=[p.pk])).content.decode()
        self.assertNotIn("data-play", page)
        self.assertNotIn(self.clip_url(p, "target"), page)
        self.assertNotIn(self.clip_url(p, "native"), page)

    def test_audio_resolves_the_frozen_pair_across_a_rotation(self):
        card = self.prepared_card()
        frozen = card.active_pair
        self.publish(frozen, sound=b"frozen-clip")
        p = self.present(card, "recognition")
        rotated = ExamplePair.objects.create(card=card, source_version=card.source_version,
            target_sentence=PAIR["target_sentence"]+" Again.", target_highlight=PAIR["target_highlight"],
            target_highlight_start=PAIR["target_highlight_start"], native_sentence=PAIR["native_sentence"],
            native_highlight=PAIR["native_highlight"], native_highlight_start=PAIR["native_highlight_start"])
        card.active_pair = rotated
        card.save(update_fields=["active_pair"])
        self.publish(rotated, sound=b"rotated-clip")
        response = self.client.get(self.clip_url(p, "target"))
        self.assertEqual(b"".join(response.streaming_content), b"frozen-clip")

    def test_missing_and_partial_clips_leave_practice_usable(self):
        card = self.prepared_card()
        p = self.present(card, "recognition")  # both sides still queued
        page = self.client.get(reverse("presentation", args=[p.pk])).content.decode()
        self.assertNotIn("data-play", page)
        for side in ("target", "native"):
            self.assertEqual(self.client.get(self.clip_url(p, side)).status_code, 404)
        SpeechClip.objects.filter(pair=card.active_pair, side="native").update(state="done", file="late.mp3")
        (Path(settings.TTS_DIR)/"late.mp3").write_bytes(b"late")
        page = self.client.get(reverse("presentation", args=[p.pk])).content.decode()
        self.assertNotIn('data-play="native"', page)  # the front never shows the hidden side
        review.submit(p, "skip")
        back_html = self.client.get(reverse("status", args=[p.pk])).json()["back_html"]
        self.assertIn('data-play="native"', back_html)
        self.assertNotIn('data-play="target"', back_html)

    def test_settings_default_and_saved_autoplay_preference(self):
        settings_page = self.client.get(reverse("settings")).content.decode()
        self.assertIn('id="id_autoplay_enabled" checked', settings_page)
        self.assertFalse(LearnerPreferences.objects.exists())
        response = self.client.post(reverse("settings"), {"language_pair": "English:Chinese"})  # unchecked box saves False
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LearnerPreferences.objects.get(user=self.user).autoplay_enabled, False)
        self.assertNotIn('id="id_autoplay_enabled" checked', self.client.get(reverse("settings")).content.decode())
        card = self.prepared_card()
        self.publish(card.active_pair)
        p = self.present(card, "recognition")
        self.assertIn('data-autoplay="0"', self.client.get(reverse("presentation", args=[p.pk])).content.decode())
        LearnerPreferences.objects.get(user=self.user).delete()  # an account without a saved row defaults to on
        self.client.post(reverse("settings"), {"language_pair": "English:Chinese"})  # unchecked box saves False
        self.assertEqual(LearnerPreferences.objects.get(user=self.user).autoplay_enabled, False)
        LearnerPreferences.objects.all().delete()
        self.assertIn('data-autoplay="1"', self.client.get(reverse("presentation", args=[p.pk])).content.decode())
        self.client.post(reverse("settings"), {"autoplay_enabled": "on", "language_pair": "English:Chinese"})
        self.assertEqual(LearnerPreferences.objects.get(user=self.user).autoplay_enabled, True)
