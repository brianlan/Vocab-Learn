# Vocabulary field separation acceptance, 2026-11-07

This is the development implementation of step 4 following [PR #1](https://github.com/brianlan/Vocab-Learn/pull/1).
The [field specification](../specs/vocabulary-fields.md) owns behavior; [operations](../operations.md#vocabulary-field-extraction)
describes the reviewed-manifest command. Production was read only for a consistent SQLite snapshot; no production
application deployment, schema migration or content update was performed.

## Implementation

- Migration `0010_structured_vocabulary_details` adds `definition`, `pronunciations` and `synonyms` to Card.
  New Vocabulary preparation saves typed values atomically. Existing `explanation` remains the compatibility source;
  Generic content, old CSV identity and the four-field creation contract remain supported.
- Detail pages and new review backs show teaching information separately. New example inputs and frozen review snapshots
  carry separate metadata; Judge inputs use the extracted definition and visible context. Existing presentations and scored
  history are unchanged.
- `vocabulary_fields export` produces a private plan for unmigrated Vocabulary rows. `apply` checks source digests,
  updates only the three new columns in one transaction, skips matching repeats and refuses different newer details.
  Missing legacy information is not generated or invented, and existing Ready cards stay available.

## Executed checks

The full **119-test suite passed** using the requested Python 3.11 environment and isolated SQLite. Fifteen tests were
added beyond the merged 104-test baseline. They cover actual schema upgrade/reversal, typed completion, exact block
indentation, LF/CRLF, unknown versus explicitly empty synonyms, source-drift rejection with atomic rollback, idempotency,
older provenance, held/frozen history, API shape, escaped rendering and unchanged edits. System and schema-drift checks passed.

Two consistent database snapshots were upgraded and backfilled in isolated local copies:

| Copy | All Card rows | Vocabulary rows split | Original tables compared |
| --- | ---: | ---: | ---: |
| Development before this increment | 1,666 | 1,660 | 17 |
| Production read-only snapshot | 1,654 | 1,648 | 16 |

Every preexisting column in these tables retained its value: source/identity/version fields, memory and scheduling,
Ready/collection/streak, direction/cue state, accounts, examples, jobs, presentations, transcripts and scored history.
The production copy started before migration 0009; its expected new authoring-key permissions/content type were allowed
while all preexisting authentication rows were preserved. No historical learning value was changed.

Both copies passed repeated application, rollback to 0009, upgrade and reapplication. SQLite integrity was `ok`, with no
foreign-key violations. Extracted definitions were verbatim source substrings, readings and synonyms were checked against
the saved source, and no pronunciation/synonym wrapper remained in the extracted definitions. A development-only older
completion lacked its original input; that preliminary rehearsal exposed an export failure. The final adapter falls back
to saved text for that case, with a regression test. The failed run and the successful follow-up were retained.

The live local development database then applied the same reviewed 1,660-card plan. All original fields across its 17
tables matched the before snapshot, and all three new values matched the plan for every card. A second application made
zero updates. This includes all 1,645 cards in the learner's two decks. Their existing source omitted synonyms on 23 cards;
those remain `null`. The two original demo cards also lack pronunciation and synonyms. No old card was regenerated.

Headless desktop Edge exercised optional web creation, mocked structured completion with a nested usage label, separate
detail rendering, typed HTTP status and duplicate creation, an actual Forgot review with structured frozen metadata,
stale-form rejection, unchanged fresh-form saving and deliberate clearing/repreparation. No page errors or horizontal
overflow occurred. The initial browser pass exposed CRLF submission causing reparsing and a trailing carriage return;
the final parser/authoring fixes and LF/CRLF regression passed the repeated browser flow.

The synthetic browser fixtures belong only to the dedicated QA account. Their decks were archived afterward and temporary
API keys revoked. No learner deck gained a synthetic scored review. Development web/worker were rebuilt and restarted.
Private snapshots, manifests, logs, reports, scripts and screenshots are under ignored
`var/exports/vocabulary-fields-20261107/`, with restrictive file permissions.

## Limits and next step

This is content extraction rather than a new dictionary-quality audit. Existing meanings, readings, labels and synonym
claims were copied, not re-evaluated or supplemented. An unlabelled pronunciation keeps an empty variety. Missing
synonyms remain distinguishable from a confirmed absence of close synonyms. The raw source is retained for verification.

Provider responses were mocked for runtime tests; live model quality, physical microphones and other clients' private
DNS/certificate setup were not rechecked. Task profile defaults and prompt text are unchanged. A separately requested
production release must take a fresh cold backup and migrate/backfill the live database in place. These development
databases and reviewed plans must not replace production data.
