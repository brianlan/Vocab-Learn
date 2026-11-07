# Working on Vocab-Learn

This checkout is the development environment. Application code, UI text and project documents use English.

Production runs on `rlan@192.168.71.97` in `/home/rlan/projects/Vocab-Learn`, serving
`vocab.home.arpa` through `192.168.71.97` and `10.133.109.169`.

Develop and test against the local `vocab-learn-dev` Compose project or isolated temporary databases.
Promote application/schema changes to production only after development verification and an explicit user deployment request.
Production owns live learning data; migrate its database in place during an approved release. Never replace it with a development database.

Read [operations](docs/operations.md) when starting environments, changing model settings, backing up or restoring data,
or preparing a release. Read [the domain glossary](CONTEXT.md) and [the specification](docs/specs/v1.md) before changing learning rules.
Read [the creation increment](docs/specs/vocabulary-creation.md) for optional explanations, completion and authoring credentials;
it supersedes V1's required-explanation rule for Vocabulary creation.

Schema and source migrations must preserve existing learning progress, schedules, example revisions and frozen history
unless the user explicitly requested a semantic source change. Keep private snapshots, credentials and backups in ignored directories.
