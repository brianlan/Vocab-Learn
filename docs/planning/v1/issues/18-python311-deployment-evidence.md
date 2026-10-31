# Verify Python 3.11 Application and Deployment Options

Id: 18
Parent: [Vocab-Learn Browser V1 Decision Map](../map.md)
Type: research
Labels: wayfinder:research
Mode: AFK
Status: resolved
Assignee: /root/research_scheduling
Blocked by: 15, 16
Research branch: research/python311-deployment
Research commit: b188996e8ca5aab49c198f34f3ec5b9a980479c7

## Question

Which minimal Python 3.11 application/deployment options can support the settled small-private-app contracts without inventing authentication or adding an unnecessary frontend/service stack? Compare a maintained Python-3.11-compatible Django release with the already installed FastAPI ecosystem using official documentation and bounded environment inspection.

Verify supported Python versions and relevant support horizon, existing installed package/tool versions without reading secrets, standard account/session/CSRF/admin/migration features, server-rendered templates plus small browser JavaScript, and execution constraints for provider calls outside database transactions. Examine SQLite transaction/locking limitations (including select-for-update behavior), practical optimistic or short-transaction protection, and safe backup of a database in a named Compose volume. Contrast PostgreSQL only where concurrency materially changes the choice. Check FFmpeg availability without installing it. Distinguish one web process, an optional same-image worker, and third-party queues; do not select an architecture or promise a task system from an incompatible framework version.

Capture primary-source facts and explicit recommendations separately in one English note on an isolated `research/python311-deployment` branch, with its commit pointer. No production code, package installation, image pulls, running containers, credential inspection, deployment, paid calls, or edits to the main tracker by the research worker.

## Answer

Resolved on 2026-10-31. The [research note](../../../research/v1-python311-deployment.md) records current official framework/runtime support, local tools/packages, persistence constraints, worker tradeoffs, static serving, and consistent backup options.

Django 5.2 LTS supports Python 3.11 and supplies the account/session/CSRF/admin/migration foundation. The existing FastAPI installation is viable but does not supply that full application stack. Server templates plus focused JavaScript are feasible; WhiteNoise is a small compatible static-file option. These facts do not select the frontend/framework.

SQLite serializes writers, and Django's SQLite select-for-update has no locking effect. Short transactions and conditional updates are material design requirements; ASR/LLM calls must occur outside database writes. The published WAL-reset advisory affects the inspected runtime's version range unless vendor-patched. It concerns WAL specifically: initial rollback-journal mode remains a candidate, with concurrency/runtime checks still required. No local database corruption was observed or asserted.

A same-image application worker can execute persisted intent, but it needs bounded claims/recovery and idempotent commits. Django 6 Tasks is unavailable under the requested interpreter and would still require execution infrastructure. Named volumes are persistent storage, not automatic backups; use consistent snapshots or stop every writer before cold export, and prove restore on a fresh volume.

No packages were installed, images pulled, containers run, credentials inspected, application code written, or providers called. Actual deployment, concurrency, recovery, backup restoration, and final-image/runtime compatibility remain unverified. The main agent owns the architecture decision.

Follow-up evidence for the user's LAN-only HTTPS choice verifies Caddy internal issuance, local name resolution, per-client root-certificate trust, persistent CA storage, and publishing the container port on the host LAN IP. The note cites official Caddy/Compose documentation and the home.arpa reservation. No certificate was generated/imported and no exposure/trust test was run. The updated research commit supersedes the earlier evidence pointer while retaining the same scope.
