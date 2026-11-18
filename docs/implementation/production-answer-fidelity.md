# Production answer fidelity — prompt experiment, 2026-11-18

## Final branch decision

The maintainer subsequently selected **Qwen Chat Completions with the current prompt's judgment-only variant**.
The branch now implements that choice as `spoken-audio-v4`, rather than the stricter candidate described below.
See the [transcript-output experiment and adoption decision](transcript-output-experiment.md).
The reusable probe cases remain, adapted to judgment-only output. Production has not been deployed by this work.

## Historical candidate status

**Draft, not acceptance-ready. The reported incomplete-word false positive is not solved.**

Fresh human recordings subsequently confirmed the failure: in 40 balanced calls, both the current and draft
prompts accepted the correct recording every time and incorrectly accepted the shortened recording every time,
in both Qwen API modes. See the human-recording validation below. The candidate remains unsuitable as a fix.

A subsequent [80-call transcript-output experiment](transcript-output-experiment.md) found that omitting the
transcript reduces some false acceptances but introduces rejection of the correct recording and invalid output.
It does not establish a reliable replacement; the results below concern the original transcript-output contract.

The experimental candidate clarified the Production prompt, recorded the intended boundary between a malformed word and an
ordinary pronunciation variant, and adds seven reusable live-probe fixtures. It does not add a second model
call, a pronunciation score, transcript matching, a word blacklist, new configuration, or a schema migration.
No production application, saved grade, schedule, or history was changed. The worktree is based on merged
Responses support at `9682372a84bd4d62d8076a9bd00a5af1d1918c78`.

Three prompt approaches were explored with live Qwen calls. The final candidate preserves the tested ordinary
learning cases and fixes one explicitly illustrated malformed word, but still accepts shortened forms of
`neuroticism`. It must not be described as a reliable correction or deployed on the strength of this experiment.

## Problems and intended behavior

Read-only production inspection found a Production answer transcribed as `Privy.` but marked incorrect because
it was not a complete sentence. The same frozen task was subsequently answered `privy` and graded complete.
The intended task is retrieval of the highlighted expression; a standalone target word is sufficient.

Another Production answer, reported by the learner as `neurocism`, was transcribed as `Neuroticism.` and graded
complete. Its original audio had already been deleted by normal assessed-recording cleanup. The stored result
therefore does not independently establish what sounds were present. At inspection, production used Qwen
Chat Completions, `qwen3.8-omni-flash`, prompt `spoken-audio-v2`, and application commit `499471d`.

The requested distinction is lexical recall, not a new pronunciation score: retain intelligible accents,
established pronunciation variants and ordinary reductions, while rejecting a clearly incomplete/malformed
target when accepting it requires supplying missing word parts. Preserve the actually heard form in the
transcript. Suitable different synonyms remain partial, and Recognition still requires native-language meaning.

## Historical candidate changes

- `learning/providers.py`: candidate `spoken-audio-v3` puts audio fidelity before answer matching; explicitly
  accepts standalone Production targets; prohibits repairing missing word parts; preserves accent tolerance,
  ordinary reductions and the existing Recognition, synonym and wrong-answer rules.
- `scripts/probe_providers.py`: adds standalone-word cases for `privy`, `neuroticism` and `responsibility`, plus
  incomplete-word and accented-word cases for the latter two. Each result retains expected utterance and observed
  transcript separately. Missing recordings do not trigger paid calls.
- `learning/tests/test_audio_probe.py`: reconstructs a provider's normalized false positive and proves the probe
  reports `needs-review`, retaining both expected `neurocism` and observed `neuroticism`. This validates reporting,
  not the model's hearing. No mocked passing grade is presented as acoustic evidence.
- The specification and operations guide state the intended rule and the candidate's unresolved limitation.

## Live method — initial synthetic experiment

**128 paid Qwen calls total**, sequential and without automatic retries:

1. Three 16-call pilot comparisons against `spoken-audio-v2`: 48 calls.
2. An eight-call listening-only diagnostic without the target word, example or grading context.
3. A 72-call comparison using the final checked-in candidate.

Each pilot used the same four fixtures across baseline/candidate and Responses/Chat Completions. The first
candidate explicitly contrasted `neurocism` with `neuroticism`; it sometimes rejected a shortened form but also
rejected an intact target. The second used general word-identity instructions without that contrast. The third
put audio-first transcription at the beginning and illustrated the rule with `responsity`/`responsibility`.
Before final validation, its standalone-target rule was explicitly scoped to Production and its malformed-word
rule clarified to preserve suitable-synonym partial outcomes. Exact prompt versions/hashes are in the private plans.

The final comparison used eight main fixtures in all four arms (32 calls), two additional repetitions of each
shortened-neuroticism fixture in all four arms (16), and twelve candidate-only control fixtures in both modes
(24). Mode/prompt order was randomized within each fixture block with seed `20261118`; controls were shuffled.
Provider, model, thinking-disabled settings, token budget (8192), time budget (15 seconds), and omitted sampling
overrides matched the application. Both modes used the actual one-call assessment adapter and validation.
Request captures asserted identical task and encoded-audio hashes across prompt/mode arms.

The original two production task snapshots were reused privately. Audio was newly synthesized using the
already installed eSpeak NG library, mono 16-kHz PCM, then transported through the existing MP3 encoder.
The setup used the documented [eSpeak NG API](https://raw.githubusercontent.com/espeak-ng/espeak-ng/master/src/include/espeak-ng/speak_lib.h).
Intact US/British voice forms, a text-synthesized `neurocism`, and a controlled phoneme variant deleting the
middle `t#I2` from the US target were saved before calls, with hashes and synthesis specifications. This makes
the synthetic distinction reproducible; it is not a recreation of the learner's voice or an independent listening judgment.

Other controls included intact `responsibility`, malformed `responsity`, intact `opportunity`, malformed
`opportity`, the ordinary reduced pronunciation of `comfortable`, standalone/full-sentence `privy`, a suitable
synonym (`informed`), a wrong word (`private`), previously labelled human Chinese responses, and the earlier
synthetic English-repeat Recognition fixture. Human clips included quiet speech. Regional synthetic voices
are not evidence of broad non-native accent robustness.

## Final 72-call results

| Condition | Baseline Responses | Candidate Responses | Baseline Chat | Candidate Chat |
|---|---|---|---|---|
| Standalone `privy` | complete | complete | complete | complete |
| Intact `neuroticism`, US and British variants | 2/2 complete | 2/2 complete | 2/2 complete | 2/2 complete |
| Two shortened `neuroticism` variants, three trials each | 6/6 falsely complete | 5/6 falsely complete; 1 invalid output | 6/6 falsely complete | 5/6 falsely complete; 1 invalid output |
| Intact `responsibility` | complete | complete | complete | complete |
| `responsity` for `responsibility` | falsely complete | incorrect, transcript preserved | falsely complete | incorrect, transcript preserved |
| British-voice reduced `comfortable` | complete | complete | complete | complete |
| `opportity` for `opportunity` | not tested | falsely complete | not tested | incorrect, approximate transcript |
| Other candidate-only controls | not tested | all expected outcomes | not tested | all expected outcomes |

Baseline: 10 expected judgments and 14 false-positive judgments in 24 calls. Candidate: 35 expected judgments,
11 false-positive judgments and two invalid-output failures in 48 calls. These totals have different case mixes
and must not be compared as overall accuracy percentages.

For the specific shortened-neuroticism problem, **all 12 candidate outputs normalized the transcript to
`neuroticism`**, including the two invalid outputs. Those two used outcome `correct` instead of an allowed enum;
the adapter rejected them. They are not successful detection of a malformed word. None of the 12 delivered the
required incorrect judgment with a faithful approximation of the shortened word.

All 32 candidate controls excluding malformed Production words had the expected outcomes: correct standalone
and full-sentence targets, regional variants/reductions, partial synonyms, wrong words, correct/partial/incorrect
Chinese meanings, an explicit unknown answer, and English repetition during Recognition. This is limited
fixture evidence, not proof that the earlier intermittent `privy` error is eliminated. That full-sentence-demand
error was not reproduced by the synthetic baseline in this run.

`responsity` appears explicitly in the candidate prompt, so its improvement alone does not establish
generalization. The held-out `opportity` still failed in Responses. Its Chat judgment was incorrect as expected,
but the reason described it as unintelligible; that wording is inconsistent with the unassessable-audio rule
and is another reason not to claim a clean semantic acceptance pass.

## Diagnostic interpretation

Without the expected target or task, Responses transcribed the shortened fixtures as `Nora'sism` and `Noraism`;
Chat still returned `Neuroticism` for both. Chat also transcribed the intact US fixture as `Naradicism`, while
the intact British fixture was recognized correctly. These eight exploratory calls support both contextual
normalization and imperfect acoustic recognition as possible contributors; they do not isolate a provider
mechanism or prove that no future prompt can help.

The first candidate's false rejection of an intact word is particularly important: simply making the prompt
more severe can introduce false negatives without reliably removing false positives. Do not deploy the
candidate as a solved pronunciation boundary, or add reference/transcript equality as a workaround—the model
has already rewritten the transcript before local validation sees it.

## Human-recording validation

The maintainer supplied two fresh files, `neuroticism.m4a` and `neurocism.m4a`, labelled as the correct and
shortened forms respectively. These labels and expected outcomes were fixed before model calls; no independent
listening judgment was made in this run. Originals were preserved, and private copies were converted with the
actual `learning.work.normalize` function to mono 16-kHz, 16-bit WAV, without gain changes or trimming.
Decoded durations were 3.5294375 and 2.809625 seconds. Both used the exact frozen production task from the
reported attempt, with the model, disabled-thinking settings and budgets of the initial experiment.

**40 additional live Qwen calls** tested each recording five times under each prompt/API-mode combination.
Five blocks each contained all eight combinations in randomized order (seed `20261118`). Calls were sequential,
with one request per assessment and no automatic retries. Input hashes confirmed that each recording's task and
encoded audio were identical across arms. The candidate prompt matched the checked-in draft byte for byte.

| API mode | Prompt | Correct recording accepted | Shortened recording incorrectly accepted |
|---|---|---:|---:|
| Responses | Current `spoken-audio-v2` | 5/5 | 5/5 |
| Responses | Draft `spoken-audio-v3` | 5/5 | 5/5 |
| Chat Completions | Current `spoken-audio-v2` | 5/5 | 5/5 |
| Chat Completions | Draft `spoken-audio-v3` | 5/5 | 5/5 |

Every call returned HTTP 200, model `qwen3.8-omni-flash`, valid assessment units with outcome `complete`, and
transcript `neuroticism` apart from capitalization/punctuation. There were no technical failures to exclude.
The candidate failed to distinguish the two human recordings, just as it failed on the shortened synthetic
fixtures. This establishes no prompt improvement for this pair; it does not prove that every possible future
prompt or audio model would fail. The provider's internal recognition/normalization mechanism was not observed.

The original and normalized hashes remain in the private manifest. Baseline prompt SHA-256 is
`6bfb1141e697cba95be24ed2f293bc2fb17d39cf8b7cb2a40aa3325cf288feb4`; draft SHA-256 is
`def532553f6e50ad094fd920b11724f7978fdad73d681ef727c97457e2c15f4e`.
Reported usage was 50,440 input tokens and 1,780 output tokens. These 40 calls bring the investigation total to
168, including the earlier 128 calls. No application or prompt changes were made during this follow-up.

Private evidence is under `/home/rlan/.local/share/vocab-learn/audio-eval/20261118-human-neuroticism/`:
the untouched-original manifest, normalized copies, frozen task, exact prompts and pre-call plan, 40 responses
with request IDs, input hashes and `summary.json`. The analysis checks balanced coverage, unchanged original
files, input equivalence and equality with the worktree's prompt. No production database was opened by this run.

## Verification and next step

- The full existing suite passed **241 tests** in 66.105 seconds during the second prompt iteration.
- After the final wording, the existing provider suite passed **29 tests**; the final targeted run including
  the new probe regression passed **30 tests** in 1.421 seconds. Syntax and whitespace checks passed.
  These tests do not establish model accuracy.
- A no-network fixture self-check verified all seven new probe labels and missing-audio behavior.
- No new dependency, production deployment, regrading, source edit, model switch or paid automatic retry occurred.

Fresh human recordings are now available and still collapse to the same model output. Keep this work as a
draft. A next step would be to compare audio-model capability on this frozen pair while preserving the one-call
design, rather than deploy an unverified wording change as a solution. Broader accent and lexical coverage would
still be needed before accepting any replacement; this experiment covers one speaker and one target word.

Private reproducibility artifacts are under
`/home/rlan/.local/share/vocab-learn/audio-eval/20261118-production-fidelity/` with owner-only directory access:
synthetic WAVs/specifications, frozen private task snapshots, pre-call plans, all raw responses, request IDs,
prompt/input hashes, diagnostic scripts and `summary.json`. Credentials and private production snapshots are
not committed. The final prompt hash is checked against the validation plan by the private analysis script.
