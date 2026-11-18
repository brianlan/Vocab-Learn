# Transcript output experiment — 2026-11-18

## Adoption decision after reviewing the experiment

The maintainer accepted the observed limitations and explicitly requested committing **Chat Completions with
the current prompt and no transcript output** as the default. The branch implements that choice as
`spoken-audio-v4`, using the exact current/judgment-only prompt below, SHA-256
`faaff348960cf19de2c9292e394e3380a842954c4ecdf5ee2ccf27892ce04716`. The stricter draft is not selected.

Runtime configuration, Compose and `.env.example` default to Qwen Chat Completions. Responses remains an
explicit option, and both modes use the judgment-only contract. The adapter and worker return/save units and
feedback without generating a transcript. Invalid fields, outcomes, identities and refusals remain unassessed.
Existing transcript data and its readonly display are preserved without a schema migration; new results show
feedback without an empty transcript panel. Learning grades, schedules, audio cleanup and one-request behavior
are unchanged. The public status response retains its historical `transcript` field, empty for new assessments.

Existing explicit mode/endpoint settings take precedence over defaults. To switch an installed deployment,
set `AUDIO_ASSESS_API_MODE=chat_completions` and clear `AUDIO_ASSESS_ENDPOINT` or use its Chat Completions URL.
No production configuration or deployment was changed here.

Implementation verification passed **242 tests in 66.741 seconds** against an isolated SQLite test database.
This includes both providers/API modes, invalid output, worker retries and cleanup, replay without another
assessment, and escaped historical-transcript display. Django system checks and the no-migration check passed.
Compose configuration resolved Chat Completions for both web and worker with an unset mode and with the example
environment. The application prompt was checked byte for byte against the pre-call experimental plan.
No additional paid model calls or physical-browser tests were run for the implementation.

The following experimental findings and initial recommendation are retained as evidence, not a claim that
this choice eliminates malformed-word errors or validates all providers and API modes.

## Experimental conclusion before the adoption decision

Removing the transcript changed Qwen's judgments substantially, but did not provide a reliable improvement.
It reduced false acceptance of the shortened recording while introducing rejection of the correct recording.
The current prompt with Chat Completions was the most promising condition; even there, only one of five
shortened-word trials received the required `incorrect` outcome. Do not change the production contract on
the strength of this experiment.

## Method

The experiment made **80 live calls** to `qwen3.8-omni-flash`: two human recordings, two API modes, two prompts,
two output formats, and five repetitions of each combination. All calls returned HTTP 200 with that model ID.
The recordings and frozen Production task are the same as in the
[previous prompt experiment](production-answer-fidelity.md#human-recording-validation).
The maintainer labelled `neuroticism.m4a` correct and `neurocism.m4a` shortened; expected outcomes were fixed
as `complete` and `incorrect` before calls. No independent phonetic adjudication was performed.

The prompts were current `spoken-audio-v2` from commit `9682372` and the worktree's draft `spoken-audio-v3`.
For each, the comparison was:

```json
{"transcript":"...","units":[{"id":1,"outcome":"complete|partial|incorrect","reason":"short English reason"}]}
```

versus:

```json
{"units":[{"id":1,"outcome":"complete|partial|incorrect","reason":"short English reason"}]}
```

Judgment-only retained the feedback reason. Transcript-specific instructions were rewritten to judge the
heard form without emitting a transcript, and the prompt explicitly prohibited a transcript field. The
direction, standalone-word, synonym, malformed-word, accent and silence grading rules were retained.
This tests a coherent judgment-only prompt, not deletion of a JSON key alone: the current-prompt variant also
explicitly says not to silently repair malformed words. The effect of these wording changes cannot be isolated
from the effect of omitting the transcript. Exact prompts and their diff are reproducible from the private plan.

Both formats used the existing request builders and response-envelope parsing. The private judgment-only
validator required exactly `units` at the top level and reused `validate_units`; the normal format used
`validate_assessment`, including its mandatory transcript check. Missing transcripts were therefore not
misclassified as experiment failures. No application parser, response contract or persistence code was changed.

Calls were sequential, without retries, shuffled within five complete blocks using seed `2026111802`.
Thinking was disabled, the output budget was 8192, the encoding-plus-request budget was 15 seconds, and sampling
overrides were omitted. Both modes used the same normalized WAVs and existing MP3 encoder. Request captures
asserted identical task and encoded-audio hashes across all conditions for each recording, plus the intended
model, prompt, JSON mode and disabled-thinking settings. Responses requests used `store: false`.

## Grading results

Every transcript-output condition accepted both recordings in all five trials: correct acceptance was **5/5**,
but detection of the shortened word was **0/5**. All 40 transcripts normalized to `neuroticism`, ignoring case
and punctuation. The following are judgment-only results; counts include all scheduled calls, not just valid replies.

| Prompt | API mode | Correct recording: complete / partial / incorrect / invalid | Shortened recording: complete / partial / incorrect / invalid |
|---|---|---|---|
| Current | Responses | 2 / 1 / 2 / 0 | 3 / 1 / 1 / 0 |
| Current | Chat Completions | 5 / 0 / 0 / 0 | 1 / 3 / 1 / 0 |
| Draft | Responses | 0 / 0 / 5 / 0 | 0 / 0 / 5 / 0 |
| Draft | Chat Completions | 1 / 1 / 2 / 1 | 0 / 1 / 3 / 1 |

Across these equally weighted conditions, transcript output produced 20/40 expected judgments. Judgment-only
produced 18/40: eight correct acceptances and ten correct rejections, with 20 wrong grades and two invalid replies.
This pooled total describes only this balanced experiment, not application-wide accuracy.

Current-prompt Chat avoided falsely granting `complete` to the shortened recording in four of five trials,
while retaining all five correct acceptances. Three of those four detections were `partial`, which is still
the wrong learning outcome for the labelled malformed target. Draft Responses simply rejected both recordings
every time; its perfect detection of the shortened recording is not evidence of useful discrimination.

Feedback is also unstable. Shortened-word explanations variously claimed to hear `neurosis`, `newer system`,
`nervousness` or a nonword. On the correct recording, some replies alleged an extra syllable, incorrect stress,
or a missing initial sound. These are model claims, not verified acoustic findings. One shortened-word reply
described the word as unintelligible while still issuing an assessed outcome, conflicting with the prompt's
unassessable rule. Correct outcome labels alone do not establish faithful feedback.

Both invalid replies came from draft Chat judgment-only: trial 29 returned a bare JSON array instead of the
requested object; trial 39 used outcome `correct`, outside the allowed enum. Neither counts as successful
detection. No valid judgment-only reply included a transcript field. No transport failures or retries occurred.

## Latency and usage

Each row aggregates ten calls, five per recording. Time includes local encoding and the provider request;
it excludes application queues, upload and UI processing. Failures remain included.

| Prompt / mode | Median seconds, transcript → judgment-only | Mean output tokens, transcript → judgment-only |
|---|---:|---:|
| Current / Responses | 3.275 → 3.676 | 45.0 → 39.8 |
| Current / Chat Completions | 3.261 → 3.169 | 46.2 → 40.3 |
| Draft / Responses | 3.010 → 3.261 | 46.5 → 48.4 |
| Draft / Chat Completions | 3.318 → 3.327 | 42.9 → 45.0 |

There was no consistent latency benefit. Current-prompt output tokens fell modestly; draft output tokens
increased because feedback became longer. Input-token counts also changed with prompt wording. Total reported
usage was 100,560 input and 3,541 output tokens. No monetary savings or production latency improvement is claimed.

## Interpretation and limits

The results are consistent with transcript generation influencing the judgment, potentially by normalizing
the spoken word before the model produces its grade. They do not expose the model's internal computation or
prove that mechanism. Omitting the transcript also appears to encourage stricter pronunciation criticism in
some conditions, despite the draft's explicit tolerance for accents and ordinary reductions.

Keep judgment-only as an experimental candidate, particularly with the current prompt and Chat Completions,
but do not present it as a fix. Before adoption, test a pre-labelled set spanning more speakers, accents, intact
and shortened words, Recognition meanings, synonyms, standalone targets and silence. Five repeated calls on
each of two recordings measure response variability, not generalization to five different speakers or words.
Silence and `privy` were not retested here. At experiment time the app still required a transcript; the subsequent
implementation is described above. Production remains unchanged.

## Reproducibility and verification

Private artifacts are under `/home/rlan/.local/share/vocab-learn/audio-eval/20261118-transcript-ablation/` in an
owner-only directory: `experiment.py`, `analyze.py`, pre-call `plan.json`, 80 trial records with raw responses,
request IDs and input hashes, and `summary.json`. Original recordings and normalized WAV hashes were verified
unchanged. Credentials and private production task snapshots are not included in this report or committed.

| Prompt | Transcript SHA-256 | Judgment-only SHA-256 |
|---|---|---|
| Current | `6bfb1141e697cba95be24ed2f293bc2fb17d39cf8b7cb2a40aa3325cf288feb4` | `faaff348960cf19de2c9292e394e3380a842954c4ecdf5ee2ccf27892ce04716` |
| Draft | `def532553f6e50ad094fd920b11724f7978fdad73d681ef727c97457e2c15f4e` | `e506346651e137d02a349ec2f604a4b9b2ed85418d0d2217bf6a86112a5ce156` |

An offline self-check exercised both request builders, both output validators, intentional omission of the
transcript, and rejection of invalid fields/enums. Final analysis verified complete balanced coverage, one
request per trial, input equivalence and unchanged original audio. Application tests were not rerun for this
documentation-only experiment follow-up; the prior implementation's test results remain in the linked report.
