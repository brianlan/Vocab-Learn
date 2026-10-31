# Define Generic and Vocabulary Card Learning Units

Id: 14
Parent: [Vocab-Learn Browser V1 Decision Map](../map.md)
Type: grilling
Labels: wayfinder:grilling
Mode: HITL
Status: resolved
Assignee: /root
Blocked by: none

## Question

The user distinguishes authored Generic Cards (`question`, `answer`, `explanation`) from a new vocabulary-focused type authored from `word`, `explanation`, and `native_language`. The new type produces target-language recognition questions answered in the native language, and native-language production questions answered with the target expression. Define the smallest domain model and naming that support both without treating new generated sentences as unrelated authored cards.

Clarify whether Generic Cards still require a cloze marker or may also contain an ordinary question. Preserve the existing authored-answer, Markdown, voice-only assessment, and independent-card behavior unless explicitly superseded.

Decide whether recognition and production share one review schedule/Normal-Forgot membership or are independently scheduled learning units under the same vocabulary entry. Use a concrete case where understanding a word is easy but producing it is difficult. Keep generated example revisions distinct from edits to the authored word/meaning; changing an example alone must not accidentally create fresh vocabulary progress.

The existing three proposed vocabulary fields do not always identify the target language (for example, `gift`). Decide whether to add an explicit `target_language` field or obtain an explicit language selection during entry/import. Do not silently restrict vocabulary cards to English or conflate the native answer language with the English-only application interface.

## Comments

2026-10-31: The user explicitly asked to return to flashcard modeling before continuing provider/architecture decisions. Their new requirement includes paired AI-generated examples, type-specific judging, and outcome-driven example retention/replacement. Naming and review ownership are not yet settled. Example lifecycle and grading each have their own dependent decision ticket.

First-round questions asked about ordinary Generic questions, separate versus shared direction progress, and explicit target-language entry. The agent initially recommended separate progress; the user chose shared progress instead.

### Confirmed so far

- Generic Cards allow ordinary questions with no cloze markers as well as questions with one or more blanks. One authored question/answer/explanation remains the source; no vocabulary-derived features are inferred from it.
- A Vocabulary Card is one scheduled learning unit. Recognition and Production are alternative presentations of that same card and update one shared learning cadence. They do not have separate progress records. Keep one Normal/Forgot membership, scheduler state, next due time, and qualifying success streak for the card; record the actual direction on each review.
- Language is explicitly supplied during manual Vocabulary Card creation or through a CSV column, rather than inferred from the word. The user specified initial options Chinese and Spanish; which field this restricts is the only remaining clarification in this ticket.

### Language clarification history

The user called Chinese/Spanish the learning-language choices, while the earlier example used target-language English and native-language Chinese. Asked whether the restriction applies to `target_language` or `native_language`. Do not silently choose either interpretation or remove the English example before that response. The other language must also be explicit so generation, answer-language guidance, and ASR hints have an unambiguous direction.

The user subsequently clarified that Chinese/Spanish are native-language options, target languages initially include English/Spanish, and an explicit target-language field is acceptable if needed. The agent selected explicit entry/storage because word forms can be ambiguous and an explanation need not be in the target language. The user also accepted balanced random direction selection.

### Assessment and follow-up

Shared progress is a coherent product choice for a single vocabulary-level cadence. Its schedule represents a mixture of recognition and production performance. A run of the easier direction can lengthen the interval before the other direction is tested. Recommend a balanced random direction policy (for example, one of each in randomized two-review blocks), but leave that selection and its behavior under Skip/failed attempts to [Define Vocabulary Example Pairs and Rotation](15-vocabulary-example-lifecycle.md). This recommendation does not add separate direction schedules or override the user's choice.

Judge non-cloze Generic Cards as one whole-answer unit against the authored reference; preserve per-blank assessment when actual blanks exist. Vocabulary completeness is goal-specific and belongs to the grading decision. Record the unified schedule as vocabulary-level progress rather than a claim about independently established ability in both directions. No empirical retention calibration has been performed.

## Answer

Resolved on 2026-10-31 through the user's explicit Generic/shared-progress choices, language clarification, acceptance of explicit target-language entry when necessary, and acceptance of balanced random directions.

### Two content sources

- A Generic Card contains authored `question`, `answer`, and `explanation`. Its question may have zero or more real cloze blanks. Zero-blank questions use one whole-answer assessment; actual multi-blank questions retain per-blank aggregation. Do not infer vocabulary entries or generate variants from Generic content.
- A Vocabulary Card contains `word`, `explanation`, `native_language`, and `target_language`. These are the four required source fields for manual entry and the four CSV column names; header order may vary. `word` is the plaintext target expression, and `explanation` is the authored Markdown meaning context. AI-generated examples/references are derived review content, not additional authored CSV columns.
- Distinct card instances keep independent progress even when their word text matches. A Vocabulary Card's generated example revision is not a fresh learning card.

### Explicit languages

The manual creation form requires both language selections. A Vocabulary CSV provides both named columns rather than relying on word/explanation detection. Use English UI names in authoring values:

| Field | Initial choices |
| --- | --- |
| `target_language` | `English`, `Spanish` |
| `native_language` | `Chinese`, `Spanish` |

This is an explicit content-language boundary for Vocabulary Cards, not an additional UI language. Generic content remains language-independent. Separate languages also determine which response-language hint applies to Recognition versus Production. Do not install or call a language-detection model to infer a field the author can supply. Same-language generation behavior and answer-leak prevention belong to the example-lifecycle ticket rather than an implied extra mode.

### One learning unit and balanced directions

Each user's Vocabulary Card has one scheduler state, one Normal/Forgot membership, one next due time, and one qualifying success streak. Recognition and Production update that same progress. Preserve the chosen direction on each interaction; do not create two independently due sibling cards or count the word twice in due/distinct-card metrics.

Use balanced random two-review blocks: each block contains one Recognition and one Production, with a randomized order. This preserves random presentation while ensuring both goals are sampled. Drawing/locking a direction and consuming a block slot on assessed, skipped, or failed interactions are lifecycle details still owned by [Define Vocabulary Example Pairs and Rotation](15-vocabulary-example-lifecycle.md).

The shared schedule represents mixed-direction performance. It is not separate empirical evidence of proficiency in each direction. Grading remains goal-specific, examples remain versioned, and no interval or progress reset is introduced solely by a new example.

### Handoff

See the [Vocabulary CSV example](../../../examples/vocabulary-cards.csv) and [authoring notes](../../../examples/README.md). [Define Vocabulary-Direction Grading and Timing](16-vocabulary-grading.md) owns complete/partial correctness, feedback copy, and timing; [Define Vocabulary Example Pairs and Rotation](15-vocabulary-example-lifecycle.md) owns generation quality, retention, activation, and failure handling. The source and shared-progress choices above supersede the original cloze-only baseline where necessary. No production import, language detection, generation, or review workflow was implemented by this decision.
