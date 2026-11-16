"""Selection language metadata describes visible content, never the hidden answer."""
import json
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from learning import authoring, review
from learning.models import Card, Deck, ExamplePair


class Regions(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.languages = []
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if "data-selection-region" in attributes:
            self.languages.append(attributes.get("data-selection-language", ""))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SelectionContentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("content-learner")
        self.client.force_login(self.user)

    def vocabulary(self, target, native, direction, *, generated=False):
        deck = Deck.objects.create(owner=self.user, name=f"{target}/{native}/{direction}")
        word = "hiddenreference" if target == "English" else "referenciaoculta"
        card = authoring.save_card(deck, "vocabulary", {"word": word, "explanation": "Private teaching definition.",
            "target_language": target, "native_language": native})
        target_sentence = f"A {word} appeared." if target == "English" else f"Una {word} apareció."
        native_sentence, highlight = (("一段可见的提示。", "提示") if native == "Chinese" else
                                      ("Una pista visible apareció.", "pista"))
        pair = ExamplePair.objects.create(card=card, source_version=card.source_version,
            target_sentence=target_sentence, target_highlight=word, target_highlight_start=target_sentence.index(word),
            native_sentence=native_sentence, native_highlight=highlight,
            native_highlight_start=native_sentence.index(highlight))
        card.active_pair, card.ready = pair, True
        card.direction_block = [direction, "production" if direction == "recognition" else "recognition"]
        card.save()
        if generated:
            card.generation_jobs.update(provenance={"definition_generated": True})
        return card, review.next_question(self.user, deck)

    def test_front_uses_frozen_visible_language_for_every_pair_and_direction(self):
        for target, native in sorted(authoring.LANGUAGE_PAIRS):
            for direction in ["recognition", "production"]:
                with self.subTest(target=target, native=native, direction=direction):
                    card, p = self.vocabulary(target, native, direction)
                    frozen = p.snapshot.copy()
                    response = self.client.get(reverse("presentation", args=[p.pk]))
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.context["front"]["cue_language"],
                                     target if direction == "recognition" else native)
                    self.assertEqual(Regions(response.content.decode()).languages,
                                     [target if direction == "recognition" else native])
                    bootstrap = response.context["selection_add"]
                    self.assertFalse({"word", "reference", "snapshot", "question_html", "explanation"} & bootstrap.keys())
                    if direction == "production":
                        for secret in [card.word, frozen["target_sentence"], frozen["explanation"]]:
                            self.assertNotIn(secret, response.content.decode())
                    p.refresh_from_db()
                    self.assertEqual(p.snapshot, frozen)

    def test_legacy_unknown_language_is_not_inferred_from_live_card_or_expected_response(self):
        card, p = self.vocabulary("English", "Chinese", "production")
        p.snapshot.pop("target_language")
        p.snapshot.pop("native_language")
        p.save(update_fields=["snapshot"])
        response = self.client.get(reverse("presentation", args=[p.pk]))
        self.assertEqual(response.context["front"]["language"], "English")
        self.assertEqual(response.context["front"]["cue_language"], "")
        self.assertEqual(Regions(response.content.decode()).languages, [""])
        self.assertNotIn(card.word, response.content.decode())

    def test_detail_and_dynamic_back_keep_target_and_native_regions_distinct(self):
        for generated in [False, True]:
            with self.subTest(generated=generated):
                card, p = self.vocabulary("English", "Chinese", "production", generated=generated)
                language = "English" if generated else ""
                response = self.client.get(reverse("card", args=[card.pk]))
                self.assertEqual(Regions(response.content.decode()).languages, ["English", "English", "Chinese", language])
                frozen = p.snapshot.copy()
                attempt = review.submit(p, "speak", 2)
                # The displayed back belongs to the frozen presentation, not mutable parent language fields.
                Card.objects.filter(pk=card.pk).update(target_language="Spanish")
                payload = self.client.get(reverse("status", args=[p.pk])).json()
                self.assertEqual(payload["state"], "submitted")
                self.assertEqual(Regions(payload["back_html"]).languages, ["English", language, "English", "Chinese"])
                p.refresh_from_db(); attempt.refresh_from_db()
                self.assertEqual(p.snapshot, frozen)
                self.assertEqual(attempt.duration, 2)

    def test_generic_content_has_no_invented_language_and_bootstrap_is_safe_text(self):
        name = '</script><img src=x onerror="alert(1)">'
        deck = Deck.objects.create(owner=self.user, name=name)
        card = authoring.save_card(deck, "generic", {"question": "A **readable** phrase?", "answer": "private answer",
                                                    "explanation": "An authored explanation."})
        response = self.client.get(reverse("card", args=[card.pk]))
        html = response.content.decode()
        self.assertEqual(Regions(html).languages, ["", "", ""])
        bootstrap = html.split('<script id="selection-add-config" type="application/json">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(bootstrap)["decks"], [{"id": deck.pk, "name": name}])
        self.assertNotIn("<img", bootstrap)
        self.assertIn("\\u003C/script\\u003E", bootstrap)
