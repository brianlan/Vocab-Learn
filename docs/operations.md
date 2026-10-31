# Running and maintaining Vocab-Learn

The [development specification](specs/v1.md) owns product rules. This guide describes the delivered application, account administration, model settings and cold-backup procedure. See the [acceptance record](implementation/v1-acceptance.md) for executed checks and remaining device-specific verification.

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

The worker is required for ASR, judgment and Vocabulary preparation. Sources and submissions persist if it stops; the web exposes expired work for explicit retry after the 300-second execution budget. A new study run does not silently retry uncertain paid calls.

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

One `migrate` service completes before web/worker start. The same application image runs web and worker. Caddy uses an internal CA, retained in its named volumes. Export only its public root certificate:

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

### Three independent model tasks

`ASR_*`, `JUDGE_*` and `GENERATOR_*` settings are independent. Both LLM defaults are `MiniMax-M3.1-Flash`; ASR defaults to native MiniMax `asr-1.0`. The full settings/defaults are in the specification and `.env.example`.

For another compatible provider, explicitly configure that task's full endpoint URL, model and API key. Select `ASR_PROTOCOL=openai` for the multipart transcription adapter, including its own `ASR_API_KEY`; the native MiniMax language header and transcription language form field are different contracts. The default MiniMax credential is never sent to another origin. Other protocols need an adapter, not a model-name-only change.

Worker profiles are validated at startup, and production WSGI startup checks all three profiles without making paid requests. After changing Compose settings, recreate web/worker so their process environments reflect the changes:

```sh
docker compose up -d --force-recreate web worker
```

Queued/new executions use settings at dispatch; already dispatched calls retain their profile. Frozen questions, recordings, timing, accepted examples and completed grades remain fixed. Retry is explicit; there is no automatic fallback or hidden provider retry. A configuration/account error requires deployer correction and can be closed unassessed.

### Import and daily learning

Create a private deck, then add a Generic/Vocabulary Card or use Import CSV. [Samples and authoring syntax](examples/README.md) describe the exact schemas. Import is limited to 5 MB/10,000 source records and is all-or-nothing on validation failure; duplicates are skipped without overwriting/restoring them. Vocabulary sources become study-ready only after valid paired examples are saved. Refresh their detail page for preparation status; failures expose Retry.

Start a run explicitly. Skip/closed-unassessed defer only within that run. Resume retains those deferrals; a finished run does not automatically repeat them. Explicitly starting a new run permits due deferred cards again. Current Due now counts can remain positive after a run is finished.

Speak records the whole answer. Cancel is available before submission, including pending microphone permission. Stop & check fixes the complete recording before reference reveal. Read the back while processing; a service error permits the same-input Retry or a server-confirmed unassessed exit. Typed transcript changes and replacement recordings after reveal cannot affect the score.

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

## Delivered cold backup and restore

Use the provided host-side Python command from this repository. It uses the deployed application image and Docker CLI; no extra Python packages are required.

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
