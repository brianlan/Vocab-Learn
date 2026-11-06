# Vocabulary creation and completion

This development increment adds optional Vocabulary explanations and a private, key-authenticated HTTP creation interface.
Production remains on the migration baseline until a separately requested release. Card schema changes and splitting
existing explanations have been deferred at the user's request; existing card content and learning history remain unchanged.

## Creation contract

The web form, CSV importer and HTTP creation route share authoring validation and durable preparation.
Each request targets one existing private deck and supplies `word`, `target_language` and `native_language`.
The supported language combinations remain English/Chinese, English/Spanish and Spanish/Chinese.
`explanation` may be omitted, null or blank for Vocabulary. Generic requirements are unchanged.

Missing teaching details are prepared asynchronously: one useful learner sense, its pronunciation and its close synonyms,
then an aligned bilingual example pair. Supplied definitions establish the intended meaning and are preserved.
The completion task returns structured missing fields; its exact structured output and non-secret profile/prompt provenance
are saved in the preparation record. During this compatibility phase the display content is assembled into the existing
`Card.explanation` field. A later field migration can use the retained structured output without regenerating it.

Definitions use familiar target-language words, an appropriate full-sentence learner-dictionary frame and a clear word
class/construction. They teach one contemporary, broadly useful sense without claiming a statistical frequency ranking.
English pronunciation defaults to US IPA; Spanish defaults to a common standard Spain reading, with explicit labels.
Open constructions retain slots and transcribe their fixed words. Close synonyms belong to the selected sense and target
language; an empty list means no suitable close synonyms. They do not become a complete-recall answer whitelist.
Unknown, unreliable or incomplete expressions require clarification rather than silent correction or invented content.

The new task has independent `DEFINITION_ENDPOINT`, `DEFINITION_MODEL`, `DEFINITION_API_KEY`,
`DEFINITION_TIMEOUT_SECONDS` and `DEFINITION_MAX_COMPLETION_TOKENS` settings. Defaults match the existing MiniMax chat
profile. MiniMax-key fallback remains limited to the MiniMax origin. Requests continue to omit `reasoning_effort` and `thinking`.

## Duplicate and execution behavior

- An omitted/blank explanation skips an existing card with the exact same expression and language pair in that deck,
  including archived, queued or failed cards. It preserves existing content and learning progress.
- A supplied explanation retains content-based identity and permits different intended senses for the same expression.
- The initial input identity remains recorded for the current source revision after completion changes the display text.
  Resubmitting that original input reuses the same card rather than starting another paid preparation.
- Different decks and users remain independent. CSV validates the whole batch before one source/intent transaction;
  network or model failures later do not roll back valid imports.
- Queued work has no execution deadline until claimed. Completion and example calls share the existing bounded execution
  budget. Slow requests run outside transactions. Claim/source/archive checks fence both stage commits.
- A saved definition is a durable checkpoint. If examples fail, explicit retry reuses the definition and its provenance.
  New dispatch settings can affect the retried example call without rewriting the completed definition.
- A card becomes Ready only after valid paired examples are saved. Initial completion adds no scored review, schedule
  update, example rotation, source-version change or learning reset. User source edits keep their existing reset behavior.

The detail page distinguishes vocabulary completion, example preparation and Ready, labels AI-generated definitions,
and exposes the existing explicit retry action. New review snapshots freeze that label with the explanation;
old snapshots retain their original content.

Edit forms carry the source identity displayed when the page was loaded. Saving compares that identity with the current
card inside the authoring transaction; stale forms must reload and cannot overwrite completed preparation or reset newer
learning progress. A source-version check alone does not detect initial completion, which intentionally keeps that version.
A freshly loaded form still permits deliberate source edits and clearing an explanation, with the existing reset behavior.
Trusted Python callers receive the same check against their supplied Card instance's identity by default.

The compatibility formatter keeps pronunciation in its own paragraph, separated from the unchanged definition by a blank
line, so Markdown headings, lists, quotes and code blocks retain their structure. Pronunciation labels escape delimiters,
backslashes and line breaks on write; the parser also accepts existing balanced nested labels. Structured model labels
remain unchanged in provenance.

## API keys and HTTP routes

Deployer commands create, list and revoke keys bound to one active learner. Store only a SHA-256 digest of the random
secret; display the original key only when it is created. Revocation and account deactivation take effect on subsequent
requests. These are application credentials, separate from provider API keys and browser login sessions.
Migration `0009_authoring_key` adds only the credential table; it does not alter Card or rewrite learning data.

Send `Authorization: Bearer <key>` over private HTTPS. Session cookies and query-string keys do not authenticate these
routes. Development accepts its existing loopback HTTP origin. Browser authoring retains session authentication and CSRF.

`POST /api/v1/decks/{deck_id}/vocabulary-cards/` accepts one JSON object containing only the four Vocabulary source fields.
Return 201 for a created card and 200 for a skipped duplicate, including `created`, `id`, `status_url`, current source
fields and preparation state. The source persists immediately; the request does not wait for paid model calls.
`GET /api/v1/vocabulary-cards/{card_id}/` returns the caller's card and its preparation result, including safe error/retry
information. Other users' or unavailable decks/cards return 404. Invalid credentials return 401; invalid source/JSON returns
400, wrong content type 415, oversized requests 413, and unsupported methods 405. A single request is limited to 64 KB.
Oversized declared Content-Length is rejected before reading the stream. Otherwise the handler reads at most 65,537 bytes
and rejects bodies above 65,536 bytes, including requests without a reliable declared length. Invalid or negative declared
lengths return 400. This per-route bound leaves the application's existing upload limits unchanged.

This interface covers creation and queries. Retries/source corrections remain available in the existing private web pages.
The current network exposure remains private; API callers must resolve the hostname and trust its private CA.
