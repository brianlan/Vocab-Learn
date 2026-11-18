import contextlib
import io
import tempfile
import wave
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from scripts import probe_providers


class AudioProbeTests(TestCase):
    def test_incomplete_word_false_positive_is_reported_without_a_transcript(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "PRODUCTION-INCOMPLETE-NEUROTICISM.wav"
            with wave.open(str(audio), "wb") as fixture:
                fixture.setnchannels(1)
                fixture.setsampwidth(2)
                fixture.setframerate(16000)
                fixture.writeframes(b"\x00\x01" * 16000)
            # Reconstruct the false-positive provider output; this tests reporting, not hearing.
            answer = ([{"id": 1, "outcome": "complete", "reason": "Matches."}],
                      {"model": "test-model", "api_mode": "chat_completions"})
            with patch.object(probe_providers, "audio_assessment", return_value=answer) as assess, \
                    contextlib.redirect_stdout(io.StringIO()):
                report = probe_providers.run(Path(folder), task="audio")
            assess.assert_called_once()
            task, supplied_audio = assess.call_args.args
            self.assertEqual((task["direction"], task["word"], supplied_audio),
                             ("production", "neuroticism", audio))
        result = next(row for row in report["results"] if row["name"] == "PRODUCTION-INCOMPLETE-NEUROTICISM")
        self.assertEqual((report["status"], result["status"]), ("needs-review", "needs-review"))
        self.assertEqual(result["expected"], ["incorrect"])
        self.assertEqual(result["profile"]["expected_utterance"], "neurocism")
        self.assertNotIn("transcript", result["profile"])
