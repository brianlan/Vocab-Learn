# Direction-specific prompt comparison

**Experimental; not deployed.** Started 2026-11-21T16:10:15.573412+00:00.

## Prompt and method

The supplied `/home/rlan/Downloads/vocab_audio_system_prompts_v1.json` bundle identifies itself as `spoken-audio-v5-candidate-1`. Its three complete system prompts are selected by frozen task kind/direction; they are never concatenated. The source file is preserved unchanged. Bundle SHA-256: `c60221a2ccb9b477f8f5d34257bb12061223f0dbfe4575bcae2ec8bb83f2faf8`.

The baseline is the [previous combined revised prompt](revised-prompt-five-cases.md), remeasured in this experiment. It is not production v4 or the narrower worktree candidate. The only changed request content is the selected system message.

- Qwen `qwen3.8-omni-flash`, Chat Completions, thinking disabled, sampling defaults (`temperature`, `top_p` and model `seed` omitted).
- Actual application adapter and validator, MP3 audio transport, JSON judgment without transcript, 8192-token cap, 15-second execution budget.
- Five supplied correct-answer recordings, five repetitions per prompt: 50 calls. Eight controls, two repetitions per prompt: 32 calls. **82 planned and completed calls**, sequential and shuffled within repetition blocks using order seed `2026112201`.
- Controls: synthetic thinker/mobile/handyman, human neuroticism/neurocism, human correct/wrong Chinese meanings for absorb, and prior human-recorded silence. The silence fixture uses its original generic call-off task; it only checks the Generic prompt on silence.
- Every trial made one request; no retries/fallback. Assertions verify balanced conditions, unchanged WAV hashes, intended prompt selection and identical encoded audio/task/full body except the system message.
- Format failures are separate from wrong grades. An exact `{"unassessable":true}` is a pass only for the silent fixture; false abstentions on spoken answers are wrong outcomes.
- No application source, production configuration, learning data or original audio was changed.

## Five primary cases

Counts below are valid `complete` judgments; all five intended answers should be complete.

| Answer | Previous combined prompt | Supplied prompt |
|---|---:|---:|
| tinker | 2/5 | 5/5 |
| mortal | 3/5 | 0/5 |
| dissect | 2/5 | 3/5 |
| 缩小 | 3/5 | 3/5 |
| 收缩 | 0/5 | 3/5 |
| **Total** | **10/25** | **14/25** |

## Controls

| Case | Expected | Previous combined prompt | Supplied prompt |
|---|---|---|---|
| thinker-en-us | incorrect | 2 complete | 1 complete, 1 incorrect |
| mobile-en-us | incorrect | 1 complete, 1 incorrect | 1 partial, 1 complete |
| human-neuroticism | complete | 1 complete, 1 incorrect | 2 incorrect |
| human-neurocism | incorrect | 2 partial | 2 incorrect |
| recognition-correct | complete | 2 complete | 1 incorrect, 1 complete |
| recognition-wrong | incorrect | 2 incorrect | 2 incorrect |
| handyman-en-us | partial | 2 incorrect | 2 incorrect |
| human-silence | unassessable | 2 incorrect | 2 unassessable |

## Findings

The supplied prompt improved the primary-case total from 10/25 to 14/25 in this paired run, but did not improve
every case. `tinker` increased from 2/5 to 5/5 and `收缩` from 0/5 to 3/5; `mortal` fell from 3/5 to 0/5.
Both prompts produced three invalid outputs on primary cases. Baseline results differ from prior runs; all
comparisons here use the baseline remeasured alongside the candidate, not historical counts.

Every candidate `收缩` reply described its meaning as correct, but two used the unsupported outcome `correct`
instead of `complete`. Thus this case shows a semantic improvement with a remaining output-contract failure;
it is not five successful application assessments. The other invalid candidate reply, on `缩小`, also used
`correct`, while its reason contradicted that judgment by claiming a direct translation did not convey meaning.
One valid candidate reply rejected Chinese `缩小` as merely repeating the English target word.

The five candidate `mortal` failures included claims that “mor-tal” adds an extra syllable or is malformed,
a claimed wrong final sound, a non-word claim and confusion with `model`. The candidate also continued to
give pronunciation diagnoses despite its instruction to omit fine-grained diagnoses. Removing IPA or detailed
phonetic feedback from the requested output did not eliminate this class of false rejection.

Controls matched the expected outcome in 6/16 baseline trials and 8/16 candidate trials. Improvements included
silence (0/2 to 2/2 unassessable), shortened `neurocism` (0/2 to 2/2 incorrect) and thinker (0/2 to 1/2 incorrect).
However, candidate still falsely accepted one thinker and one mobile sample, rejected both correct neuroticism
trials, rejected one correct `吸收` answer, and never awarded the expected partial outcome to handyman. The
neurocism rejections called the utterance “newer system”; an expected grade does not establish faithful feedback.

Across all 82 calls, expected outcomes were **16/41 versus 22/41**, with three invalid outputs per prompt. All
calls returned HTTP 200; no timeouts occurred. These selected-case gains and regressions do not justify replacing
the production prompt. They also do not isolate which wording change helped: direction splitting, rewritten
rubrics and different output instructions were changed together as one supplied candidate.

## Every primary trial

Reasons are verbatim model claims, not independently verified phonetic findings. Run numbers are repetition order within each case and prompt; saved trial numbers identify raw evidence.

### tinker

| Prompt | Run | Trial | Validated outcome | Raw outcome if invalid | Model reason / error |
|---|---:|---:|---|---|---|
| baseline | 1 | 020 | incorrect | — | The learner pronounced the word as 'tinker' (with a clear /k/ sound) instead of the target word 'tinker'. |
| baseline | 2 | 032 | incorrect | — | The learner produced 'Tinker' with a silent final consonant, resulting in the word 'tin-ker'. The target word requires the /k/ sound at the end. |
| baseline | 3 | 057 | complete | — | The learner correctly produced the target word 'tinker'. |
| baseline | 4 | 068 | invalid_output | complete | The learner produced the target word 'tinker'.; validation: The model did not return a complete valid JSON answer. Retry the fixed input. |
| baseline | 5 | 078 | complete | — | The learner correctly produced the target word 'tinker'. |
| candidate | 1 | 024 | complete | — | The learner correctly recalls the target expression 'tinker'. |
| candidate | 2 | 027 | complete | — | The learner correctly recalled the target expression 'tinker'. |
| candidate | 3 | 058 | complete | — | The learner provided the exact target word 'tinker'. |
| candidate | 4 | 064 | complete | — | The learner supplied the target expression 'tinker'. |
| candidate | 5 | 080 | complete | — | The learner correctly recalled the target expression 'tinker'. |

### mortal

| Prompt | Run | Trial | Validated outcome | Raw outcome if invalid | Model reason / error |
|---|---:|---:|---|---|---|
| baseline | 1 | 009 | complete | — | The speaker produced the target word 'mortal' with clear pronunciation. |
| baseline | 2 | 036 | incorrect | — | The speaker said 'mortal', which is an adjective meaning subject to death. The question asks for the verb phrase corresponding to '会死' (will die). A correct answer would be a verb like 'die' or 'perish'. Using the adjective 'mortal' does not convey the action of dying required by the context. |
| baseline | 3 | 054 | incorrect | — | 'mortal' is not the target word 'mortar'. |
| baseline | 4 | 070 | complete | — | The learner produced the target word 'mortal'. |
| baseline | 5 | 073 | complete | — | The speaker correctly produced the target word 'mortal'. |
| candidate | 1 | 014 | incorrect | — | The speaker produced 'mortal' with an extra syllable ('mor-tal'), which is a malformed attempt at the target word. |
| candidate | 2 | 029 | incorrect | — | The learner pronounced 'mortal' with a final /ɔ/ sound instead of the correct /əl/, making it an incomplete or malformed attempt at the target word. |
| candidate | 3 | 060 | incorrect | — | The learner produced a non-word instead of the target expression. |
| candidate | 4 | 067 | incorrect | — | The learner said "mortal" but pronounced it as "mor-tal", which is a clearly malformed attempt at the target word. |
| candidate | 5 | 074 | incorrect | — | The learner produced a phonetically similar but incorrect word ('model') instead of the target 'mortal'. |

### dissect

| Prompt | Run | Trial | Validated outcome | Raw outcome if invalid | Model reason / error |
|---|---:|---:|---|---|---|
| baseline | 1 | 010 | complete | — | The speaker produced the target word 'dissect'. |
| baseline | 2 | 048 | complete | — | The learner correctly produced the target word 'dissect'. |
| baseline | 3 | 062 | incorrect | — | The learner pronounced 'desect', which is a mispronunciation of the target word 'dissect'. |
| baseline | 4 | 066 | incorrect | — | The learner pronounced the word with a missing initial 'd' sound, resulting in an unintelligible or incorrect form. |
| baseline | 5 | 075 | partial | — | Pronunciation of the final consonant cluster is unclear, making it sound like 'dissect' with a weak ending. |
| candidate | 1 | 015 | incorrect | — | The spoken word 'desect' is a malformed attempt at the target 'dissect', failing to produce the correct phonological form. |
| candidate | 2 | 050 | complete | — | The learner provided the target word 'dissect'. |
| candidate | 3 | 061 | complete | — | The learner correctly recalled the target word 'dissect'. |
| candidate | 4 | 072 | incorrect | — | The learner produced 'desect', which is a clearly malformed attempt at the target word 'dissect'. |
| candidate | 5 | 082 | complete | — | The learner correctly recalled and produced the target word 'dissect'. |

### 缩小

| Prompt | Run | Trial | Validated outcome | Raw outcome if invalid | Model reason / error |
|---|---:|---:|---|---|---|
| baseline | 1 | 004 | complete | — | The learner correctly conveyed the meaning of 'shrank' as becoming smaller ('缩小'). |
| baseline | 2 | 034 | complete | — | The learner provided the correct Chinese meaning '缩小' for the English word 'shrink'. |
| baseline | 3 | 055 | complete | — | The learner correctly conveyed the meaning of 'shrank' in Chinese. |
| baseline | 4 | 069 | invalid_output | correct | The learner provided the meaning '缩小', which correctly translates to 'becomes smaller in size or amount'.; validation: The judgment contained invalid units. |
| baseline | 5 | 076 | invalid_output | correct | The learner correctly identified the meaning of 'shrank' as '缩小'.; validation: The judgment contained invalid units. |
| candidate | 1 | 002 | complete | — | The learner correctly translated the target expression "shrank" into its Chinese equivalent "缩小", which accurately conveys the intended meaning of becoming smaller. |
| candidate | 2 | 045 | incorrect | — | The learner repeated the target English word without providing its meaning in Chinese. |
| candidate | 3 | 053 | complete | — | The learner correctly identified the meaning of 'shrink' in Chinese ('缩小'). |
| candidate | 4 | 071 | invalid_output | correct | The response '缩小' is a direct translation of the target word, which does not convey its meaning in Chinese.; validation: The judgment contained invalid units. |
| candidate | 5 | 079 | complete | — | The response '缩小' correctly conveys the meaning of becoming smaller in size. |

### 收缩

| Prompt | Run | Trial | Validated outcome | Raw outcome if invalid | Model reason / error |
|---|---:|---:|---|---|---|
| baseline | 1 | 001 | incorrect | — | '收缩' means 'to contract' or 'to shrink', but it is a verb action rather than the state of becoming smaller in size or amount as described by 'shrinks'. A more accurate translation would be '变小' (become smaller). |
| baseline | 2 | 040 | incorrect | — | The learner said '收缩' (to contract/shrink). While related, the specific definition provided requires the meaning of becoming smaller in size or amount ('变小'), which is distinct from the mechanical action of contracting. |
| baseline | 3 | 059 | incorrect | — | '收缩' (contract/shrink) describes the process or action of becoming smaller, whereas '缩小' (become smaller/reduce in size) directly matches the definition's result state ('becomes smaller'). |
| baseline | 4 | 065 | incorrect | — | '收缩' means contract/shrink but doesn't convey becoming smaller in size/amount as required by 'shrink' |
| baseline | 5 | 077 | partial | — | '收缩' means 'contract/shrink', which is close but less precise than the expected sense of becoming smaller in size or amount. |
| candidate | 1 | 003 | complete | — | The learner provided the Chinese equivalent '收缩', which accurately conveys the meaning of becoming smaller. |
| candidate | 2 | 033 | invalid_output | correct | The learner provided '收缩' (contract/shrink), which is a direct and accurate translation of the target word 'shrank'.; validation: The judgment contained invalid units. |
| candidate | 3 | 056 | complete | — | The learner provided the correct Chinese translation '收缩' for the target word. |
| candidate | 4 | 063 | invalid_output | correct | The learner provided the Chinese translation '收缩' (to contract/shrink), which accurately conveys the intended contextual meaning of the English word 'shrank'.; validation: The judgment contained invalid units. |
| candidate | 5 | 081 | complete | — | The response correctly provides the Chinese equivalent "收缩" for the meaning of "shrink". |

## Evidence and limits

Private source bundle copy, baseline text, pre-call plan, exact prompt strings/hashes, request fingerprints, raw responses and summary: `/home/rlan/.local/share/vocab-learn/audio-eval/20261122-direction-prompts-v1/`.

Only five primary human recordings and a small control set were tested. Repetition measures consistency on these samples, not population accuracy. No independent phonetic adjudication or dedicated accent suite was performed. Generic recall, multiple blanks and generic partial/wrong answers were not evaluated; only generic silence was tested. The synthetic controls are identified explicitly and are not equivalent to testing additional human speakers.

Follow-up: [StepAudio 3 Chat comparison](stepaudio3-prompt-experiment.md) evaluates the supplied prompts and identical audio/task inputs with another provider.
