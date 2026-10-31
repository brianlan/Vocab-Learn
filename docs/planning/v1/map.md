# Vocab-Learn Browser V1 Decision Map

Labels: wayfinder:map
Status: resolved

Planning archive: the approved decisions and acceptance cases have been consolidated into the [V1 Development Specification](../../specs/v1.md). Use that document for current development and subsequent rule changes; this map preserves decision history.

## Destination

Resolve the product, grading, scheduling, visual, and deployment decisions required before implementing the first browser version. This effort produces decisions, research, and disposable prototypes; production implementation follows planning.

## Notes

- Use [V1 Requirements and Confirmed Boundaries](brief.md) as the input. It records the user's requirements and scope choices without preselecting implementation details.
- All interface copy, code identifiers/comments, and project documentation use English. V1 has no other UI languages. Learning content remains language-independent.
- A styled frontend is part of V1. Evaluate visual direction and card interactions together in the disposable UI prototype.
- See the [domain glossary](../../../CONTEXT.md). Subsequent sessions use wayfinder, grilling, and domain-modeling; research tickets use research, interaction tickets use prototype, and coding follows ponytail.
- Use the local Markdown tracker: each child is a file in the [issues directory](issues/); `Parent` links to this map and `Blocked by` records dependencies. The frontier is the first numbered ticket with `Status: open`, no assignee, and all dependencies `resolved`.
- Claim before working: save `Status: claimed` and `Assignee`. To resolve, append `## Answer`, set `Status: resolved`, and add only a one-line conclusion pointer below.
- Resolve at most one non-research ticket per session. HITL tickets require a real exchange with the user. Suggestions made during charting are not settled implementation choices.
- The vocabulary-card extension is settled alongside authored Generic Cards. The frontier returns to provider contracts, persistence/deployment, and acceptance. Earlier cloze rules remain the Generic baseline except for the explicit learning-unit, grading-copy, and lifecycle updates indexed below.
- Research assets live in `docs/research/`, with a `research/<name>` branch and commit reference. Never read credential values or make paid model calls for this investigation.
- The user cannot see the interactive question widget. Present remaining decision questions in ordinary conversation text, with recommendations and clear choices; do not rely on tool-only controls or treat unseen options as accepted.
- The user authorized incorporating the [reviewer assessment](../../reviews/v1-reviewer-feedback-assessment.md) and the [second reviewer assessment](../../reviews/v1-reviewer-feedback-assessment-round2.md). Completion/interruption, run, generation, worker-capacity, grading and backup contracts are synchronized, preserving the accepted Generic rubric.
- The user confirmed reviewer approval of the final handoff, revision reviewer-follow-up-2. All 19 decision tickets are resolved and the planning destination is reached. The application has not been implemented and runtime acceptance has not been executed; development follows this approved baseline.

## Decisions so far

<!-- Index resolved tickets only. Detailed answers belong to their tickets. -->

- [Verify MiniMax Default Models and API Contracts](issues/01-minimax-contracts.md): Both defaults are documented; strict judging-output guarantees and actual account access remain unverified.
- [Verify Desktop Recording and ASR Audio Paths](issues/02-browser-audio.md): Native recording is available; WebM acceptance and the final upload/conversion path require validation.
- [Verify Regular and Reinforcement Scheduling Options](issues/03-scheduling-evidence.md): Candidate algorithms are documented; feedback mapping and three-success Forgot graduation remain product decisions.
- [Define Cards, Vocabulary, and Per-User Progress](issues/04-learning-unit.md): Progress is per card; cards allow multiple blanks, freeform answers, and one reference answer for AI assessment.
- [Decide the Spoken-Answer Flow and Visual Direction](issues/05-spoken-card-flow.md): Fieldnotes is selected; submission reveals the answer immediately, locks the recording, and updates feedback before proceeding.
- [Define Grading, Five-Level Feedback, and Response Timing](issues/06-grading-feedback.md): Generic feedback is per attempt; C means synonym recall regardless of speed, wrong/missing blanks are B, and the back shows the scheduler's next review estimate.
- [Verify FSRS State Under the Forgot Review Policy](issues/12-fsrs-forgot-contract.md): Default FSRS passed 192 integration cases with preserved memory and due-only Forgot overrides.
- [Decide Normal and Forgot Scheduling and Graduation](issues/07-review-policy.md): Default FSRS schedules Normal; Forgot uses 1-minute resets and two 24-hour steps before its third qualifying success returns to Normal.
- [Verify Safe Markdown Rendering and Cloze Compatibility](issues/13-markdown-cloze-rendering.md): The installed parser passed formatting/cloze safety checks; bold and narrow underline need no new dependency.
- [Define the Minimum Account, Private-Deck, and Statistics Contract](issues/08-private-decks-and-stats.md): Deployer-managed accounts, atomic CSV import, safe Markdown, retained archives/history, and explicit review metrics define the V1 product contract.
- [Evaluate LiteLLM for MiniMax and Provider Compatibility](issues/17-litellm-evidence.md): Chat routing is available, native MiniMax ASR remains a separate integration, and SDK/proxy adoption stays conditional rather than an architecture decision.
- [Define Generic and Vocabulary Card Learning Units](issues/14-generic-and-vocabulary-units.md): Generic supports ordinary questions; Vocabulary shares progress across balanced random directions and stores explicit target/native languages.
- [Define Vocabulary-Direction Grading and Timing](issues/16-vocabulary-grading.md): Complete meaning earns D/E in Recognition, target retrieval earns D/E in Production, and Partial recall preserves one goal-aware feedback/scheduling contract.
- [Define Vocabulary Example Pairs and Rotation](issues/15-vocabulary-example-lifecycle.md): Paired examples freeze in Forgot, qualifying E unlocks later rotation, and only committed A-E results advance the retained balanced direction.
- [Decide Replaceable ASR and Judge Boundaries](issues/09-provider-configuration.md): ASR, Judge, and Generator have independent server-side configurations with MiniMax defaults, validated results, and fixed retries without LiteLLM.
- [Verify Python 3.11 Application and Deployment Options](issues/18-python311-deployment-evidence.md): Django 5.2 is compatible, SQLite needs deliberate short-write protection, and durable work/static serving/backup options are documented without choosing a topology.
- [Decide the Application, Persistence, and Compose Boundaries](issues/10-architecture-and-storage.md): Django/SQLite web-worker Compose uses private LAN HTTPS, short atomic writes, expiring audio, and consistent volume recovery.
- [Finalize Attempt Completion and Interruption Semantics](issues/19-attempt-completion-and-interruption.md): First terminal commit wins; bounded executions, stable presentation clocks, and cancelled capture cleanup prevent late work from changing learning state.
- [Define V1 Acceptance Examples and Implementation Handoff](issues/11-acceptance-and-handoff.md): The reviewer-approved baseline defines 45 acceptance cases, implementation order and evidence requirements, completing planning without claiming runtime acceptance.

## Not yet specified

- No additional in-scope fog is currently identified. The sample-card and prototype questions have graduated into the existing grading, scheduling, provider, and persistence tickets; revisit only if later decisions expose a new question.

## Out of scope

- Implementing the production application, deploying a production service, or publishing a website in this effort: the deliverable is a clear route into development, supported by disposable prototypes.
- Native mobile applications and complete mobile/Safari support: V1 validation prioritizes desktop Chrome and Edge.
- Other UI languages, a UI-language selector, or a translation framework: the system interface is English only; learning-content language fields are separate.
- Public registration operations, payments, social features, and a shared-deck marketplace: V1 serves a small group with private decks.
- User-facing provider selection or personal API-key settings: the deployer manages model configuration.
- Question types beyond the authored Generic and requested vocabulary recognition/production cards, and language-specific curricula: V1 supports these two content sources without a general question-type/plugin framework.
- Same-language Vocabulary definition/paraphrase training: the user chose different-language pairs for the initial [Vocabulary lifecycle](issues/15-vocabulary-example-lifecycle.md); Generic content remains unrestricted.
- Empirical calibration after real use: initial testable rules must be decided now, but later tuning requires an implemented application and observations.
