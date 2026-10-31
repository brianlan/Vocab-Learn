# Define Vocabulary-Direction Grading and Timing

Id: 16
Parent: [Vocab-Learn Browser V1 Decision Map](../map.md)
Type: grilling
Labels: wayfinder:grilling
Mode: HITL
Status: resolved
Assignee: /root
Blocked by: 14

## Question

How do the existing A-E feedback levels apply to the recognition and production goals of vocabulary cards? Keep the Generic Card rubric intact unless the user changes it. In production, target-expression recall can use the Generic distinction between target and merely synonymous expression. In recognition, a different but fully equivalent native-language wording may satisfy the whole goal rather than automatically receiving C.

Define complete semantic correctness versus partial/imprecise meaning versus the wrong sense, with contextual examples. Decide C's meaning and humane English label in each direction instead of forcing all native synonyms into the Generic Meaning recalled category. Distinguish harmless language/form variants from substituting another target expression, and do not award a wrong sense simply because a word appears in an authored synonyms list.

Determine the constrained judge output and application-owned mapping to A-E, including ambiguous/malformed output and ASR failures. Set response-time inputs for a visible highlighted expression/context rather than a cloze prompt, avoiding phonetic/Markdown syntax in length calculations. Complete correct native meaning may be D/E according to time if accepted; partial meaning must not become E merely because it was fast.

Decide whether the existing FSRS mapping and Forgot three-success policy apply unchanged to complete-success results. The user has chosen one shared progress record per Vocabulary Card, so either review direction updates its single schedule, collection, and streak. Keep current-attempt feedback and committed next-review time. Count the card once in distinct-card metrics and each scored interaction once in review metrics; retain direction as a review attribute without inventing separate mastery or schedule records.

Generic Cards may now have no blanks. Assess those as a single whole-answer unit against the authored reference instead of requiring a per-blank array with at least one actual gap. Preserve the existing Generic rubric and actual multi-blank aggregation; make response-time inputs meaningful for a zero-blank prompt as well as the vocabulary directions.

## Comments

2026-10-31: Claimed after the Generic/Vocabulary learning-unit decision resolved. Sent two independent rubric questions: Recognition accepts contextually complete equivalent native-language meanings as D/E and partial meaning as C; Production reserves D/E for the target expression or appropriate form and C for a contextually suitable substitute. Wrong meaning/expression is B, and D/E retain the existing timing distinction. These are proposals awaiting the user, not completed grading decisions.

Candidate C copy is Partial recall so incomplete meaning and incomplete target-expression retrieval can share a clear label. Final copy, normalized judge outcomes, application mapping, and timing details remain part of this ticket; they do not require extra provider calls or a new scheduling algorithm.

The user then assented to the summarized direction-aware rubric and asked to proceed to the next step. The answer below makes those principles concrete, using the earlier delegation for English feedback copy and the initial timing heuristic; it does not claim that separate numbered answers were supplied.

## Answer

Resolved on 2026-10-31 following the user's assent to the summarized Recognition/Production principles. The shared learning unit, Generic baseline, neutral actions, and default FSRS policy remain as previously settled.

### Judge the review goal

Recognition asks for the highlighted expression's intended meaning in the selected native language. A short word, phrase, or explanatory sentence can satisfy that goal. Contextually equivalent native expressions receive complete credit; do not require the exact generated gloss or an exhaustive recital of a dictionary definition. Meaning naturally implied by an idiomatic answer counts. A different sense or merely stating what happened elsewhere in the sentence does not explain the highlighted expression.

Production asks for the target-language expression anchored in the authored word/meaning and current context. Recalling that expression or a genuinely equivalent spelling/contextually appropriate form receives complete credit. A suitable substitute that conveys the meaning without recalling the target is partial. A source synonyms list is supporting context, not automatic acceptance; an inappropriate substitute is incorrect. Mentioning the target inside a contradictory answer does not establish retrieval. Neither direction requires translating the whole example sentence.

Answer-language expectations follow the selected task. Repeating the visible prompt or giving only an answer in the other language does not satisfy the task merely because the phrase is related. Legitimate borrowed expressions and ordinary equivalent forms are judged contextually rather than rejected by a simple language-detector heuristic.

### Five feedback levels

Use Your recall this time for attempt-level feedback. Unify C's English label as Partial recall for both card sources; this changes the Generic display wording, not its previously settled eligibility or scheduling.

| Grade | English label | Recognition | Production |
| --- | --- | --- | --- |
| A | Needs a refresh | The user chooses Forgot. | The user chooses Forgot. |
| B | Needs practice | The meaning is wrong, a different sense, or does not answer the task. | The expression is wrong, unsuitable in context, or missing. |
| C | Partial recall | A relevant meaning is established but remains materially incomplete or imprecise. | A suitable synonym/paraphrase conveys the meaning without recalling the target expression. |
| D | Correct recall | Complete in-context meaning, above the fast budget. | Target expression or equivalent form, above the fast budget. |
| E | Quick recall | Complete in-context meaning, at or below the fast budget. | Target expression or equivalent form, at or below the fast budget. |

Speed never upgrades C or B. A valid but wrong answer is B; a service failure is Not assessed. An explicitly chosen Forgot is A without ASR/judging. The judge cannot turn another action into A or Skip.

### Generic questions and normalized outcomes

Preserve the Generic rubric: retrieving its benchmark target/content under the established equivalence rule is complete; merely conveying the intended meaning through a substitute is partial; a wrong or unanswered component is incorrect. A naturally completed sentence is valid evidence, not a requirement to match the whole transcript literally. Generic Cards without gaps have one whole-answer unit; cloze cards have one unit per actual parsed blank. A Vocabulary review has one whole-expression/meaning unit for its frozen direction.

Make the existing target-recall goal explicit for the Generic call off/cancel fixture: call off is the authored target, so a suitable cancel substitute is partial/C regardless of speed. Do not silently switch this fixture to semantic-only D/E or generalize it into character-by-character recitation. Live Judge tests must receive the explicit goal; prelabelled fake outcomes test mapping rather than language judgment.

The normalized judgment supplies one result for every declared unit: its identity, an outcome of complete / partial / incorrect, and an English reason. An explicit inability to assess is separate from these semantic outcomes. The application validates the expected unit identities, count, enum values, and usable content before applying any result. A missing unit in malformed service output is Not assessed; a valid result stating that the learner left a required blank unanswered is incorrect and produces B.

The application applies this precedence: any incorrect unit gives B; otherwise any partial unit gives C; otherwise all units are complete and measured time selects D/E. The LLM does not choose A-E, invent elapsed time, set a due time, or change the user's action. Treat content/transcript as data and escape generated feedback. Exact provider wire format and retry handling remain with [Decide Replaceable ASR and Judge Boundaries](09-provider-configuration.md).

Skip remains outside A-E and accuracy. Cancel has no assessment. Empty/unusable transcription, provider errors, invalid judgment, or genuinely unresolved ambiguity are Not assessed; preserve the established same-recording retry or unassessed-exit flow. An intelligible wrong response must not be excused as a hypothetical ASR error merely because it is wrong.

### Response clock and budget

Reuse the established display-to-submission clock, including thinking and cancelled recordings, excluding microphone-permission blocking and upload/model/retry waits. Start only when the actual question is ready and fully displayed; generation wait is not recall time. Freeze duration with the submitted prompt/direction/reference.

Keep `T = max(12, ceil(5 * N + Q / 20 + R / 5))` seconds. For actual cloze questions N is the real blank count; for a non-cloze Generic question or a Vocabulary review N is 1, representing the one answer task. Q counts non-whitespace Unicode code points in the actual visible question, excluding cloze tokens and Markdown syntax. In Vocabulary it includes the displayed example and highlighted expression, not hidden counterpart sentences, phonetics, or back-side explanation. R counts the frozen reference: the native contextual gloss for Recognition, and the authored target expression for Production.

Complete recall at exactly T is E; above T is D. Invalid/missing timing is a technical assessment problem, not evidence for B, C, or D. Keep the measured duration and budget with the result. The formula remains an initial delegated heuristic rather than a calibrated language-comparison model.

Follow [completion/interruption semantics](19-attempt-completion-and-interruption.md) for same-presentation refresh, explicit clock recovery/restart, and indefinite permission waiting. Server receipt/action time is the distinct scheduling anchor; post-submission processing cannot alter either saved duration or anchor.

### Shared scheduling and statistics

Both directions update the card's one saved schedule, collection, and streak. Apply the existing mapping unchanged: A/B/C to FSRS Again, D to Good, E to Easy. D/E now mean complete success for the current task; Recognition's fully equivalent native meaning qualifies. A/B enter Forgot, Normal C stays Normal, and Forgot A/B/C reset the shared streak with a one-minute due override. Either direction's D/E increments that one qualifying streak; successes one/two schedule 24 hours later and success three graduates under the existing preserved-state policy. Skip/Not assessed leave progress unchanged.

Use Recall accuracy as the English statistic label, with the already agreed D/E divided by A-E formula. This expresses complete performance on the current review goals without claiming separate proficiency in both directions. One Vocabulary Card reviewed twice contributes one distinct card and two reviews. Keep direction and exact assessed source/example/reference with each event. Example replacement itself does not reset progress or add a scored review; its activation policy belongs to the lifecycle decision.

### Decisive acceptance examples

| Situation | Required behavior |
| --- | --- |
| Recognition gives a complete in-context native synonym or natural explanatory phrase | D/E by time, even when the generated gloss uses another wording |
| Recognition gives only materially partial meaning | C at both short and long times |
| Recognition describes the sentence's consequence instead of the highlighted expression | B |
| Production recalls the target expression or an appropriate form | D/E by time |
| Production gives an in-context substitute without the target | C at both short and long times |
| A listed source synonym is unsuitable for this sense/context | B |
| A complete response arrives exactly at T | E |
| Any Generic blank is genuinely wrong/missing while another is partial | B |
| A provider omits a required judgment unit | Not assessed; no scheduler call |
| A due Vocabulary Card receives three qualifying D/E results across either direction | One shared graduation, with no duplicate direction-level progress |
| Skip, Cancel, or a technical failure | No A-E correctness credit and no artificial wrong-answer grade |

These are implementation acceptance requirements, not claims of tested model accuracy. Existing FSRS integration evidence establishes the unchanged rating/state path; it does not establish language grading, example quality, or real-user retention. No live model call, new provider dependency, or production grading code was introduced by this decision.
