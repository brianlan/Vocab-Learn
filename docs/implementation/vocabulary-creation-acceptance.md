# Vocabulary creation acceptance, 2026-11-06

This increment is verified in local development at `http://127.0.0.1:8766`. Production remains at the migration
baseline `82f94b8`, with private HTTPS on both new production addresses. The
[creation specification](../specs/vocabulary-creation.md) owns its behavior and the
[operations guide](../operations.md#vocabulary-http-creation) gives key and request examples.

## Executed checks

- The full 92-test suite passed on an isolated file-backed SQLite database, including authoring, ownership, source
  fencing, retry checkpoints, provider contracts, scheduling, SQLite races and bounded-worker recovery.
- The focused final completion/requeue checks passed. Django system and migration-drift checks passed.
- Real HTTP requests created ten fixtures asynchronously. A repeated request reused its existing card. Queries exposed
  Queued, vocabulary completion, example preparation, Ready and explicit clarification failure.
- A monitoring client encountered an idle keep-alive disconnect. Its original trace was retained; reconnecting and
  resubmitting the original inputs reused all ten existing IDs without creating additional cards or paid preparation.
- Headless desktop Edge exercised login, the optional explanation form, duplicate reuse, an explanation-less CSV,
  Ready content, the AI-definition label and explicit retry. No page errors or horizontal overflow were observed.
- A failed Spanish preparation was explicitly retried after the prompt update. An adjective fixture was regenerated
  through the existing source-edit form. Both completed, with original failed/earlier outputs retained.
- The original 1,654 Card rows and all original learning-table contents matched their pre-feature fingerprints:
  decks, pairs, presentations, attempts, scored reviews and generation jobs. Card table-info metadata was unchanged.
  Only the new authoring-credential table was added to the development schema.
- Both production TLS health checks still passed. Production's Git revision remained `82f94b8`, and it had no
  `learning_authoringkey` table. Development changes were not promoted or copied over live production data.

The initial creation fixtures belong to a dedicated development account. They did not add scored learner reviews.
The temporary HTTP key was revoked after verification. Private credentials, source snapshots, logs, responses and
screenshots are under ignored `var/exports/vocabulary-creation-20261106/` with restrictive permissions.

## Content observations and prompt revision

The first completion prompt produced eight Ready results from nine known-word API cases. The additional unknown
expression correctly required clarification. A browser-created ordinary word also reached Ready. Structural success
was not treated as language-quality approval: the first model falsely rejected Spanish aprovechar and produced an
incorrect consonant symbol in germy's pronunciation. The standard word is attested by [RAE](https://dle.rae.es/aprovechar),
and [Collins](https://www.collinsdictionary.com/dictionary/english/germy) shows the expected initial affricate.

The deployed development completion prompt is `learner-entry-v2`, SHA-256
`9ad691f0d6371b2ad5c36011bc88cc42d7d94de3b88118cef5fc74e82737bd8f`.
Its general revisions put recognizable-word completion first, distinguish ordinary polysemy from genuine uncertainty,
check whole-expression IPA, and strengthen the requirement for sense-related synonyms. There are no per-word rules.
The existing example Generator remains original D; the Judge and ASR contracts remain unchanged.

A selected follow-up made twelve independent completion calls: two repetitions each of an adjective, a Spanish
transitive verb, a Spanish polysemous verb, a unit, an open construction and an unknown string. All ten known-expression
calls returned structurally complete entries; both unknown-string calls required clarification. The earlier false
rejection and incorrect consonant did not recur. All twelve final raw responses, request-field lists and usage metadata
were retained. Request bodies had only model, stream, max_completion_tokens and messages; reasoning_effort and thinking
were omitted. Reasoning text was not retained.

The two subsequent real application preparations also reached Ready: the adjective had a clearer definition and
germ-specific synonyms, and the Spanish verb used its ordinary beneficial-use sense. These were newly generated
results; no generated sentence or definition was manually corrected.

## Limits

This is a small selected development check, not a measured general dictionary-accuracy rate or a controlled causal
comparison of prompts. Near-synonym breadth still varies; the follow-up included broader hygiene adjectives, unit
symbols/paraphrases and some target-language word-class labels despite the English-label instruction. These details
remain candidates for further prompt/provider evaluation, rather than proof that all future content will be correct.
The model's chosen common sense is not established by a frequency corpus. Generated pronunciation and idiomaticity
still need wider linguistic review. Synonyms are supporting study material, never an automatic full-credit whitelist.

Physical microphone behavior and other computers' browser trust/DNS were not retested for this creation increment.
Existing explanations were not split, rewritten or bulk-refreshed. The private HTTP interface is not yet available
on production; that requires a separately requested release.

## PR #1 review corrections

The [review of baseline 053e434](https://github.com/brianlan/Vocab-Learn/pull/1#issuecomment-6688080330)
identified three correctness defects and one nonblocking input-memory improvement. Each was reproduced locally with
mocked provider responses and isolated SQLite; the earlier passing 92-test baseline did not cover these cases.

- Edit forms now carry their loaded source identity, checked inside the authoring transaction. Both blank and supplied
  original inputs are covered after completion and an actual Forgot review: stale saves preserve the entire Card row,
  scored history and generation jobs. Stale trusted Card instances and missing form identities are also rejected;
  a fresh form can still intentionally clear the explanation and queue a new source revision.
- The pronunciation codec now handles nested parentheses, escaped delimiters/backslashes and line breaks in accepted
  structured labels. Existing natural nested labels remain readable, and a valid completion passes its final completeness check.
- Pronunciation and definition occupy separate Markdown blocks. Regressions check headings, lists, blockquotes,
  indented code and fenced code for both supplied and generated definitions, preserving their original block counts.
- The API rejects declared oversize before a stream read, bounds other reads to 64 KiB + 1 byte, handles invalid lengths,
  accepts exactly 64 KiB and rejects one byte more. Stream-counting tests verify the handler does not cache the whole body.

All 104 tests passed on the requested Python 3.11 environment and isolated SQLite, including 12 new regression tests.
The added scenarios failed against the previous implementation before the fixes. Django system and migration-drift
checks passed; no migration was generated.

Headless desktop Edge also exercised the real HTTP form and Forgot paths with mocked provider responses: an edit page
remained open during completion, a second page rendered the nested label and original heading/list and submitted a
scored Forgot review, and the first page then rejected its stale save. Every Card field, scored-review row and generation
job matched the pre-save snapshot. Reloading the edit form and deliberately clearing the explanation created revision 2
and queued preparation as intended. No browser page errors occurred. This synthetic scored review belongs only to a
new, subsequently archived deck on the dedicated development account; no learner's deck was changed.

The local development web and worker use the rebuilt image. Private regression logs, browser script, report and
screenshots are under ignored `var/exports/pr1-review-fixes/`. Provider network calls were mocked for these corrections;
physical microphone and live model behavior were not rechecked.

No Card schema migration, source backfill, model prompt change or production update is part of these corrections.
