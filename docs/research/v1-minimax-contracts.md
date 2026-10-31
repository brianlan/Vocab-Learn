# MiniMax models and API contracts

Checked on 2026-10-30 (UTC). This investigation reads official documentation and the supplied local bridge; it does not establish account access, real latency, transcription accuracy, or grading quality. Learning content remains language agnostic even though the interface and code will use English.

## Findings

The requested models are documented. The exact identifiers are `asr-1.0` and **`MiniMax-M3.1-Flash`**; the latter differs in capitalization from the name in the original request. MiniMax lists M3.1-Flash as available. No substitute model is needed on documentary evidence. Actual availability to this account remains untested. [ASR reference](https://platform.minimax.cn/docs/api-reference/speech-to-text), [available models](https://platform.minimax.cn/docs/faq/models).

### Speech recognition

| Item | Documented contract |
| --- | --- |
| Request | `POST https://api.minimax.cn/v1/speech_to_text`; Bearer API key; multipart form |
| Fields | Required `model=asr-1.0`, `file`; `response_format=json`, `stream=false` fit a completed recording |
| Result | `text`, `duration` in audio seconds, `trace_id`; verbose output adds timestamped segments and speakers |
| Language | Optional **HTTP header** `language`; omitted or empty enables mixed-language recognition |
| Listed language codes | `zh`, `yue`, `en`, `ja`, `ko`, `th`, `vi`, `id`, `ms`, `fil`, `ar`, `tr`, `fr`, `de`, `es`, `it`, `pt`, `pl`, `ru`, `uk` |
| Audio | WAV, AIFF, FLAC, ALAC/M4A, MP3, AAC, Opus, Ogg; raw PCM is unsupported |
| Limits | At most 500 seconds and 50 MB; excess duration returns HTTP 400, excess size HTTP 413 |

WebM is absent from that format list: Opus codec support alone does not prove acceptance of a WebM container. The basic JSON response does not document a confidence score. `duration` measures the recording, not time spent thinking before recording. [ASR reference](https://platform.minimax.cn/docs/api-reference/speech-to-text).

Language-independent cards therefore do not imply universal ASR language coverage. Short isolated words, proper nouns, code switching, and languages outside this list need later empirical checks; documentation does not establish their accuracy.

### Text grading

MiniMax documents an OpenAI-compatible base URL, `https://api.minimax.cn/v1`, and model `MiniMax-M3.1-Flash`. This is a protocol option; adopting the OpenAI SDK is not required by the wire format. M3.1-Flash always reasons: disabling thinking or requesting `reasoning_effort=none` returns HTTP 400. Supported effort levels are `low`, `medium`, `high`, `xhigh`, `max`; default is `max`. `temperature` is fixed at 1, `top_p` at 0.95, so specifying temperature zero cannot promise deterministic grading. Thinking consumes the output budget; an undersized budget can produce `finish_reason=length` with no final text. [OpenAI compatibility guide](https://platform.minimax.cn/docs/api-reference/text-openai-api).

The concrete route is `POST /v1/chat/completions`, Bearer-authenticated JSON containing `model` and `messages`. The response example separates `choices[0].message.content` from `reasoning_content`, with `finish_reason`, `usage` and `base_resp`. Its schema includes function tools. The rendered reference and its complete Markdown/OpenAPI schema do **not** list `response_format` or a JSON Schema output mode. This is an evidence gap, not proof that every undocumented parameter is rejected. [Chat Completions reference](https://platform.minimax.cn/docs/api-reference/text-chat-openai), [complete reference/schema](https://platform.minimax.cn/docs/api-reference/text-chat-openai.md).

The Responses route also exists, but its published `text.format.type` schema enumerates only `text`; it does not document `json_schema` or `json_object`. Its schema lists only automatic tool selection. A switch to Responses therefore does not establish strict JSON output support. [Responses reference](https://platform.minimax.cn/docs/api-reference/responses-create), [complete reference/schema](https://platform.minimax.cn/docs/api-reference/responses-create.md).

Anthropic-compatible Messages is another protocol with a different endpoint and content-block response. Its API reference describes `tool_choice` as supporting only `auto`; its SDK compatibility guide calls tool choice fully supported. This inconsistency should prevent assuming that a forced grading tool is guaranteed without a focused check. [Messages reference](https://platform.minimax.cn/docs/api-reference/text-chat-anthropic), [Anthropic compatibility guide](https://platform.minimax.cn/docs/api-reference/text-anthropic-api).

No comprehensive natural-language grading accuracy guarantee was found in these references. Prompting for JSON or defining tool arguments can be investigated later, but the application still needs to validate the result and distinguish malformed output, refusal, truncation and provider failure from an incorrect student answer. These are implementation implications, not a selected grading schema.

### Capacity, failures and timeouts

The current rate-limit page says speech recognition requires a topped-up account and lists two concurrent ASR connections for that tier. Audio seconds count toward its per-minute allowance. Text limits are separate. Sharing an environment-variable key does not prove that both services are enabled for the account. [Rate limits](https://platform.minimax.cn/docs/guides/rate-limits).

| Failure category | Relevant documented codes |
| --- | --- |
| Temporary/provider | `1001` timeout, `1002` rate exceeded, `1024` internal error, `2066` processing timeout, `2160` speech service unavailable |
| Configuration/account | `1004` authorization, `1008` balance, `2013` invalid parameters, `2022` missing or inaccessible model |
| Content rejection | `1026` input moderation, `1027` output moderation |

The official error catalogue recommends retrying temporary errors and correcting account/parameter failures. Translating these into bounded retries and user-visible recovery is still a product/integration decision. The inspected references do not define one suitable application timeout or promise a latency bound. [Error catalogue](https://platform.minimax.cn/docs/api-reference/errorcode).

## What the supplied bridge demonstrates

Source: `/home/rlan/Downloads/minimax-asr-bridge`, read on the date above; no execution or credential inspection.

- It translates a host application's chat-style `input_audio` block into MiniMax's multipart ASR request. It is not evidence that ASR itself uses Chat Completions or the standard `/audio/transcriptions` route.
- It uses the documented domestic ASR endpoint and reads only the returned `text`, wrapping it as a chat completion. Its transport timeout is 300 seconds; that is a local choice.
- It forwards an inbound authorization header, with `MINIMAX_API_KEY` as fallback. A web application's server-held credential boundary needs its own implementation; this header-forwarding pattern is not a requirement.
- It labels audio using the supplied format without transcoding it. Renaming a browser WebM recording cannot make it WAV or Ogg.
- Missing `text` currently becomes an empty string. The example therefore does not settle how the application should distinguish silence, an unexpected response and a service failure.

## Consequences for the pending configuration decision

These are questions to settle in the integration ticket, not architecture decisions resolved by this investigation:

1. Configure ASR and LLM model, endpoint and server-side credential source independently. `MINIMAX_API_KEY` can supply both defaults without merging the two protocols.
2. Define the supported protocol family for each replacement. Model names and base URLs alone cannot bridge multipart ASR, chat-style audio, Chat Completions and Messages response shapes.
3. Keep provider parsing and validated grading results outside repetition rules. Neither an empty transcript nor an invalid model response should silently become mastery grade B.
4. Choose an output strategy that works with the documented MiniMax protocol and has an explicit malformed-output path. Strict JSON Schema enforcement remains unverified; another provider's model listing cannot establish MiniMax-origin behavior.
5. Keep user-response timing separate from upload, reasoning and network time. Benchmark any lower reasoning-effort choice before treating it as sufficient grading quality.

## Remaining verification

- Access and billing for both defaults under the actual account.
- Representative multilingual, short-answer transcription and exact/near-meaning grading cases.
- Strict output-mode support if selected, including truncation and refusal behavior.
- Browser-recorded file acceptance, latency, timeout and retry behavior under actual concurrency.

No application code, dependencies, model requests, key inspection or browser recording tests were performed. Documentary existence is verified; working account access and result quality are not.
