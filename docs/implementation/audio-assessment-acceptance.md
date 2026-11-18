# Audio assessment acceptance — PR #13

## Maintainer decisions, 2026-11-18

The maintainer explicitly narrowed this PR's live acceptance to Qwen and requested the Recognition prompt
correction. Doubao model quality is no longer an acceptance blocker; its existing adapter remains available.
The maintainer also deferred latency investigation and optimization outside PR #13. The previously specified
95%-within-five-seconds target is **not achieved or claimed** by this record. The existing 15-second execution
deadline, recovery, single-call execution and protection against late or duplicate learning updates remain required
and unchanged. These decisions supersede the corresponding acceptance gates in issue #12 for this PR only.

No production release or merge was authorized. Responses API support remains the separate issue #14.

## Recognition correction

During real Mac testing, a Chinese Recognition question for `absorbed` accepted the spoken English word
`absorbed` as complete. Its feedback explicitly treated repetition as evidence of understanding. The frozen
task correctly requested Chinese; the request builder retained its direction and language. This was a semantic
judgment error, not a swapped task or server grade mapping error.

`spoken-audio-v2` applies direction before matching words. In Recognition, the target identifies the question:
reading it aloud without giving its meaning in the requested native language is incorrect. In Production,
the target or an appropriate form remains a valid answer. Concise equivalents and ordinary borrowed forms
remain allowed. This clarifies the existing learning rules; it adds no second judgment call or transcript-based
override. New assessments record the new prompt version; historical results are preserved.

### Live Qwen checks

All calls used `qwen3.8-omni-flash`, Chat Completions, disabled thinking (`reasoning_effort=none`), JSON output
and the application's normalized-WAV-to-MP3 transport. There were no automatic retries or fallback calls.

The initial controlled comparison used one fixed, locally synthesized `absorbed` recording and the actual frozen
Recognition task. Original successful audio had already been deleted under the cleanup policy. Across three
interleaved trials per prompt, v1 incorrectly accepted repetition twice; the candidate rejected it in all three.
Four candidate controls also passed: Chinese `吸收`, Production `absorbed`, partial `改时间`, and incorrect `缩小`.
The committed v2 prompt is byte-identical to that candidate; no word-specific exception was added.

The final source was then checked using the six new cases in `scripts/probe_providers.py` and two existing
human-audio controls. Expected outcomes were fixed before calls. All **8/8 judgments** matched expectations:

| Spoken input | Recognition, Chinese meaning requested | Production, English expression requested |
| --- | --- | --- |
| absorbed | incorrect | complete |
| postponed | incorrect | complete |
| misunderstanding | incorrect | complete |

The same audio bytes were used for both directions of each word. These six inputs were synthesized locally;
the two human recordings were `吸收` for absorb (complete) and `改时间` for postpone (partial).
Transcripts matched apart from casing/punctuation and one Recognition transcription of `postponed` as
`postpone`. That inflection difference did not change the expected judgment, but transcript fidelity is not
claimed perfect. The eight calls took 2.62–3.65 seconds each; these are serial provider-path measurements,
not browser latency. Missing optional probe recordings were reported as missing and made no request; the
entire multilingual probe suite was not claimed passed.

Reproduce with private, case-named WAV files and authorized credentials:

```sh
python scripts/probe_providers.py --live --task audio --audio-dir /private/audio --output /private/results.json
```

The new filenames are `RECOGNITION-REPEATED-<WORD>.wav` and `PRODUCTION-REPEATED-<WORD>.wav`, for
`ABSORBED`, `POSTPONED` and `MISUNDERSTANDING`. Copy the same recording to both names to test direction
handling. `LEXICAL-ABSORB.wav` and `PARTIAL-MEANING.wav` cover the human controls above.

## Earlier live application and physical-client checks

These checks ran at `d0fd228` with v1, before the prompt-only correction:

- Seven privately supplied recordings exercised six spoken cases and silence against each provider. Qwen's
  seven outcomes matched the expected outcomes. Doubao hallucinated a response to recorded silence;
  its quality was subsequently removed from this PR's acceptance scope by the maintainer.
- An isolated LAN HTTPS site ran the exact PR source with a fresh database, dedicated accounts and Qwen.
  Application TLS validated against its private CA; the untrusted-certificate negative control failed as expected.
  Six real-provider automated browser submissions committed exactly one score each. Reload preserved results;
  successful recordings were deleted. Browser microphone input was synthetic, not physical-device evidence.
- The maintainer tested from a Mac on the same LAN and reported no usability problems. Logs identify Chrome
  157 and eight recorded submissions. All eight committed once and cleaned their successful audio. Actual
  speech differed from some prescribed negative cases, so those cases were not counted as covered merely
  because the deck titles matched. The Recognition failure above was found in the subsequent database audit.
- The original silence-labelled card was answered aloud with `call off`, as confirmed by the maintainer; its
  correct result was not a silence test. A dedicated subsequent silent recording closed unassessed after two
  executions, with no grade, score or learning-progress update. Its final error was an unusable/empty transcript,
  so this verifies safe refusal to score, not an explicit model `unassessable=true` response. The retained failed
  recording follows the existing 24-hour expiry policy.
- The earlier three-simultaneous-submission browser timings were **8.805, 3.790 and 3.790 seconds**. All results
  were correct, but only two were within five seconds. No latency improvement is included in this correction.

Human recordings, credentials, raw responses and local audit records remain private and outside Git.
No identifiable audio or credentials are included in this acceptance summary.

## Automated regression and limits

After the prompt/probe changes, `python manage.py test learning.tests --noinput` passed **236 tests** using
isolated temporary SQLite/audio directories, dummy credentials and a loopback-only socket guard. Existing
single-call, provider contract, retry, deadline, concurrency, history and scheduling coverage remains intact.
The probe compiled and `git diff --check` passed. The public probe cases and live checks above provide the
semantic regression evidence; mocked model outputs do not demonstrate linguistic correctness.

This is a small English/Chinese sample, not a guarantee across all accents, languages or borrowed/mixed-language
answers. Physical Edge and comprehensive microphone-permission transitions were not independently observed.
The user's Mac usability report and server-side audit are distinguished from the earlier synthetic browser checks.
No new GitHub CI result, production deployment, or overall latency pass is claimed.
