# LiteLLM and MiniMax provider compatibility

Checked on 2026-10-31. This note supports [Evaluate LiteLLM for MiniMax and Provider Compatibility](../planning/v1/issues/17-litellm-evidence.md); it does not select the application's dependency or architecture. MiniMax remains the default. Scope includes transcription, answer judging and vocabulary example generation.

Evidence snapshot: official documentation, PyPI release metadata for `litellm` and `litellm-core` **1.106.6**, and upstream source at **`d1d6d550631d0aaa3a2dc3eeaf48e7d3379cbcec`**. That development snapshot declares version 1.109.0; it must not be confused with the published release. No package was installed or imported.

## Verified integration boundaries

### Chat: plausible transport support, exact model not certified

LiteLLM documents MiniMax chat through both its dedicated `minimax/` provider and its generic OpenAI-compatible route. The dedicated provider accepts an explicit API base and `MINIMAX_API_KEY`, and constructs `/chat/completions`. Its examples still use M2.x names. The inspected provider implementation does not hard-code those names as its only accepted models. [MiniMax guide](https://docs.litellm.ai/docs/providers/minimax), [provider source](https://github.com/BerriAI/litellm/blob/d1d6d550631d0aaa3a2dc3eeaf48e7d3379cbcec/litellm/llms/minimax/chat/transformation.py).

The generic documented route uses an `openai/` model prefix, explicit `api_base`, and API key. Therefore `openai/MiniMax-M3.1-Flash` with `https://api.minimax.cn/v1` is a reasonable integration candidate. This is a source-backed transport inference, not a tested configuration. MiniMax itself documents the exact model and domestic Chat Completions endpoint. [OpenAI-compatible routing](https://docs.litellm.ai/docs/providers/openai_compatible), [MiniMax Chat Completions](https://platform.minimax.cn/docs/api-reference/text-chat-openai).

The inspected cost/capability map has no first-party `minimax/MiniMax-M3.1-Flash` entry, although third-party routes contain M3.1-Flash entries. Absence from this map is **not proof of incompatibility**: it means model-specific capabilities, cost estimates and parameter handling must not be assumed from the catalogue. Another provider's entry cannot establish behavior at MiniMax's own endpoint. [Inspected model metadata](https://github.com/BerriAI/litellm/blob/d1d6d550631d0aaa3a2dc3eeaf48e7d3379cbcec/model_prices_and_context_window.json).

Judging and example generation can use the same configured chat transport with separate prompts and validated result schemas; a second application use case does not itself require a gateway. This is an application-design inference.

### ASR: native MiniMax support is missing from the inspected path

MiniMax `asr-1.0` accepts multipart uploads at **`/v1/speech_to_text`**; its optional `language` hint is a header. This differs from OpenAI-style `/v1/audio/transcriptions`, including the route and some parameter placement. [MiniMax ASR reference](https://platform.minimax.cn/docs/api-reference/speech-to-text).

LiteLLM's transcription guide does not list MiniMax. The inspected audio-provider configuration has no MiniMax branch, and the transcription dispatcher raises `UnsupportedEndpointError` for providers without a recognized transport/configuration. MiniMax is also absent from the inspected OpenAI-compatible transcription-provider set. Consequently, native `minimax/asr-1.0` support is not established and should be treated as requiring a direct adapter or a new integration. [Transcription guide](https://docs.litellm.ai/docs/audio_transcription), [configuration dispatch](https://github.com/BerriAI/litellm/blob/d1d6d550631d0aaa3a2dc3eeaf48e7d3379cbcec/litellm/utils.py#L10171), [transcription dispatch](https://github.com/BerriAI/litellm/blob/d1d6d550631d0aaa3a2dc3eeaf48e7d3379cbcec/litellm/main.py#L8519), [provider sets](https://github.com/BerriAI/litellm/blob/d1d6d550631d0aaa3a2dc3eeaf48e7d3379cbcec/litellm/constants.py).

Pointing a generic OpenAI transcription client at MiniMax's base URL does not rewrite that protocol into MiniMax's native ASR protocol. A proxy's configurable pass-through route could forward a native request, but forwarding is not schema translation or verified transcription integration; multipart behavior would still need testing. [Pass-through routes](https://docs.litellm.ai/docs/proxy/pass_through).

## SDK, packages and operational cost

The published 1.106.6 packages require Python `>=3.10,<3.15`, so Python 3.11 meets their declared interpreter constraint. Evaluating their dependency markers for Python 3.11 yields **20 mandatory direct requirements for `litellm` and 18 for `litellm-core`**. These are metadata counts, not installed size or a solved transitive dependency graph. Both include OpenAI, HTTPX, Pydantic, JSON Schema validation and token-counting dependencies; installation may upgrade packages already present in the supplied environment. [Published LiteLLM metadata](https://pypi.org/pypi/litellm/1.106.6/json), [published core metadata](https://pypi.org/pypi/litellm-core/1.106.6/json).

`litellm-core` is the relevant SDK-only option: it retains provider translation, async calls, Router, retries and error mapping while omitting bundled dashboard/CLI assets and mandatory `boto3`, `tokenizers`, and `huggingface-hub` requirements. It still includes `tiktoken` and `jsonschema`. The two distributions share the `litellm` namespace and must not be installed together. [Official core package guide](https://docs.litellm.ai/docs/litellm_core).

| Choice | What it buys for this app | What remains / additional cost |
| --- | --- | --- |
| Direct configured clients | Reuse one chat transport for compatible model endpoints; retain MiniMax defaults | Native ASR request, application validation and bounded error handling remain application code; no routing service |
| In-process LiteLLM SDK/core | Provider translation, shared error types, optional retries/routing across supported protocols | Additional dependency graph; exact MiniMax model behavior still needs checking; native ASR still needs its own path |
| Separate LiteLLM proxy | Shared central configuration, virtual keys, usage accounting, routing and an admin interface across clients | Additional deployed service and network hop; ASR translation gap remains; only worthwhile when shared gateway features are required |

The proxy is a separately hosted OpenAI-compatible gateway; its central keys, budgets and management features differ from installing the Python SDK inside this app. Neither a database nor Redis is asserted as mandatory for every minimal gateway setup. [SDK and proxy overview](https://docs.litellm.ai/docs/).

## Structured results and failure handling

LiteLLM documents capability checks before requesting JSON Schema output and offers optional **client-side validation**. Validation can reject a malformed result; it cannot confer native strict generation on an upstream model. MiniMax-origin strict output support remains unverified in the [existing MiniMax research](v1-minimax-contracts.md). Judging and example generation still need application-owned semantic validation and an explicit failure path. [Structured-output guide](https://docs.litellm.ai/docs/completion/json_mode).

The SDK accepts request timeouts and retry/fallback settings. These features do not select a fair student-response timer, an application-wide deadline, or exactly-once storage. Decide retry ownership explicitly to avoid stacking app, SDK and proxy retries; provider calls can repeat even when only one learning attempt should be stored. Model fallback is a policy choice, not an automatic substitute for the selected judge. [Input settings](https://docs.litellm.ai/docs/completion/input), [retry/fallback guide](https://docs.litellm.ai/docs/completion/reliable_completions).

## Conditional recommendation for the later architecture decision

- **If replacements remain genuinely compatible Chat Completions endpoints:** direct configurable clients are sufficient. Keep endpoint, model and server-side key references independent for ASR and LLM; reuse chat transport for judging and example generation. LiteLLM adds limited value solely for changing compatible endpoints.
- **If several distinct provider protocols or shared SDK routing/error normalization become a concrete near-term need:** evaluate a pinned in-process `litellm-core` release. It is a credible reuse option without operating a proxy, but leaves MiniMax ASR as a separate integration unless native support is verified later.
- **If several applications or teams need centrally managed provider keys, budgets or routing:** revisit the proxy. The currently described small private application does not by itself establish that need.

Before adopting either SDK route, verify the exact domestic model request, accepted parameters, final-text extraction, malformed/truncated results and retry behavior against a pinned version. Preserve the default models during that assessment. This recommendation remains provisional while card and learning rules are being reconsidered.

No installations, live model calls, credential inspection, proxy deployment or latency/size benchmarks were performed. Documentation/source establish integration boundaries; they do not establish working credentials or answer quality.
