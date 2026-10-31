# V1 Requirements and Confirmed Boundaries

Planning archive: use the consolidated [V1 Development Specification](../../specs/v1.md) for current development. This file preserves the original inputs and boundary confirmations.

This is input to the [decision map](map.md), not a finalized implementation specification. Individual decision tickets own the detailed rules and technical choices.

## Requested behavior

- Build a browser-based vocabulary learning application around flash cards and spaced repetition. The original cloze scope now has two requested content sources: authored Generic Cards and vocabulary cards with AI-generated recognition/production examples. The new card decisions own the extension; earlier cloze rules remain the Generic baseline until explicitly changed.
- The front shows a question; the back shows the answer and explanation. Generic Cards allow ordinary questions and zero or more cloze blanks. The front has Skip, Speak, and Forgot actions. All three paths lead to the back.
- Only Speak can produce a correct answer. ASR transcribes the recording, and an AI judge evaluates the answer.
- Generic Cards use authored `question`, `answer`, and `explanation`, with no vocabulary-derived generation features. Vocabulary Cards use authored `word`, `explanation`, `native_language`, and `target_language` and generate aligned examples for Recognition and Production. Both directions update the card's one shared progress record and learning cadence. Balanced random two-review blocks advance on A-E only; Skip/technical failures retain the selected direction.
- Vocabulary examples should use simple surrounding language and the meaning supplied by the author. Initially generate one paired set, retain it until Quick recall, rotate it for later Quick recall, retain it for D/C, and freeze it on A/B/Forgot. The lifecycle ticket records the accepted freeze rule and remaining generation/direction-slot details. Do not reinterpret the request as generating unrelated questions on every display.
- The [Vocabulary lifecycle](issues/15-vocabulary-example-lifecycle.md) settles pair freezing/rotation, scored-only direction advancement, retained Skip/error questions, generation failure behavior, and source-edit/history rules. Same-language definition training is outside initial Vocabulary scope. No production generation or persistent review workflow has been implemented by these decisions.
- The requested default ASR is MiniMax `asr-1.0`. The requested judge model was written as `Minimax-M3.1-Flash`; research must verify the exact official identifier and interface rather than assume spelling or availability.
- Read the default credential from the server environment variable `MINIMAX_API_KEY`. ASR and judging must be independently replaceable without changing review business rules.
- The original five intended feedback meanings were: A explicitly forgot; B substantially incorrect; C slow and only a near-synonym or approximate meaning; D fully correct but slow; E fully correct and fast. The resolved grading ticket supersedes this original wording with the agreed rubric and English labels.
- Later clarification: feedback describes the current attempt, with an approximate Next review time such as 1 min, 1 day, 4 days, or 1 month. The confirmed rubric belongs to [Define Grading, Five-Level Feedback, and Response Timing](issues/06-grading-feedback.md); actual intervals belong to the scheduling decision.
- The later [direction-aware rubric](issues/16-vocabulary-grading.md) gives complete credit to equivalent native meanings in Recognition and target-expression retrieval in Production. C is labelled Partial recall; its Generic eligibility is unchanged. Both directions use the shared schedule and the established rating/collection policy.
- Items start in the Normal Collection. Forgot or a B result moves an item into the Forgot Collection.
- The Normal Collection follows regular spaced repetition. Forgot items return soon on the same day and remain closely scheduled even after success. Three spaced complete-recall successes return the item to Normal; the scheduling ticket records the now-agreed intervals and interruption rules.
- Include question entry, user accounts, flash-card learning, statistics, and spaced repetition.
- Prefer Docker Compose with persistent data in Docker volumes for migration.

## Confirmed development boundaries

- This effort first produces the V1 decision map and development boundaries. Implementation follows planning.
- Generic Card content is language-independent. Vocabulary Cards explicitly select `target_language` from English/Spanish and `native_language` from Chinese/Spanish, both during manual creation and in CSV, with different languages required. No automated language inference is required. A provider's actual ASR language coverage is a capability to investigate, not a promise that the default model supports every language.
- The entire system uses English: interface copy, navigation, feedback, validation and error messages, code identifiers, comments, and project documentation. No additional UI languages, UI-language selector, or translation system in V1. Learning-content language fields are distinct from system/UI language.
- Serve the owner and a few acquaintances, with independent accounts; public-service operations are outside this effort.
- Each user maintains private decks and independent progress.
- Include manual question entry/editing and bulk CSV import; the account/deck/statistics ticket records the agreed schema and failure behavior.
- Question and explanation render Markdown, including bold and documented underline syntax. Preserve source for editing, keep the answer plaintext, and apply safe rendering consistently to imported and manually entered cards.
- The deployer manages three separate server-side configurations: ASR, Judge, and Generator. Judging and generation both default to MiniMax-M3.1-Flash but can independently change endpoint, model, key, and request budgets. There is no user-facing API-key or provider settings screen.
- MiniMax remains the requested default. After the LiteLLM evaluation, the user accepted starting without its SDK or proxy. Independent ASR/LLM configuration remains required; provider-contract and architecture decisions resume now that the card extension is settled.
- The [provider contract](issues/09-provider-configuration.md) now specifies native/OpenAI-compatible ASR adapters and independently configured Judge/Generator profiles using reusable Chat Completions code, server-held keys, task validation, bounded failure handling, and unchanged-attempt retries. Runtime model quality and account access remain unverified.
- Prioritize desktop Chrome and Edge. Full mobile and Safari compatibility is not a V1 acceptance requirement.
- Remote access is LAN-only private HTTPS. Client certificate trust and local name resolution are deployment requirements; public ingress is outside the selected initial deployment mode.
- The [application/deployment contract](issues/10-architecture-and-storage.md) settles Django 5.2/SQLite with same-image web/worker processes, private Caddy HTTPS, named volumes, short atomic writes, and cold backup/restore. Successful audio is deleted; failed/interrupted audio expires after 24 hours while recognized text/results/history remain. No application or deployment has been run during planning.
- Reviewer-driven [completion/interruption rules](issues/19-attempt-completion-and-interruption.md) distinguish retryable failure from terminal unassessed exit, fix race winners, preserve same-presentation timing, and define cancellable microphone waiting. The initial whole-assessment execution budget is 300 seconds including queue time; the final acceptance draft provides fixed cases for these rules and early implementation-phase live checks.
- The authorized second-review refinements add explicit [study-run resume/finish/new-run rules](issues/07-review-policy.md), [durable generation recovery and locked-pair rotation rules](issues/15-vocabulary-example-lifecycle.md), and [bounded worker resource recovery](issues/10-architecture-and-storage.md). Generation has its own initial 300-second whole-execution budget, separate from its 120-second call cap; local cleanup/recovery initially has a 10-second grace. Restore evidence must use the delivered cold-backup procedure. The user confirmed reviewer approval of the [reviewer-follow-up-2 handoff](issues/11-acceptance-and-handoff.md), completing the decision map. Its accepted Generic target-expression rubric is preserved; runtime acceptance is not claimed.
- The frontend must have a deliberate, attractive visual design as part of V1. Establish the visual direction through a styled prototype and carry it consistently through the learning and supporting screens.
- The original cloze learning-unit baseline is recorded in [Define Cards, Vocabulary, and Per-User Progress](issues/04-learning-unit.md); the subsequent two-source, shared-progress, and explicit-language choices belong to [Define Generic and Vocabulary Card Learning Units](issues/14-generic-and-vocabulary-units.md).

## Inspected environment

- The repository initially contained only initialization files, with no application, domain documentation, or configured issue tracker.
- The requested environment, `/home/rlan/anaconda3/envs/mykik_py311`, is available with Python 3.11.13.
- FastAPI, SQLAlchemy, pytest, httpx, uvicorn, and Jinja2 are installed. This is an environment fact, not a selected stack.
- After the FSRS decision, `fsrs==6.3.2` was installed in the requested environment and its default-scheduler integration passed 192 fixed-clock cases. No optimizer dependencies were added. The algorithm and state contract are recorded in the scheduling ticket.
- Docker, Docker Compose, and the Docker daemon are available. Image pulls and application containers have not been tested.
- Browser QA is available through the Chrome DevTools Protocol. The disposable prototype was exercised in headless Chromium with DOM interactions, state assertions, and screenshots; the user accepted this approach. A separate Playwright MCP setup is not required.
- The local reference `/home/rlan/Downloads/minimax-asr-bridge` is readable. Its behavior is not proof of official model availability or supported formats.
- Do not read or display credential values or make paid model calls during this research.

## Inputs

- [MiniMax speech-to-text documentation](https://platform.minimax.cn/docs/api-reference/speech-to-text).
- [Domain glossary](../../../CONTEXT.md).
- Local Markdown tracker conventions (local-only reference: `/home/rlan/.agents/skills/setup-matt-pocock-skills/issue-tracker-local.md`).
