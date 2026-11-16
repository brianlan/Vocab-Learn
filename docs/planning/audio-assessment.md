# Direct audio assessment — agreed design

Status: requirements clarified through Q1–Q12; implemented on the audio-assessment
branch with contract/workflow/browser verification and fake-transport tests. Live
provider accuracy and latency evidence (Qwen and Doubao accounts, real microphone
audio, three-submission latency measurement) remains outstanding and is reported
as such in the implementation PR. Deployment requires a separate explicit request
after development verification.

Implementation tracking: [GitHub issue #12](https://github.com/brianlan/Vocab-Learn/issues/12).
The issue contains the complete acceptance contract independently of this file.

## Requested direction

- Replace the sequential ASR and text Judge calls with one multimodal model call
  receiving the fixed spoken answer and the frozen learning task.
- Initially support Qwen3.8-Omni-Flash and Doubao Seed 2.1 Lite; default to Qwen,
  with a configuration switch to Doubao. Low-priority queueing is excluded;
  purchasing a reserved TPM package is not a requirement. Use regular inference
  (`service_tier="default"`) for Doubao and evaluate its actual latency. The user
  rejected `fast` for this phase because of its cost.
- Explicitly disable thinking by default for both providers.
- Return JSON compatible with the application's assessment contract.

## Existing contract and proposed seam

`learning/providers.py:assess` currently accepts a frozen task and transcript,
and returns validated answer units plus provider provenance. The model returns
`units` with `id`, `outcome` (`complete`, `partial`, `incorrect`) and an English
`reason`, or signals that assessment is impossible. Application code computes
B–E from those units and frozen timing; the model never chooses scheduling.

The proposed deep module accepts the frozen task and fixed audio, and returns
validated assessment data or a stage error. Qwen and Doubao adapters occupy the
same seam; provider payload differences stay inside the module. Learning-state
writes and execution ownership remain with the existing worker/review workflow.
The same call must also return a transcript for a successfully scored answer.

Task context includes the authored definition, review direction, response
language, selected expression position and required unit identities where
applicable. A translated highlight alone is not the grading authority for
Recognition. Generic cards also require support for zero or multiple blanks.

## Verified documentation facts

Checked on 2026-11-16; documentation evidence, not live account verification.

- [Qwen Omni](https://help.aliyun.com/zh/model-studio/qwen-omni) documents audio
  input with text output, nonstreaming JSON Mode and
  `reasoning_effort="none"` for `qwen3.8-omni-flash`. Its JSON Mode does not
  enforce a JSON Schema; application validation remains necessary.
- [Doubao low-priority inference](https://docs.volcengine.com/docs/ark/online-inference-flex?lang=zh)
  lists `doubao-seed-2-1-lite-260915` and selects low priority using
  `service_tier="flex"`. It permits minute-scale queueing, does not guarantee
  completion time or success, and does not automatically fall back to standard
  priority. Server resource waiting can last up to 20 minutes unless bounded.
- [Doubao audio input](https://docs.volcengine.com/docs/ark/audio-understanding?lang=zh)
  supports WAV; the existing browser-recording conversion is relevant because
  browser WebM/Opus is not among its listed pure-audio formats.

## Accepted decisions

1. Replace all Generic and Vocabulary spoken assessments, including both review
   directions and multi-blank answers. Other model tasks retain their settings.
2. Preserve recall semantics and all A–E rules. Do not add pronunciation scoring;
   intelligible accents do not reduce scores. Recognition accepts equivalent
   meanings; Production and Generic distinguish targets from suitable substitutes.
3. Retain readonly Your response text, returned in the same model call and
   required for a successful scored assessment. Judge the audio directly; never
   add a separate ASR call for display. The glossary definition is now independent
   of which model produces the transcript.
4. Silence or genuinely unintelligible audio is Not assessed and leaves progress
   unchanged. Clear wrong answers or statements of not knowing are incorrect.
   Do not infer an audio problem merely because the answer differs from the target.
5. Retain full-recording WAV normalization without clipping the spoken answer.
6. At most one model request per assessment execution. No automatic model retry,
   JSON-repair call or provider fallback. Explicit Retry uses fixed audio and the
   current configuration; completed results remain unchanged.
7. Use Doubao regular inference (`service_tier="default"`) for live evaluation.
   Do not use low-priority inference, buy reserved TPM capacity or silently switch
   to the more expensive `fast` tier. Missing the latency target requires reporting
   the result and revisiting the design, not changing the selected tier implicitly.
8. Measure latency from Stop & check to the complete displayed assessment. For
   recordings up to 30 seconds with three simultaneous submissions, the accepted
   target is 95% within five seconds. A submission exceeding 15 seconds shows a
   timeout and permits explicit retry. These are acceptance targets, not measured
   capabilities or per-stage allowances. They apply to Qwen and Doubao alike.
   Include upload, application queueing, conversion, model work, persistence and
   result delivery; provider timeouts alone do not enforce this target. Existing
   claim/late-result protections must continue to prevent obsolete results from
   changing progress after execution timeout.
9. Keep the current WAV/original-recording lifecycle described below. Successful
   assessment deletes both; failed/interrupted recordings expire at the original
   submission plus 24 hours. Retry never extends retention. Audio stays outside
   the current cold-backup scope.
10. Stop supporting transcript-only retries when audio is missing or expired,
    including legacy pending submissions and restored backups. Offer unassessed
    exit and a later new review; do not retain a text-only Judge path. Preserve
    existing transcripts, completed results, history and learning progress.

## Audio storage facts

`learning/work.py:normalize` writes a temporary WAV beside the uploaded recording,
validates it, then renames it to `<audio_name>.wav` for reuse. Conversion scratch
files are removed in a finally block during ordinary execution; interrupted
process leftovers are covered by cleanup. Both the original and converted files
are deleted after assessment commits. Failed/interrupted audio expires 24 hours
after original submission; worker cleanup runs at startup and every minute.
Cleanup cannot run while the worker is stopped. Current backups exclude audio.

Compose mounts the `audio_tmp` named volume at `/audio`; outside Compose the
default directory is `var/audio`, unless overridden by configuration. These are
disk files with a temporary lifetime, not only in-memory buffers.

## Implementation evidence still required

- Verify account access and the combined audio/JSON/thinking configuration for
  Qwen and Doubao regular inference before claiming support. Neither the model's
  documented capabilities nor its inference-tier name proves the latency target.
- Exercise real audio with concise equivalents, target/substitute distinctions,
  accents, silence, noise and answer anchoring. Validate transcript and unit
  completeness, English feedback, and equivalence to the accepted learning rules.
  Mock transport tests cannot establish linguistic accuracy or latency.
- Measure the accepted latency scenario, including application worker contention
  with other model tasks. Keep the existing recording limits; 30 seconds defines
  the performance test scenario, not a new upload limit.

## Expected implementation reach

Provider module and worker; retry/recovery rules; transcript display and
provenance if changed; task configuration in environment/Compose and startup
validation; provider probes and contract, workflow, concurrency and restore
tests; glossary, specification and operations documentation. Preserve historical
results, frozen task snapshots, example revisions and learning progress.

Only planning documentation and the agreed Transcript glossary definition have
changed. No application code or learning rules changed; no credentials inspected,
paid calls made or production actions performed. Actual grading accuracy and
latency remain unmeasured.
