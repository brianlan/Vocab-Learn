# Corpus review and small Generator benchmark

Completed 2026-11-05, Asia/Shanghai. This experiment re-read the 1,645-card snapshot captured at 2026-11-04 14:20 UTC and compared unedited outputs from prompt drafts with a fresh production-v5 baseline. It is separate from the [earlier unapproved v6 experiment](generator-prompt-evaluation.md). Authored-sense selection is covered in the [explanation review](explanation-sense-review.md).

Decision: retain production `lexical-pair-v5`. Four new drafts produced development acceptance of 32, 35, 36 and 36 out of forty, against v5's 35/40. None met the predeclared promotion criteria. This does not establish that prompting cannot improve the model; it does not justify deploying these particular drafts.

## Current corpus

All 1,645 cards were Ready. Structural checks found no invalid highlight positions or source-version mismatches in their active/current cue pairs. Every explanation and active bilingual pair was read. Initial suspicions were adjudicated against primary references where needed; the private ledger retains both the initial flag and the revised finding.

| Review disposition | Cards |
| --- | ---: |
| No material issue identified | 1,570 |
| Example improvement identified | 34 |
| Source concern identified | 6 |
| Combined source/example issue | 1 |
| Source scope/precision note | 6 |
| Uncertain; not counted as a demonstrated error | 28 |

Example improvements include natural context, fluency and focus scope; they are not all factual or grammatical errors. Twenty-two are direct definition-echo cases. Qualified scientific/legal learner wording is not automatically rejected because a specialist exception exists. Ordinary lexicalized native compounds and necessary short causative pronouns are allowed, without an arbitrary character limit.

The active corpus contains 1,109 v2, 393 v4, 142 v5 and one v3 pair. Of the 35 example-or-combined flags, 18 came from v2, 15 from v4, and two from v5. A stored historical defect cannot be attributed directly to current v5 generation.

## Frozen benchmark

Thirty-one selected cases were frozen before this round's baseline or candidate calls. Fifteen retain the exact current authored explanation and old pair used for replacement generation; sixteen reuse [synthetic regression fixtures](generator-regression-cases.json). Twenty cases form the development set and eleven form the validation set. Coverage includes exact lexical sense/class, translation assertions, native fluency, compact focus, filled constructions, and English/Spanish target/native combinations.

The benchmark SHA-256 is `7134a26e3eb499b995156f52de9841c32a327b0b72572e4765f3dde395d34f55`.

Each run requests two independent outputs per case with the deployed MiniMax-M3.1-Flash Generator profile, the same inputs, endpoint and budgets, and two concurrent requests. Every declared output and failure is retained. Reviewer criteria and split metadata are not sent to the model. No output editing, best-of selection, quiet retry, source edit or production data write is allowed during evaluation.

Acceptance records structural validity, authored sense/class, equivalent assertions, idiomatic wording, complete but limited learning focus, and independent usage context. A generic useful function can be valid; a wrapper around a full copied definition is not a distinct usage scene. Stylistic uncertainties alone are not semantic failures.

Promotion criteria were recorded before collection: normally improve development acceptance by at least four of forty samples; if the baseline is already at least 36/40, retain acceptance and reduce an identifiable targeted issue. Do not lower structural validity or semantic correctness, do not repeat a new correctness failure on a case passing both baseline samples, do not lower validation acceptance, and confirm a promising candidate with fresh matched development outputs.

## Development evidence

| Run | Accepted unedited outputs | Structural validity |
| --- | ---: | ---: |
| Fresh production v5 | 35/40 | 40/40 |
| Draft A: shared-scene/meaning-first rewrite | 32/40 | 40/40 |
| Draft B: v5 plus unrelated usage/scope examples | 35/40 | 40/40 |
| Draft C: compose the native cue before the target counterpart | 36/40 | 40/40 |
| Draft D: v5 plus a compact spoken-answer focus check | 36/40 | 40/40 |

Draft A repaired the two sampled monthly adjective/adverb failures but introduced expanded single-word focuses and retained definition-like digestion examples. Draft B retained good contextual examples but once selected finished as the focus for marathon, still expanded causative focuses around named participants, and changed the linguistic object child to its translation when discussing that actual word. Neither was promoted.

Draft C kept the sampled authored senses, assertions and usage contexts, but highlighted explanatory clauses for accountable and independent participant/head-noun content elsewhere. Its one additional acceptance over v5 did not meet the predeclared development improvement criterion.

Draft D retained most v5 wording, adding a general distinction between a normal short lexical answer and a full definition, an actual-word/class check, and two unrelated format examples. It still used monthly as an adverb once, lost causation from a native embarrass focus, broadened primitively to simple methods, and restated the digestion definition. Its one additional acceptance also fell short.

The v5 validation baseline accepted 16/22 outputs. Remaining patterns were a winner focus losing the defeating relation, effort losing the difficulty in struggle, an attempted action becoming an achieved result, and unicorn descriptions repeating their defining body features.

All 222 declared requests are retained: 40 v5 development, 160 candidate-development and 22 v5 validation outputs. Every one passed structural validation; each received a separate content review. No draft qualified for candidate validation or fresh matched confirmation, so those extra calls were not run. No draft was deployed and no stored definition/example or learning record was changed by this experiment.

Thirteen provider-contract and probe tests passed. Artifact checks verified fixture identity, every declared repetition, verdict coverage, equal provider budgets, prompt hashes, and all 1,645 review-CSV rows. The running server still reports `lexical-pair-v5` with SHA-256 `e25ee7222b815837a7879f7f487b55bd9ecc77c903fcb26969d37e0cf11f326f`, matching the baseline. These checks establish collection/application consistency, not linguistic correctness.

## Reproduction and limits

The private evidence directory is `var/exports/generator-benchmark-20261104/`: complete snapshot, per-card adjudicated ledger, review CSV, primary-source checks, frozen cases/protocol, exact prompts and every raw parsed result plus its individual review. These artifacts contain private card data and are excluded from Git.

Use `scripts/probe_generation.py --live --cases <frozen-cases.json> --repeat 2 --output <private-result.json>` to collect the current prompt. The exact historical prompts are retained with their results; a comparison must use those texts rather than assuming the current prompt is still v5. Collection is read-only and semantic review is explicit.

This is a small, selected regression benchmark reviewed by one unblinded agent, not a measured population accuracy or certification of all 1,645 sources. Validation cases had prior exposure in the earlier experiment, and the v5 validation baseline was inspected before the final draft; do not describe this as blind, unseen holdout evidence. Fresh matched confirmation guards practical regressions but does not remove these limits.
