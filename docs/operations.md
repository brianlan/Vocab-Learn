# Running and maintaining Vocab-Learn

The [development specification](specs/v1.md) owns product rules. This guide describes the delivered application, account administration, model settings and cold-backup procedure. See the [acceptance record](implementation/v1-acceptance.md) for executed checks and remaining device-specific verification.

## Development and production

Since 2026-11-06, production runs on `rlan@192.168.71.97` in `/home/rlan/projects/Vocab-Learn`.
Its private HTTPS listeners are `192.168.71.97:443` and `10.133.109.169:443`, both serving `vocab.home.arpa`.
Clients should resolve that hostname to the address they can reach. The migrated Caddy CA is unchanged;
clients that already trusted it do not need a replacement certificate. Update hosts entries that still point to the old server.

This machine is development. Its private `.env` selects `COMPOSE_FILE=compose.yaml:compose.development.yaml`.
The development override uses project `vocab-learn-dev`, image `vocab-learn:dev`, independent named volumes,
and loopback HTTP at `http://127.0.0.1:8766`. Caddy is inactive in the default development profile.
The same account passwords work in the copied development data; sessions are separate.

```sh
docker compose build web
docker compose up -d
docker compose ps
```

Make and verify application/schema changes in development. A production release is a separate, explicitly requested operation:
back up production, deploy the reviewed commit/image, and migrate the live production database. Development data is never
copied back over live production data. The retired local `vocab-learn` containers and volumes are retained stopped for rollback,
with automatic restart disabled. [Migration evidence](implementation/production-move-20261106.md) records the initial move.

## Local development

Use Python 3.11 and FFmpeg/FFprobe on PATH. The requested environment is `/home/rlan/anaconda3/envs/mykik_py311`.

```sh
conda activate /home/rlan/anaconda3/envs/mykik_py311
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createlearner your_username
python manage.py runserver 127.0.0.1:8766
```

In another terminal with the same Python environment and exported provider settings:

```sh
python manage.py runworker
```

Open `http://127.0.0.1:8766`. Only localhost HTTP is a supported development recording origin. Use private HTTPS for LAN clients. The local server intentionally binds loopback. Port 8000 may already belong to another service.

Local commands read the process environment; they do not automatically source `.env`. The default database and private audio directory are under ignored `var/`. Set `APP_DATA_DIR` and `AUDIO_DIR` for another location. `.env` is used by Compose.

Migration `0007_retain_incomplete_directions` restores cleared direction locks for existing incomplete Vocabulary reviews and Forgot reinforcement. Stop web/worker during upgrade. It restores the latest current-source scored direction against the current active example pair; already held questions remain fixed. It changes only direction index/cue fields, preserving due, memory, collection/streak, counts and history. Reversing this migration retains the restored locks; use a matching cold backup/image for an exact rollback.

The worker is required for ASR, judgment and Vocabulary preparation. Sources and submissions persist if it stops. Generation waits durably in Queued without an execution deadline; claiming starts its 300-second execution budget. The web exposes expired Generating work for explicit retry. Spoken assessments retain their 300-second submission-based deadline, including queue wait. Opening Practice does not silently retry uncertain paid calls.

Migration `0008_example_highlight_positions` adds and backfills the selected positions for saved example pairs. Stop web/worker for the upgrade. Original sentence/highlight strings, progress, schedules, direction locks and frozen history are preserved. Existing failed tasks require explicit Retry; migration does not call a model or retry them. Use a matching cold backup/image for an exact rollback.

Migration `0010_structured_vocabulary_details` adds three Vocabulary teaching properties. It does not rewrite sources
or backfill content automatically. Apply the reviewed [field extraction](#vocabulary-field-extraction) separately.

## Docker Compose and private LAN HTTPS

```sh
cp .env.example .env
```

Configure these deployment values in `.env`:

- `DJANGO_SECRET_KEY`: a new random secret; retain it across restarts/migration. Generate one with Python's `secrets.token_urlsafe(48)`.
- `MINIMAX_API_KEY`: the server-side provider credential, unless each task has its own override. An exported host variable takes precedence over `.env`.
- `LAN_BIND_IP`: this server's private LAN IPv4 address. The example defaults to loopback until you deliberately select the LAN interface.
- `APP_HOSTNAME`: initially `vocab.home.arpa`; every client must resolve it to `LAN_BIND_IP` using local DNS or a hosts entry.
- `APP_ORIGIN`: initially `https://vocab.home.arpa`. Include the port if you change `HTTPS_PORT` from 443.

Keep `.env` private and out of Git. Neither database/audio volumes nor web/worker ports are published. Only the configured IP and HTTPS port are published by Caddy.

```sh
docker compose build
docker compose up -d
docker compose ps
docker compose exec web python manage.py createlearner your_username
```

One `migrate` service completes before web/worker start. The same application image runs web and worker. Caddy uses an internal CA, retained in its named volumes.

To also bind a second private IPv4 address, add both lines to `.env`:

```dotenv
COMPOSE_FILE=compose.yaml:compose.secondary-ip.yaml
SECONDARY_LAN_BIND_IP=10.243.80.19
```

Compose merges the second Caddy port mapping with `LAN_BIND_IP`, keeping both addresses on `HTTPS_PORT`. Both addresses must be configured on the host. Apply with `docker compose config --quiet` and `docker compose up -d --no-deps caddy`. Future Compose commands automatically use both files through `.env`; remove the two lines to return to a single listener. Clients on either network resolve the same `APP_HOSTNAME` to the address they can reach and use the same HTTPS origin and trusted root. The web/worker processes and named data volumes do not need recreation for this change.

Export only Caddy's public root certificate:

```sh
mkdir -p var
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt var/vocab-root.crt
```

On each supported desktop Chrome/Edge client, import that public root into the trust store used by the browser. Configure local name resolution, open the matching hostname, confirm there is no certificate warning, then allow microphone access. Do not export the CA private key or use certificate-warning bypasses. Client trust is a platform-specific setup step, not something the web application can install.

For a server-side TLS/hostname check, replace the example IP with the configured LAN address:

```sh
curl --cacert var/vocab-root.crt --resolve vocab.home.arpa:443:192.168.1.10 https://vocab.home.arpa/health/
```

This verifies the actual CA/hostname chain; it does not establish another client's browser trust or physical microphone behavior. HSTS is limited to one hour on the app hostname. Public preload and unrelated subdomain coverage are deliberately disabled for the private hostname; only those two inapplicable Django deployment warnings are silenced.

### Network configuration

If package downloads need a proxy, pass pip's `--proxy http://127.0.0.1:18080` on the host. A mirror can be selected for the image build using `--build-arg PIP_INDEX_URL=...`.

Inside a container, `127.0.0.1` refers to that container, not the host. Configure reachable server-side `HTTP_PROXY`/`HTTPS_PROXY` values in `.env` if outbound provider calls require them. Keep `NO_PROXY` for localhost and internal services. Caddy deliberately ignores inherited outbound proxy settings for its internal reverse-proxy route; this avoids sending Docker-only `web:8000` through a host proxy.

### Accounts and passwords

Accounts have private decks and progress. There is no public registration or email recovery. The deployer can create or reset learners from the CLI:

```sh
docker compose exec web python manage.py createlearner alice
docker compose exec web python manage.py changepassword alice
docker compose exec web python manage.py createsuperuser
```

The trusted administrator can use `/admin/` for Django user administration. Deck/Card admin views are read-only; learner-facing mutations apply source, history and scheduling rules. Password changes use Django's hashing and session invalidation. For noninteractive account creation, `createlearner NAME --password-env VARIABLE_NAME` reads a password from a named process environment variable without putting its value in command arguments.

### Four independent model tasks

`ASR_*`, `JUDGE_*`, `GENERATOR_*` and `DEFINITION_*` settings are independent. The three LLM defaults are
`MiniMax-M3.1-Flash`; ASR defaults to native MiniMax `asr-1.0`. `DEFINITION_*` controls new Vocabulary teaching-detail
completion, separately from example generation. The full settings/defaults are in `.env.example` and the
[creation increment](specs/vocabulary-creation.md). These new creation capabilities are development-only until a production release.

The current Generator prompt is the original scope-workflow D, tracked as `lexical-pair-v6-d`. It is distinct from the
earlier unpromoted experimental `lexical-pair-v6` and from D2. Judge remains `lexical-meaning-v3`; requests continue to omit
`reasoning_effort`. New preparation and ordinary future rotations use D. Deploying the prompt does not refresh saved pairs,
invalidate held questions or reset learning progress; the explicit refresh command below remains a separate operation.

For another compatible provider, explicitly configure that task's full endpoint URL, model and API key. Select `ASR_PROTOCOL=openai` for the multipart transcription adapter, including its own `ASR_API_KEY`; the native MiniMax language header and transcription language form field are different contracts. The default MiniMax credential is never sent to another origin. Other protocols need an adapter, not a model-name-only change.

Worker profiles are validated at startup, and production WSGI startup checks all four profiles without making paid requests. After changing Compose settings, recreate web/worker so their process environments reflect the changes:

```sh
docker compose up -d --force-recreate web worker
```

Queued/new executions use settings at dispatch; already dispatched calls retain their profile. Frozen questions, recordings, timing, accepted examples and completed grades remain fixed. Retry is explicit; there is no automatic fallback or hidden provider retry. A configuration/account error requires deployer correction and can be closed unassessed.

### Import and daily learning

Create a private deck, then add a Generic/Vocabulary Card or use Import CSV. [Samples and authoring syntax](examples/README.md) describe the exact schemas. Import is limited to 5 MB/10,000 source records and is all-or-nothing on validation failure; duplicates are skipped without overwriting/restoring them. Vocabulary explanations may be omitted; missing definitions, pronunciation and close synonyms prepare before examples. Sources become study-ready only after valid paired examples are saved. Refresh their detail page for preparation status; failures expose Retry. A completed definition survives an example-stage retry.

### Vocabulary field extraction

The [field specification](specs/vocabulary-fields.md) owns the structured representation and preservation guarantees.
These commands target the development project. A production release remains separately authorized and must use its
live database and a current matching cold backup. Do not copy a development database or manifest onto production.

After migration 0010, export a plan, copy it to an ignored private directory for review, then apply that same plan:

```sh
docker compose exec web python manage.py vocabulary_fields export /data/migrations/vocabulary-fields.json
mkdir -m 700 -p var/exports/vocabulary-fields
docker compose cp web:/data/migrations/vocabulary-fields.json var/exports/vocabulary-fields/reviewed.json
# Review the private JSON before running the following command.
docker compose exec -T web python manage.py vocabulary_fields apply /dev/stdin < var/exports/vocabulary-fields/reviewed.json
```

The plan copies available definition, pronunciation and synonym information without model calls. Unknown synonyms stay
`null`; an explicitly empty list stays `[]`. No existing Ready card becomes unprepared because legacy metadata was absent.
Apply is atomic and source-fenced; repeat application skips matching rows, and a changed source requires a freshly
exported/reviewed plan. Standard input lets the command apply the actual reviewed file, including review edits.

Old `Card.explanation` text remains for source editing, input identity and old re-imports. Runtime teaching uses
`definition`, `pronunciations` and `synonyms`; new HTTP responses expose those properties alongside compatible `explanation`.
Each new initial preparation retains its complete structured input/result, including provided metadata omitted from
compatibility text. Export can reuse that record only for the current source revision and matching source boundaries;
retry preserves it. Fresh export after reversing/reapplying 0010 can recover those recorded values. Keep reviewed plans
and matching backups for older revisions whose source and provenance never recorded the missing metadata.
Frozen historical reviews keep their original content. See the [acceptance record](implementation/vocabulary-fields-acceptance.md)
for the executed development and production-copy rehearsal.

### Vocabulary HTTP creation

Create a user-bound application key from the deployer's terminal. Its secret appears once; keep it private.
These commands run in the local development project until this increment is released to production.
Password changes do not rotate application keys; revoke keys explicitly when replacing automation access.

```sh
docker compose exec web python manage.py vocabulary_api_key create torran --name "My script"
docker compose exec web python manage.py vocabulary_api_key list torran
docker compose exec web python manage.py vocabulary_api_key revoke torran --id KEY_ID
```

Put the secret in `VOCABULARY_API_KEY` in the caller's environment and use an existing owned deck ID.
For local development:

```sh
curl --fail-with-body http://127.0.0.1:8766/api/v1/decks/6/vocabulary-cards/ \
  -H "Authorization: Bearer $VOCABULARY_API_KEY" \
  -H 'Content-Type: application/json' \
  --data '{"word":"absorb","target_language":"English","native_language":"Chinese"}'
```

The response returns `id`, `created`, `ready` and `status_url` immediately. GET that status URL with the same header
to query preparation. A repeated explanation-less submission reuses an existing same-expression/language card in that
deck, including an archived card; it does not restore or overwrite it. Supply an explanation to teach a specific other sense.

Python callers can use the already-installed HTTP client:

```python
import os
import httpx

headers = {"Authorization": "Bearer " + os.environ["VOCABULARY_API_KEY"]}
response = httpx.post("http://127.0.0.1:8766/api/v1/decks/6/vocabulary-cards/", headers=headers,
                      json={"word": "absorb", "target_language": "English", "native_language": "Chinese"})
response.raise_for_status()
card = response.json()
print(httpx.get("http://127.0.0.1:8766" + card["status_url"], headers=headers).json())
```

After an approved production release, LAN/private-network callers use `https://vocab.home.arpa` instead and trust its
existing private CA (`curl --cacert PATH_TO_PUBLIC_ROOT`; `httpx` with an SSL context loading that root).
The caller's hosts/DNS maps that hostname to `192.168.71.97` or `10.133.109.169`. A browser login is unnecessary.
An API key authenticates only its owner and never substitutes for another user's ownership checks.

Use **Practice** on the dashboard or **Study this deck** in a private deck. Practice is continuous: the same selected scope restores its current unfinished question, while future questions are selected as needed. There are no study runs to start, finish or resume. The dashboard remembers the latest displayed scope as its default selection.

Due Forgot cards come first, followed by due reviewed Normal cards, then a random eligible unseen card. Reviewed cards retain earliest-due/card-ID order. New examples can become Ready during practice; checking an empty practice page again reevaluates current availability. Current questions and fixed submissions stay unchanged.

Skip and a confirmed unassessed exit set the card aside for 30 minutes across visits and scopes. Its stored FSRS due, memory, collection, streak and review direction remain unchanged. Due now excludes temporarily deferred cards; **Available again** shows when practice can resume. At expiry the card becomes eligible if its scheduler due permits. Repeating the same action does not extend the timer, and stale work cannot postpone newer progress. Already accepted work may still finish, subject to the existing terminal/progress guards.

Speak records the whole answer. Cancel is available before submission, including pending microphone permission. Stop & check fixes the complete recording before reference reveal. Read the back while processing; a service error permits the same-input Retry or a server-confirmed unassessed exit. Typed transcript changes and replacement recordings after reveal cannot affect the score.

Vocabulary backs show the authored target and original explanation. Recognition accepts concise equivalent meanings such as 吸收 for absorb; a correct word does not have to expand every property in its definition. Production still requires the target expression for complete recall. Generated example pairs contain sentences and minimal highlights only, with no separate translated definition.

### Initial D review intervals

For a Normal card, a D whose FSRS result remains in Learning is scheduled a uniformly selected 1, 2 or 3 elapsed days after the original submission. This replaces its minute-scale learning step while preserving FSRS memory/state and the learning step itself. Once D completes Learning and enters Review, its native adaptive interval applies. E remains fully history-adaptive, and Forgot retains its one-minute failure/partial and 24-hour first/second-success rules. The effective due is saved once and reused on processing/result replay. Deploying this policy does not reschedule existing cards or rewrite past reviews.

### Recovering failed initial preparation

Background generation starts its execution clock only when a worker claims it. Queued tasks may wait longer than five minutes or survive a worker restart without failing; each claim receives its full `GENERATION_TIMEOUT_SECONDS` budget. The existing two-slot worker prioritizes queued spoken assessments when a slot becomes available. Running calls are not preempted. Changing concurrency or raising a timeout is not needed to correct queue ageing.

To explicitly recover a learner's failed initial preparation, preview and then requeue:

```sh
docker compose exec web python manage.py requeue_preparation alice --dry-run
docker compose exec web python manage.py requeue_preparation alice
```

This retries only the latest failed initial request for each active, current-version, not-ready source belonging to that learner. It reuses saved sources/jobs, preserves Ready pairs and learning/history, and skips active work, archives, other owners and older revisions. Rerunning does not enqueue duplicates. The command makes no provider calls; the worker processes committed requests independently. Its preview reports requests with prior dispatch metadata. This is an explicit retry, and old records without dispatch metadata do not prove that no remote request was ever issued.

A new model/transport/validation failure remains Failed and exposes Retry; no automatic paid retry is added. Queued and Generating are distinct on card details. Long queues still take time to process; the execution budget limits active work, not total preparation latency.

### Correcting older Ready examples

After upgrading to the lexical-pair prompt, preview and explicitly refresh a learner's existing examples:

```sh
docker compose exec web python manage.py refresh_examples alice --dry-run
docker compose exec web python manage.py refresh_examples alice
```

The second command makes paid Generator calls with at most two concurrent requests, using the independently configured Generator profile. It saves new pair revisions and skips cards whose active pair already uses the current prompt version. Failed calls leave the old pair available; rerun explicitly to retry the remaining cards. Newer source/active-pair changes win over a stale correction result. Not-ready cards, archived sources and other users are excluded; this command does not retry bulk-import preparation failures.

FSRS memory/due, collection, streak, review counts, direction position and historical grades stay intact. An unfinished question or fixed/failed submission in any scope keeps its original pair; the correction takes effect at a later safe presentation boundary. Obsolete rotation work is cancelled. Run this command separately from the cold-backup maintenance window.

## Persistence, audio expiry, and upgrade

Named volumes are `app_data`, `audio_tmp`, `caddy_data` and `caddy_config`. SQLite starts in rollback-journal mode. Do not enable WAL without verifying the runtime/topology. Do not delete volumes during an ordinary restart.

Assessed audio is deleted after the result commits. Failed/interrupted audio expires at original submission +24 hours, including after retries/restarts/restores. Durable transcript/history remain. Access checks enforce expiry; the worker performs physical cleanup at startup and every minute. A powered-off server cleans up after restart. Manual cleanup is available:

```sh
docker compose exec worker python manage.py cleanaudio
```

For an application upgrade, take a cold backup first, stop writers, build/select the intended image, run migrations once, then restart:

```sh
docker compose stop web worker
docker compose build
docker compose run --rm migrate
docker compose up -d web worker caddy
```

Migration `0004_continuous_practice` removes historical run metadata while preserving card progress, presentations, attempts, scored reviews, frozen inputs and deadlines. It also copies presentation scope and the remaining time of recent valid neutral deferrals. Legacy unassessed exits have no separate closure timestamp, so their remaining deferral is reconstructed from the saved submission time. Take a cold backup and retain its exact image before upgrading; this migration is not reversible with `migrate` alone. Roll back using the pre-upgrade backup and matching image. Existing question URLs remain valid; old run bookmarks redirect to the dashboard and old start forms redirect to Practice.

Migration `0005_remove_examplepair_gloss` intentionally removes the generated definition column from example pairs. All other fields and historical presentation/review JSON remain unchanged; old grades are not recalculated. Retain the pre-upgrade cold backup and image to recover that removed column on rollback. Existing Ready sentences need the explicit correction command above to benefit from the new generation prompt.

Migration `0006_generation_execution_budget` adds nullable start times/deadlines and a queue-order index, and clears only legacy queued deadlines. Done, failed and processing records retain their old deadlines and metadata; unknown historical start times stay empty. It does not retry old failures automatically. Take a cold backup and preserve its matching image; rollback uses that artifact rather than reversing the changed queue semantics. Run the explicit recovery command after upgrading, separately from the backup window.

## Delivered cold backup and restore

Run the provided host-side Python command from the production checkout on `192.168.71.97`. It uses the deployed
application image and Docker CLI; no extra Python packages are required. The loopback development profile has no active
Caddy instance and is not the target of this production backup workflow.

```sh
python ops/backup.py create backups/v1-snapshot
```

The procedure stops web/worker/Caddy, archives durable application and Caddy volumes consistently, and restarts only their existing containers that were previously running. Do not run migrations, management-command writers or other instances sharing these volumes during the maintenance window; the script rejects an active migration service. Artifacts have private permissions. The manifest records the actual image ID, applied migration names, renderer/FSRS versions, procedure-source hash and artifact SHA-256 digests. Temporary audio and deployer secrets/environment are excluded. Preserve required secrets separately under operator control. A failed backup does not silently overwrite another snapshot.

Transfer the backup directory and the matching application image/configuration to the new server. Export the built image with `docker image save vocab-learn:v1 -o backups/v1-image.tar` and import it there with `docker image load -i backups/v1-image.tar`; rebuilding from a rolling base can produce a different image ID. Use a fresh Compose project/volumes for restore. No running target or existing volume data is overwritten:

```sh
python ops/backup.py restore backups/v1-snapshot --project vocab-restored
docker compose -p vocab-restored run --rm migrate
docker compose -p vocab-restored up -d web worker caddy
```

Use the exact backup image first; the script rejects an image mismatch. Configure a nonconflicting LAN IP/port if testing a second project on the same server. Restore validates digests and SQLite integrity, retains CA identity, and leaves processes stopped until the operator starts them. Existing empty directory scaffolding is allowed; existing files are not. Required Django/provider secrets are supplied separately, not recovered from the snapshot.

Missing restored audio with no transcript becomes an explicit technical/unassessed path. A durable transcript can support Judge-only Retry while nonterminal. A committed grade replays without another scored review, schedule update, direction slot or rotation. Startup/retry never extends the original audio expiry.

Keep the original hostname/CA relationship and update local DNS/hosts for a new server address. Verify account isolation, card/history/progress continuity, actual TLS, browser microphone access and representative review before calling a migration successful.

## Tests and evidence

```sh
python -m pip install -r requirements-dev.txt
python manage.py test learning.tests --noinput
python manage.py check
python manage.py makemigrations --check --dry-run
docker compose config --quiet
docker compose exec web python manage.py check --deploy
```

Tests use a separate file-backed SQLite test database. They include real competing database connections, whole-stage timeout behavior, and supervisor recovery after a stalled provider or conversion child. Fake outputs test application rules, not linguistic accuracy.

`tests/browser_smoke.py` exercises a dedicated account against a running server using a supplied synthetic WAV and Chromium executable. It creates/archives its own QA deck and makes real configured ASR/Judge/Generator calls. Supply a private JSON access file with `username`, `password` and `url`; do not commit credentials.

```sh
python tests/browser_smoke.py --access-file /private/access.json --audio /private/fixture.wav --chromium /path/to/chrome
```

`scripts/probe_providers.py --live --output /private/results.json` explicitly opts into paid public-fixture model probes. `--task judge|generator|asr` limits the task; `--audio-dir` supplies `English.wav`, `Spanish.wav`, `Chinese.wav`. Human microphone/Edge/client-trust checks remain separate from synthetic/headless evidence.
