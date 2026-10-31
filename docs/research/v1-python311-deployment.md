# Python 3.11 application and deployment evidence

Checked on 2026-10-31 for **Verify Python 3.11 Application and Deployment Options**. This note informs the architecture decision; it does not select a framework, database, or worker topology.

## Runtime and framework facts

Django **5.2 LTS** supports Python 3.11. The official support table currently lists patch **5.2.18**, with extended security/data-loss support through **April 2028**. Django 6.0 requires Python 3.12 or newer; 5.2 is the last series supporting 3.11. Python 3.11 itself is in security-only maintenance with an October 2027 end-of-life, so Django's longer support window does not extend the interpreter's life. Only current Python micro releases are officially supported; the inspected interpreter's patch level was not upgraded. [Django compatibility](https://docs.djangoproject.com/en/5.2/faq/install/#what-python-version-can-i-use-with-django), [Django support table](https://www.djangoproject.com/download/#supported-versions), [6.0 compatibility](https://docs.djangoproject.com/en/6.0/releases/6.0/#python-compatibility), [Python lifecycle](https://devguide.python.org/versions/).

| Capability | Django 5.2 | Existing FastAPI ecosystem |
| --- | --- | --- |
| Accounts and passwords | Included user/account, password hashing, login/logout tools, groups and permissions. | Security helpers exist, but an application's users, password storage, browser login/logout and recovery still need a selected implementation. Installed FastAPI alone is not an account system. |
| Browser sessions | Database-backed sessions by default; the browser holds an identifier rather than the session data. | Starlette offers signed, client-readable cookie sessions; this is not a database-backed session/revocation service. Its implementation imports `itsdangerous`, which is absent locally. |
| CSRF and administration | Built-in CSRF protection and trusted-staff admin. Ordinary users still need ownership-scoped application views. | Cookie authentication needs a deliberate CSRF/session design; administration needs application views or another chosen component. |
| Persistence and migrations | Integrated ORM and schema migrations. | SQLAlchemy is installed; migration management is a separate choice such as Alembic, currently absent. |

Sources: [Django auth and its limits](https://docs.djangoproject.com/en/5.2/topics/auth/), [default sessions](https://docs.djangoproject.com/en/5.2/topics/http/sessions/), [CSRF for forms/AJAX](https://docs.djangoproject.com/en/5.2/howto/csrf/), [admin's intended internal role](https://docs.djangoproject.com/en/5.2/ref/contrib/admin/), [migrations](https://docs.djangoproject.com/en/5.2/topics/migrations/), [FastAPI security helpers](https://fastapi.tiangolo.com/tutorial/security/), [Starlette 0.46.2 session behavior](https://github.com/encode/starlette/blob/0.46.2/docs/middleware.md#sessionmiddleware), [session dependency](https://github.com/encode/starlette/blob/0.46.2/starlette/middleware/sessions.py), [Alembic](https://alembic.sqlalchemy.org/en/latest/).

Neither framework automatically enforces this app's private-card ownership or stale-revision rules. Django's generic auth explicitly does not supply object-level permissions. Built-in admin is for trusted management, not the whole learner UI.

Both options can render HTML on the server: Django provides `render()`; FastAPI documents Starlette/Jinja2 templates and static files. **Inference:** ordinary templates plus focused JavaScript can support recording, submission/status polling, and card transitions without a separate SPA/build stack. This is feasibility, not a tested production frontend. [Django rendering](https://docs.djangoproject.com/en/5.2/topics/http/shortcuts/#render), [FastAPI templates](https://fastapi.tiangolo.com/advanced/templates/).

## Bounded local inspection

Inspected package metadata through `/home/rlan/anaconda3/envs/mykik_py311/bin/python`, without reading environment values or credentials:

| Item | Observed |
| --- | --- |
| Interpreter/database library | Python 3.11.13; its `sqlite3` links SQLite 3.45.3. |
| Installed web/data packages | FastAPI 0.115.14; Starlette 0.46.2; SQLAlchemy 2.0.46; Jinja2 3.1.4; Uvicorn 0.35.0; HTTPX 0.28.1. |
| Relevant packages absent | Django, python-multipart, Alembic, itsdangerous, pwdlib, argon2-cffi, psycopg/psycopg2-binary, Celery, RQ, Redis. |
| Host tools | FFmpeg 4.4.2 at `/usr/bin/ffmpeg`; Docker 29.6.1; Docker Compose v5.3.1. |
| Other PATH commands found | sqlite3, node, npm, gunicorn, psql. Gunicorn/sqlite3 resolve through the base Conda installation, not proof they belong to the specified environment. |

These observations establish availability, not dependency security review, container contents, codec testing, server connectivity, or deployment readiness. A Docker image would need its own pinned dependencies and required FFmpeg binary; a host installation does not put FFmpeg inside it.

## SQLite concurrency and short writes

SQLite permits only one writer at a time. Multiple web requests and a worker can contend even with few human users; WAL improves reader/writer concurrency but does not permit simultaneous writers. [SQLite isolation](https://www.sqlite.org/isolation.html), [WAL concurrency](https://www.sqlite.org/wal.html#concurrency).

Django's SQLite `select_for_update()` **does nothing**. Its default transaction mode is DEFERRED; IMMEDIATE/EXCLUSIVE can be configured. The docs recommend short transactions, discourage request-wide transactions with these stronger modes, and warn that a longer timeout merely waits longer for locking problems. No framework option removes SQLite's writer limit. [Django 5.2 SQLite notes](https://docs.djangoproject.com/en/5.2/ref/databases/#sqlite-notes).

**Integration inference:** a viable small-app design must use brief database work to claim or validate an attempt/job, commit, perform ASR/LLM/FFmpeg work outside the transaction, then briefly validate its revision and commit the result. Apply review outcome, FSRS state, direction advancement and replacement intent together, once. Avoid keeping a write transaction open during network calls.

For optimistic protection, Django's filtered `QuerySet.update()` executes an SQL update and returns the matched-row count. A condition on the expected state/revision can therefore serve as compare-and-swap: one matched row wins; zero requires rereading or rejecting stale work. This is an inference from the API, not a tested adapter. Multirow consistency still needs a short transaction and constraints. Lock failures and transient conflicts need bounded handling outside provider execution; blindly replaying a whole transaction could repeat paid calls. [Update contract](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#update), [short-transaction guidance](https://docs.djangoproject.com/en/5.2/topics/db/transactions/#controlling-transactions-explicitly).

**Patch prerequisite if WAL is chosen:** SQLite reports a WAL-reset corruption bug in versions 3.7.0 through 3.51.2, fixed in 3.51.3 and later, with backports including 3.44.6 and 3.50.7. The local 3.45.3 version falls in that range; a vendor backport was not established. Do not approve this runtime for WAL by version number alone. Select/verify a patched runtime before testing that topology. This is a **WAL-specific** advisory, not evidence of local corruption or a reason to rule out evaluating the initial rollback-journal mode. Rollback mode retains SQLite's write-locking constraints; use a maintained runtime and verify relevant patches in either deployment. [SQLite's published bug and fix](https://www.sqlite.org/wal.html#walresetbug), [default rollback mode](https://www.sqlite.org/isolation.html#isolation_and_concurrency).

PostgreSQL is a material alternative when concurrent web/worker writes, multiple workers, or multiple hosts make SQLite's serialized writes operationally awkward. It supplies real row locks; it also adds a database service, driver, credentials, maintenance and backup procedure. Django 5.2 supports PostgreSQL 14+ with psycopg 3.1.8+; the driver is not installed here. This is a compatibility floor, not a recommendation to deploy an old server version. [PostgreSQL row locks](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS), [Django PostgreSQL requirements](https://docs.djangoproject.com/en/5.2/ref/databases/#postgresql-notes).

## Durable example generation and provider execution

The settled example lifecycle requires preparation/replacement intent to survive interruption, with source/trigger revisions preventing stale activation. A callback held only in web-process memory cannot establish that durability.

| Shape to evaluate | What it buys | Cost/limit |
| --- | --- | --- |
| Web process only | Fewest running processes; synchronous calls are straightforward. | Long provider calls occupy request capacity. In-process background tasks can disappear on process termination unless persisted work is explicitly recovered. A database intent plus only an in-memory wakeup is insufficient. |
| Same-image worker process/service | One application/dependency image, separate command, and restart-independent execution of persisted jobs. | The application must implement bounded claim/recovery behavior, idempotent completion and stale-source checks. Sharing SQLite still means sharing its one-writer constraint. |
| Queue package and broker | Established task transport/execution machinery and independent worker scaling. | Adds dependencies/services and delivery/acknowledgment configuration; it does not remove duplicate-execution or stale-result concerns. |

Starlette background tasks run **in-process after the response**. FastAPI's larger-worker example explicitly adds infrastructure such as a broker. Django 5.2 supports custom management commands, which can host an application-specific worker; that is a mechanism, not a bundled durable job system. [Starlette behavior](https://github.com/encode/starlette/blob/0.46.2/docs/background.md), [FastAPI tradeoff](https://fastapi.tiangolo.com/tutorial/background-tasks/#caveat), [Django management commands](https://docs.djangoproject.com/en/5.2/howto/custom-management-commands/).

Do not assume Django's newer Tasks API solves this on Python 3.11: it was introduced in Django 6.0, and even there Django provides task definition/enqueuing rather than a production worker/backend. `transaction.on_commit()` is useful for post-commit notification but is not durable storage or a transactional guarantee that a remote side effect completed. [Tasks limitations](https://docs.djangoproject.com/en/6.0/topics/tasks/), [on_commit semantics](https://docs.djangoproject.com/en/5.2/topics/db/transactions/#performing-actions-after-commit).

**Integration inference:** persist pending intent with the originating change; claim briefly, execute outside locks, and condition completion on the still-current revision/claim. Reclaiming interrupted work must respect the selected provider retry/budget contract. A broker cannot promise exactly-once paid requests across a crash between remote execution and local completion; Celery itself requires attention to idempotency and acknowledgment policy. [Celery task delivery](https://docs.celeryq.dev/en/stable/userguide/tasks.html).

## Named volumes, backup, and migration

Docker volumes outlive individual containers; they are not automatic backups. If SQLite is chosen, mount its containing directory, including any journals, at a stable path shared only by the required same-host processes. WAL is not supported over a network filesystem. [Docker volume lifecycle](https://docs.docker.com/engine/storage/volumes/), [SQLite WAL filesystem requirement](https://www.sqlite.org/wal.html#overview).

For a running database, Python 3.11's `Connection.backup()` supports concurrent access and uses SQLite's backup facility. Copying only the live `.sqlite3` file is unsafe in WAL mode: committed data can still reside in `-wal`. **Operational inference:** create a completed database-consistent snapshot, export that artifact off the source volume, and test restoration into a fresh volume with the compatible application/migrations. Alternatively, stop every writer/connection cleanly before making a cold copy; do not treat a generic live-volume tar as a database snapshot. [Python backup API](https://docs.python.org/3.11/library/sqlite3.html#sqlite3.Connection.backup), [SQLite online backup](https://www.sqlite.org/backup.html), [persistent WAL state](https://www.sqlite.org/wal.html#the_wal_file).

Migrations belong to versioned application code. Django cautions that many SQLite schema changes involve rebuilding tables; migration and backup/restore behavior need a maintenance-window test. PostgreSQL's `pg_dump` can export consistently during concurrent use, but its own docs distinguish simple export scenarios from a complete production backup strategy. Durable uploaded assets, if required by the provider policy, need matching retention/export treatment. [Migration behavior](https://docs.djangoproject.com/en/5.2/topics/migrations/#sqlite), [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html).

## Decision guidance and remaining checks

These are recommendations for the architecture discussion, not adopted choices:

- Compare total account/session/CSRF/admin/migration implementation rather than counting the already installed FastAPI package as a finished foundation. Django 5.2 is a maintained integrated candidate on the requested interpreter.
- Keep server-rendered pages plus focused JavaScript as a credible minimum. No current requirement establishes a need for a separate frontend framework.
- Evaluate a same-image worker against the explicit durability requirement before accepting only in-process callbacks; add a broker when its operational value exceeds its added services.
- Evaluate initial SQLite rollback-journal mode with short-write/concurrency checks and proven backup/restore; require a verified WAL fix before enabling WAL. Use a maintained runtime and compare PostgreSQL if these constraints dominate the proposed implementation.

Still unverified: actual concurrency/load, crash recovery, provider timeouts, deployment image/runtime versions, any SQLite vendor backport, backup restoration, filesystem permissions and HTTPS/proxy setup. No packages were installed, images pulled, containers run, application code written, model calls made, or production services deployed. The main worktree and tracker were not changed.

## Follow-up: static files without a localhost proxy

WhiteNoise **6.12.0** is a compatible small candidate for a Django 5.2/Python 3.11 WSGI deployment. Its published metadata requires Python >=3.10, lists Django 5.2/Python 3.11, and has no mandatory runtime dependencies; Brotli is an optional extra. The published wheel is approximately 20 kB. This is declared compatibility, not an installed integration test. [Package metadata](https://pypi.org/project/whitenoise/6.12.0/), [exact dependency metadata](https://pypi.org/pypi/whitenoise/6.12.0/json).

The official Django guide uses `STATIC_ROOT`, `collectstatic`, and `WhiteNoiseMiddleware` immediately after `SecurityMiddleware`. It also documents an optional compressed-manifest staticfiles backend for gzip and versioned caching; Brotli is unnecessary for basic serving. Use the application's normal production server: WhiteNoise handles collected static assets without requiring Caddy/nginx or a CDN merely for localhost static-file delivery. It does not replace the application server or provide HTTPS. [WhiteNoise Django guide](https://whitenoise.readthedocs.io/en/stable/django.html), [WSGI scope](https://whitenoise.readthedocs.io/en/stable/#requirements).

**Recommendation to evaluate, not an adopted dependency:** this small, purpose-built package can remove a proxy service and hand-written static-serving/cache logic from the localhost shape. It is for public application assets, not private recordings or user uploads; the guide explicitly excludes uploaded media. If a reverse proxy is already needed, it can instead serve the collected `STATIC_ROOT` directly, at the cost of an asset-copy/shared-mount and routing arrangement. Neither option is required to settle the other deployment choices. [Media limitation](https://whitenoise.readthedocs.io/en/stable/django.html#serving-media-files), [Django static deployment](https://docs.djangoproject.com/en/5.2/howto/static-files/deployment/), [Caddy file serving](https://caddyserver.com/docs/caddyfile/directives/file_server).

WhiteNoise was not installed; `collectstatic`, production static requests and private-upload isolation remain implementation checks.

## Follow-up: selected private LAN HTTPS

The user selected LAN-only private HTTPS. Caddy's `tls internal` uses its own local CA rather than a public issuer; local HTTPS does not use ACME or public DNS validation. This supports a small LAN deployment without public certificate issuance, WAN port forwarding, or a publicly registered application domain. [Internal issuer](https://caddyserver.com/docs/caddyfile/directives/tls#internal), [local HTTPS](https://caddyserver.com/docs/automatic-https#local-https).

Use a deployment-configurable hostname, proposed as **`vocab.home.arpa`** for a home LAN. RFC 8375 reserves `home.arpa.` for non-unique residential home-network use; it does not configure name resolution automatically. Each client must resolve the chosen name to the server's LAN address through local DNS or its hosts configuration. Browse that same hostname: trusting the CA does not fix a mismatched name, and a DNS-name certificate does not automatically cover browsing the raw IP. [RFC 8375](https://www.rfc-editor.org/rfc/rfc8375.html), [TLS identity matching](https://www.rfc-editor.org/rfc/rfc9525.html#section-6).

Every learner's Chrome/Edge client must trust the exported **public root certificate**, using its applicable OS/browser certificate store. Trust installed inside the server/container does not transfer to other devices; Caddy's Docker guide explicitly requires exporting `root.crt` and provisioning host/browser trust. Under its documented Docker layout the certificate is `/data/caddy/pki/authorities/local/root.crt`. Client trust and name resolution must be verified on each actual supported client; accepting a warning is not the deployment contract. [Docker local-HTTPS setup](https://caddyserver.com/docs/running#local-https-with-docker).

Persist Caddy's `/data` in a named volume so its CA keys/certificates survive container replacement; retain `/config` as documented for configuration state. Caddy's data directory is important persistent storage, not disposable cache. Export only `root.crt` for clients, **never `root.key`**; CA private keys stay in protected server storage and protected backups. Losing/replacing the CA requires clients to trust the replacement root. [Caddy data-directory requirements](https://caddyserver.com/docs/conventions#data-directory), [documented Compose volumes](https://caddyserver.com/docs/running#docker-compose), [CA certificate/key storage implementation](https://github.com/caddyserver/caddy/blob/master/modules/caddypki/ca.go).

**Concrete networking inference for the Compose design:** publish Caddy's HTTPS port on the configured host LAN IP using Compose `host_ip`/host-IP port syntax; do not omit it and unintentionally publish on every interface. If HTTP redirect or HTTP/3 ports are enabled, apply the same host binding to those ports. Keep the application port unpublished on the internal Compose network. With ordinary bridge networking, the host LAN IP is not an interface inside the container: host publication performs the LAN restriction, while the container listens on its own interface. Caddy's `bind` directive is the corresponding socket control when running directly on a host; it is not interchangeable with Docker's host-IP publication. Host/router access rules must preserve LAN-only reachability, without opening WAN ports. [Compose host-IP binding](https://docs.docker.com/reference/compose-file/services/#ports), [Caddy bind behavior](https://caddyserver.com/docs/caddyfile/directives/bind), [internal upstream networking](https://caddyserver.com/docs/running#docker-compose).

These are first-party documentation facts and a proposed configuration shape, not a deployment test. No Caddy/container was started, certificate generated/exported/imported, private key read, client trust changed, or network exposure verified. The separate accepted audio-retention policy remains success-delete/failure-at-most-24-hours; TLS/CA persistence does not extend recording retention.
