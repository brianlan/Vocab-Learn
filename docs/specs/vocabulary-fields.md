# Structured Vocabulary teaching details

This is step 4 following the merged Vocabulary creation increment. It separates teaching information in development;
production promotion remains a separate release. The [creation contract](vocabulary-creation.md) still owns input,
deduplication and preparation rules. Learning, grading and example-rotation rules are unchanged.

## Stored meaning and compatibility source

Vocabulary cards have three dedicated properties:

| Property | Representation | Meaning |
| --- | --- | --- |
| `definition` | Markdown text | The selected sense in simple target-language words, without pronunciation/synonym wrappers. `null` identifies a legacy row awaiting extraction; an empty string is a new card awaiting definition completion. |
| `pronunciations` | List of `{ipa, variety, label}` objects | Available labelled IPA readings. An empty list means pronunciation has not been supplied. Do not infer a variety from an unlabelled legacy reading. |
| `synonyms` | List of strings, or `null` | `null` means not supplied; `[]` means explicitly no suitable close synonyms. Both differ from a populated list. |

The existing `Card.explanation` remains the compatibility source for input identity, old CSV re-imports, the existing
source-edit form and the HTTP `explanation` response key. Backfill does not rewrite it or recompute identity. New writes
persist both that compatible representation and the three structured values atomically. This retention is deliberate;
see [ADR 0006](../adr/0006-structured-vocabulary-details.md).

Creation and CSV inputs retain their current four-field contract. The HTTP response additionally exposes `definition`,
`pronunciations` and `synonyms`, so callers can consume typed teaching information without parsing `explanation`.
Generic cards keep their existing explanation and are excluded from extraction.

## Runtime behavior

`learning.lexical` owns the legacy-text adapter and the structured teaching representation. Authoring extracts supplied
details once. Completion consumes and returns structured values, fills only missing information, and preserves raw
provider fields in provenance. Its checkpoint writes the separate columns before examples can activate a card.
An unchanged edit preserves the saved structured values instead of reparsing their compatibility text.
Edits compare the definition, pronunciation prefix and synonym footer separately. An unchanged source component keeps
its saved typed value, including a literal `none` synonym or a single phrase containing a comma. A definition formatting
edit updates its Markdown without reparsing the other components; an actual metadata edit uses the legacy input grammar.
Browser CRLF submission alone retains the original source text; extraction supports both LF and CRLF block separators
without leaving a carriage return attached to the definition or stripping meaningful code indentation.

Example generation receives the definition and supporting pronunciation/synonym fields separately. New review snapshots
freeze the same separate values. The Judge receives the definition and visible context; new pronunciation/synonym
properties are not forwarded as answer criteria. Synonyms remain study material, never an automatic answer whitelist.
Task profiles and prompt text do not change.

Card detail and new review backs show pronunciation, rendered definition and synonyms separately, with ordinary escaping
for metadata and the existing safe Markdown renderer for definitions. Old snapshots render their original explanation;
they are never retroactively split. Unmigrated cards can still display/study through the legacy-text adapter.

Synonym footers are recognized only in the final top-level Markdown paragraph. Fenced and indented code, quotes and
lists remain definition content, including literal `Synonyms:` or `[synonyms: ...]` examples. A real footer following a
code block is still extracted. The existing inline trailing `[synonyms: ...]` source format remains supported.

## Explicit legacy extraction

Migration `0010_structured_vocabulary_details` only adds the three columns. It performs no model calls or source writes.
The separate operator command exports a private, reviewable plan, then applies that reviewed plan:

```sh
docker compose exec web python manage.py vocabulary_fields export /data/migrations/vocabulary-fields.json
# Copy/read this private manifest and review the extracted fields before applying it.
docker compose exec web python manage.py vocabulary_fields apply /data/migrations/vocabulary-fields.json
```

Export includes all Vocabulary rows whose `definition` is null, including archived and unprepared cards. It never
overwrites an existing file. The file has mode 0600 and its newly created directory has mode 0700. Keep plans and snapshots
out of Git. A completed generation's structured fields are reused when its retained original input reproduces the current
source exactly. Older/incomplete provenance falls back to saved source text; it is not trusted over different content.

Review checks the actual source against its extracted definition, every pronunciation/label and each synonym. Definitions
must be extracted verbatim. Missing source metadata remains missing; extraction neither invents synonyms nor silently turns
unknown data into an explicit empty list. This operation does not audit or change the underlying linguistic claims.

Apply checks a digest of each current source/revision and validates field shapes. Changed/unavailable sources, duplicate
IDs, invalid records and different already-populated details abort the entire transaction. Matching previously applied
records are skipped, so repeating a plan is safe. Updates name only the three new columns: identity, source/progress
versions, Ready, FSRS, due, collection, streak, direction locks, examples, jobs and frozen history remain unchanged.
New reviews between export and apply do not invalidate a plan or lose their progress.

Existing Ready cards remain Ready even when their old source omitted metadata. They are not queued for automatic
completion or example regeneration. New cards still need complete teaching details and paired examples before study.

## Release and rollback

The [operations guide](../operations.md#vocabulary-field-extraction) describes the development procedure. A production
release must take a current cold backup with its matching application image, migrate the live production database,
export/review its own plan and verify preservation before service resumes. A development database or plan must never
replace production data. Migration 0009 from the earlier creation increment is also required if production has not
received that increment yet.

Reversing to 0009 removes only these three properties. The compatibility source and all existing learning/history fields
remain, allowing a subsequent upgrade and reapplication of the same reviewed plan. Use the application image matching the
selected schema; the original cold backup remains the recovery reference.
