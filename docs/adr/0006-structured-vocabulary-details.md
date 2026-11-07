# Preserve source identity while separating Vocabulary teaching details

Vocabulary cards store their learner definition, pronunciation entries and synonyms separately. Retain the existing
`explanation` as the compatibility source for old imports, content identity and edit forms: rewriting it during the split
would change deduplication and could reset learning progress. Rendering, new review snapshots and model tasks use the
structured fields; legacy snapshots remain untouched. Backfill is an explicit, reviewed operation which copies available
information and preserves unknown metadata rather than generating or inventing it.
