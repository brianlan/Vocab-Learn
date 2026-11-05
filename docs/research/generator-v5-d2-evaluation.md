# V5 versus D2 generation experiment

Decision, 2026-11-05: **D2 is not promoted.** It improved observed output-format compliance but did not outperform the
fresh V5 control on scope, language content or end-to-end acceptance. Production remains lexical-pair-v5.

The user requested testing the [D2 candidate](generator-d2-candidate.txt) against V5, superseding the D/D2 comparison
suggested in the [proposal analysis](generator-scope-workflow-evaluation.md#d2-diagnosis-and-unmeasured-proposal).

## Frozen comparison

Collect 150 real outputs, 75 per prompt. Each prompt receives five repetitions for each of the five focal words in
replacement mode, five in initial mode, and one request for each of the 25 existing public regression cases. The source
objects, explanations and previous pairs are identical between prompts. All six batches were completed, with prompt
batches alternating by mode. No prompt or source was edited during collection.

Both use MiniMax-M3.1-Flash at the production endpoint, two-call concurrency, a 120-second timeout and an 8,192 completion
token limit. **Neither reasoning_effort nor thinking is sent.** The only request difference is the system prompt. V5
SHA-256 is `e25ee7222b815837a7879f7f487b55bd9ecc77c903fcb26969d37e0cf11f326f`; D2 is
`6d37376f1ce16ce73b2624a01760a93b65a0a1cdcddec824f2a624e716be2aca`.

Every declared output and failure is retained. There are no hidden retries, best-of selection or manual sentence edits.
Review uses the same structural, sense, alignment, fluency, scope/compactness and context dimensions as before. Language
content is reviewed independently of missing markers. Scope can miss the chosen compactness target while the sentence
remains understandable and correctly translated. Conventional compounds, necessary native grammar and filled construction
roles are allowed, with no character limit or preferred-translation whitelist.

## Results

| Outcome | Fresh V5 | D2 |
| --- | ---: | ---: |
| Valid structure | 72/75 | 75/75 |
| Scope/compactness passes | 65/75 | 57/75 |
| Raw text language-content passes | 70/75 | 68/75 |
| End-to-end accepted | 60/75 | 52/75 |

The format improvement did not compensate for eight fewer end-to-end accepted outputs. V5's three structural misses are
omitted focus markers, rather than transport failures. All 150 requests returned responses without a technical failure.

| Batch | Structure | Scope | Raw language | End-to-end |
| --- | ---: | ---: | ---: | ---: |
| V5 replacement | 24/25 | 19/25 | 23/25 | 17/25 |
| D2 replacement | 25/25 | 12/25 | 22/25 | 11/25 |
| V5 initial | 24/25 | 22/25 | 23/25 | 20/25 |
| D2 initial | 25/25 | 23/25 | 21/25 | 19/25 |
| V5 regression | 24/25 | 24/25 | 24/25 | 23/25 |
| D2 regression | 25/25 | 22/25 | 25/25 | 22/25 |

D2's replacement scope is substantially weaker than its initial-generation scope in these samples. The historical pair
may anchor wording, or the revised ordering/completeness emphasis may interact with it. These are hypotheses: this test
does not isolate those mechanisms or individual prompt edits. The replacement input was not removed or weakened to
improve the score.

## Five focal words

Each cell covers ten outputs, five per generation mode.

| Word | V5 scope | D2 scope | V5 end-to-end | D2 end-to-end |
| --- | ---: | ---: | ---: | ---: |
| deterioration | 10/10 | 6/10 | 10/10 | 6/10 |
| germy | 8/10 | 8/10 | 8/10 | 8/10 |
| hybrid | 9/10 | 6/10 | 7/10 | 1/10 |
| match | 8/10 | 9/10 | 7/10 | 9/10 |
| swift | 6/10 | 6/10 | 5/10 | 6/10 |
| Total | 41/50 | 35/50 | 37/50 | 30/50 |

D2 does not meet the earlier focal stability target of at least 47/50 scope passes and at least 9/10 per word. There are
local gains for match and in broader language-content checks; the candidate does not satisfy the full set of outcomes.

## Failure patterns and counterexamples

Bold represents the original markers. None of these outputs was corrected before scoring.

- D2 replacement deterioration 3: “旧桥的**状况恶化**导致道路封闭。” The condition frame belongs beside the lexical focus.
  Three other replacement outputs mark **逐渐恶化**, expanding the already lexical process meaning. Those three are
  compactness misses, not claims of incorrect Chinese or incorrect translation.
- D2 replacement germy 1: “他用热水洗了那条**满是细小病菌的**毛巾。” The explanatory tiny-germs property remains inside
  the focus. The same pattern occurs in V5; restoring definition priority did not establish a fresh-control gain here.
- D2 uses hybrid as a modifier in **7/10** focal outputs, versus 2/10 for V5. Examples include “hybrid flower”, “hybrid
  fruit” and “hybrid bicycle”. These are possible English phrases; the failure is the required noun-head use for this
  authored noun definition. The noun-frame instruction and unrelated positive illustration did not make that constraint
  reliable in this sample.
- D2 replacement swift 2: “The team sent a **swift** reply to my message.” becomes “团队**迅速回复**了我的消息。” The native
  focus includes reply. Another output likewise includes the independent drop action in **迅速下降**.
- D2 regression embarrass marks **这让她在同学面前很尴尬**, including a demonstrative subject and the audience/location
  outside the English target. Monthly marks **每月出版一次**, including the publication action of the surrounding magazine
  context. Existential absorbs the topic list that the English states separately in an unhighlighted about-complement.

There are genuine positive observations too. D2's regression batch preserves all reviewed language content, including a
struggle sentence rendered with **绞尽脑汁想**, keeping hard effort without asserting a completed solution. V5's struggle
sample adds completed arrival upstairs. Both prompts also produce correct broad existential meanings in this run, rather
than the earlier philosophical-school narrowing. These observations do not establish which individual D2 edit caused them.

V5 remains imperfect: it produces a plural-subject “These red shoes matches”, the fragment “The grey horse swift”,
expanded speed/action focuses and missing markers. Retaining V5 is a decision about this comparison, not a claim that
its generated examples all meet the requirements.

## Review boundaries and robustness

The private per-output records include notes for accepted borderline wording. In particular, ordinary lexicalized
descriptors such as 疾驰的/飞奔的 are not mechanically split by character count; contextual nominal-type and compound
translations are allowed. Some academic/agentive terms need a longer natural paraphrase. Explicit scene complements
still belong outside a single-word focus. Mild collocation or contextual-metonym preferences do not automatically fail
the same rubric.

Two post-hoc checks leave the original verdicts unchanged:

- Crediting D2's three gradual-only compactness misses would raise its end-to-end count to **55/75**, below V5's 60/75.
- Excluding all ten hybrid cases from each prompt yields **53/65** accepted for V5 and **51/65** for D2. D2's non-hybrid
  raw language count is 65/65 versus V5's 62/65, but the additional scope failures still prevent an overall gain.

These are robustness descriptions, not preregistered replacement metrics. They show both D2's local language strengths
and the boundary problems that remain even when the repeatedly failing noun is removed.

## Request evidence and checks

Per-request evidence verifies that all **150/150** bodies contain only model, stream, max_completion_tokens and messages;
the hashes agree with the frozen prompt and source. All final model objects remain equal to their captured content.
149 responses expose nonempty reasoning_content and a positive reasoning-token count despite the parameter being omitted.
One V5 replacement hybrid response exposes neither field and omits both focus pairs; absence of these fields is not proof
of the provider's internal execution mode. Thinking text is not stored, only its length/hash and reported usage.

Median reported reasoning tokens are 900 for V5 and 773 for D2; median request times are 15.54 and 14.33 seconds. These
are observations of this collection, not a causal speed or efficiency claim. Thirteen provider/probe tests passed in the
specified Python environment. Identity and verdict-coverage checks cover all 150 primary requests.

The protocol, frozen runs, unedited outputs, individual reviews, CSV, comparison and robustness checks are private under
`var/exports/v5-d2-20261105/`. Private card data is excluded from Git. No production prompt/configuration, source
explanation, saved example or learning progress was modified.

This is a selected, reused benchmark with one unblinded reviewer, not unseen vocabulary or a population accuracy study.
Specialist physical/botanical claims and speech/browser behavior were not independently verified. D2 changes several
instructions at once; the result cannot assign causation to one edit. A more informative next revision would retain the
better-performing scope workflow and test a small accuracy change separately, including the authority of previous_pair
versus the authored definition. No further prompt revision or model run is part of this experiment.
