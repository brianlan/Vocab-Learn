# Evaluate LiteLLM for MiniMax and Provider Compatibility

Id: 17
Parent: [Vocab-Learn Browser V1 Decision Map](../map.md)
Type: research
Labels: wayfinder:research
Mode: AFK
Status: resolved
Assignee: /root/research_minimax
Blocked by: 01, 02
Research branch: research/litellm-provider-compatibility
Research commit: 67767a7daa05a98fd1d416de4af642ec6208ca9c

## Question

The user retains MiniMax as the default and asks whether a layer such as LiteLLM is worthwhile for future same-protocol provider changes. Verify current primary-source support for the exact `MiniMax-M3.1-Flash` chat model and native MiniMax `asr-1.0` `/v1/speech_to_text` protocol. Distinguish documented provider support, generic OpenAI-compatible configuration, and provider-specific transcription limitations; model-name changes alone cannot bridge multipart path differences.

Compare the minimum direct integrations, an in-process LiteLLM dependency, and its separately deployed proxy only where capabilities/costs matter to this small private application. Consider chat judging plus vocabulary example generation, independent ASR/LLM configuration, structured-result limits, retries/timeouts, Python 3.11 compatibility/dependency footprint, and whether a gateway solves any requested need. Do not install dependencies, make live model calls, read credentials, deploy services, or choose the final architecture.

Use a background research worker and the research skill; save an English primary-source note on an isolated `research/litellm-provider-compatibility` branch with its commit pointer. The main agent owns tracker integration. Clearly separate verified facts, inferred recommendations, and untested behavior.

## Answer

Resolved on 2026-10-31. The [primary-source research note](../../../research/v1-litellm-provider-compatibility.md) compares direct configured clients, an in-process SDK, and a separate proxy without selecting a dependency.

LiteLLM supports MiniMax chat routing and configurable OpenAI-compatible chat endpoints. The exact first-party M3.1-Flash catalogue metadata is absent in the inspected snapshot; this is not proof of incompatibility or a reason to change the default model. Native MiniMax ASR uses a different endpoint/parameter contract and is not covered by the inspected transcription dispatch. Neither the generic route nor deploying the proxy establishes that translation.

Published LiteLLM/core metadata permits Python 3.11. The SDK-only `litellm-core` omits proxy/dashboard/CLI assets and several heavy requirements, but remains an additional dependency graph. No installation footprint was measured. Structured results, timeouts, retries, and exactly-once review storage still have application-owned boundaries.

The conditional recommendation is direct clients for truly compatible endpoints, consideration of pinned in-process core for concrete cross-protocol needs, and a proxy only for an actual shared-gateway need. Provider/architecture decisions remain paused at the user's request. Source snapshot and published-version distinctions are recorded in the note. No package installation, model call, credential read, or deployment was performed; exact domestic model behavior remains untested.
