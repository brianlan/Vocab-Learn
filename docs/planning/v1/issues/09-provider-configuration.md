# Decide Replaceable ASR and Judge Boundaries

Id: 09
Parent: [Vocab-Learn Browser V1 Decision Map](../map.md)
Type: grilling
Labels: wayfinder:grilling
Mode: HITL
Status: resolved
Assignee: /root
Blocked by: 01, 02, 06, 15, 16, 17

## Question

With deployer-managed server configuration and the default `MINIMAX_API_KEY`, what minimum integration genuinely permits ASR and judging to be replaced independently instead of only changing model names? Use research evidence to settle V1 protocols, separate endpoints/model IDs/credential references, and adapters for actual protocol differences.

Define which configurations are validated in V1 and where another provider requires an explicit adapter. Do not promise arbitrary-provider plug-and-play or build a plugin framework without a target. Credentials remain server-side, and provider failures stay distinct from wrong answers.

Decide transcription/judge input and output contracts, timeout and retryable-error representation, handling of malformed judge output, and reproducible offline fake responses. Any unverified default-model capability must remain visible rather than trigger a silent model substitution.

Honor the settled reveal flow: accept a fixed recording and make the reference available before the slow ASR/LLM work completes. Represent submitted, processing, assessed, and failed/unassessed states explicitly. A retry processes the same recording rather than replacing the spoken answer after reveal.

Honor the settled grading contract: for actual cloze questions the judge reports per-blank outcomes; ordinary Generic questions use a whole-answer assessment, and Vocabulary Cards use their direction's learning goal. The application validates outcomes and computes the grade and timing distinction with English system feedback. Empty or invalid service output is unassessed. Return the committed next due time with the final assessment; do not let the LLM invent the Next review interval.

Question/explanation may be Markdown. Use the canonical visible question with ordered blank identities as the judging context, and retain the single plaintext reference. Presentation HTML or literal code/URL markers must not create extra judged blanks or change response-length timing.

## Comments

2026-10-31: Asked whether V1 needs any named provider beyond the MiniMax defaults and separately configurable OpenAI-compatible ASR/chat interfaces. This is a proposed development boundary awaiting the user's response, not a verified compatibility claim. Protocol-specific adapters, including MiniMax's native ASR contract, must remain explicit; implementation checks will distinguish documented compatibility from live-provider validation.

The user retained MiniMax as the default, requested a LiteLLM-layer evaluation, and explicitly paused this thread to revisit flashcards. Return here after the vocabulary-card generation/grading contracts and LiteLLM evidence are available. Treat generation as a separately identifiable LLM task; do not silently select its model or imply that the user accepted a specific extra provider.

[Evaluate LiteLLM for MiniMax and Provider Compatibility](17-litellm-evidence.md) now supplies the requested evidence and a conditional direct/SDK/proxy comparison. No compatibility layer has been adopted; resume this decision only after the card extension is settled.

The user subsequently accepted starting without LiteLLM. Do not add its SDK or proxy to the initial implementation; retain independently configurable ASR/LLM integrations and the MiniMax defaults. This settles that dependency preference without resolving the remaining provider contracts or advancing the paused architecture thread.

The card extension has now resolved, so this ticket resumes as the frontier. Generation must honor the lifecycle contract: validated pairs before display, fixed references during grading, no learner penalty for provider failures, and no stale example activation. The current proposals to confirm are the initial protocol families and whether judging/generation share one deployer-managed LLM configuration. No named additional provider has been requested or tested.

Sent Q1 proposing native MiniMax ASR plus OpenAI-compatible transcription/chat protocols, separately configurable endpoints/model IDs/server-side keys, and explicit adapters for other protocols without LiteLLM. Sent Q2 proposing one shared LLM configuration for judging and generation, with task-specific prompts/validation and independent ASR configuration. Both choices await the user; this ticket is not resolved by the completed card decisions.

The user then said OK and asked to continue. Proceed with the recommended protocol range and shared LLM configuration; record this as general assent to the summarized recommendations, not fabricated separately numbered answers. Concrete interface, parsing, timeout, and credential rules below are agent-specified implementation decisions.

The user subsequently explicitly required independently configurable judging and generation models, while retaining identical MiniMax defaults. This supersedes the shared-configuration recommendation. They also reported that the interactive question controls were not visible; unanswered deployment/retention choices must be presented in normal conversation text rather than inferred from those controls.

## Answer

Resolved on 2026-10-31, amended by the user's explicit requirement for three independently configured tasks: ASR, judging, and example generation, retaining the MiniMax defaults. Do not add LiteLLM, a provider gateway, or a general plugin registry.

### Production protocol range

- Native MiniMax ASR uses multipart `POST https://api.minimax.cn/v1/speech_to_text`, default model `asr-1.0`, completed/nonstreaming JSON output, and an optional language header. Its response supplies text; confidence must not be invented. [MiniMax ASR reference](https://platform.minimax.cn/docs/api-reference/speech-to-text).
- The replacement transcription adapter supports the OpenAI-compatible multipart `/v1/audio/transcriptions` family with configured model/file, nonstreaming JSON text, and a language form field when known. This is a separate adapter: changing a base URL does not translate MiniMax's route/header contract. Model-specific formats/options still require compatibility checks. [Transcription reference](https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create).
- Judging and example generation each have their own nonstreaming Chat Completions configuration. Both default to endpoint `https://api.minimax.cn/v1/chat/completions` and model `MiniMax-M3.1-Flash`, but endpoint, model, credentials, and request budgets can be changed independently. Reuse the protocol implementation while retaining distinct task prompts and validated outputs. [MiniMax chat reference](https://platform.minimax.cn/docs/api-reference/text-chat-openai).

Same-protocol providers can be changed through server configuration when they implement the adapter's required request/response subset. A nominal OpenAI-compatible label is not certification of every optional field or model capability. Other routes/protocols, such as Messages or Responses-only providers, need an explicit adapter when actually requested. Do not silently switch models when the chosen default is unavailable.

### Configuration and credentials

Use direct server-side HTTP integrations with the installed HTTPX client; an OpenAI SDK is not required by the wire protocol. Configure full request URLs, avoiding implicit path rewriting across the two ASR families.

| Setting | Initial value or behavior |
| --- | --- |
| `ASR_PROTOCOL` | `minimax`; replacement value `openai` selects the other multipart contract |
| `ASR_ENDPOINT` | `https://api.minimax.cn/v1/speech_to_text` |
| `ASR_MODEL` | `asr-1.0` |
| `JUDGE_ENDPOINT` | `https://api.minimax.cn/v1/chat/completions` |
| `JUDGE_MODEL` | `MiniMax-M3.1-Flash` |
| `GENERATOR_ENDPOINT` | `https://api.minimax.cn/v1/chat/completions` |
| `GENERATOR_MODEL` | `MiniMax-M3.1-Flash` |
| `MINIMAX_API_KEY` | Server environment source for all three default MiniMax task configurations |
| `ASR_API_KEY` | Explicit stage-specific override when supplied |
| `JUDGE_API_KEY` | Explicit judging-only override when supplied |
| `GENERATOR_API_KEY` | Explicit example-generation-only override when supplied |
| `ASR_TIMEOUT_SECONDS` | Initial ASR provider-call deadline 60 seconds, bounded by remaining execution time |
| `ASSESSMENT_TIMEOUT_SECONDS` | Initial whole spoken-attempt execution deadline 300 seconds, including queue waiting |
| `GENERATION_TIMEOUT_SECONDS` | Initial whole generation execution deadline 300 seconds, including queue waiting and persistence |
| `WORKER_CLEANUP_GRACE_SECONDS` | Initial bounded local-resource cleanup/recovery budget 10 seconds after execution expiry |
| `JUDGE_TIMEOUT_SECONDS` | Initial Judge provider-call deadline 120 seconds, bounded by remaining execution time |
| `GENERATOR_TIMEOUT_SECONDS` | Initial Generator provider-call deadline 120 seconds, bounded by remaining execution time |
| `JUDGE_MAX_COMPLETION_TOKENS` | Initial judging completion budget 8192, including reasoning |
| `GENERATOR_MAX_COMPLETION_TOKENS` | Initial generation completion budget 8192, including reasoning |

Apply MiniMax endpoint/model defaults only to the default integration. Switching protocol or origin requires explicit replacement settings and its own key; do not accidentally send `MINIMAX_API_KEY` to another host. The implicit key fallback is limited to the configured default MiniMax origin. Validate URLs/protocol/model/required credentials at startup without printing values or making a paid request. Use HTTPS for external endpoints, with deliberate local/internal HTTP configuration permitted for private development services. Do not follow redirects carrying provider authorization to another origin. Browser credentials and Authorization headers are never forwarded as provider credentials.

Keep optional provider parameters with the concrete adapter/profile. For the documented MiniMax default, retain its supported reasoning behavior, omit unsupported temperature-zero/thinking-disabled overrides, and cap output using its supported completion-token parameter (initial budget 8192). A replacement must support the configured subset or receive an explicit profile adjustment; do not send MiniMax-specific options blindly. These budgets are initial engineering defaults requiring latency/quality checks, not provider guarantees.

Judge and Generator resolve their settings independently even when every default currently matches. There is no shared `LLM_MODEL`/`LLM_API_KEY` setting that unintentionally changes both tasks. A task-specific override does not alter another task's profile. Retain actual non-secret provider/model metadata for each execution; changing the judge affects new judging calls, not accepted examples, and changing the generator does not regrade completed attempts. Existing frozen examples, submissions, and completed results remain governed by their revision/history contracts.

### Small caller interfaces

The application uses three concrete module interfaces: transcribe fixed audio into a transcript, assess a frozen question/reference/transcript into validated unit outcomes, and generate a validated example pair from a frozen vocabulary source. The ASR adapter seam has native MiniMax and OpenAI-compatible implementations. The assessment and example modules reuse the chat protocol implementation with separately injected Judge and Generator configurations and task rules. In-memory fake implementations support offline tests without creating a learner-facing demo/provider-switch UI.

Callers see normalized results or stage errors, not multipart paths, raw provider dictionaries, reasoning text, or SDK exceptions. Keep interface contracts and validation together; do not build pass-through class hierarchies, discovery hooks, or per-provider scheduling logic.

### Recording normalization and ASR inputs

Capture the complete browser recording and commit the fixed submission before releasing its reference answer. Conversion/transcription/judging occur after that release. Normalize accepted recordings server-side to mono 16 kHz signed 16-bit PCM WAV, using FFmpeg directly without a Python audio-wrapper dependency. Preserve the original immutable submission and reuse its normalized derivative on retry; renaming WebM is not conversion. WAV is documented by the default ASR, while direct WebM acceptance remains unverified. [Browser/audio evidence](../../../research/v1-browser-audio.md).

Validate actual decodability, file size, duration, and complete input rather than trusting extension/MIME. Start with the default provider ceiling of 500 seconds and 50 MB for uploaded recordings; reject excess clearly rather than truncating a student's answer. Bound conversion runtime/resources, restrict it to local input, and keep audio outside public static/media routes. Real browser recordings and final-image conversion still require implementation checks.

Recognition supplies the selected native-language hint; Production supplies the target-language hint, mapped to the adapter's parameter location. Generic has no declared language and uses the provider's mixed/automatic path. Send no reference-answer text as an ASR keyword prompt, so the transcription input is not biased toward the expected answer. A successful transcript is readonly; an empty or structurally invalid transcript is Not assessed, not a wrong answer. Provider audio duration cannot replace the measured display-to-submit response time.

### Judgment and generation parsing

Use the exact frozen task type, visible question and ordered unit identities, reference/meaning context, language direction, transcript, and relevant content revision. Markdown HTML does not create judgment units. The [grading contract](16-vocabulary-grading.md) owns complete/partial/incorrect interpretation and the application's A-E mapping. The [example lifecycle](15-vocabulary-example-lifecycle.md) owns generated fields, highlighting, activation, and stale-work rejection.

Request a single JSON object in final message content. Locally parse and strictly validate the task's expected fields, identities/counts, enum values, and usable content. A single whole-response JSON code fence may be unwrapped; do not extract a convenient fragment from arbitrary prose, execute generated text, or infer success from a partial object. Missing units, unexpected outcome values, empty final text, refusal, truncation, or failed validation are explicit processing failures. Prompting for JSON is not native schema enforcement.

Inspect HTTP status and provider error payloads, including a nonzero MiniMax `base_resp` even with HTTP 200. Read final `message.content`; never use `reasoning_content` as the answer or show/store it as learner feedback. Tool calls are not executed by these modules. MiniMax strict JSON-schema generation remains unverified, so V1 cannot depend on it. [Existing MiniMax evidence](../../../research/v1-minimax-contracts.md).

### Failure, retry, and result reuse

Normalize errors by stage, stable category, retryability, safe English message, and optional provider trace identity. Conversion/capture errors, timeouts, transport/temporary provider failures, authentication/configuration/balance/model errors, and malformed output remain distinct internally. Learners receive a useful message without credentials or raw provider dumps. Timeout/rate-limit/temporary failures can offer Retry; account/configuration failures require correction by the deployer and still permit an unassessed exit.

Disable hidden SDK retries and model/provider fallback. Initially make one upstream call per stage in each processing execution, with bounded deadlines; explicit same-attempt Retry controls further calls while the attempt remains nonterminal. Persist a successful transcript if judging fails so retry runs only the failed judging stage. Retry keeps the original question, references, timing, recording, direction, submission time, and audio expiry. Once an assessment or explicit unassessed exit commits, repeat requests return that terminal result instead of calling the model or scheduling again. No repeated attempt may fish for a different grade after reveal.

Persist the immutable submission before any slow provider work and distinguish retryable failure from terminal closed-unassessed. [Attempt completion and interruption](19-attempt-completion-and-interruption.md) specifies first committed terminal outcome wins, per-execution claims, profile snapshots, and a 300-second whole-execution budget including unclaimed work. Stage deadlines never exceed remaining execution time. Status/retry/exit routes can expire unfinished work without a healthy worker; late expired/closed/stale results have no learning effects. The architecture supplies storage and processing. A worker crash or uncertain upstream completion cannot guarantee exactly one billed provider invocation; the required guarantee is that one learning result and its schedule/slot update commit at most once.

Timeouts and generation waiting are excluded from recall speed. Failed processing does not become B, consume a direction slot, move collections, increment/reset a streak, or alter a due time. Answer reveal does not wait for ASR, grading, or a new example; Next remains governed by the previously accepted assessed/unassessed flow.

Generation also has a distinct whole-execution deadline and durable recovery route under the [example lifecycle](15-vocabulary-example-lifecycle.md). Apply call limits within the remaining execution budget. HTTPX inactivity/phase timeouts and Future wait timeouts alone do not implement these wall-clock or capacity guarantees. The [worker architecture](10-architecture-and-storage.md) requires bounded actual cleanup and subsequent healthy-job progress; do not merely invalidate a database claim and leave every execution slot occupied.

### Verification and handoff

Offline contract checks must cover both ASR request families, response validation, language placement, cached-transcript retry, HTTP-200 embedded errors, malformed/fenced/truncated/refused chat output, correct unit completeness, no cross-origin default-key leakage, no duplicate grading, and generation failure/stale-candidate behavior. Verify that changing only Judge endpoint/model/key/budgets leaves Generator and ASR unchanged, and vice versa, with identical defaults still accepted. Tests use fake transports and the same caller interfaces as production; fake results do not certify linguistic quality or external accounts.

Rechecked the current MiniMax ASR/chat and official transcription references during this decision. No application client, paid API call, key inspection, recording conversion benchmark, or live model test was run. The existing research establishes documentary support only. Implementation must verify exact account access, short-answer transcription in English/Spanish/Chinese, JSON reliability, model parameters, final-image conversion, and real latency before claiming the defaults work end to end.
