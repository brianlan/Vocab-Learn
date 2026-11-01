# Vocab-Learn

Vocabulary learning through authored and vocabulary-focused cards, spoken answers, and spaced repetition.

## Language

**Generic Card**:
An authored learning card with a question, one reference answer, and an explanation; the question may contain zero or more cloze blanks. Its content is not used to derive vocabulary-specific questions or features.

**Cloze Card**:
A Generic Card with one or more blanks in its Markdown question. Distinct authored cards remain separate learning units, including cards that target the same vocabulary in different contexts.

**Vocabulary Card**:
A vocabulary-focused learning card containing a target expression, its authored meaning explanation, a Target Language, and a Native Language. The authored explanation defines the intended sense and remains the teaching definition. Recognition and Production are alternative ways to review the same card.

**Target Language**:
The language of the expression being learned and of the response expected during Production.

**Native Language**:
The learner's selected language for explaining the expression's meaning during Recognition and for the context shown during Production.

**Recognition**:
A Vocabulary Card review that presents a target-language context and asks for the highlighted expression's meaning in the native language.

**Production**:
A Vocabulary Card review that presents a native-language context and asks for the corresponding target-language expression.

**Example Pair**:
Aligned target-language and native-language sentences expressing the same situation, with corresponding expressions identified for review.

**Example Revision**:
A saved version of an Example Pair and its generation provenance used by a review, distinct from the vocabulary being learned. It has no separately generated definition or native reference-answer paragraph.

**Example Rotation**:
Replacement of a Vocabulary Card's current Example Pair while preserving its learning progress and historical reviews.

**Review Direction**:
The selected Recognition or Production form of a Vocabulary Card, determining the displayed cue and requested response.

**Reference Answer**:
For a Generic Card, the author's single plaintext benchmark response for the whole card, covering all its blanks when present. It can contain words, phrases, or short sentences; other formulations are assessed by the AI judge rather than enumerated as accepted variants.

**Card Progress**:
One user's accumulated learning status for one Generic or Vocabulary Card, independent of other cards with the same target vocabulary. A Vocabulary Card shares this progress across its review directions.

**Attempt Feedback**:
The assessment of one interaction with a card, distinct from the user's long-term learning progress.

**Complete Recall**:
Fulfillment of the current review goal: a conventional equivalent lexical meaning during Recognition or the required target expression/content during Production and Generic review. Recognition does not require expanding a correct equivalent word into an exhaustive definition.

**Partial Recall**:
Retrieval that establishes relevant meaning but leaves the current review goal incomplete, including a suitable substitute for a required target expression.

**Target Recall**:
Retrieval of the authored target expression, including genuinely equivalent spelling or contextually correct word-form variants.

**Meaning Recall**:
Retrieval of the intended meaning through a synonym or paraphrase in a task requiring a particular target expression.

**Next Review**:
The next scheduled review opportunity for a card, displayed as an approximate relative time.

**Success Streak**:
Consecutive qualifying complete-recall successes for a card in the Forgot Collection, preserved across missed days and ungraded interactions.

**Graduation**:
A card's return from the Forgot Collection to the Normal Collection after completing its spaced success streak.

**Private Deck**:
A collection of learning cards maintained by one user for their own learning.

**Archived Card**:
A retained card excluded from active study, with its authored content, learning progress, and review history available for restoration.

**Scored Review**:
A card interaction producing one A-E result, including a user's explicit Forgot action. Skip and unassessed interactions are not scored reviews.

**Continuous Practice**:
Ongoing study that resumes an unfinished question or selects an eligible card whenever the learner returns, without separately started or completed passes.

**Temporary Deferral**:
A time-limited pause in a card's availability for practice, preserving its spaced repetition progress and historical reviews.

**Spoken Answer**:
One spoken response to the whole card, supplied through Speak and addressing all blanks when present. It can contain words, phrases, or sentences.

**Answer Submission**:
A spoken answer committed for assessment. The submitted recording stays fixed after the reference answer becomes visible.

**Presentation**:
One display of a fixed review question, direction, reference context, and response clock, distinct from a later review of the same card.

**Assessment Execution**:
One processing run of a fixed spoken submission; an explicit retry can start another execution without becoming another learning review.

**Card Reveal**:
The transition from the question to its reference answer and explanation. Revealing a submitted answer does not imply that transcription or grading has finished.

**Transcript**:
The ASR-generated text of a submitted spoken answer, shown as a readonly account of what the service recognized.

**Unassessed Attempt**:
A submitted response without a scored correctness result because of a technical interruption or an unassessed exit. It is distinct from a wrong answer.

**Unassessed Exit**:
The learner's server-confirmed closure of a submitted attempt without a score, preventing a later processing result from changing learning progress.

**Cancel**:
The action of discarding a recording before submission and returning to the question without revealing its answer.

**Skip**:
An ungraded action that reveals the answer and temporarily defers the card for 30 minutes while preserving its learning progress.

**Forgot**:
The action of explicitly reporting that the answer has been forgotten and viewing the back of the card.
_Avoid_: Using Forgot alone to refer to the Forgot Collection.

**Normal Collection**:
The default collection of learning items following the regular spaced repetition schedule.

**Forgot Collection**:
The collection for reinforcing items that the user explicitly forgot or answered substantially incorrectly.
_Avoid_: Using Forgot Collection to refer to the Forgot action.
