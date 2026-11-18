# Qwen API-mode live verification — PR #15 R3

## Result and scope

On 2026-11-18 the maintainer authorized verification using Qwen and the existing private credentials/recordings.
The evaluated application commit was `3913ea5f25ea4994dc0ac72142643650d2ee2e75`, unchanged throughout testing.
Only Qwen was called. This record makes no live compatibility or quality claim for either Doubao mode.

**R3 verification did not pass acceptance.** Both Qwen API families accept the implemented wire contract and
return usable spoken-answer assessments, but Responses sometimes fabricates a correct answer to quiet recorded
audio. Responses also missed the inherited five-second target in the measured application workload, including
two provider timeouts. Successful transport is not sufficient evidence of safe judgment or latency acceptance.

The earlier latency deferral was explicitly for PR #13. This report neither assumes a new waiver for PR #15 nor
changes the existing 15-second safety budget. No runtime fix, automatic fallback, merge or production release
was performed during this verification.

## Provider-path checks

- Requested and returned model: `qwen3.8-omni-flash`; prompt: `spoken-audio-v2`.
- Both modes used the provider/mode default endpoint with an empty endpoint override: DashScope
  `/compatible-mode/v1/responses` and `/compatible-mode/v1/chat/completions`.
- The application supplied normalized mono 16-kHz WAV through its MP3 transport. Each probe dispatched exactly
  one request; no automatic retries. Responses sent `store=false` and `reasoning={"effort":"none"}`;
  Chat sent `reasoning_effort="none"`. No tools or response chaining were configured.
- Expected outcomes and utterances were taken from the pre-existing, frozen private human-audio fixtures before
  examining outputs. Six spoken samples were 2.44–2.90 seconds; the recorded silence sample was 6.316 seconds.

| Recorded utterance / task | Expected outcome | Responses | Chat Completions |
| --- | --- | --- | --- |
| call off / recall call off | complete | complete | complete |
| cancel / recall call off | partial | partial | partial |
| 吸收 / absorb Recognition | complete | complete | complete |
| 改时间 / postpone Recognition | partial | partial | partial |
| 缩小 / absorb Recognition | incorrect | incorrect | incorrect |
| 我不知道 / absorb Recognition | incorrect | incorrect | incorrect |
| Quiet room recording / recall call off | no score | fabricated complete answer | rejected unassessable |

All twelve spoken transcripts matched their pre-labelled utterances apart from capitalization/punctuation.
The first fourteen requests all returned HTTP 200; the semantic silence failure was an otherwise valid response.

### Silence diagnostics

Two additional, explicitly scheduled Responses trials used the identical quiet-room WAV and frozen task. One
was safely rejected for an empty transcript; the other again fabricated a complete answer. Thus **2/3** Responses
trials on this recording returned a nonempty transcript and `complete` unit accepted by the application validator.
Both fabricated transcripts were: “We had to call off the meeting because the speaker was ill.” A complete
unit would map to D/E if committed; these provider-only probes did not write a learning database.

The quiet recording is not all-zero PCM (RMS -60.22 dBFS, peak -42.49 dBFS); it was supplied and labelled as
silence by the maintainer. An additional three-second, verified all-zero PCM recording was safely rejected by
both modes with `unassessable=true`. The broader finding is therefore inconsistent handling of quiet/non-speech
recordings, not an assertion that every silent input fails or that Chat is universally immune.

An offline capture of each mode's request confirmed byte-identical encoded audio, identical system prompt and
identical task JSON. The observed difference was not caused by accidentally changing the question or recording.
The small trial count is diagnostic evidence, not a population error-rate estimate.

There were **18 direct paid requests** in total: 10 Responses and 8 Chat, all HTTP 200. Provider-path elapsed
times were 2.207–4.279 seconds for Responses and 2.711–4.069 seconds for Chat. These include MP3 encoding but
exclude browser upload, worker queueing and persistence; they are not end-to-end timing evidence.

## Responses application checks

The exact commit ran in an isolated Compose project with fresh SQLite/audio volumes and dedicated fixtures,
loopback HTTP, the standard Gunicorn web command and three worker slots. No other generation jobs occupied
the worker. Unrelated model tasks had dummy credentials. Production and the existing PR #13 test site were untouched.

Chromium 151 used the real page's Speak / Stop & check workflow with a fake microphone fed by the human
`call off` recording. Two rounds each submitted three independent cards within approximately one millisecond.
The longer fixture padded the same short utterance with silence; it was not 29 seconds of continuous speech.

| Recording duration | Stop to displayed terminal result | Result |
| --- | --- | --- |
| 3.548 s | 5.296 s | correct, E |
| 3.548 s | 7.301 s | correct, E |
| 3.548 s | 7.302 s | correct, E |
| 29.062 s | 15.324 s | provider timeout, not assessed |
| 29.062 s | 15.324 s | provider timeout, not assessed |
| 29.061 s | 11.314 s | correct, D |

**0/6** submissions produced a complete assessment within five seconds, with both failures retained in the
denominator. This sample does not meet the target. The 15.324-second entries measure browser display after the
server execution deadline, not permission to commit after 15 seconds. Retained normalized WAVs for the timed-out
cases measured 29.04 seconds; both remained unscored with unchanged progress/FSRS when checked more than
45 seconds after their deadlines. The UI offered the existing retry path. No retry was performed in this run.

A seventh browser submission captured the quiet-room fixture for about 6.08 seconds and was safely rejected for
an empty transcript after 5.292 seconds. This additional safe outcome does not erase the direct Responses failures.
It used browser re-encoding and is distinct from the identical-WAV diagnostic trials above.

Database checks found four successful attempts with exactly one score/progress update each, three failed attempts
with zero scores or progress changes, Responses/Qwen provenance on all seven, one execution per attempt, and
successful-recording cleanup. Reload preserved each result. No browser JavaScript errors occurred. These checks
are seven additional live calls, bringing this verification to **25 Qwen calls**. They are not new physical-device
or HTTPS/private-CA tests.

## Required follow-up and evidence

The missing Qwen evidence is now available, but it identifies an acceptance failure. Quiet/non-speech input must
not gain a correctness score merely because the model invents a valid transcript and unit. Investigate and verify
that failure before declaring the Responses path safe; preserve legitimate quiet spoken answers and the one-call
contract. Timing also needs an explicit PR #15 acceptance decision or further work; no silent relaxation is recorded.

Private artifacts contain frozen fixture identities/hashes, exact probe scripts, raw response envelopes and usage,
the request-equivalence check, browser timing records, screenshots and database audits. They remain outside Git;
no credentials or recordings are published. No application code changed, so the reviewer's existing 241-test result
on the evaluated commit remains separately attributed; this live verification does not claim a fresh full-suite run.
