# Generator prompt evaluation

Decision, 2026-11-04: the experimental v6 prompt was **not promoted**. Production and `learning/providers.py` retain `lexical-pair-v5`. The [candidate text](generator-v6-unapproved.txt) is an experiment, not an approved replacement.

The subsequent [1,645-card review and frozen 31-case benchmark](generator-corpus-benchmark.md) records four additional prompt trials and the separate source-sense review. This page preserves the earlier v6 experiment and its repeatable workflow.

Fixing saved content and improving generation are different outcomes. A Generator improvement must be demonstrated using unedited model output. If a generated sentence or focus needs editorial correction, record that sample as needing work; the corrected text cannot count as a successful generated sample. Explicitly requested content maintenance can be useful, but must remain separately identified.

## Evidence

The 11 actual-card cases that previously needed editorial correction were frozen with the same authored explanations, language fields and old `previous_pair`. One v5 baseline and five candidate prompt drafts each received one request per case. Every draft and result was retained, including format/provider failures. These were development cases, not an unseen accuracy test.

| Prompt | Structurally valid outputs from the 11 actual-card inputs |
| --- | ---: |
| v5 baseline | 10/11 |
| v6 draft 1 | 10/11 |
| v6 draft 2 | 9/11 |
| v6 draft 3 | 9/11 |
| v6 draft 4 | 9/11 |
| v6 draft 5 | 11/11 |

The drafts tried meaning-first planning, preserving word class and distinguishing semantic features, avoiding imitation of defective previous examples, shorter instructions, and format/scope illustrations using unrelated words. They contain no per-target dispatch rules or expected answers for the tested words. Neither generated sentence text nor focus positions were edited for evaluation.

The final candidate and v5 were also run once each against the same [25 public regression fixtures](generator-regression-cases.json), covering the troublesome meanings, single words, filled constructions, English/Spanish targets and Chinese/Spanish native cues. These are selected regression samples, with reviewer criteria frozen before collection, not a population benchmark or a blind review.

| Single-run public-fixture result | v5 | Candidate v6 |
| --- | ---: | ---: |
| Structurally valid | 24/25 | 25/25 |
| Accepted by the agent's content review | 18/25 | 20/25 |
| Needs content work | 6/25 | 5/25 |
| Failed structural validation | 1/25 | 0/25 |

These small, unseeded samples do not demonstrate a reliable improvement in the output distribution. The candidate also introduced clear failures on previously passing cases:

- **monthly:** the source explicitly requests an adjective. V5 produced an adjective modifying a magazine; the candidate used the adverb in “The book club meets monthly on Sunday.”
- **share sth with sb:** v5 kept shared use of a desk. The candidate changed sharing an umbrella into lending it to the other person, changing the action and roles.
- **struggle:** the candidate's native focus still included the separately expressed action of lifting. On the actual-card input, it also changed an attempt into an asserted completed result.
- **deserve:** the public-fixture candidate retained entitlement, but the actual-card candidate again used advice-like 应该. Success on one paraphrased definition did not establish that the original failure was resolved.
- **defeater:** independent participants still appeared inside the native focus. More instructions and unrelated illustrations did not consistently solve the scope issue.

The aggregate acceptance count alone is insufficient for promotion. The candidate remains unapproved because the original problems persist and new meaning/word-class failures appeared. The agent reviews are unblinded qualitative judgments; fluency and compactness notes should not be mistaken for objective grammatical proofs. Natural lexicalized translations and necessary short causative pronouns are allowed, without an arbitrary character limit.

Public raw parsed JSON, validated spans, errors, exact prompts, hashes, provider metadata and individual reviews are in the [v5 results](generator-v5-regression-results.json) and [candidate results](generator-v6-regression-results.json). Actual-card inputs and all development trials remain private under `var/exports/generator-prompt-evaluation-20261104/`. Earlier trials, including an exploratory 25-case run with draft 3, are development evidence, not substituted for the final paired run.

## Repeatable workflow

1. Freeze the input cases and review criteria before changing the prompt. Include the reported failure and controls for previously working words, constructions and language pairs. Use authored meaning, not a hand-corrected answer, as input.
2. Collect a baseline with the same model, endpoint and budgets. Record the exact prompt/version/hash. Input criteria in `check` are reviewer-only and must not be sent to the Generator.
3. Change general prompt instructions or illustrative patterns. Do not introduce per-word rules, special-case expected answers or a database of patches to make the test pass.
4. Collect raw outputs without rewriting them. Keep every declared repetition and failure. A new prompt draft or further repetition is another trial, not a replacement for a failed record.
5. Review exact sense and target word class, idiomatic collocations, native fluency, equivalent assertions, complete but minimal focus meanings, filled construction roles and answer leakage. Structural validity alone never establishes semantic acceptance.
6. Compare failures and regressions as well as totals. Recheck promising candidates with fresh samples before promotion; do not treat one favorable selected run as an accuracy guarantee. If evidence is insufficient, keep the deployed version and retain the candidate and results.

With Generator credentials/profile configured in the process environment, run the current prompt using the Python 3.11 environment:

```sh
python scripts/probe_generation.py --live \
  --cases docs/research/generator-regression-cases.json \
  --repeat 2 --output var/exports/generator-probe.json
```

The probe uses two concurrent calls and performs no database writes. `--live` acknowledges paid calls. Results retain the complete parsed model JSON and every outcome; unreadable JSON/transport failures are recorded as failures, without full HTTP-body capture. Exit zero means collection and structural checks succeeded; the report still says `needs_semantic_review`. It does not automatically retry, edit, score semantics or promote a prompt.

## Verification and limits

- Two new mocked tests verify that invalid raw parsed JSON is retained, reviewer criteria stay out of the model input, all repetitions/failures remain visible, and structural success is not called semantic success.
- Focused tests: 13 passed. Full Django suite: 77 passed. These verify application/probe behavior, not LLM linguistic reliability.
- No schema, scheduler, Judge, ASR or language-validation change. No production deployment or card-content write occurred in this experiment; previously accepted content corrections remain as they were.
- The selected samples and one agent's review do not certify all cards, future random generations or other providers/models. No spoken-answer or microphone test was performed.
