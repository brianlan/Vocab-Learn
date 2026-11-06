# Production move, 2026-11-06

The existing application at commit `82f94b8` was moved from the former production host
to `rlan@192.168.71.97:/home/rlan/projects/Vocab-Learn` before schema or feature development.
Private HTTPS serves `vocab.home.arpa` on `192.168.71.97:443` and `10.133.109.169:443`.
The destination's unrelated LearnLoop containers and volumes were left in place.

## Data and image verification

The existing cold-backup workflow stopped ingress, drained accepted work, and stopped the writer processes.
It archived application data and both Caddy volumes; temporary audio contained no files.
Runtime provider configuration and the Django secret were transferred privately. Original volumes and a cold backup
were retained on the development host; a second copy of the backup is on production.

The transferred image archive was checksum-verified. The source Docker image store identifies images by config digest,
while the target's containerd store identifies them by OCI manifest digest. The archive's manifest/config blobs were
verified against their hashes, and all root filesystem layers matched before restore. The target restore manifest records
this verified identity translation and retains the unmodified source manifest alongside it. Docker documents the
[containerd image store](https://docs.docker.com/engine/storage/containerd/).

| Image | Source config digest | Target manifest digest |
| --- | --- | --- |
| Application | `sha256:88d24a24d7e9edd4ecce4a6994aafdfa844f28ebdb145145ec0f5aeca4e94c14` | `sha256:e97f828520b05cb4e132fd444ee9d16230e6bb04977db359bb35c3ad8467a3d7` |
| Caddy | `sha256:aac61abc4024c323602ccb9ee38bd68b147601f518626b2a055e06944e01c510` | `sha256:5bf74fd0ea8316ea9934240b594242392bcc0e4f2678d4e06d5c5d3fb9f5932d` |

Every database table's row count and complete-content SHA-256 matched before restore and after startup.
SQLite integrity and foreign-key checks passed. The preserved data includes 2 accounts, 7 decks, 1,654 cards,
1,960 example pairs, 210 presentations, 207 attempts, 198 scored reviews and 1,726 generation jobs.
An existing learner session authenticated and read its private deck without a password reset or a new session.

The Generator remains original D (`lexical-pair-v6-d`), prompt SHA-256
`f25e5e616a91eda36f6e3641521dd2d3d2bf69e1569dfc008415b25ac96a2b83`.
No model request, source rewrite, example refresh or scheduling change was part of this move.

## HTTPS and retained evidence

Both private addresses passed `/health/` checks with hostname verification and the original public CA.
The public root SHA-256 remains `2bb484236da2ad93fbb627f79440d65d98a2561a74a07454b5b550f25ecab430`.
Client hosts entries need the new reachable address; existing certificate trust remains valid.
Browser microphone access and client-side DNS/certificate setup were not tested on other computers.

Private transfer evidence is under `var/exports/production-move-20261106/` on the development machine.
Cold backups are `backups/production-move-20261106-cold/` locally and
`backups/production-move-20261106/cold/` on production. They are ignored by Git and permission-restricted.
The original local production containers are stopped and their restart policy is `no`.
