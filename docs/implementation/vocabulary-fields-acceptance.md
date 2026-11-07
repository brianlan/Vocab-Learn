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

## PR #2 review corrections

The [review of 903fd2e](https://github.com/brianlan/Vocab-Learn/pull/2#issuecomment-6701547333) found two content-preservation
defects not covered by the initial 119 tests. Both were independently reproduced with isolated SQLite and mocked providers.

- Edits now compare the source of each teaching component and retain the stored typed value when its component is
  unchanged. Definition formatting keeps literal `none` and comma-containing synonym phrases intact, including browser
  CRLF submissions. Actual pronunciation/synonym edits still take effect; `none` to `No close synonyms` explicitly yields
  an empty list. Definition Markdown and unrelated metadata are updated independently.
- Footer extraction uses the existing Markdown parser's final top-level paragraph. Code blocks, quotes and lists are
  preserved as definition content. A real footer after code and the legacy inline bracket format still work. Tests cover
  backtick/tilde fences, unfinished fences, indented code, LF/CRLF, code whitespace, rendering, new Judge inputs and real
  manifest export/apply.

The six added regression tests failed on the previous implementation; the corrected full **125-test suite passed** on
Python 3.11. Django system and migration-drift checks passed. No schema, prompt or provider-setting changes were needed.

The previous development and production-read-only snapshots were rechecked locally: all 1,660/1,648 existing Vocabulary
sources produced the same extracted values as 903fd2e. Fresh copies passed migration, backfill, exact preservation of old
fields across 17/16 tables, idempotency, rollback/reapplication, SQLite integrity and foreign-key checks. No existing card
in those snapshots needed a correction for these findings; no live production access or update was required for this follow-up.

Desktop Edge verified the two reported phrases after actual completion and scored Forgot reviews, followed by formatting
edits and typed API queries. Only source/definition formatting changed; all metadata, progress, jobs and frozen history
matched. A third card kept its complete code example through editing/rendering, and a legacy fixture passed real
export/apply and browser rendering without extracting its example's synonyms. No page errors or horizontal overflow.
The temporary QA key was revoked and the fixture decks archived; no learner deck was changed. Development web/worker use
the rebuilt code. Private regression/rehearsal logs, reports and browser artifacts are in ignored `var/exports/pr2-review-fixes/`.

These checks used mocked provider responses. Live model quality and physical microphones were not retested, and no
production deployment or source refresh is part of the corrections.

## PR #2 follow-up boundary corrections

The [follow-up review of adba67f](https://github.com/brianlan/Vocab-Learn/pull/2#issuecomment-6703728294) confirmed the original
reported cases and found two further combinations: completion footers inside unfinished fences, and old provenance
replayed under a changed footer grammar. Both were independently reproduced on temporary SQLite before the fixes.

- Completion now decides which definition is supplied/generated from the actual completion fields. A synonym footer is
  written to compatible source text only when it can be read wholly outside the authored Markdown. Otherwise its values
  remain in the dedicated field/provenance and remain visible through the UI and typed API. Authored blocks are unchanged.
- Explicit empty/whitespace clearing resets definition, pronunciations and synonyms together. Recompletion requests all
  three; a different chosen sense cannot inherit the old synonyms through that clearing path.
- Previously written unsafe layouts use the stored definition and known footer as component boundaries. Formatting,
  metadata edits and clear operations are covered. An ambiguous simultaneous change in an unfinished legacy layout
  returns a validation error with an atomic rollback; closing the fence or editing separately is supported.
- Legacy extraction replays recorded composition boundaries, restores the supplied definition and generated fields,
  supports both historical pronunciation separators, and preserves verified formatting differences. Incompatible or
  malformed optional provenance falls back to validated source extraction; the card is still included in the batch.
  A sole plain `Synonyms:` definition retains its original interpretation.

Seven new tests failed against the prior implementation. The complete **132-test suite passed** on Python 3.11, with
system and schema-drift checks passing. Coverage includes backtick/tilde fences, LF/CRLF, direct and post-format clearing,
actual Forgot history, changing the chosen sense on recompletion, supplied/generated definitions, old unsafe sources,
explicit legacy metadata edits, safe rollback of ambiguous edits, and complete-batch fallback for incompatible records.

The earlier development/production-read-only snapshots were rechecked locally: all 1,660/1,648 sources retained their
extracted values. Fresh local copies again passed backfill, preservation of all preexisting fields across 17/16 tables,
repeat application, rollback/reapplication, integrity and foreign-key checks. No live production access was needed.

Desktop Edge exercised new and historical unfinished-fence cards through actual Forgot, formatting saves and clearing.
New completion into a financial-bank sense requested every teaching field and returned the new synonyms to Generator,
the page and typed API. A real three-record legacy export/apply included an unsafe composition, the old `Synonyms:`
definition and incompatible provenance; each retained its source/progress fields and received the expected teaching values.
Temporary QA decks were archived and the API key revoked. No provider network calls or page errors occurred.

Private logs, reports, snapshots and browser artifacts are under ignored `var/exports/pr2-boundary-fixes/`. Development
web/worker use the rebuilt application. These corrections add no schema, dependency, prompt or provider-setting change.
Live model quality and physical microphones were not retested, and production was not updated.

## PR #2 consecutive-edit and recovery corrections

The [review of c08d6d8](https://github.com/brianlan/Vocab-Learn/pull/2#issuecomment-6704236865) identified two further
preservation failures. Both sequences failed in isolated regression tests before the correction.

- Older unsafe source layouts now recognize the actual saved prefix/footer around the stored definition, rather than
  rebuilding the footer with semicolons. A comma-separated, bracketed or explicitly empty metadata edit can be prepared
  and followed by a definition formatting edit without absorbing the footer into that definition.
- Every new initial preparation records its complete structured input with its compatibility source. Completion saves
  the complete result atomically with the fields, including provided/carried-forward values when no definition request
  was needed. Retry retains this record; the provider's generated-field provenance remains unchanged.
- Export prefers a current-revision complete record only when source identity, definition boundaries and field validation
  pass. Formatting-only definition changes retain current Markdown. Invalid records fall back to historical replay or
  validated source extraction, and another source revision cannot supply the values.

The full **136-test suite passed** on Python 3.11. Django system, migration-drift and whitespace checks passed.
Four added tests cover CSRF-enforced consecutive edits across both fence types and LF/CRLF; complete-record recovery
including unknown/empty/literal/comma-containing synonyms; invalid/stale records; and actual schema rollback/upgrade
followed by a fresh export/apply. The migration regression covers queued, completed, formatted and historical unsafe
revisions, and compares every row/field of every learning model, including scored history. The existing example-failure
retry regression now also verifies retention of the complete record.

Fresh local copies of the retained development and read-only production snapshots again passed extraction of
**1,660/1,648 Vocabulary cards**, preservation of all original values across **17/16 tables**, idempotent application,
actual rollback/upgrade and fresh export/apply. Fresh manifests matched the original plans; SQLite integrity and
foreign-key checks passed. The snapshots were already local; no live production access was needed.

Private failure/test logs, rehearsal scripts, manifests and databases are under ignored `var/exports/pr2-preservation-fixes/`.
These corrections add no schema, dependency, prompt or provider-setting change. Provider outputs were mocked; desktop
browser and physical microphone tests were not repeated. Production was not updated. Older revisions that never recorded
omitted metadata still require their retained reviewed plan or matching backup; the correction cannot invent that data.

## PR #2 parsed definition boundary correction

The [review of 0277fc9](https://github.com/brianlan/Vocab-Learn/pull/2#issuecomment-6704836751) verified the previous
reproductions and reported one remaining P2 issue with two recovery examples. A definition repeated in a pronunciation
label could select the wrong split; an empty definition selected the start of the entire source. Both discarded a valid,
current complete record and lost metadata during fresh recovery. These values were recorded, so the older-unrecorded-data
limitation did not apply.

The source parser now retains the actual definition start after the pronunciation prefix, before footer extraction.
Definition frames match at that component boundary, including zero-length definitions. Recovery and legacy metadata edits
share this boundary logic. Existing source-identity, revision, footer and field-shape validation remains in place.

Both added end-to-end tests failed on 0277fc9 with LF and CRLF. They perform authoring and mocked worker preparation,
actual Forgot reviews, an IPA-only edit or definition-only removal, actual `0010 -> 0009 -> 0010` migrations and fresh
export/apply. The Ready expression keeps `["no, thank you"]` as one synonym; the queued empty-definition card keeps its
pronunciation and `["riverbank", "shore"]`. Every row/field of every learning model matches its pre-rollback snapshot.
The existing migration round-trip assertions were shared by these tests rather than duplicated.

The full **138-test suite passed** on Python 3.11. System, migration-drift and whitespace checks passed. Fresh local copies
of the retained development/read-only-production snapshots again passed **1,660/1,648-card** extraction, preservation of
original values across **17/16 tables**, idempotent application, rollback/upgrade, matching fresh manifests, SQLite integrity
and foreign-key checks. No live production access was needed.

Private logs and rehearsal artifacts are under ignored `var/exports/pr2-definition-boundary-fixes/`. No schema, dependency,
prompt or provider configuration changed. Provider responses were mocked; desktop browser and physical microphone checks
were not repeated, and production was not updated.

## PR #2 checkpoint-backed blank definition recovery

The [review of 90dfddf](https://github.com/brianlan/Vocab-Learn/pull/2#issuecomment-6705124793) confirmed the preceding
reproductions and found a remaining P2 variant: clearing only the definition of an unsafe legacy composition can leave
a plain synonym footer. The current complete record correctly identifies the definition as blank, but source-only parsing
sees a standalone `Synonyms:` paragraph as definition text. Framing or migration validation then rejected the recorded
interpretation and exported the fallback, contaminating the definition and losing synonyms.

- Complete-record recovery now honors its explicit blank definition only after checking source identity and confirming
  that the remaining body is empty or consists entirely of a recognized metadata footer. The saved blank text is preserved
  verbatim; unrelated prose and literal code cannot take that path. Source-only parsing retains its existing grammar.
- Export and apply share the same database-backed validation. When a proposed blank definition conflicts with source-only
  parsing, all proposed fields must match a verified complete record for that card's current source revision. The manifest
  has no bypass flag. Missing, stale, malformed, incompatible or different records cannot authorize clearing a definition.

The new end-to-end migration regression failed on 90dfddf in all **16 combinations**: both historical pronunciation
separators, LF/CRLF, and empty/space/newline/blank-line definitions. It uses actual worker execution with the historical
composer, an actual Forgot review and definition-only edit, actual `0010 -> 0009 -> 0010` migrations, fresh export/apply
and idempotent reapplication. All learning-model rows/fields match their pre-migration snapshots. A second regression
covers nine refusal cases, including a standalone `Synonyms:` definition, real prose, literal code, stale or malformed
records and attempted metadata changes; rejected applies preserve all saved values.

The full **140-test suite passed** on Python 3.11. System, migration-drift and whitespace checks passed. Retained local
development/read-only-production snapshots passed **1,660/1,648-card** extraction, preservation across **17/16 original
tables**, idempotency, rollback/upgrade, matching fresh manifests, SQLite integrity and foreign-key checks. No live
production access was needed.

Private logs and rehearsal artifacts are under ignored `var/exports/pr2-empty-footer-recovery/`. There are no schema,
dependency, prompt or provider-setting changes. Provider responses were mocked; desktop browser and physical microphone
checks were not repeated, and production was not updated.

## PR #2 queued blank-definition metadata edits

The [review of 806df95](https://github.com/brianlan/Vocab-Learn/pull/2#issuecomment-6708731794) verified the recovery fix
and identified a P2 authoring failure before preparation: after clearing a legacy definition, another footer edit could
turn the footer into the definition while retaining the old typed synonyms. The next worker incorrectly considered the
definition supplied. Both new editing/preparation regressions failed on 806df95.

Editing and complete-record recovery now share the interpretation of a known blank, metadata-only source. Authoring
compares the actual metadata fragments, reparses edited fields and preserves untouched typed fields. A new revision's
complete record therefore retains the blank definition and updated metadata, and preparation requests the definition.
Supplying a real definition remains supported. A new standalone plain `Synonyms:` definition keeps its existing meaning
when no retained footer establishes a metadata edit; real definition text followed by an actual footer is never treated
as an entirely metadata-only source.

The full **143-test suite passed** on Python 3.11. System, migration-drift and whitespace checks passed. New coverage uses
worker-created historical layouts, CSRF-enforced edit forms with fresh identities, actual scored Forgot history and
subsequent worker preparation. The **32-sequence** matrix covers both historical separators, LF/CRLF, empty/whitespace
definitions, semicolon/comma synonym edits, explicit empty synonyms and footer removal. It verifies cancellation of the
older queued revision, complete input records, requested definition fields, updated provider/Generator inputs and frozen
history. Additional cases retain literal `none`, comma-containing phrases and empty lists through pronunciation edits and
manual definition entry. A new empty card still accepts a standalone `Synonyms:` definition. Recovery's negative coverage
also rejects clearing an actual `Synonyms:` definition followed by a real metadata footer.

Fresh copies of the retained development/read-only-production snapshots passed **1,660/1,648-card** extraction, preservation
across **17/16 original tables**, idempotency, rollback/upgrade, matching fresh manifests, SQLite integrity and foreign-key
checks. No live production access was needed. Private logs and rehearsal artifacts are under ignored
`var/exports/pr2-queued-metadata-edits/`.

No schema, dependency, prompt or provider-setting changes were required. Provider outputs were mocked; desktop browser
and physical microphone checks were not repeated, and production was not updated.
