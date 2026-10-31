# Define Cards, Vocabulary, and Per-User Progress

Id: 04
Parent: [Vocab-Learn Browser V1 Decision Map](../map.md)
Type: grilling
Labels: wayfinder:grilling
Mode: HITL
Status: resolved
Assignee: /root
Blocked by: none

## Question

What is the smallest unit of scheduling and collection membership: an individual cloze card or an abstract vocabulary item? What does V1 allow when the same answer appears in two contexts, an answer is a phrase, a card contains multiple blanks, or several answers are acceptable, and where is progress recorded?

Learning content is language-independent; users own private decks and independent progress. Discuss concrete examples with the user to establish the relationships between cards, answers, acceptable variants, attempts, and progress. Resolve only V1 boundaries rather than building an unrequested question-type framework. Add settled terms to CONTEXT.md; keep this decision's details in this ticket's answer.

## Answer

Resolved through the user's explicit answers to interview questions Q1-Q4 on 2026-10-30.

- The learning unit is an individual cloze card. Each user's progress, Normal/Forgot membership, and review scheduling belong to that card; different cards targeting the same vocabulary do not share progress.
- A card may contain multiple blanks. One spoken response addresses the whole card and all its blanks in one attempt; blanks do not become separately scheduled items.
- Answers are freeform text and may include words, phrases, or short sentences. V1 imposes no single-word-only or phrase-only product restriction.
- Store one author-provided reference answer for the whole card, rather than a list of accepted variants. AI evaluates other formulations against the question and reference. This decision does not make every synonym fully correct.
- An attempt belongs to one user and one card. Grading and statistics decide later which interactions count as assessed reviews; this ticket does not define Skip's statistical effect.

Follow-up responsibilities stay with existing tickets: [Decide the Spoken-Answer Flow and Visual Direction](05-spoken-card-flow.md) shows a multi-blank interaction; [Define Grading, Five-Level Feedback, and Response Timing](06-grading-feedback.md) decides partial correctness and overall card feedback; [Define the Minimum Account, Private-Deck, and Statistics Contract](08-private-decks-and-stats.md) decides entry and CSV representation. No per-blank storage schema or partial-credit rule was silently chosen here.

Settled terms are recorded in [CONTEXT.md](../../../../CONTEXT.md).

## Later scope extension

The user has named this authored content source Generic Cards and requested a distinct vocabulary-derived source. [Define Generic and Vocabulary Card Learning Units](14-generic-and-vocabulary-units.md) owns the extension; this historical resolution does not settle vocabulary-direction progress or generated-example identity.
