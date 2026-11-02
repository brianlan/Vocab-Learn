import copy
import json
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import TestCase
from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from fsrs import Card as MemoryCard, Rating, Scheduler


class ContinuousPracticeMigrationTests(TestCase):
    def test_generation_migration_only_removes_queued_deadlines_and_preserves_failed_work(self):
        alias="generation_migration_test"
        with tempfile.TemporaryDirectory() as folder:
            config=copy.deepcopy(connections["default"].settings_dict)
            config["NAME"]=str(Path(folder)/"legacy.sqlite3")
            connections.databases[alias]=config;connection=connections[alias]
            try:
                executor=MigrationExecutor(connection);old_target=[("learning","0005_remove_examplepair_gloss")]
                executor.migrate(old_target);old=executor.loader.project_state(old_target).apps
                user=old.get_model("auth","User").objects.using(alias).create(username="learner",password="!")
                deck=old.get_model("learning","Deck").objects.using(alias).create(owner_id=user.pk,name="Private")
                card=old.get_model("learning","Card").objects.using(alias).create(deck_id=deck.pk,
                    kind="vocabulary",word="absorb",explanation="Take in liquid.",identity="absorb",ready=False,
                    fsrs={"unchanged":"memory"},review_count=3)
                Job=old.get_model("learning","GenerationJob")
                now=timezone.now()
                for state in ["queued","processing","failed","done"]:
                    Job.objects.using(alias).create(card_id=card.pk,source_version=1,state=state,
                        requested_at=now-timedelta(hours=1),deadline=now-timedelta(minutes=55),
                        provenance={"model":"previous-dispatch"} if state!="queued" else {})
                before=list(Job.objects.using(alias).order_by("pk").values())
                card_before=old.get_model("learning","Card").objects.using(alias).values().get(pk=card.pk)
                executor=MigrationExecutor(connection);target=[("learning","0006_generation_execution_budget")]
                executor.migrate(target);new=executor.loader.project_state(target).apps
                after=list(new.get_model("learning","GenerationJob").objects.using(alias).order_by("pk").values())
                for row in before:
                    row["started_at"]=None
                    if row["state"]=="queued":row["deadline"]=None
                self.assertEqual(after,before)
                self.assertEqual(new.get_model("learning","Card").objects.using(alias).values().get(pk=card.pk),card_before)
                with connection.cursor() as cursor:
                    self.assertEqual(cursor.execute("PRAGMA integrity_check").fetchone()[0],"ok")
                    self.assertEqual(cursor.execute("PRAGMA foreign_key_check").fetchall(),[])
            finally:
                connection.close();del connections[alias];del connections.databases[alias]

    def test_removing_generated_gloss_preserves_pair_and_frozen_history(self):
        alias="lexical_migration_test"
        with tempfile.TemporaryDirectory() as folder:
            config=copy.deepcopy(connections["default"].settings_dict)
            config["NAME"]=str(Path(folder)/"legacy.sqlite3")
            connections.databases[alias]=config
            connection=connections[alias]
            try:
                executor=MigrationExecutor(connection)
                old_target=[("learning","0004_continuous_practice")]
                executor.migrate(old_target)
                old=executor.loader.project_state(old_target).apps
                user=old.get_model("auth","User").objects.using(alias).create(username="learner",password="!")
                deck=old.get_model("learning","Deck").objects.using(alias).create(owner_id=user.pk,name="Private")
                card=old.get_model("learning","Card").objects.using(alias).create(deck_id=deck.pk,
                    kind="vocabulary",word="absorb",explanation="Soak up liquid and hold it.",identity="absorb",
                    target_language="English",native_language="Chinese",fsrs={"unchanged":"memory"},review_count=3)
                pair=old.get_model("learning","ExamplePair").objects.using(alias).create(card_id=card.pk,source_version=1,
                    target_sentence="The sponge absorbs the water.",target_highlight="absorbs",
                    native_sentence="海绵把水吸进去并留住了。",native_highlight="把水吸进去并留住了",gloss="吸进去并留住")
                card.active_pair_id=pair.pk;card.cue_pair_id=pair.pk;card.cue_direction="recognition";card.save(using=alias)
                frozen={"kind":"vocabulary","word":"absorb","reference":"吸进去并留住","gloss":"吸进去并留住"}
                presentation=old.get_model("learning","Presentation").objects.using(alias).create(user_id=user.pk,
                    card_id=card.pk,source_version=1,progress_version=0,snapshot=frozen,budget=18)
                attempt=old.get_model("learning","Attempt").objects.using(alias).create(presentation_id=presentation.pk,
                    action="speak",state="assessed",transcript="吸收",grade="C",reason="Original judgment.")
                old.get_model("learning","ScoredReview").objects.using(alias).create(attempt_id=attempt.pk,
                    card_id=card.pk,user_id=user.pk,grade="C",reviewed_at=timezone.now(),next_due=card.due,
                    snapshot=frozen,fsrs_log={},duration=2,budget=18)
                names=["Card","ExamplePair","Presentation","Attempt","ScoredReview"]
                before={name:list(old.get_model("learning",name).objects.using(alias).order_by("pk").values()) for name in names}
                before["ExamplePair"][0].pop("gloss")
                target=[("learning","0005_remove_examplepair_gloss")]
                executor=MigrationExecutor(connection);executor.migrate(target)
                new=executor.loader.project_state(target).apps
                for name in names:
                    self.assertEqual(list(new.get_model("learning",name).objects.using(alias).order_by("pk").values()),before[name])
            finally:
                connection.close()
                del connections[alias]
                del connections.databases[alias]

    def test_existing_progress_submissions_history_and_scope_survive_run_removal(self):
        alias="continuous_migration_test"
        with tempfile.TemporaryDirectory() as folder:
            config=copy.deepcopy(connections["default"].settings_dict)
            config["NAME"]=str(Path(folder)/"legacy.sqlite3")
            connections.databases[alias]=config
            connection=connections[alias]
            try:
                executor=MigrationExecutor(connection)
                old_target=[("learning","0003_attempt_error_category_attempt_retryable_and_more")]
                executor.migrate(old_target)
                old=executor.loader.project_state(old_target).apps
                User=old.get_model("auth","User")
                Deck=old.get_model("learning","Deck")
                Card=old.get_model("learning","Card")
                Run=old.get_model("learning","StudyRun")
                Presentation=old.get_model("learning","Presentation")
                Attempt=old.get_model("learning","Attempt")
                ScoredReview=old.get_model("learning","ScoredReview")
                Deferral=old.get_model("learning","Deferral")
                user=User.objects.using(alias).create(username="migration-learner",password="!")
                deck=Deck.objects.using(alias).create(owner_id=user.pk,name="Private legacy deck")
                scoped=Run.objects.using(alias).create(user_id=user.pk,deck_id=deck.pk,finished=True)
                unscoped=Run.objects.using(alias).create(user_id=user.pk)
                now=timezone.now()
                snapshot={"kind":"generic","direction":"generic","question_text":"Two plus two?",
                    "question_html":"Two plus two?","reference":"four","explanation":"Addition.","units":1,"language":""}

                def card(label):
                    return Card.objects.using(alias).create(deck_id=deck.pk,kind="generic",identity=label,
                        question=label,answer="four",explanation="Addition.",ready=True,due=now-timedelta(hours=1))

                def presentation(c,scope,version=None):
                    return Presentation.objects.using(alias).create(user_id=user.pk,run_id=scope.pk,card_id=c.pk,
                        source_version=c.source_version,progress_version=c.progress_version if version is None else version,
                        snapshot=snapshot,budget=12,clock_claimed=True)

                reviewed=card("Reviewed card")
                memory,log=Scheduler(enable_fuzzing=False).review_card(MemoryCard(card_id=reviewed.pk),Rating.Easy,
                    review_datetime=now-timedelta(days=1))
                reviewed.fsrs=json.loads(memory.to_json());reviewed.due=memory.due
                reviewed.review_count=1;reviewed.progress_version=1;reviewed.save(using=alias)
                graded=presentation(reviewed,scoped,version=0)
                assessed=Attempt.objects.using(alias).create(presentation_id=graded.pk,action="speak",state="assessed",
                    grade="E",reason="Complete fixture",transcript="four",duration=2,next_due=memory.due,
                    submitted_at=memory.last_review)
                scored=ScoredReview.objects.using(alias).create(attempt_id=assessed.pk,card_id=reviewed.pk,user_id=user.pk,
                    grade="E",reviewed_at=memory.last_review,next_due=memory.due,snapshot=snapshot,
                    fsrs_log=json.loads(log.to_json()),duration=2,budget=12)
                pending_card=card("Cached transcript")
                pending=presentation(pending_card,unscoped)
                failed=Attempt.objects.using(alias).create(presentation_id=pending.pk,action="speak",state="failed",
                    transcript="four",duration=3,audio_name="original.audio",submitted_at=now-timedelta(minutes=2),
                    audio_expires_at=now+timedelta(hours=23),deadline=now-timedelta(minutes=1),
                    asr_provenance={"model":"original-asr"})
                paused=card("Recent skip")
                skip=presentation(paused,scoped)
                skipped_at=now-timedelta(minutes=5)
                Attempt.objects.using(alias).create(presentation_id=skip.pk,action="skip",state="skipped",submitted_at=skipped_at)
                Deferral.objects.using(alias).create(run_id=scoped.pk,card_id=paused.pk)
                stale=presentation(reviewed,scoped,version=0)
                Attempt.objects.using(alias).create(presentation_id=stale.pk,action="speak",state="closed_unassessed")
                Deferral.objects.using(alias).create(run_id=scoped.pk,card_id=reviewed.pk)
                expired_card=card("Old skip")
                expired=presentation(expired_card,scoped)
                Attempt.objects.using(alias).create(presentation_id=expired.pk,action="skip",state="skipped",submitted_at=now-timedelta(hours=1))
                Deferral.objects.using(alias).create(run_id=scoped.pk,card_id=expired_card.pk)
                before={name:list(old.get_model("learning",name).objects.using(alias).order_by("pk").values())
                    for name in ["Card","Presentation","Attempt","ScoredReview"]}
                scopes={row["id"]:Run.objects.using(alias).get(pk=row["run_id"]).deck_id for row in before["Presentation"]}

                executor=MigrationExecutor(connection)
                target=[("learning","0004_continuous_practice")]
                executor.migrate(target)
                new=executor.loader.project_state(target).apps
                for name,rows in before.items():
                    after=list(new.get_model("learning",name).objects.using(alias).order_by("pk").values())
                    if name=="Presentation":
                        self.assertEqual({row["id"]:row["scope_deck_id"] for row in after},scopes)
                    for row in rows:row.pop("run_id",None)
                    for row in after:
                        row.pop("scope_deck_id",None);row.pop("deferred_until",None)
                    self.assertEqual(after,rows,name)
                NewCard=new.get_model("learning","Card")
                self.assertEqual(NewCard.objects.using(alias).get(pk=paused.pk).deferred_until,skipped_at+timedelta(minutes=30))
                self.assertIsNone(NewCard.objects.using(alias).get(pk=reviewed.pk).deferred_until)
                self.assertIsNone(NewCard.objects.using(alias).get(pk=expired_card.pk).deferred_until)
                tables=connection.introspection.table_names()
                self.assertNotIn("learning_studyrun",tables);self.assertNotIn("learning_deferral",tables)
                with connection.cursor() as cursor:
                    cursor.execute("PRAGMA foreign_key_check")
                    self.assertEqual(cursor.fetchall(),[])
            finally:
                connection.close()
                del connections[alias]
                del connections.databases[alias]
