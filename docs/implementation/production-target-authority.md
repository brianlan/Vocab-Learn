# Production target authority — 2026-11-21

**Status: experimental draft, not a verified fix.** Two initial comparisons completed 112 Qwen calls, followed
by 24 calls investigating Recognition and inflection, and 82 calls using new human recordings and controls
(218 calls total). Both initial candidates
improved some correct-target judgments but increased false acceptance of nearby wrong words. The narrower
candidate was retained as `spoken-audio-v5` during these experiments, not selected for production.
The later [StepAudio integration](stepaudio3-integration.md) supersedes that worktree candidate.

## Incidents and scope

Read-only production inspection found two assessed answers under Qwen Chat Completions,
`qwen3.8-omni-flash`, prompt `spoken-audio-v4`:

- `tinker`: the feedback claimed the learner said `Tinker` instead of `tinker`, and returned `incorrect`.
  A written case difference cannot support a spoken-pronunciation error.
- `mortal`: the feedback claimed the required word was `die`, although the frozen task's authored word was
  `mortal`. The native question was “即使最健康的人也会死。” with “会死” highlighted. The target was passed to the
  provider; the application did not substitute `die` or compare case-sensitive transcripts.

The application mapped each `incorrect` outcome to B as specified. Both original recordings had been deleted
after assessment; feedback cannot independently establish the acoustic content. The current-prompt SHA-256 on
the running worker matched the previously selected judgment-only variant. No production data, schedules,
configuration or code were changed during this investigation.

## Candidate rules

The experiment preserves Qwen Chat Completions, disabled thinking, judgment-only JSON, the existing unit validator,
and one model call. It tests system-prompt changes only; neither task payload nor audio changes between variants.

Production must use the authored `word` as its target rather than inventing a translation of the native cue.
Written capitalization and punctuation are not audible distinctions. Standalone targets remain sufficient;
different suitable synonyms remain partial, wrong words incorrect, and Recognition still requires native-language
meaning. No pronunciation score, feedback-string matching, special-case word whitelist or extra judge is added.
The prompts contain neither `tinker` nor `mortal` as worked examples.

The first candidate replaces the opening Production paragraph with explicit target authority, standalone-word
acceptance, case/punctuation tolerance and a reason-consistency check. A narrower candidate keeps that original
paragraph and adds target-authority/case rules with explicit preservation of synonym and wrong-word outcomes.
Both exact prompt texts and hashes are in their respective private pre-call plans.

## Controlled method

The baseline is production `spoken-audio-v4` from `c0ac4cc`. Calls use the real `audio_assessment` adapter,
normalized mono 16-kHz WAVs and its Qwen MP3 transport, a 15-second budget, 8192 output-token budget and provider
sampling defaults. Calls are sequential, with no retries or fallback. Variant/case order is shuffled within
repetition blocks using seed `20261121`. Request captures verify the intended system prompt and identical task
and encoded-audio hashes for each case across variants. Raw response envelopes, parsed judgments, HTTP status,
request IDs, errors and timing are retained privately. Invalid outputs count as failures, not correct rejection.

The reported tasks reuse the exact frozen production snapshots. New synthetic recordings use the installed
eSpeak NG library with US and British voices for correct `tinker` and `mortal`; US-voice controls say `thinker`,
`mobile`, `die` or `handyman`. The expected outcomes are complete for the targets, partial for the suitable
substitute `handyman`, and incorrect for the other controls. These labels are fixed before calls. Synthetic
voices are reproducible acoustic fixtures, not evidence of the learner's voice or broad accent tolerance.

Additional controls reuse the maintainer's labelled `neuroticism` / `neurocism` recordings, and Chinese
Recognition responses `吸收` / `缩小` for `absorb`. The shortened word is expected to be incorrect; partial is
reported separately as a wrong grade. The two new incident recordings have been requested for direct human
validation; a synthetic pass does not recreate the deleted production audio.

## First candidate: 64 calls

Each of eight synthetic cases ran three times per prompt; four human controls ran twice per prompt.

| Case | Current prompt | First candidate |
|---|---|---|
| Correct `tinker`, both voices | 4 complete, 1 incorrect, 1 invalid | 4 complete, 2 invalid |
| Correct `mortal`, both voices | 2 complete, 1 partial, 2 incorrect, 1 invalid | 6 complete |
| `thinker` for `tinker` | 3 falsely complete | 2 falsely complete, 1 invalid |
| `mobile` for `mortal` | 3 incorrect | 3 falsely complete |
| `die` for `mortal` | 3 incorrect | 3 incorrect |
| `handyman` for `tinker` | 3 incorrect (expected partial) | 3 incorrect (expected partial) |
| Human correct `neuroticism` | 1 incorrect, 1 partial | 1 complete, 1 partial |
| Human shortened `neurocism` | 1 partial, 1 invalid | 2 partial |
| Human Recognition controls | 4 expected outcomes | 4 expected outcomes |

Baseline: 16/32 expected grades, 13 wrong grades and 3 invalid outputs. Candidate: 18/32 expected grades,
11 wrong grades and 3 invalid outputs. These are fixture-specific results, not application accuracy estimates.

The baseline reproduced target substitution on correct synthetic `mortal`, requiring `will die` / `can die`
instead. The candidate removed that observed failure, but accepting every `mobile` recording is a regression.
The first candidate is therefore not an acceptable general fix. The exact capitalization-only `tinker` feedback
was not reproduced; other incorrect and invalid judgments of the correct `tinker` fixtures occurred.

## Narrower candidate: 48 calls

The same twelve cases ran twice per prompt, again against the unchanged production baseline. The narrower
candidate was frozen before this second phase. The two phases have different repetition counts; compare
within each phase rather than treating their pooled percentages as a single randomized comparison.

| Case | Current prompt | Narrower candidate |
|---|---|---|
| Correct `tinker`, both voices | 3 complete, 1 incorrect | 3 complete, 1 invalid |
| Correct `mortal`, both voices | 2 complete, 1 incorrect, 1 invalid | 4 complete |
| `thinker` for `tinker` | 1 partial, 1 incorrect | 2 falsely complete |
| `mobile` for `mortal` | 2 incorrect | 2 falsely complete |
| `die` for `mortal` | 1 incorrect, 1 invalid | 2 incorrect |
| `handyman` for `tinker` | 2 incorrect (expected partial) | 2 incorrect (expected partial) |
| Human correct `neuroticism` | 1 incorrect, 1 complete | 2 complete |
| Human shortened `neurocism` | 1 incorrect, 1 falsely complete | 1 partial, 1 falsely complete |
| Human Recognition controls | 4 expected outcomes | 4 expected outcomes |

Baseline: 15/24 expected grades, 7 wrong grades and 2 invalid outputs. Candidate: 15/24 expected grades,
8 wrong grades and 1 invalid output. This candidate does not establish an overall improvement either.
All 112 calls returned HTTP 200 and the requested model ID; invalid responses were locally rejected, never
retried or credited as correct grades. Failures included outcome `correct`, an empty reason and the unexpected
top-level field `unit_results`. Some invalid replies also had contradictory feedback; relaxing the validator
would not make those trustworthy.

Expected outcome counts do not certify feedback correctness. For example, in the second phase the baseline
rejected a `mobile` control while claiming it heard `mortal` but required `die`. It also rejected shortened
`neurocism` while wrongly claiming the task required the adjective `neurotic`. Those match the expected
incorrect label for the wrong reason. Conversely, candidate acceptance of nearby wrong words explicitly
claimed to hear the authored target. We cannot infer the provider's internal acoustic process from these reasons.

## Conclusion and remaining validation

Explicit target authority mitigated the reproduced `mortal` target-substitution failure on these correct
synthetic recordings. It did not improve correct `tinker` acceptance, and both candidates regressed on wrong-word
controls. The original capitalization-only feedback was not reproduced, so a specific fix for that failure
has not been demonstrated. Do not deploy either candidate as a reliable repair based on these results.

The narrower candidate remains an uncommitted experimental change. Fresh human `tinker` and `mortal` recordings
are needed for the next paired comparison, using the same frozen questions and settings. The original
recordings cannot be recovered from this run. No production changes or paid automatic retries occurred.
Responses, Doubao, silence, broader vocabulary and browser microphone behavior were not retested.

The final narrower candidate passed the provider/audio-probe suite: **30 tests in 1.419 seconds**. Its prompt
matched the experimental plan byte for byte, and whitespace checks passed. No runtime contract, database schema,
grading mapping or audio-retention change was introduced. The full application suite was not rerun for this
prompt/fixture/documentation-only draft.

## Additional incidents: Recognition meaning and Production inflection

Further read-only inspection found three B judgments on the same `shrink` Recognition card: one rejected
`收缩` as insufficient and two called `缩小` the opposite of shrinking. The authored definition explicitly
means becoming smaller, and the frozen example describes a balloon shrinking as air leaks out. All three used
the same production v4 profile. These reasons conflict with the task and the equivalent-lexical-meaning rule.
Their original recordings are unavailable; no grades or schedules were rewritten.

The v4 prompt contains the negative example `'absorb' answered as '缩小' is incorrect.` A separate **12-call**
ablation tested whether removing just that sentence helps. The same existing human `缩小` clip was assessed
against the exact frozen `shrink` question and the existing `absorb` control, three times per prompt/task.

| Task for the same `缩小` recording | Current v4 | V4 with only that example removed |
|---|---|---|
| `shrink`, expected complete | 2 complete, 1 invalid | 3 invalid |
| `absorb`, expected incorrect | 2 incorrect, 1 invalid | 3 incorrect |

Every `shrink` reply's feedback described the meaning as correct, including invalid replies. Invalid outputs
used `correct` instead of `complete`, or returned a bare array rather than the required object. No opposite-meaning
claim was reproduced in these twelve calls. Therefore this run does not establish example interference as the
cause, and removing the example is not a demonstrated fix. All calls returned HTTP 200; validator failures are
not successful assessments. Private evidence: `20261121-shrink-cue/` alongside the main experiment directory.

A further Production record for `dissect` was graded C because the model required `dissected` to match “解剖了”.
The authored `word` was `dissect`, and the actual selected native highlight was only “解剖”; “了” lay outside it.
The hidden English example used `dissected`, but that hidden sentence and highlight were not included in the
Production assessment payload. The model imposed a sentence-tense requirement on a lexical-recall task.
The current rule accepts the authored word itself as well as an appropriate inflected form.

A separate **12-call** comparison used that frozen Production task and US-voice synthetic `dissect`, `dissected`
and `insect`, twice per prompt. The candidate added only an explicit base-word/inflected-form alternative rule
to production v4; it was not combined with either target-authority candidate or deployed.

| Utterance | Current v4 | V4 with explicit base-form acceptance |
|---|---|---|
| `dissect` | 1 complete, 1 incorrect | 1 complete, 1 incorrect |
| `dissected` | 2 complete | 1 complete, 1 partial |
| `insect` | 1 incorrect, 1 partial | 1 incorrect, 1 falsely complete |

All twelve outputs were structurally valid. Expected grades were 4/6 for baseline and 3/6 for candidate;
this small comparison does not establish a fix. Some feedback invented phonetic errors or sentence requirements.
The synthetic baseline did not reproduce the original base-form-to-past-tense rejection exactly. Private evidence
is in `20261121-dissect-form/` beside the other experiment directories. These are preliminary fixture checks,
not a replay of the unavailable human recording. The branch's reusable probe now includes `shrink` meaning,
standalone `dissect`, inflected `dissected` and wrong-word `insect` cases for future human validation.

## New human recordings: combined candidate

The maintainer supplied fresh `tinker`, `mortal` and `dissect` recordings. The first `shrink.m4a` was explicitly
withdrawn as problematic before any model call used it; it is excluded from all results. Replacement recordings
were subsequently supplied and explicitly labelled `缩小` and `收缩`. Original files were preserved, private
copies normalized with the application's actual `normalize` function, and file hashes recorded. No independent
phonetic adjudication was performed; expected outcomes use the supplied labels and task rules.

This comparison tests a **new combined candidate**, kept privately rather than replacing the worktree prompt:
the narrower target-authority candidate plus explicit acceptance of the authored base word alongside appropriate
inflections, and a Recognition rule that example judgments apply only to their stated targets. It contains no
worked example naming `tinker`, `mortal`, `dissect` or `shrink`. Its SHA-256 is
`06edbab737912331bc2281fd8dd3b81540058eb929429f56553d31b1ca2b6ca0`. Baseline remains production v4, including
its original negative `absorb` example. The earlier example-removal variant is not used here.

The three new English recordings ran five times per prompt against the corresponding exact frozen production
tasks. Six earlier controls ran twice per prompt: synthetic `thinker`/`mobile`, human `neuroticism`/`neurocism`,
and human correct/wrong Chinese meanings for `absorb`. This first phase completed **54 calls**, sequentially,
in shuffled repetition blocks (seed `2026112103`). Model, API mode, audio transport, settings, validation and
identical-input checks are the same as above; no retries or production mutations occurred.

| New human recording | Current v4 | Combined candidate |
|---|---|---|
| `tinker` | 3 complete, 2 invalid | 4 complete, 1 invalid |
| `mortal` | 1 complete, 2 partial, 2 incorrect | 2 complete, 3 incorrect |
| `dissect` | 3 complete, 2 partial | 3 complete, 1 partial, 1 incorrect |

The current prompt reproduced the target-substitution problem on this new human `mortal` recording, requiring
`will die` or another expression for “会死”. The combined candidate also produced contradictory feedback: one
reply printed the same IPA on both sides of its alleged pronunciation difference, and another claimed the target
was `mordal`. Thus the candidate does not reliably enforce target authority, even where the aggregate number of
complete judgments increases. The original capitalization-only `tinker` and tense-only `dissect` reasons were
not reproduced; partial/incorrect judgments of `dissect` instead claimed pronunciation defects.

Across these three intended-correct recordings, usable complete results increased from 7/15 to 9/15. The tinker
difference is in format compliance: all structurally valid tinker judgments were complete under both prompts.
Invalid replies included `correct` instead of `complete`, or an empty reason, and were not scored as passes.

Controls remain mixed: `thinker` false acceptance changed from 2/2 to 1/2, but `mobile` went from 2/2 incorrect
to one false complete and one invalid reply. Both prompts failed both correct-neuroticism trials. For shortened
neurocism, baseline returned one partial and one incorrect; candidate returned one false complete and one incorrect.
All four Chinese-meaning control judgments per prompt matched their expected outcomes. Whole-phase expected
grades were 14/27 for baseline and 15/27 for candidate, with two invalid replies each. These small, deliberately
selected case counts do not establish a population accuracy rate or a stable fix.

Human evidence is under `/home/rlan/.local/share/vocab-learn/audio-eval/20261121-human-target-authority/`:
original/normalized manifests, excluded-first-recording record, exact candidate text, pre-call plans, raw trial
responses and summaries. Main-phase results use private copies of earlier controls, unaffected by the later
replacement of the user's `缩小.m4a` file.

### Replacement Chinese recordings

The two new recordings each ran five times per prompt against the frozen `shrink` Recognition task, plus twice
per prompt against `absorb` as wrong-meaning controls. This completed another **28 calls** with the same combined
candidate, unchanged inputs across variants and no retries.

| New human recording and task | Current v4 | Combined candidate |
|---|---|---|
| `缩小` for `shrink` | 1 complete, 1 incorrect, 3 invalid | 4 complete, 1 incorrect |
| `收缩` for `shrink` | 2 complete, 1 partial, 2 incorrect | 1 complete, 1 partial, 2 incorrect, 1 invalid |
| `缩小` for `absorb` | 2 incorrect | 2 incorrect |
| `收缩` for `absorb` | 2 incorrect | 1 incorrect, 1 timeout |

The candidate reproduced the original semantic contradiction verbatim: **"'缩小' is the opposite of 'shrink'."**
Other candidate failures rejected `收缩` as insufficient for becoming smaller, despite the balloon losing air
context. Baseline also imposed a past-tense requirement on Chinese `缩小`, demanding `缩小了` for `shrank`.
These replies explicitly identify the intended Chinese words, so their stated reasons reveal grading-rule or
semantic errors rather than demonstrating a failure to hear those words. They do not establish the model's
internal cause or prove that another prompt could not improve it.

Shrink-phase expected outcomes were 7/14 for baseline and 8/14 for candidate. Across all **82 calls**, expected
outcomes were 21/41 versus 23/41: baseline had 15 wrong judgments and 5 invalid outputs; candidate had 14 wrong
judgments, 3 invalid outputs and 1 timeout. The five new intended-correct recordings yielded usable complete
judgments in 10/25 versus 14/25 trials. Improvements on some samples coexist with regressions on `收缩` and
wrong-word controls; this combined prompt is not a verified production fix. Repeated calls on these few recordings
measure consistency on selected cases, not general accuracy. No further user recording is needed to demonstrate
the reported failure.

## Evidence storage

Private artifacts live under `/home/rlan/.local/share/vocab-learn/audio-eval/20261121-target-authority/` with
owner-only directory access: frozen task snapshots, synthetic WAVs and phoneme manifests, cases/expected outcomes,
the runner, analysis script, pre-call plans, raw trial records and summaries. Audio and credentials are not committed.
The analysis verifies unchanged WAV hashes, balanced planned conditions, one request per trial and input equivalence.

The initial prompt/fixture change passed the existing provider and audio-probe tests (30 tests in 1.471 seconds).
These deterministic checks verify application contracts, not model hearing or grading accuracy.

Prompt SHA-256 values:

- Baseline: `faaff348960cf19de2c9292e394e3380a842954c4ecdf5ee2ccf27892ce04716`.
- First candidate: `2d95fe2b7638962d13317d28ffc260d61a01ef4b5a406b6373dcfa3f33fe549e`.
- Narrower candidate: `7d38e2b843b1c64c730fc10523ccbb52c741035959229c1d3ffc80031fe08f8c`.
