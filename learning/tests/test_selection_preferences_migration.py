import copy
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from unittest import TestCase
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


class LearnerPreferencesMigrationTests(TestCase):
    def test_additive_preferences_upgrade_preserves_all_rows_without_backfilling(self):
        alias = "selection_preferences_migration_test"
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as folder:
            config = copy.deepcopy(connections["default"].settings_dict)
            config["NAME"] = str(Path(folder) / "legacy.sqlite3")
            connections.databases[alias] = config
            connection = connections[alias]
            try:
                old_target = [("learning", "0010_structured_vocabulary_details")]
                executor = MigrationExecutor(connection)
                executor.migrate(old_target)
                old = executor.loader.project_state(old_target).apps
                user = old.get_model("auth", "User").objects.using(alias).create(username="learner", password="!")
                other = old.get_model("auth", "User").objects.using(alias).create(username="inactive", password="!", is_active=False)
                deck = old.get_model("learning", "Deck").objects.using(alias).create(owner_id=user.pk, name="Private", description="Retain this.")
                old.get_model("learning", "Deck").objects.using(alias).create(owner_id=other.pk, name="Archived", archived=True)
                now = timezone.now()
                card = old.get_model("learning", "Card").objects.using(alias).create(deck_id=deck.pk, kind="vocabulary",
                    word="absorb", explanation="Original **meaning**.", definition="Original meaning.",
                    pronunciations=[{"ipa": "/x/", "variety": "US", "label": "verb"}], synonyms=["soak up"],
                    target_language="English", native_language="Chinese", identity="original-identity",
                    source_version=3, progress_version=7, collection="Forgot", streak=2, review_count=5,
                    fsrs={"unchanged": {"memory": 4}}, due=now + timedelta(days=1), deferred_until=now + timedelta(minutes=30),
                    direction_block=["recognition", "production"], direction_index=1, rotation_token=uuid.uuid4())
                pair = old.get_model("learning", "ExamplePair").objects.using(alias).create(card_id=card.pk, source_version=3,
                    target_sentence="We absorb water.", target_highlight="absorb", target_highlight_start=3,
                    native_sentence="我们吸收水。", native_highlight="吸收", native_highlight_start=2,
                    provenance={"original": True})
                revised = old.get_model("learning", "ExamplePair").objects.using(alias).create(card_id=card.pk, source_version=3,
                    target_sentence="They absorb water.", target_highlight="absorb", target_highlight_start=5,
                    native_sentence="他们吸收水。", native_highlight="吸收", native_highlight_start=2,
                    provenance={"corrects_pair_id": pair.pk})
                card.active_pair_id, card.cue_pair_id, card.cue_direction = revised.pk, pair.pk, "recognition"
                card.save(using=alias)
                frozen = {"kind": "vocabulary", "direction": "recognition", "pair_id": pair.pk,
                          "reference": "frozen reference", "explanation": "frozen explanation", "units": [1]}
                presentation = old.get_model("learning", "Presentation").objects.using(alias).create(user_id=user.pk,
                    scope_deck_id=deck.pk, card_id=card.pk, source_version=3, progress_version=6,
                    snapshot=frozen, budget=17, clock_claimed=True)
                attempt = old.get_model("learning", "Attempt").objects.using(alias).create(presentation_id=presentation.pk,
                    action="speak", state="assessed", duration=2, transcript="fixed transcript", grade="E",
                    reason="Original judgment.", asr_provenance={"model": "saved-asr"}, judge_provenance={"model": "saved-judge"},
                    outcomes=[{"id": 1, "outcome": "complete"}], next_due=card.due)
                old.get_model("learning", "ScoredReview").objects.using(alias).create(attempt_id=attempt.pk,
                    card_id=card.pk, user_id=user.pk, grade="E", reviewed_at=now, next_due=card.due,
                    snapshot=frozen, fsrs_log={"original": [1, 2]}, duration=2, budget=17)
                for state in ["queued", "processing", "failed", "done"]:
                    old.get_model("learning", "GenerationJob").objects.using(alias).create(card_id=card.pk,
                        source_version=3, state=state, mode="rotation", token=card.rotation_token,
                        started_at=now if state != "queued" else None, deadline=now + timedelta(minutes=5) if state != "queued" else None,
                        result_id=revised.pk if state == "done" else None, provenance={"original": state},
                        error="Retain failure" if state == "failed" else "")
                old.get_model("learning", "AuthoringKey").objects.using(alias).create(owner_id=user.pk,
                    name="Existing key", digest="a" * 64, revoked_at=now)
                names = [("auth", "User")] + [("learning", name) for name in
                    ["Deck", "Card", "ExamplePair", "Presentation", "Attempt", "ScoredReview", "GenerationJob", "AuthoringKey"]]
                before = {(app, name): list(old.get_model(app, name).objects.using(alias).order_by("pk").values())
                          for app, name in names}
                old_tables = set(connection.introspection.table_names())
                target = [("learning", "0011_learner_preferences")]
                for state in [target, old_target, target]:
                    executor = MigrationExecutor(connection)
                    executor.migrate(state)
                    apps = executor.loader.project_state(state).apps
                    for app, name in names:
                        self.assertEqual(list(apps.get_model(app, name).objects.using(alias).order_by("pk").values()), before[app, name])
                    tables = set(connection.introspection.table_names())
                    self.assertEqual(tables, old_tables | ({"learning_learnerpreferences"} if state == target else set()))
                    if state == target:
                        preferences = apps.get_model("learning", "LearnerPreferences")
                        self.assertFalse(preferences.objects.using(alias).exists())
                        defaults = preferences(user_id=user.pk)
                        self.assertEqual((defaults.selection_add_enabled, defaults.target_language, defaults.native_language),
                                         (True, "English", "Chinese"))
                        self.assertIsNone(defaults.pk)
                with connection.cursor() as cursor:
                    self.assertEqual(cursor.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertEqual(cursor.execute("PRAGMA foreign_key_check").fetchall(), [])
            finally:
                connection.close()
                del connections[alias]
                del connections.databases[alias]
