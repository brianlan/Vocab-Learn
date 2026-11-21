# Temperature comparison on five human recordings

Experiment started: 2026-11-21T15:28:11.830469+00:00. **Experimental results; no production changes.**

## Question and controlled setup

Does changing only `temperature` improve the five known cases under the [combined revised prompt](revised-prompt-five-cases.md)? The application currently omits `temperature`. The [provider documentation](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions) lists 0.7 as the nonthinking Qwen3.8-Omni-Flash default and a supported range of [0, 2). The omitted arm is remeasured in this run; it is not substituted with historical results. The service does not echo the effective temperature, so documented defaults and sent values do not prove internal sampling behavior.

- Model/API: `qwen3.8-omni-flash`, Qwen Chat Completions; thinking disabled (`reasoning_effort="none"`).
- Prompt: exact combined human-experiment candidate; SHA-256 `06edbab737912331bc2281fd8dd3b81540058eb929429f56553d31b1ca2b6ca0`.
- Arms: omitted, 0, 0.2, 0.7 and 1.2. Five calls per case per arm: **125 calls**.
- Same frozen task and same normalized human recording per case; actual application adapter, MP3 transport, JSON-only judgment without transcript, 8192-token cap and 15-second assessment budget.
- Only temperature varies. `top_p` and `seed` are omitted in every arm. Sequential calls are shuffled within five repetition blocks using local order seed `2026112104`; this is not a model seed.
- One request per trial, no retries/fallback. Invalid outputs and timeouts count as failures, separately from wrong grades. All five answers are expected to be `complete` under the supplied labels and learning rules.
- Assertions verified balanced completed conditions, unchanged WAV hashes, identical encoded audio/task/full request body excluding temperature, and the intended outgoing sampling parameters. No original files or production data were changed.

## Valid complete judgments

| Answer | Omitted | 0 | 0.2 | 0.7 | 1.2 |
|---|---:|---:|---:|---:|---:|
| tinker | 5/5 | 5/5 | 5/5 | 5/5 | 4/5 |
| mortal | 3/5 | 3/5 | 3/5 | 3/5 | 2/5 |
| dissect | 4/5 | 4/5 | 3/5 | 5/5 | 3/5 |
| 缩小 | 3/5 | 3/5 | 3/5 | 1/5 | 1/5 |
| 收缩 | 2/5 | 3/5 | 0/5 | 0/5 | 1/5 |
| **Total** | **17/25** | **18/25** | **14/25** | **14/25** | **11/25** |

| Temperature | Complete | Partial | Incorrect | Invalid output | Unassessable | Median elapsed (s) |
|---|---:|---:|---:|---:|---:|---:|
| default | 17 | 0 | 8 | 0 | 0 | 4.014 |
| 0 | 18 | 0 | 7 | 0 | 0 | 4.292 |
| 0.2 | 14 | 0 | 10 | 1 | 0 | 4.564 |
| 0.7 | 14 | 0 | 8 | 3 | 0 | 4.634 |
| 1.2 | 11 | 1 | 8 | 3 | 2 | 5.15 |

## Findings

Lowering temperature did not demonstrate a clear overall improvement: 0 achieved 18/25 versus 17/25 with the
parameter omitted, a difference of one result. The per-case counts were identical except for `收缩` (3/5 versus
2/5). Temperature 0.2 did worse overall and rejected `收缩` in all five trials. There is no monotonic relationship
between lower temperature and correct grading in these samples. These are descriptive counts, not a claim of
statistical significance or equivalence between settings.

Temperature 0 did not eliminate the original failure classes:

- Trial 048 rejected `缩小` because it invented the target meaning `变大` (become larger).
- Trial 055 rejected spoken `mortal` as not matching `会死` / “will die”.
- Each of the four cases other than `tinker` received both complete and incorrect judgments at temperature 0,
  despite identical full request bodies and audio. The client-side evidence cannot determine why the provider
  remains variable at zero.

Temperature 1.2 performed worst in this run (11/25), with three malformed judgments and two `unassessable`
responses for the same mortal recording accepted in other trials. These two abstentions are shown separately
from format errors even though the application groups both under its `invalid_output` error category. All 125
requests returned HTTP 200; no timeouts occurred.

Omitted and explicit 0.7 are separate measured arms. Their different counts (17/25 and 14/25) do not demonstrate
different effective defaults: five repetitions per case and variable provider results are insufficient to infer
that. The documented default is not echoed by the API.

This experiment does not justify a production temperature change as a fix. In particular, setting zero would
not solve the demonstrated target-substitution and semantic-contradiction errors. No application parameter or
production configuration was changed.

## Every trial

Run is the repetition number within each case/temperature; trial identifies the saved record. Reasons are verbatim model claims, not independently verified phonetic findings. Invalid responses retain their raw outcome when available but are never counted as valid grades.

### tinker

| Temperature | Run | Trial | Validated outcome | Raw outcome if invalid | Model reason / error |
|---|---:|---:|---|---|---|
| default | 1 | 007 | complete | — | The learner produced the target word 'tinker'. |
| default | 2 | 026 | complete | — | The learner correctly produced the target word 'tinker'. |
| default | 3 | 062 | complete | — | The learner correctly produced the target word 'tinker'. |
| default | 4 | 096 | complete | — | The speaker correctly produced the target word 'tinker'. |
| default | 5 | 122 | complete | — | The speaker correctly produced the target vocabulary word 'tinker'. |
| 0 | 1 | 018 | complete | — | The learner produced the target word 'tinker'. |
| 0 | 2 | 050 | complete | — | The speaker correctly produced the target word 'tinker'. |
| 0 | 3 | 064 | complete | — | The learner correctly produced the target word 'tinker'. |
| 0 | 4 | 080 | complete | — | The learner produced the target word 'tinker'. |
| 0 | 5 | 125 | complete | — | The learner correctly produced the target word 'tinker'. |
| 0.2 | 1 | 005 | complete | — | The learner produced the target word 'tinker'. |
| 0.2 | 2 | 047 | complete | — | The learner correctly produced the target word 'tinker'. |
| 0.2 | 3 | 052 | complete | — | The learner correctly produced the target word 'tinker'. |
| 0.2 | 4 | 093 | complete | — | The learner produced the target word 'tinker'. |
| 0.2 | 5 | 123 | complete | — | The speaker correctly produced the target word 'tinker'. |
| 0.7 | 1 | 022 | complete | — | The speaker produced the target word 'tinker'. |
| 0.7 | 2 | 036 | complete | — | The learner correctly produced the target vocabulary word 'tinker'. |
| 0.7 | 3 | 072 | complete | — | The learner correctly produced the target word 'tinker'. |
| 0.7 | 4 | 083 | complete | — | The learner correctly produced the target word 'tinker'. |
| 0.7 | 5 | 115 | complete | — | The speaker correctly produced the target word 'tinker'. |
| 1.2 | 1 | 020 | complete | — | The learner clearly produced the target word 'tinker'. |
| 1.2 | 2 | 040 | complete | — | The speaker produced the exact English target word 'tinker' requested by the vocabulary production task. |
| 1.2 | 3 | 058 | invalid_output | complete | [empty reason]; validation: The judgment contained invalid units. |
| 1.2 | 4 | 090 | complete | — | The learner correctly produced the target word 'tinker'. |
| 1.2 | 5 | 112 | complete | — | The spoken word 'tinker' matches the target vocabulary exactly. |

### mortal

| Temperature | Run | Trial | Validated outcome | Raw outcome if invalid | Model reason / error |
|---|---:|---:|---|---|---|
| default | 1 | 023 | complete | — | The speaker produced the target word 'mortal' clearly. |
| default | 2 | 033 | incorrect | — | Pronunciation error: 't' was pronounced as /d/, making the word sound like 'model'. |
| default | 3 | 070 | incorrect | — | The learner pronounced the word as 'mortal' with a clear /ɔː/ vowel sound, which is incorrect. The target word 'mortal' should have an /ɒ/ or /ɑː/ sound depending on dialect, but the specific pronunciation error here makes it unrecognizable as the intended target in this context. |
| default | 4 | 086 | complete | — | The learner produced the target word 'mortal'. |
| default | 5 | 113 | complete | — | The learner produced the target word 'mortal' with clear pronunciation. |
| 0 | 1 | 019 | complete | — | The learner produced the target word 'mortal'. |
| 0 | 2 | 031 | incorrect | — | The learner pronounced the word as 'mortal' with a clear /ɔː/ sound, which is incorrect for this target. |
| 0 | 3 | 055 | incorrect | — | The spoken word 'mortal' does not match the target expression '会死' (will die). |
| 0 | 4 | 081 | complete | — | The learner produced the target word 'mortal'. |
| 0 | 5 | 120 | complete | — | The learner produced the target word 'mortal'. |
| 0.2 | 1 | 004 | complete | — | The learner produced the target word 'mortal'. |
| 0.2 | 2 | 029 | complete | — | The speaker produced the target word 'mortal'. |
| 0.2 | 3 | 051 | incorrect | — | The learner pronounced the word as 'mortal' with a clear /ɔː/ vowel sound, which is not the target pronunciation. |
| 0.2 | 4 | 099 | complete | — | The learner produced the target word 'mortal'. |
| 0.2 | 5 | 116 | incorrect | — | The learner pronounced the word as 'mortal' with a clear /ɔː/ sound, which is not the target word 'mortal' (/ˈmɔːrtəl/) nor any appropriate form of it. |
| 0.7 | 1 | 008 | incorrect | — | The speaker said 'mortal' with a pronunciation that is difficult to recognize as the target word. |
| 0.7 | 2 | 049 | complete | — | The speaker correctly produced the target word 'mortal'. |
| 0.7 | 3 | 073 | incorrect | — | The learner said 'model', which is a different word from the target 'mortal'. |
| 0.7 | 4 | 076 | complete | — | The speaker produced the target word 'mortal'. |
| 0.7 | 5 | 110 | complete | — | The speaker correctly produced the target word 'mortal'. |
| 1.2 | 1 | 001 | complete | — | The response contains the target word with correct pronunciation. |
| 1.2 | 2 | 041 | unassessable | — | No assessable spoken response was recognized in this recording.; validation: No assessable spoken response was recognized in this recording. |
| 1.2 | 3 | 069 | complete | — | 'Mortal' was produced clearly. |
| 1.2 | 4 | 092 | incorrect | — | Pronunciation is unclear and deviates significantly from the target. |
| 1.2 | 5 | 124 | unassessable | — | No assessable spoken response was recognized in this recording.; validation: No assessable spoken response was recognized in this recording. |

### dissect

| Temperature | Run | Trial | Validated outcome | Raw outcome if invalid | Model reason / error |
|---|---:|---:|---|---|---|
| default | 1 | 024 | complete | — | 'desect' is pronounced as 'dissect', matching the target. |
| default | 2 | 027 | incorrect | — | The spoken word is 'desect', which does not match the target vocabulary 'dissect'. |
| default | 3 | 071 | complete | — | The speaker produced the target word 'dissect' with a pronunciation that matches the reference. |
| default | 4 | 100 | complete | — | The learner correctly produced the target vocabulary word 'dissect'. |
| default | 5 | 111 | complete | — | 'dissect' is the correct target word. |
| 0 | 1 | 015 | incorrect | — | The learner pronounced the word as 'desect' instead of 'dissect', which is a mispronunciation. |
| 0 | 2 | 043 | complete | — | The learner produced the target word 'dissect'. |
| 0 | 3 | 068 | complete | — | The speaker produced the target word 'dissect'. |
| 0 | 4 | 077 | complete | — | The learner produced the target word 'dissect'. |
| 0 | 5 | 121 | complete | — | The learner correctly produced the target word 'dissect'. |
| 0.2 | 1 | 003 | complete | — | The learner correctly produced the target word 'dissect'. |
| 0.2 | 2 | 030 | complete | — | The learner produced the target word 'dissect' with clear pronunciation. |
| 0.2 | 3 | 056 | incorrect | — | The learner pronounced the word as 'desect', which is not a valid English word and does not match the target 'dissect'. |
| 0.2 | 4 | 089 | complete | — | The speaker produced the target word 'dissect'. |
| 0.2 | 5 | 107 | incorrect | — | The learner pronounced the word as 'desect' instead of 'dissect'. |
| 0.7 | 1 | 002 | complete | — | The spoken word matches the target vocabulary 'dissect'. |
| 0.7 | 2 | 028 | complete | — | The learner correctly produced the target word 'dissect'. |
| 0.7 | 3 | 065 | complete | — | The speaker correctly produced the target word 'dissect'. |
| 0.7 | 4 | 094 | complete | — | The spoken word 'dissect' matches the target vocabulary. |
| 0.7 | 5 | 114 | complete | — | The learner produced the target word 'dissect' with clear pronunciation. |
| 1.2 | 1 | 017 | partial | — | 'de sect' pronounces the target with an internal pause that breaks the single syllable onset. |
| 1.2 | 2 | 034 | complete | — | The learner correctly produced the target word 'dissect'. |
| 1.2 | 3 | 057 | incorrect | — | Pronunciation of /ɛ/ as [æ] in the stressed syllable changes the word identity to 'desect', which is not the target. |
| 1.2 | 4 | 079 | complete | — | Pronunciation matches the target 'dissect' closely. |
| 1.2 | 5 | 106 | complete | — | The spoken form matches the target word 'dissect' (heard with minor initial consonant confusion between /d/ and /ð/, but still recognizable). |

### 缩小

| Temperature | Run | Trial | Validated outcome | Raw outcome if invalid | Model reason / error |
|---|---:|---:|---|---|---|
| default | 1 | 006 | complete | — | '缩小' correctly conveys the meaning of 'shrink'. |
| default | 2 | 032 | complete | — | The learner correctly identified the meaning of 'shrank' as '缩小' (to shrink/become smaller). |
| default | 3 | 074 | complete | — | The learner correctly identified the meaning of 'shrank' as '缩小' (to shrink/become smaller). |
| default | 4 | 091 | incorrect | — | '缩小' means 'reduce' or 'make smaller', which describes an action applied to something else, whereas 'shrink' refers to the object becoming smaller on its own. |
| default | 5 | 102 | incorrect | — | The learner said '缩小' which means 'to shrink/reduce'. However, the target word is 'shrink', and the definition provided states that when something shrinks, it becomes smaller. The answer given by the learner does not match the intended meaning of becoming smaller in size or amount. |
| 0 | 1 | 011 | complete | — | The learner correctly identified the meaning of 'shrank' as '缩小'. |
| 0 | 2 | 048 | incorrect | — | The learner said "缩小" (to shrink/reduce), which is the opposite of the target meaning "变大" (to become larger). |
| 0 | 3 | 060 | incorrect | — | The learner said "缩小" (to shrink/reduce), which is the action of making something smaller, not the state of becoming smaller described by "shrink". |
| 0 | 4 | 084 | complete | — | '缩小' correctly conveys the meaning of 'shrink/shrank'. |
| 0 | 5 | 117 | complete | — | The learner correctly identified the meaning of 'shrank' as '缩小'. |
| 0.2 | 1 | 016 | complete | — | The learner correctly identified the meaning of 'shrank' as '缩小'. |
| 0.2 | 2 | 042 | complete | — | '缩小' correctly conveys the meaning of 'shrink/shrank'. |
| 0.2 | 3 | 066 | invalid_output | correct | The learner provided the accurate Chinese translation '缩小' for the meaning of 'shrink/shrank'.; validation: The judgment contained invalid units. |
| 0.2 | 4 | 085 | incorrect | — | '缩小' means 'to shrink/reduce', which is the action or process of becoming smaller. The target word 'shrank' refers to the state/result of having become smaller ('变小'). While related, they are not equivalent in this context. |
| 0.2 | 5 | 118 | complete | — | '缩小' correctly conveys the meaning of 'shrink/shrank'. |
| 0.7 | 1 | 012 | invalid_output | correct | '缩小' means 'shrink', which is the correct meaning.; validation: The judgment contained invalid units. |
| 0.7 | 2 | 037 | incorrect | — | The learner responded with "缩小" (reduce/shrink), which describes an action performed on something else. The target word "shrank" refers to becoming smaller by itself (e.g., 变小/缩水). |
| 0.7 | 3 | 053 | incorrect | — | '缩小' is the opposite of 'shrink', which means to become larger. |
| 0.7 | 4 | 082 | complete | — | '缩小' accurately conveys the meaning of 'shrink' as becoming smaller in size. |
| 0.7 | 5 | 119 | invalid_output | correct | The learner said '缩小', which correctly conveys the meaning of 'shrink/shrank' as becoming smaller in size.; validation: The judgment contained invalid units. |
| 1.2 | 1 | 014 | complete | — | Conveys the meaning of 'shrink' in Chinese. |
| 1.2 | 2 | 044 | invalid_output | partial | '缩小' (to shrink/reduce) is a close synonym and conveys part of the meaning, but it is slightly less precise than the standard translation for this context.; validation: The model did not return a complete valid JSON answer. Retry the fixed input. |
| 1.2 | 3 | 067 | incorrect | — | The spoken response '縮小' means to shrink or reduce, which aligns with the meaning of the highlighted word 'shrank'. However, since the learner gave a definition rather than identifying the target expression's lexical equivalence in context using natural Chinese phrasing such as '变小了' or '收缩', this is considered incorrect under strict recognition criteria. |
| 1.2 | 4 | 078 | incorrect | — | 缩小 means 'to make something smaller' (transitive) rather than becoming smaller on its own, which does not convey the intransitive meaning of shrink. |
| 1.2 | 5 | 105 | incorrect | — | “缩小” means to make something smaller actively, while “shrink” refers to becoming smaller on its own. |

### 收缩

| Temperature | Run | Trial | Validated outcome | Raw outcome if invalid | Model reason / error |
|---|---:|---:|---|---|---|
| default | 1 | 013 | incorrect | — | '收缩' describes contraction or shrinking in volume/size, which is not the standard meaning of 'shrink' as becoming smaller. |
| default | 2 | 046 | incorrect | — | '收缩' (contract/shrink) describes the action of becoming smaller, but fails to convey the specific result '变小' (become smaller in size or amount) required by the definition. |
| default | 3 | 054 | complete | — | '收缩' correctly conveys the meaning of 'shrink'. |
| default | 4 | 087 | incorrect | — | The learner said '收缩' (contract/shrink). The target word 'shrank' in this context refers to becoming smaller, which should be translated as '缩小'. |
| default | 5 | 108 | complete | — | '收缩' accurately conveys the meaning of 'shrink' (to become smaller) in this context. |
| 0 | 1 | 025 | complete | — | The learner correctly identified the meaning of 'shrank' as '收缩'. |
| 0 | 2 | 038 | complete | — | '收缩' correctly conveys the meaning of 'shrink' becoming smaller. |
| 0 | 3 | 061 | incorrect | — | '收缩' means contract/shrink in volume, but the target 'shrank' refers to becoming smaller in size or amount. |
| 0 | 4 | 088 | complete | — | '收缩' correctly conveys the meaning of becoming smaller. |
| 0 | 5 | 104 | incorrect | — | The learner said "收缩" (contract/shrink), which describes the action of shrinking but does not convey the meaning of becoming smaller in size or amount. |
| 0.2 | 1 | 021 | incorrect | — | '收缩' means contract/shrink in a physical sense, but the target 'shrank' refers to becoming smaller in size or amount. |
| 0.2 | 2 | 039 | incorrect | — | '收缩' means contract/shrink, but the target 'shrank' requires conveying the meaning of becoming smaller in size or amount. |
| 0.2 | 3 | 063 | incorrect | — | The learner said '收缩' (contract/shrink), which is a different sense from the target meaning of becoming smaller in size or amount. |
| 0.2 | 4 | 097 | incorrect | — | The learner said "收缩" (contract/shrink), which describes the action of shrinking but does not convey the meaning of becoming smaller in size or amount. |
| 0.2 | 5 | 103 | incorrect | — | The learner said '收缩' (contract/shrink), which is a wrong sense for this context where the balloon becomes smaller due to leaking air. |
| 0.7 | 1 | 010 | incorrect | — | '收缩' means 'contract/shrink in size', which is a related but distinct concept from the specific target meaning of becoming smaller in size or amount ('变小'). |
| 0.7 | 2 | 045 | incorrect | — | The learner said '收缩' (contract/shrink), which describes the process of becoming smaller but does not convey the specific result state of being 'smaller in size or amount' required by the definition. |
| 0.7 | 3 | 059 | incorrect | — | '收缩' means 'to contract/shrink' but is the action verb rather than the state of becoming smaller ('变小') required by the definition. |
| 0.7 | 4 | 095 | invalid_output | correct | The learner provided the Chinese term '收缩' which accurately conveys the meaning of 'shrink/shrank' as becoming smaller.; validation: The judgment contained invalid units. |
| 0.7 | 5 | 101 | incorrect | — | The learner translated the target word as "收缩" (to contract/shrink), which describes the process but does not convey the result of becoming smaller in size or amount. |
| 1.2 | 1 | 009 | incorrect | — | The learner translated the word as '收缩' (contract/shrink in volume), which misses the core meaning of becoming smaller ('变小'). |
| 1.2 | 2 | 035 | incorrect | — | '收缩' (contract/shrink) does not capture the specific meaning of 'becomes smaller in size or amount' as defined by 'shrink'. It is more commonly used for physical contraction or shrinking due to external factors like heat/water. |
| 1.2 | 3 | 075 | complete | — | Correctly identified the meaning of 'shrank' as '收缩'. |
| 1.2 | 4 | 098 | incorrect | — | '收缩' (contract/shrink) refers to the act of reducing size, not becoming smaller in size. |
| 1.2 | 5 | 109 | invalid_output | — | The assessment included fields outside the judgment-only format.; validation: The assessment included fields outside the judgment-only format. |

## Limits and evidence

This is a consistency experiment on five selected correct-answer recordings, with five repetitions per setting. It does not measure accuracy on new speakers or false acceptance of wrong answers. No independent phonetic adjudication was performed. Lower output variability alone would not establish better grading; a model can repeat the same wrong answer. An HTTP 200 response confirms parameter acceptance but does not prove the provider applied it internally.

Private plans, exact prompt, audio hashes, request fingerprints, sampling fields and raw responses: `/home/rlan/.local/share/vocab-learn/audio-eval/20261121-temperature-sweep/`. No credentials or audio are committed.
