# Define the Minimum Account, Private-Deck, and Statistics Contract

Id: 08
Parent: [Vocab-Learn Browser V1 Decision Map](../map.md)
Type: grilling
Labels: wayfinder:grilling
Mode: HITL
Status: resolved
Assignee: /root
Blocked by: 04, 06, 07, 13
Prototype branch: prototype/spoken-card-ui
Prototype commit: d15c55773e6d52feb0fecc7b280213fc222fee90

## Question

Scope note: the settled three-column import and content-edit rules apply to Generic Cards. The new vocabulary source and its generated examples are handled by [Define Generic and Vocabulary Card Learning Units](14-generic-and-vocabulary-units.md) and [Define Vocabulary Example Pairs and Rotation](15-vocabulary-example-lifecycle.md), rather than silently changing existing Generic imports.

What minimum workflows and data rules provide the owner and a few acquaintances with independent accounts, private decks, manual entry, and CSV import? Confirm account creation/recovery, deck/card viewing, editing and deletion, and isolation of content and progress between accounts.

Use the settled learning unit to define minimum CSV fields, blank markers, encoding, preview/error feedback, repeated imports, and partial failure. Establish the effect of editing answers or deleting cards on existing progress and history. System UI, CSV field names, and validation messages are English; question/answer/explanation content remains Unicode and language-independent.

Support multiple blanks and one freeform reference answer per card, including phrases and short sentences. Decide how authors clearly associate the reference with the blanks in manual entry and CSV; do not introduce an accepted-variants list or per-blank learning progress.

Choose only useful V1 statistics from today's due/completed counts, accuracy, feedback distribution, and Forgot counts. Define how Skip, repeated reviews, and failed requests count. This is a product contract rather than a database or chart-library choice; do not add shared decks or public-service operations.

The five feedback levels describe an individual attempt, not a newly inferred lifetime mastery score. Skip and technical failures are excluded from accuracy; do not silently reclassify them as wrong. Next review on the card uses the scheduler's actual next due time, not a second independent estimate.

## Comments

2026-10-31: The user accepted deployer-managed account creation and password resets, with username/password login. Invitation-based or open self-registration is not part of V1.

The user subsequently accepted the proposed CSV contract, edit/reset/archive rules, and basic statistics. They added Markdown rendering for question and explanation, including bold and underline. This applies consistently to manual entry and imports while retaining the single plaintext reference answer. Rendering facts were verified in [Verify Safe Markdown Rendering and Cloze Compatibility](13-markdown-cloze-rendering.md).

An optional follow-up asked whether formatting-only question edits should preserve progress. No reply was received while independent work continued. The agent explicitly adopted preservation for proven inline presentation-only changes as an implementation interpretation of unchanged learning content, rather than recording silence as user approval. That stated default can be revised if the user answers differently.

## Answer

Resolved on 2026-10-31 from the user's acceptance of account, CSV, edit/archive, and statistics recommendations and their added Markdown requirement. The formatting-only interpretation is identified separately below.

### Accounts and ownership

- The deployer creates learner accounts and resets passwords. Learners log in with username/password and can log out; V1 requires no invitation, self-registration, email verification, or email recovery service.
- Each learner's decks, cards, progress, attempts, and statistics are private to that account through the application. Ownership checks apply to detail, mutation, import, and review endpoints as well as lists.
- Authentication primitives, secure sessions, password hashing, and reset/session behavior are provided by the chosen framework in the architecture ticket, not a new custom auth protocol.

### Entry and CSV contract

Support manual card entry/editing and CSV import into a deck selected in the UI. Both use the same validation and rendering rules. A card has a question, one reference answer covering all blanks, and an explanation; all three must be nonblank. Validate emptiness without stripping meaningful Markdown indentation or destroying the original source.

The CSV has exactly the unique headers `question`, `answer`, and `explanation`. Header order may vary. Use UTF-8 and accept an optional BOM, standard quoting, commas/quotes inside fields, and quoted multiline Markdown. Content may use any learning language; headers and system messages remain English.

Validate the entire batch before writing. A malformed header, invalid record shape, or missing field fails the batch with CSV record numbers; preserve all existing data and write none of the new cards. The later [Generic Card decision](14-generic-and-vocabulary-units.md) permits ordinary questions without a cloze marker, superseding the original requirement for at least one gap. Resource limits and transactions are implemented in the architecture, not by truncating content.

Within the selected deck, skip duplicate question/answer learning identities, including repeats inside the batch and existing archived cards. Do not overwrite an existing explanation or silently restore an archive during import. A formatting-only equivalent can be identified by the canonical question/answer key described below. Different decks may contain independent cards with the same text. Report created and skipped counts.

See the ready-to-use [CSV example](../../../examples/cloze-cards.csv) and [authoring notes](../../../examples/README.md).

### Markdown and blanks

- Store original Markdown in question/explanation and render it with the same configured path wherever displayed. The reference answer stays plaintext and is escaped for display.
- Use CommonMark text formatting: bold, emphasis, paragraphs, headings, lists, quotes, code, and safe links. Underline is the documented extension `<u>text</u>`: exact lowercase, attribute-free, paired in one inline block, and properly nested. `__text__` is bold, not underline.
- Questions use `{{blank}}` in parsed prose. Formatting may wrap a blank, including `**{{blank}}**` and `<u>{{blank}}</u>`. Number actual blanks in reading order.
- Escaped markers, code spans/fences, Markdown link destinations/autolinks, and HTML token contents remain literal. Bare unlinked URLs are prose; escape a marker or put that URL in code/autolink syntax when it must stay literal. Explanation never expands cloze markers.
- Arbitrary authored HTML is escaped. Only controlled blank markup and validated underline pairs are emitted by the extension. Unsafe/custom/protocol-relative links are inactive; images display alt text without remote loading. This is a narrow text-formatting profile, not an arbitrary HTML editor.
- Derive rendered HTML, visible text, blank structure, and the semantic comparison from one parsed representation. Give the AI the visible question with explicit numbered blanks, not formatting HTML. Reading-length calculations exclude actual blank tokens and Markdown syntax while retaining literal code/text.

The installed `markdown-it-py==4.0.0` was sufficient; no additional renderer or sanitizer package was required. The configured token/render path must be reused consistently rather than calling its default HTML-enabled renderer elsewhere.

### Editing, history, and archive

Changes to question learning content, blank structure/order, or the plaintext reference answer reset the card to an unseen Normal card with fresh progress. Keep earlier scored reviews with their original assessed content; do not recompute historical grades or let an in-flight result overwrite the new learning state. Explanation and deck-name edits preserve progress.

**Agent-selected formatting interpretation:** proven presentation-only strong/emphasis/validated-underline changes preserve progress when the question's meaningful content, blank structure, and answer remain unchanged. This is an explicitly stated implementation default, not a claimed answer to the optional follow-up. Use the versioned semantic representation proven in the renderer experiment, retaining block structure, code kind/content, and link destinations. Do not equate arbitrary Markdown rewrites merely by stripping tags. Parser/profile upgrades require a deliberate identity migration, not silent progress resets.

Archiving removes a card from active study without deleting content, progress, or history. Restore re-enables the retained schedule; an overdue restored card is due. An archived deck similarly excludes its cards while preserving individual card archive flags. Historical reviews stay in historical statistics, while active-library counts exclude archived cards/decks. Bulk imports do not restore archives automatically.

### Statistics and counting

Use the same user/deck scope for each metric. Count days in the configured display timezone, default Asia/Shanghai, while storing timestamps in UTC. Attribute a review to its recorded submission/Forgot-action time rather than the later model completion time.

| Metric | V1 definition |
| --- | --- |
| Cards reviewed today | Distinct card identities with at least one scored A-E review today. Repeated reviews do not increase this count. |
| Reviews today | All scored A-E reviews today, including Forgot. |
| Recall accuracy | D/E reviews divided by all A-E reviews in the reporting window; show an empty state when the denominator is zero. The later direction-aware grading decision broadens the label to cover complete review goals. |
| Feedback breakdown | A-E counts over scored attempts in the same window, not an inferred lifetime mastery score. |
| Due now | Active ready cards currently eligible by their saved due time, including ready unseen cards eligible immediately; session-only deferral does not erase their due status. Vocabulary sources still preparing their first valid pair are not study-eligible. |
| Forgot cards | Active cards currently in the Forgot collection, including those scheduled for later. |

Skip, Cancel, and Not assessed do not count as scored reviews or enter accuracy. Two graded reviews of one card count as one reviewed card and two reviews. Archiving must not remove earlier valid reviews from historical metrics. A study run with only set-aside due cards is finished for that run, not globally caught up; make that distinction in its empty state. V1 does not add trend-analysis or model-training dashboards.

### Evidence and handoff

[Verify Safe Markdown Rendering and Cloze Compatibility](13-markdown-cloze-rendering.md) records 57 parser/identity/CSV assertion cases. The Markdown preview (local-only reference: `/tmp/vocab-learn-prototype-card-ui/docs/prototypes/card-review-prototype/markdown-preview.html`) and screenshot (local-only reference: `/tmp/vocab-learn-prototype-card-ui/docs/prototypes/card-review-prototype/previews/markdown-preview.png`) were generated from the actual sample CSV and checked through CDP for styling, numbering, field isolation, and seven DOM payload probes. Assets are captured on `prototype/spoken-card-ui` at `d15c55773e6d52feb0fecc7b280213fc222fee90`.

The architecture ticket owns production models, atomic import/edit operations, ownership enforcement, framework sessions, and persistent history. Database transactions, real account flows, and a production importer were not implemented or tested by this decision.
