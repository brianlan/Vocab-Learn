from unittest import TestCase
from unittest.mock import patch
from learning import providers
from scripts.probe_generation import probe


class GenerationProbeTests(TestCase):
    def test_retains_invalid_raw_outputs_and_does_not_send_review_rubric(self):
        cases = [{"id": word, "check": "Reviewer-only criterion", "source": {
            "word": word, "explanation": "A solid object.", "target_language": "English", "native_language": "Chinese"}}
            for word in ["stone", "brick"]]

        def chat(profile, rules, source):
            self.assertNotIn("check", source)
            return {"target_sentence": "A <focus>stone</focus> fell.", "native_sentence": "一块<focus>石头</focus>掉了。"} if source["word"] == "stone" else {
                "target_sentence": "A brick fell.", "native_sentence": "一块砖掉了。"}

        profile = providers.Profile("GENERATOR", "https://provider.test/chat", "model", "secret-placeholder", 2)
        with patch.object(providers, "profile", return_value=profile), patch.object(providers, "chat", side_effect=chat) as call:
            report = probe(cases)
        rows = {row["case_id"]: row for row in report["results"]}
        self.assertEqual(call.call_count, 2)
        self.assertEqual(rows["brick"]["status"], "failed")
        self.assertEqual(rows["brick"]["raw"]["target_sentence"], "A brick fell.")
        self.assertEqual(rows["stone"]["status"], "needs_semantic_review")
        self.assertEqual(report["status"], "needs_semantic_review")
        self.assertNotIn(profile.key, str(report))

    def test_repeats_preserve_every_result_without_automatic_retry(self):
        cases = [{"id": "stone", "source": {"word": "stone", "explanation": "A solid object.",
                  "target_language": "English", "native_language": "Chinese"}}]
        profile = providers.Profile("GENERATOR", "https://provider.test/chat", "model", "secret-placeholder", 2)
        with patch.object(providers, "profile", return_value=profile), patch.object(providers, "chat", side_effect=[
            providers.StageError("GENERATOR", "Timed out", "timeout"),
            {"target_sentence": "A <focus>stone</focus> fell.", "native_sentence": "一块<focus>石头</focus>掉了。"}]):
            report = probe(cases, repeats=2)
        self.assertEqual(len(report["results"]), 2)
        self.assertEqual({row["repeat"] for row in report["results"]}, {1, 2})
        self.assertEqual(sum(row["status"] == "failed" for row in report["results"]), 1)
