# StepAudio 3 Chat with the supplied direction-specific prompts

**Experiment only; not integrated or deployed.** Started 2026-11-21T16:27:02.201399+00:00.

## Interface and controlled inputs

The [model guide](https://platform.stepfun.com/docs/zh/guides/models/stepaudio-3-realtime) identifies `stepaudio-3-chat-preview` as the turn-by-turn HTTP model. The [Chat API](https://platform.stepfun.com/docs/zh/api-reference/chat/chat-completion-create.md) accepts inline MP3/WAV audio and text output. This experiment uses `https://api.stepfun.com/v1/chat/completions`, not Realtime/WebSocket.

- Exact supplied `spoken-audio-v5-candidate-1` bundle, selected by task kind/direction; bundle SHA-256 `c60221a2ccb9b477f8f5d34257bb12061223f0dbfe4575bcae2ec8bb83f2faf8`.
- Same five human recordings and eight controls as the [Qwen candidate experiment](direction-prompts-v1-experiment.md). Five repetitions for each primary case, two for each control: **41 calls**.
- Same frozen task JSON and identical encoded MP3 data as Qwen, verified by hashes; text task and audio sent together. No ASR stage or transcript output requested.
- StepAudio request: `stream=false`, `modalities=["text"]`, `response_format={"type":"json_object"}`, `max_tokens=8192`; sampling parameters omitted.
- No documented thinking-off option was established for this model. StepAudio thinking parameters were omitted, and reasoning-field presence was recorded. Qwen explicitly used `reasoning_effort="none"`; this is a material comparison difference.
- Each call gets the same 15-second assessment budget including audio encoding. Sequential calls, shuffled within repetition blocks with order seed `2026112202`; one request per trial, no automatic retries or fallback.
- A private experimental request adapter reuses application task construction, MP3 encoding, JSON parsing and assessment validation. No StepAudio support was added to the application.
- The Qwen column below is the preceding completed run using the same new prompt; Qwen was not rerun concurrently. Provider defaults and execution time can differ.

## Five primary cases

Counts are valid `complete` judgments; format errors, timeouts and wrong grades are not passes.

| Answer | Prior Qwen, new prompt | StepAudio 3 Chat, new prompt |
|---|---:|---:|
| tinker | 5/5 | 5/5 |
| mortal | 0/5 | 5/5 |
| dissect | 3/5 | 5/5 |
| 缩小 | 3/5 | 5/5 |
| 收缩 | 3/5 | 5/5 |
| **Total** | **14/25** | **25/25** |

## Controls

| Case | Expected | Prior Qwen | StepAudio |
|---|---|---|---|
| thinker-en-us | incorrect | 1 incorrect, 1 complete | 2 incorrect |
| mobile-en-us | incorrect | 1 complete, 1 partial | 2 incorrect |
| human-neuroticism | complete | 2 incorrect | 2 complete |
| human-neurocism | incorrect | 2 incorrect | 1 timeout, 1 incorrect |
| recognition-correct | complete | 1 complete, 1 incorrect | 2 complete |
| recognition-wrong | incorrect | 2 incorrect | 2 incorrect |
| handyman-en-us | partial | 2 incorrect | 2 partial |
| human-silence | unassessable | 2 unassessable | 2 unassessable |

## Completion and timing

- Expected outcomes: 40/41; main cases 25/25, controls 15/16.
- Outcome counts: 2 partial, 29 complete, 2 unassessable, 7 incorrect, 1 timeout.
- Median elapsed: 2.936 s; maximum recorded elapsed: 15.015 s. Timed-out requests, if any, are censored at the 15-second budget rather than measured to completion.
- Responses with nonempty reasoning fields: 40. Only final answer content was graded; reasoning text was never used as the learner answer.
- Elapsed time is measured in the private harness, not browser Stop-to-result latency or production concurrency performance.

## Findings

StepAudio produced valid complete judgments on **25/25 primary trials**, versus 14/25 in the preceding Qwen run
with the same supplied prompts. Controls matched expectations in **15/16** trials, versus 8/16 for Qwen. All 40
completed StepAudio replies passed the application format validator and matched their expected outcome; the
remaining request timed out without a usable response. There were no observed false acceptances or false
rejections among the completed trials. This is a strong improvement on this selected fixture set, not a general
accuracy estimate or proof that model choice alone explains the difference.

The timeout was the first shortened-neurocism trial (013). It was counted as a failed assessment and was not
retried. Its second, preplanned repetition (016) completed in 4.270 seconds with the expected incorrect outcome.
The longest completed request was 9.300 seconds; the 15.015-second maximum includes the timed-out request.
This tail failure still matters for the application's existing 15-second budget despite the 2.936-second median.

Grade correctness does not imply perfect feedback fidelity. Three dissect replies (018, 031 and 038) described
the supplied base-word recording as `dissected`. Both forms are accepted by the task, so the grade is still the
expected complete result, but the stated heard form differs from the user-provided label. One mortal reply also
included a pronunciation explanation despite the prompt asking for lexical/meaning-only feedback. No separate
acoustic adjudication was performed to resolve these descriptions.

All 40 completed replies contained nonempty reasoning fields. Qwen's comparison explicitly disabled thinking;
StepAudio's default reasoning behavior, provider implementation and request settings differ. The model was tested
as an HTTP audio judge with final-answer JSON only; reasoning was neither graded nor returned as learner feedback.
These results support StepAudio as a promising candidate for application integration, while leaving timeout
behavior, wider human coverage and generic recall for subsequent validation.

## Every StepAudio trial

Reasons below are model claims, not an independent phonetic adjudication. Run numbers are per-case repetition order.

### tinker

| Run | Saved trial | Outcome | Model reason / error | Elapsed (s) |
|---:|---:|---|---|---:|
| 1 | 009 | complete | The learner produced the exact target word 'tinker'. | 2.503 |
| 2 | 025 | complete | The learner produced the exact target word 'tinker' in English. | 2.296 |
| 3 | 027 | complete | The learner produced the target word 'tinker' exactly as required. | 2.312 |
| 4 | 033 | complete | The learner produced the exact target word 'tinker'. | 2.383 |
| 5 | 040 | complete | The learner produced the exact target word 'tinker' matching the requested English expression. | 2.42 |

### mortal

| Run | Saved trial | Outcome | Model reason / error | Elapsed (s) |
|---:|---:|---|---|---:|
| 1 | 004 | complete | The spoken answer matches the target word 'mortal'; the apparent 'd' sound reflects the common intervocalic t-flap pronunciation variant of 'mortal' in English. | 7.024 |
| 2 | 022 | complete | The learner produced the target word 'mortal' as the answer. | 2.671 |
| 3 | 030 | complete | The learner produced the exact target word 'mortal'. | 2.648 |
| 4 | 035 | complete | The learner produced the exact target word 'mortal', matching the requested vocabulary recall. | 3.06 |
| 5 | 039 | complete | The learner produced the exact target word 'mortal' as the English answer. | 2.433 |

### dissect

| Run | Saved trial | Outcome | Model reason / error | Elapsed (s) |
|---:|---:|---|---|---:|
| 1 | 002 | complete | The learner produced the exact target word 'dissect'. | 2.649 |
| 2 | 018 | complete | The learner supplied 'dissected', an inflected form of the target word 'dissect' matching the intended meaning. | 3.759 |
| 3 | 031 | complete | The learner produced 'dissected', a correct inflected form of the target word 'dissect' matching the intended meaning. | 4.081 |
| 4 | 036 | complete | The learner produced the target word 'dissect' as the answer. | 2.905 |
| 5 | 038 | complete | The learner produced 'dissected', an inflected form of the target word 'dissect' matching the past-tense context of the sentence. | 3.02 |

### 缩小

| Run | Saved trial | Outcome | Model reason / error | Elapsed (s) |
|---:|---:|---|---|---:|
| 1 | 012 | complete | The learner gave the standard Chinese equivalent '缩小', accurately conveying that 'shrank' means became smaller in size. | 3.019 |
| 2 | 026 | complete | The learner gave the standard Chinese equivalent '缩小', which conveys that something becomes smaller in size or amount, matching the intended meaning of 'shrank'. | 2.751 |
| 3 | 028 | complete | The learner gave '缩小', the standard Chinese equivalent of 'shrink', matching the intended meaning of becoming smaller. | 2.547 |
| 4 | 032 | complete | The learner gave the conventional Chinese equivalent '缩小', correctly conveying that 'shrink' means to become smaller in size or amount. | 2.971 |
| 5 | 041 | complete | The response '缩小' accurately conveys that 'shrank/shrink' means becoming smaller in size or amount. | 2.549 |

### 收缩

| Run | Saved trial | Outcome | Model reason / error | Elapsed (s) |
|---:|---:|---|---|---:|
| 1 | 008 | complete | The learner answered '收缩', the standard Chinese equivalent of 'shrink', correctly conveying the meaning of becoming smaller in size or amount. | 3.768 |
| 2 | 017 | complete | The learner gave '收缩', the standard Chinese equivalent of shrink, matching the intended meaning of becoming smaller in size or amount. | 2.904 |
| 3 | 029 | complete | The learner gave the Chinese equivalent '收缩', which accurately conveys that 'shrank' means became smaller in size. | 2.807 |
| 4 | 034 | complete | The learner provided the correct Chinese equivalent '收缩', which accurately conveys the meaning of 'shrink' as becoming smaller in size. | 2.753 |
| 5 | 037 | complete | The learner gave '收缩', the standard Chinese equivalent meaning to become smaller in size or amount, matching the intended sense of 'shrink'. | 3.23 |

### thinker-en-us

| Run | Saved trial | Outcome | Model reason / error | Elapsed (s) |
|---:|---:|---|---|---:|
| 1 | 006 | incorrect | The learner produced 'thinker', a different word with unrelated meaning, rather than the target 'tinker'. | 2.457 |
| 2 | 015 | incorrect | The learner said 'thinker', which is a different English word meaning a person who thinks, not the requested term 'tinker' for a traveling repairer. | 2.971 |

### mobile-en-us

| Run | Saved trial | Outcome | Model reason / error | Elapsed (s) |
|---:|---:|---|---|---:|
| 1 | 007 | incorrect | The learner produced 'mobile', which has a different meaning (able to move) and does not match the target word 'mortal'. | 2.695 |
| 2 | 014 | incorrect | The learner said 'mobile', which has a different meaning (able to move) and does not match the target word 'mortal' meaning subject to death. | 3.53 |

### human-neuroticism

| Run | Saved trial | Outcome | Model reason / error | Elapsed (s) |
|---:|---:|---|---|---:|
| 1 | 011 | complete | The learner produced the exact target word 'neuroticism'. | 2.73 |
| 2 | 023 | complete | The learner produced the target word 'neuroticism'. | 9.3 |

### human-neurocism

| Run | Saved trial | Outcome | Model reason / error | Elapsed (s) |
|---:|---:|---|---|---:|
| 1 | 013 | timeout | Audio assessment timed out. You can retry the fixed input. | 15.015 |
| 2 | 016 | incorrect | The spoken response is a clearly malformed mispronunciation of the target word 'neuroticism', not supplying the correct expression. | 4.27 |

### recognition-correct

| Run | Saved trial | Outcome | Model reason / error | Elapsed (s) |
|---:|---:|---|---|---:|
| 1 | 005 | complete | The learner gave the standard Chinese equivalent '吸收', which correctly conveys the intended meaning of soaking up and holding liquid. | 3.636 |
| 2 | 020 | complete | The learner gave '吸收', the standard Chinese equivalent of 'absorb', covering the intended sense of soaking up and holding liquid. | 3.311 |

### recognition-wrong

| Run | Saved trial | Outcome | Model reason / error | Elapsed (s) |
|---:|---:|---|---|---:|
| 1 | 010 | incorrect | The learner said '缩小' (to shrink/reduce), which does not convey the meaning of soaking up and holding liquid expressed by 'absorb'. | 2.936 |
| 2 | 019 | incorrect | The learner answered '缩小' (shrink/reduce), which does not convey the meaning of 'absorb' (soak up liquid); the response is unrelated to the intended sense. | 3.648 |

### handyman-en-us

| Run | Saved trial | Outcome | Model reason / error | Elapsed (s) |
|---:|---:|---|---|---:|
| 1 | 001 | partial | The learner answered 'handyman', an English word for a general repairer, which relates to the intended meaning but omits the key itinerant, traveling-from-place-to-place sense of 'tinker'; it is a different suitable English expression rather than the target or a true equivalent. | 9.073 |
| 2 | 021 | partial | The learner answered 'handyman', an English term related to repairing household items, but did not recall the target word 'tinker'. | 7.017 |

### human-silence

| Run | Saved trial | Outcome | Model reason / error | Elapsed (s) |
|---:|---:|---|---|---:|
| 1 | 003 | unassessable | Returned unassessable. | 2.593 |
| 2 | 024 | unassessable | Returned unassessable. | 3.217 |

## Evidence and limits

Private bundle copy, cases, official API documentation snapshots, pre-call plan, input hashes, parameters, raw responses and summaries: `/home/rlan/.local/share/vocab-learn/audio-eval/20261122-stepaudio3/`. Credentials were read from `STEPFUN_API_KEY` and never written into reports. Original audio and production data were unchanged.

This small selected sample cannot establish general accuracy. Correct-answer expectations come from user labels and learning rules; pronunciation was not independently adjudicated. Synthetic thinker/mobile/handyman controls are not new human speakers. Generic was tested only on silence, not ordinary recall or multiple blanks. No full application integration, browser test, deployment or concurrent load test was performed.

Follow-up: [formal adapter integration](stepaudio3-integration.md) replays the same inputs through application code and records an additional neurocism false positive. The original experiment above should not be read as a guarantee against malformed-word acceptance.
