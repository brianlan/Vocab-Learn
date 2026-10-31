# Verify MiniMax Default Models and API Contracts

Id: 01
Parent: [Vocab-Learn Browser V1 Decision Map](../map.md)
Type: research
Labels: wayfinder:research
Mode: AFK
Status: resolved
Assignee: /root/research_minimax
Blocked by: none
Research branch: research/minimax-contracts
Research commit: 7f8f702e3f8802b995049487c1948427057b9c44

## Question

What ASR and judge contracts can official documentation and the local reference establish, and what still requires validation during implementation? Verify the exact identifiers for the requested `asr-1.0` and `Minimax-M3.1-Flash`, endpoints, authentication, request/response shapes, structured judging output, language coverage and limitations, error/timeout semantics, and protocol differences when switching providers.

Use the [requirements and boundaries](../brief.md), the linked official speech documentation, and `/home/rlan/Downloads/minimax-asr-bridge`. Distinguish official facts, sample behavior, and inference. Mark unverified model names or capabilities as unknown rather than silently substituting a model. Do not read credential values or make paid calls.

Produce an English research document with primary-source citations and retain a `research/minimax-contracts` branch reference for the later provider-boundary decision.

## Answer

Resolved on 2026-10-30 by the assigned research agent.

The documentary investigation is complete. Both default model identifiers are officially documented, including the exact spelling `MiniMax-M3.1-Flash`. The ASR and judge use different request protocols; strict schema-enforced judging output is not established by the inspected documentation. See the research asset for the verified contracts, source links, and remaining empirical checks. No provider integration or account capability was validated.

Asset: [English research findings](../../../research/v1-minimax-contracts.md).

Provenance: `research/minimax-contracts` at `7f8f702e3f8802b995049487c1948427057b9c44`. The repository asset matches that research commit. No credentials, paid model calls, or application changes were used.
