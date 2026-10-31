# Define Vocabulary Example Pairs and Rotation

Id: 15
Parent: [Vocab-Learn Browser V1 Decision Map](../map.md)
Type: grilling
Labels: wayfinder:grilling
Mode: HITL
Status: resolved
Assignee: /root
Blocked by: 14, 16

## Question

How do vocabulary entries obtain and retain a matched target-language/native-language example pair and its references, and when does a new pair become eligible? The user's intended starting rule is one generated pair at creation; Quick recall unlocks new examples for the next review, Correct recall/Meaning recalled keep the examples, and A/B/Forgot freeze the examples during Forgot reinforcement. The user has chosen one shared progress/schedule per Vocabulary Card; directions are alternative presentations rather than separately scheduled items.

Settle whether rotation requires one or both directions to achieve Quick recall, whether a pending new example can activate while the relevant item is in Forgot, what happens after the third non-E success graduates an item, and what Skip/technical failures do. A generation job must not change an already displayed/submitted question. Repeating a future item early must not become a shortcut around spaced learning.

The user accepted balanced random two-review blocks: one Recognition and one Production per block, with shuffled order. Define when the draw becomes fixed, what Skip/technical failure does to a block slot, and how to prevent reloading or retrying until the easier direction appears. Do not reopen the chosen shared progress or create two sibling review items. A new scheduled review still follows the saved due time; immediate opposite-direction practice cannot count as another spaced success.

Define generation inputs and quality constraints: one intended sense anchored in the authored explanation, the target expression visibly identified in each counterpart, simple surrounding language, natural aligned meaning, a defensible native reference/gloss, and no answer leakage on the front. Phonetics/synonym lists are supporting content rather than automatic alternative answers. Decide the smallest create/import/generation-failure and regeneration experience, without blocking answer reveal on a new model call or silently grading a newly generated reference.

Production prompts must not reveal the target expression through a card title, source explanation, or the other language's example before submission. The back may show the aligned pair and the authored explanation. Keep this separate from the selected English-only UI language.

The initial enums overlap on Spanish. Decide how entry/generation handles a same-language Spanish/Spanish selection: reject it for the initial bilingual mode or explicitly define a paraphrase-based task. Do not silently expose the required production answer in a same-language translation and count it as retrieval. This question is separate from the already settled target/native field choices.

Preserve exact rendered prompt, direction, example revision, reference/rubric, and authored meaning for each assessed attempt. Decide the effect of real word/meaning/language edits on generated examples and progress; formatting-only edits and model/prompt upgrades must not silently rewrite existing learning content. Source entry duplication, archive/restore, and statistics must follow the settled learning-unit definition.

## Comments

2026-10-31: Claimed after the direction-aware grading decision resolved. Sent three independent lifecycle choices: keep the example pair frozen throughout Forgot and only apply an E-triggered replacement after graduation; advance a balanced direction slot only on a scored A-E interaction rather than Skip/technical failure; and keep initial vocabulary mode bilingual rather than adding same-language Spanish paraphrase training. Recommendations are awaiting the user's response, not accepted lifecycle rules.

The proposed freeze rule is specific: Normal E unlocks a replacement pair for the next review; the first/second Forgot E do not unlock replacement while reinforcing; a third-success E graduates and unlocks replacement, while a third-success D graduates with the same pair until a later E. Current displayed/submitted content remains fixed throughout. Initial generation failures, rotation failures, source-edit behavior, and transaction details still need a concrete contract rather than a production worker implementation.

The user accepted Q1 (the full Forgot-freeze/graduation rule above) and Q3 (different-language vocabulary mode only). Enforce `target_language != native_language` in manual entry and CSV validation; initial valid pairs are English/Chinese, English/Spanish, and Spanish/Chinese. Same-language definition/paraphrase training is outside the initial Vocabulary workflow; this does not constrain Generic content.

Q2 is not resolved: the user asked what direction advancement means. Explained that Recognition and Production are the two ways to test the same card; a scored A-E result, including wrong answers or the explicit Forgot action, would consume one slot in the balanced order. Skip or technical failure would retain that slot for the card's next eligible appearance. A retry uses the original question/direction/recording, and direction selection does not create a separate schedule. Asked the narrower product choice: after Skip, retain this way of testing until a scored result, or advance the balanced order anyway. Await that answer rather than treating the clarification request as acceptance.

After that explanation, the user explicitly accepted the recommendation. All three lifecycle choices are now confirmed. Generation-failure and source-edit behavior below are agent-selected operational defaults that make the requested workflow concrete; they are distinguished from the three choices directly answered by the user. No application data has been changed.

## Answer

Resolved on 2026-10-31 through acceptance of the freeze rule, different-language mode, and direction-slot rule after clarification. This decision completes the vocabulary-card extension and returns the frontier to provider contracts.

### Source creation and first preparation

Create Vocabulary Cards from the four source fields settled in [Define Generic and Vocabulary Card Learning Units](14-generic-and-vocabulary-units.md). Require different target/native languages. The initial combinations are English/Chinese, English/Spanish, and Spanish/Chinese. Reject Spanish/Spanish at manual-entry/CSV validation; Generic content remains language-independent.

Apply the established all-or-nothing CSV validation to the entire source batch before writing, including headers, required fields, and language combinations. Within the selected deck, skip duplicates against the batch and existing/archived sources without overwriting or restoring them. A Vocabulary source identity includes its exact target expression, canonical authored explanation, and both languages. Different explanations/senses or language pairs can therefore be independent cards. Generated examples never become part of duplicate identity.

The operational default is to persist valid sources before making generation calls. Automatically initiate preparation of one aligned example pair per new card. Until a valid pair exists, show Preparing examples and keep the card out of the study queue and Due now count. If preparation fails, retain the source with a visible retry action and a useful English error. A provider failure does not roll back a successful source import, silently delete a card, count as a learner failure, or put it in Forgot. Import feedback distinguishes created/skipped sources from examples still preparing or needing retry. This does not select a worker, queue, or transport implementation.

### Durable generation and recovery

Persist each valid new source and its initial preparation intent in the same database transaction; the source's persisted Preparing state may itself be that discoverable intent. Record the initial execution request time/deadline in that commit too. A post-commit in-memory notification is only a wakeup hint, not the authoritative work record. Failed source batches leave no runnable generation intent or provider call. A qualifying E records replacement intent and its initial execution request/deadline in the same transaction as its learning result.

Each intent identifies the source revision and, for rotation, the authorizing scored event/current rotation identity. Each explicit execution has its own claim, dispatch configuration snapshot, deadline and optional saved result. Use `GENERATION_TIMEOUT_SECONDS`, initially 300 seconds from the execution request, including unclaimed queue time, Generator call and validation/save. The existing `GENERATOR_TIMEOUT_SECONDS` remains a separate 120-second call cap, bounded by the remaining execution budget.

The worker discovers durable unclaimed work after restart while it is current and within its deadline. Web/library status and Retry routes also evaluate expiry, so a dead worker cannot leave a source silently Preparing forever. An unstarted or crashed execution that exceeds its deadline becomes visibly retryable and loses its claim. Explicit Retry starts a new execution for a still-current intent; do not silently repeat an uncertain paid call. Initial preparation failure still means no study eligibility; rotation failure still permits the old pair.

Persist a valid initial pair and the source's Ready/active-pair link together. For rotation, persist one candidate result for its intent, with activation governed by the lock rules below. A replay after result commit but before acknowledgment returns that saved result rather than another active revision or another provider call. Enforce one accepted result per intent and current source/claim identity. Old source versions cannot make a newer revision Ready. A job lease or deadline changing state does not by itself reclaim resources; the architecture's bounded cleanup rule applies to generation as well.

### Generated content and presentation

Generate from the authored expression, explanation, selected languages, and intended sense. Request one natural target-language sentence and one aligned native-language sentence, with simple surrounding vocabulary. Keep rotations within the same authored meaning; do not silently switch a polysemous word to a different sense. If the source cannot establish a usable meaning, request clarification of the explanation rather than inventing one.

A pair contains a target sentence and its highlighted expression, a native sentence and its highlighted counterpart, and a concise native-language reference gloss. Each highlight must identify one unambiguous occurrence in its sentence. The target form must be the authored expression or a contextually appropriate form. The native counterpart and gloss must match the intended sense and the paired situation. Phonetics and synonyms are supporting source information, not alternative-answer permissions.

Treat generated sentences/spans as plain text and add only application-controlled highlighting. Continue using the verified Markdown renderer for the authored explanation. Validate nonempty fields, span consistency, language selections, current source identity, and payload shape before accepting a pair. Meaning alignment, naturalness, and vocabulary simplicity are generation-quality requirements; structural validation alone does not prove them. Invalid or ambiguous generated content is a preparation failure rather than a scored answer.

Recognition shows only the target-language sentence and asks for its highlighted meaning in the native language. Production shows only the native-language sentence and asks for the corresponding target expression. Use plain English instructions such as Say the meaning in Chinese or Say the word in English. Do not expose direction-block machinery in the learner UI. Production must not reveal the answer through its title, source explanation, or hidden counterpart data returned with the front. If a literal translation/cognate would expose the target form, generate a natural native paraphrase cue; do not count copying a visible target as retrieval.

The back may show the paired examples, the contextual reference, the authored explanation, the readonly transcript, current-attempt feedback, and committed next-review estimate. Pair and reference content must already be fixed before a scored question is displayed; revealing an answer never waits for new generation.

### Balanced direction selection

Use the accepted two-slot blocks: one Recognition and one Production, in a randomized order. Persist the chosen slot and shown example before displaying a question. Refreshing, navigating away, revisiting, Cancel, or retrying processing cannot reroll the direction or displayed pair.

Consume exactly one slot when an eligible A-E review is committed, including an explicit Forgot action or a wrong answer. Duplicate requests and processing retries reuse the result and cannot consume another slot. Skip and Not assessed consume none; set the card aside for the current study run under the existing queue rule, and reuse the retained direction/example when it appears again. The next block is shuffled only after both slots are consumed. A new example pair does not restart the direction block.

A technical Retry belongs to the same submitted attempt and uses its original recording and frozen content. After an explicit unassessed exit, a later review may be a new attempt with its own recording while retaining the same chosen question/direction. It does not replace the old recording or history. Direction selection never creates another due item or grants an early review success.

[Attempt completion](19-attempt-completion-and-interruption.md) makes an explicit unassessed exit terminal, unlike a retryable failure. A late result cannot consume its slot or grant rotation after that exit; grade-first races return the stored grade instead. Existing pending cue/direction is retained for any legitimate new review.

### Pair retention and rotation

Apply the result to shared progress first, then determine whether a different pair may be used at the next review. Do not mutate the displayed question, revealed answer, or completed assessment. The rules are:

| Review and resulting state | Pair policy |
| --- | --- |
| Normal E | Unlock a new paired set for the next eligible review. Either direction can trigger it. |
| Normal C/D | Keep the current pair. |
| A/B from either collection | Keep the pair, enter/remain Forgot, and cancel any older replacement eligibility. |
| Forgot C | Keep the pair and apply the existing shared streak reset. |
| Forgot first/second qualifying D/E | Keep the pair throughout reinforcement, including E. |
| Forgot third success D, now Normal | Keep the pair until a later Normal E. |
| Forgot third success E, now Normal | Unlock a replacement pair for the next eligible review. |
| Skip/Not assessed | No new rotation trigger; retain the displayed pair and direction for the unresolved slot. |

An E during the first two Forgot successes is not banked for a later D graduation. A valid E replaces the whole aligned pair, not only the currently tested language. Activation adds no scored review and preserves logical progress version, FSRS memory/due, collection, streak, direction position and scored statistics. Active example revision and rotation intent may change or be consumed at the authorized activation boundary; do not assert that the entire learning-state vector including intent is unchanged. Normal C still stays Normal under the established grading/scheduling policy.

The operational default is to prepare a replacement before it is needed when practical, with durable replacement intent so an interruption cannot silently lose the request. Activate a validated replacement only before a new question is displayed, for the same current source and still-authorized review state. A late result cannot replace a locked prompt or activate after an A/B, a source edit, or another result that requires keeping the current pair. Store enough revision/trigger identity to reject that stale work; the persistence ticket chooses the smallest mechanism.

### Locked-presentation rotation race

Serialize pair activation and selection of a new presentation's cue in short transactions. Once an old pair is locked for a presentation or retained for an unconsumed direction slot after Skip/closed-unassessed, its question/reference, direction and clock remain fixed. A valid candidate arriving then is stored only as a pending candidate. It cannot change the parent's active-pair link, logical progress version, or the lock, and cannot make a correct answer to the displayed pair stale.

Judgment checks the example revision recorded on the frozen presentation, not solely equality with a mutable parent active-example pointer. Retain source/progress/attempt claim checks; edits, another scored review or genuinely invalidated work still reject stale results. Background candidate metadata is not a scored-progress revision.

For V1, each later qualifying E creates a fresh rotation identity, while C/D or A/B clear older eligibility as specified. Results bound to the previous intent, including a parked candidate, are discarded when that intent is superseded; they are not automatically reassigned to a new E. Skip/closed-unassessed retains the unresolved cue lock and does not allow candidate activation between attempts. This conservative rule avoids changing or invalidating an already shown question. Initial pair creation has no old presentation to invalidate.

If replacement preparation fails or no valid replacement is ready, preserve the current pair and allow the due review to proceed. Make the fallback visible without penalizing the learner. That displayed fallback stays fixed through Skip/retry. Its next scored result determines future rotation normally: E can request another replacement, C/D keep it, and A/B freeze it in Forgot. Generation wait is excluded from recall time and does not delay answer reveal or overwrite the saved due time.

### Source edits, archives, and history

The operational edit default treats `word`, explanation learning text, and either language as the Vocabulary Card's learning content. A change to any of them creates a fresh learning revision: discard obsolete example/replacement choices, prepare a new pair, and restart its one shared progress record as unseen Normal. Preserve previous attempts with their assessed source, example/reference, direction, duration/budget, and result. A late old-revision judgment cannot update the new progress. The edit UI explains the reset before saving.

Proven formatting-only explanation changes preserve progress/examples under the same narrow canonical-Markdown interpretation already verified: strong/emphasis/paired-underline wrappers may be ignored, while meaningful text, code, block structure, and link targets remain significant. Other explanation-text changes are conservatively treated as learning-content edits; do not add an unreliable semantic-diff model. This differs from a Generic explanation, which is supporting back-side content and preserves progress under its existing contract. Renderer-profile changes require deliberate identity migration.

Archive/restore retains source, progress, pair, retained direction, and history. Archives are excluded from active study. Restoring an overdue ready card makes it due; it does not create a new direction or fresh learning state. Generator/model/prompt updates do not rewrite already displayed examples or historical references automatically.

### Acceptance and limits

Implementation must demonstrate: atomic source validation with post-import generation failures; safe aligned highlights and no Production answer leakage; identical question/direction across refresh, Skip, and same-attempt retries; one slot per committed A-E result; no rotation in the first two Forgot successes; third-D versus third-E graduation; fallback to the old pair after generation failure; rejection of stale results after Forgot/source edits; and preserved history across content reset/archive restore.

The [acceptance handoff](11-acceptance-and-handoff.md) also covers lost wakeups, unclaimed/claimed generation expiry without a worker, commit-before-ack replay, actual worker-capacity recovery and a replacement arriving after a valid old pair is locked. Candidate storage cannot itself invalidate that presentation's later valid grade.

These are a complete policy contract and implementation acceptance requirements, not claims of executed application tests. No generation service, production storage, worker, model call, or paid request was implemented or run by this decision. Linguistic quality and timing/retention calibration remain implementation/live-use checks.
