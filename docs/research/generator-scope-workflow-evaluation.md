# Scope-workflow prompt experiment

This experiment applies the user-provided writing-for-agents skill to the Generator prompt: information hierarchy,
co-location, positive instructions, local completion criteria, pruning, and a shared leading term, Scope. It tests the
five words selected by the user: swift, match, deterioration, germy, and hybrid. The [candidate text](generator-scope-workflow-candidate.txt)
is an experimental prompt, not the deployed Generator. Production retains lexical-pair-v5.

Decision, 2026-11-05: the candidate improves the selected scope/compactness outcome, but is **not promoted** because
language quality and broader regression acceptance did not preserve the baseline. It remains a reviewable experiment;
production retains v5 and saved examples remain as they were.

The later [explicit-max V5/D repeat](#explicit-max-repeat-2026-11-05) reports another 150 primary requests with the prompts frozen.
The subsequent [D2 diagnosis](#d2-diagnosis-and-unmeasured-proposal) proposes another revision; the later
[V5/D2 experiment](generator-v5-d2-evaluation.md) reports its measured results without promoting it.

## What changed

V5 mixes scene creation, translation, slot realization, scope and format rules across a long body. The candidate uses an
ordered workflow: establish lexical scope, build a shared scene, mark the applicable kind of expression, and check the
actual output. Scope rules and two unrelated illustrations are co-located; the output contract is defined once and reached
by an explicit final check. Reference for single words, continuous phrases and filled constructions stays inline because
the Generator cannot fetch workspace files. No extra model stage, agent, schema field or provider option is introduced.

The completion criteria became more concrete after development failures: a single-word target marks its own inflected
form, with articles/complements and the noun modified by an adjective in surrounding text. A native equivalent must keep
the learning meaning while excluding independent scene detail. The deletion test asks whether removing an edge component
preserves the lexical meaning; internal extra detail calls for a new sentence around a conventional equivalent.

The examples use porous and expansion. None of the five target names, preferred Chinese answers or per-word branches
occurs in a candidate prompt. The authored explanations and language fields remain unchanged.

## Collection and review

Freeze the five actual-card sources and saved previous pairs before generation. The replacement-fixture SHA-256 is
`0f6ee8babce2b53fd807ecfbe630e370830005bcc264699d4c73e6ef44a07adc`. Each prompt receives five requests per word, with the
same production MiniMax-M3.1-Flash profile, budgets and two concurrent calls. Every declared sample, raw parsed response
and failure is retained. No output editing, best-of selection, silent retry or production card write is allowed.

Scope/compactness is the primary outcome. The user selected three items previously described as optional wording
improvements, so failing this target does not automatically mean an incorrect translation. Conventional compounds,
necessary native grammar, inherent intensity/causation and complete filled constructions are allowed. There is no
character limit or expected-answer whitelist. Language content and end-to-end acceptance are recorded separately.

Raw text content can be reviewed even when a model omitted markers; marker omission still fails structure, usable scope
and end-to-end acceptance. This distinction was clarified after the replacement trials began, rather than treated as a
blind preregistered analysis. Invented specialist details are not independently fact-checked by this language review.

## Replacement development

| Prompt | Words in prompt | Valid structure | Scope/compactness passes | End-to-end accepted |
| --- | ---: | ---: | ---: | ---: |
| Fresh v5 | 1,044 | 25/25 | 21/25 | 21/25 |
| Draft A | 509 | 25/25 | 18/25 | 17/25 |
| Draft B | 657 | 22/25 | 22/25 | 21/25 |
| Draft C | 737 | 23/25 | 21/25 | 21/25 |
| Draft D, retained candidate | 750 | 24/25 | 24/25 | 23/25 |

Draft A's shortened workflow still marked full noun phrases such as swift reply and the deterioration of the library's
roof. Draft B made word boundaries explicit and illustrated a compact adjective translation and a noun head without its
of-phrase; it removed the sampled expansive patterns but omitted tags three times and used hybrid as a modifier once.
Draft C put the output contract first, but still omitted markers twice and retained two scope/compactness problems.
Draft D moved the illustrations beside their scope rules and made checking both actual output values the last step.
It passed the scope target in 24/25 replacement outputs, with one marker omission and one separate hybrid word-class failure.

This supports further investigation of D; it does not establish reliable production improvement. Specialist scenes
involving invented animal/plant features also illustrate why a shorter focus alone cannot certify an example.

## Fresh initial-generation check

The D prompt was frozen before collecting another five outputs per word without previous_pair, alongside a new v5
baseline on those exact inputs. This tests first preparation as well as replacement; it is not a new unseen vocabulary set.

| Word | V5 scope/compactness passes | Candidate D scope/compactness passes |
| --- | ---: | ---: |
| deterioration | 10/10 | 10/10 |
| germy | 7/10 | 10/10 |
| hybrid | 7/10 | 9/10 |
| match | 9/10 | 9/10 |
| swift | 9/10 | 10/10 |
| Total | 42/50 | 48/50 |

The stricter compactness target improved by six observed outputs, and D met the predefined scope-only target of at least
9/10 for each word and 47/50 overall. These counts include marker omissions as failures. They do not require a particular
Chinese answer: hybrid's conventional bicycle and vehicle senses, and natural lexicalized counterparts, remain valid.
The bicycle sense is documented by [Oxford](https://www.oxfordlearnersdictionaries.com/definition/english/hybrid_2) and
[Cambridge](https://dictionary.cambridge.org/us/dictionary/english/hybrid?topic=bicycles); Trek's [Chinese FX description](https://www.trekbikes.com/cn/zh_CN/bicicletas/bicis-h%C3%ADbridas/bicis-de-ejercicio/fx/f/F421/fx-1/57134/5336621/)
also uses the corresponding bicycle term. Generic scene-category descriptions are judged separately from those lexicalized senses.

| Combined five-word outcome | V5 | Candidate D |
| --- | ---: | ---: |
| Valid structure | 49/50 | 49/50 |
| Scope/compactness passes | 42/50 | 48/50 |
| Raw text language-content passes | 48/50 | 46/50 |
| End-to-end accepted | 41/50 | 44/50 |

The candidate improved scope but did not satisfy the requirement to preserve language quality. Its separate failures include
hybrid modifying flower when the source specifies a noun, the noun-less “These blue match my blue coat” with gloves added
only in Chinese, the unsuitable shirt classifier in 这条蓝衬衫, and adverbial “moved swift” for an adjective source. Its
remaining compactness miss was a scene-specific vehicle-model description; it also omitted a target focus once.
The v5 misses included expanded tiny-germs descriptions, ad hoc mixed-entity descriptions, a running phrase inside a speed
focus, one missing marker, and an appearance qualifier lost in translation. Failures overlap across outcome columns.

These are selected unblinded samples, not evidence of a population accuracy gain or reliable correction of every future
generation. The broader frozen 25-case regression is collected separately to inspect other words, constructions and languages.

## Broader regression

The existing public 25-case fixture set was frozen before these trials and run once per prompt with D unchanged.

| Outcome | Fresh v5 | Candidate D |
| --- | ---: | ---: |
| Valid structure | 25/25 | 25/25 |
| Scope/compactness passes | 23/25 | 24/25 |
| Raw text language-content passes | 25/25 | 22/25 |
| End-to-end accepted | 23/25 | 21/25 |

The candidate added force to a centrifugal-adjective focus, translated accidental as sudden, narrowed existential to
existentialism, and used monthly as an adverb for an adjective source. V5's scope misses were the independent name in an
embarrass focus and effort without the difficulty component in struggle. Necessary short relational pronouns, ordinary
native lexicalization, and merely less polished wording were not automatically rejected.

In particular, [PONS lists 对讲机 as an intercom translation](https://en.pons.com/translate/english-chinese/intercom).
The building/office context in both versions does not establish that this means a portable radio; neither was failed merely
for choosing that term. This illustrates why an expected wording in an old review note is not an exclusive answer key.

## Complete evidence

All **225** declared requests are retained: 125 replacement-development, 50 initial-generation confirmation and 50
broader-regression outputs. Every raw parsed model object remains unedited, including omitted markers, word-class errors,
incomplete sentences and tentative specialist details. The five showcase samples in the private report are each word's
first D replacement response, selected by repeat number rather than quality.

Thirteen provider-contract/probe tests passed. Checks cover fixture identity, five repetitions per focal input/mode, one
repetition per public regression case, exact prompt hashes, equal provider profiles and complete verdict coverage. The
running worker retains lexical-pair-v5 with SHA-256 `e25ee7222b815837a7879f7f487b55bd9ecc77c903fcb26969d37e0cf11f326f`.
There was no production deployment, source-definition edit, saved-example edit or learning-progress write.

## Evidence and limits

The exact frozen sources, initial-generation variants, protocol, all candidate drafts, raw parsed outputs and individual
reviews are retained privately under `var/exports/scope-workflow-20261105/`. Private card data is excluded from Git.
The existing `scripts/probe_generation.py` collector is used without changing production code.

These are unseeded, selected samples reviewed by one unblinded agent. Several writing techniques changed together, so
the comparison cannot attribute an effect to one skill principle. Prompt word counts use whitespace splitting, not model
token billing. External factual checks of specialist scenes and spoken-answer/browser tests are outside this experiment.

## Explicit-max repeat, 2026-11-05

The user requested another run with `reasoning_effort: "max"` explicitly present, then clarified that only V5 and the
frozen D candidate should be compared. The primary repeat contains **150 requests**, 75 per prompt: five repetitions of
each focal word in replacement mode, five in initial mode, and one request for each of the 25 public regression cases.
Already collected A records and interrupted B progress remain separate and are excluded at the user's request. C was not
collected. No V5/D output was discarded or retried, and no new draft was introduced.

All six primary batches reuse the exact historical prompts, source objects, previous pairs, task profiles and budgets.
Two calls run concurrently; the timeout remains 120 seconds and `max_completion_tokens` remains 8,192. The only outgoing
JSON addition is `reasoning_effort: "max"`. Per-request hashes verify the unchanged body after removing that addition.
All 150 final model outputs remain unedited, including the three malformed focus outputs. Review uses the original
scope/compactness, sense, alignment, fluency and context criteria; ordinary native grammar, lexicalization and mild
stylistic differences remain allowed. All declared V5/D batches were completed regardless of interim scores.

### Combined results, 75 requests per prompt

| Outcome | Previous V5, omitted | Previous D, omitted | V5, explicit max | D, explicit max |
| --- | ---: | ---: | ---: | ---: |
| Valid structure | 74/75 | 74/75 | 73/75 | 74/75 |
| Scope/compactness passes | 65/75 | 72/75 | 67/75 | 70/75 |
| Raw text language-content passes | 73/75 | 68/75 | 72/75 | 68/75 |
| End-to-end accepted | 64/75 | 65/75 | 65/75 | 66/75 |

The D candidate again has a higher scope count and one additional end-to-end accepted output, while its raw language
count is four below V5. This is not a clean improvement across the predefined outcomes. Both prompts gained one accepted
output against their respective historical samples; those changes cannot be attributed to explicitly specifying max.

### Focal words, ten requests per word and prompt

| Word | V5 scope | D scope | V5 end-to-end | D end-to-end |
| --- | ---: | ---: | ---: | ---: |
| deterioration | 10/10 | 10/10 | 10/10 | 10/10 |
| germy | 9/10 | 10/10 | 9/10 | 9/10 |
| hybrid | 8/10 | 7/10 | 8/10 | 6/10 |
| match | 9/10 | 9/10 | 8/10 | 9/10 |
| swift | 8/10 | 10/10 | 8/10 | 10/10 |
| Total | 44/50 | 46/50 | 43/50 | 44/50 |

D does not meet the frozen scope stability target of at least 47/50 overall and 9/10 for every word. Its focal raw
language count is 46/50 against V5's 48/50. Replacement and initial generation differ materially: D scored 21/25 on scope
and 20/25 end-to-end for replacement, versus 25/25 and 24/25 for initial generation. Repeating the same five sources is
not evidence of reliable correction for every future card.

In the broader 25-case regression, V5 and D both passed structure in 25/25 and end-to-end in 22/25. Scope counts were
23/25 and 24/25; raw language counts were 24/25 and 22/25 respectively. D's broader language count therefore did not
recover the baseline.

### Failures and review boundaries

Examples are quoted from the unedited outputs; bold represents the original focus tags.

- V5 initial `germy`, repeat 4: the native focus is **沾满了会让人生病的细菌**. The defining sickness clause is included in
  the focus instead of a compact conventional equivalent. V5 also reproduced action frames inside `swift` focuses.
- D replacement `hybrid`, repeat 1: “The **hybrid** strawberry tastes sweet but resists disease better than the local
  variety.” The authored noun is used as a modifier instead of the required noun head, while **杂交草莓** also includes
  the scene's strawberry category. Two other replacement outputs likewise use hybrid as a modifier.
- D initial `germy`, repeat 4: “The dish towel was **germy**, so I put it in the wash.” becomes a native sentence with
  **脏兮兮的**. Its boundary is compact, but general dirtiness does not preserve the germ-contamination meaning. Scope and
  language scores are separate, just as in the earlier accidental/sudden example.
- D regression `struggle`: “My sister **struggled** to lift the heavy box onto the table.” becomes
  “我姐姐**努力**把那个沉重的箱子抬到了桌子上。” The focus loses the difficulty component and the native assertion adds
  successful completion. V5 also repeats the narrower effort-only focus problem, without that explicit completion.
- Both prompts translate broad `existential` questions as **存在主义的** questions, narrowing the meaning to a philosophical
  school. D also adds a preference, 喜欢, to an English literature sentence that only asserts reading.

Borderline items are retained with explicit notes rather than failed against a preferred-word whitelist. They include
the native nominal-type predicate in the conventional hybrid-bicycle sense, the contextual works-collection reading of
文学, short native grammatical particles, mild furniture-location ambiguity and the colloquial prank frame already
accepted in the original trial. The sporting 克星 wording is less direct than 战胜者; the
[Ministry of Education definition](https://dict.concised.moe.edu.tw/dictView.jsp?ID=18040&la=0&powerMode=0)
describes someone able to overcome the other party, without requiring repeated victories. This review consequently
accepts that single-match metaphor with a caveat; the dictionary does not establish an exclusive English translation.
These are disclosed qualitative judgments, not a claim that every accepted wording is ideal.

### Thinking evidence and interpretation

All **150/150** outgoing requests recorded `reasoning_effort: "max"`. **149/150** responses supplied both nonempty
`reasoning_content` and a positive `usage.completion_tokens_details.reasoning_tokens` count. One V5 replacement hybrid
response supplied neither field and also omitted both focus markers. This is missing observable thinking evidence,
not proof of the provider's internal execution mode. The thinking text itself is not retained; its length, hash and
reported token usage are recorded alongside the original final content.

Among responses reporting thinking usage, the median was 936 reasoning tokens for V5 and 611 for D; median request
durations across all requests were 14.90 and 11.64 seconds. Other missing-marker outputs still reported positive thinking
usage, including 289 and 363 tokens. Visible thinking does not guarantee valid markers or faithful language content.

[MiniMax's API documentation](https://platform.minimax.cn/docs/api-reference/text-openai-api) states that omitting
reasoning_effort defaults to max. The previous 150 relevant outputs are a historical unseeded sample, not a concurrent
randomized omitted-versus-max control; they did not retain thinking-token counts. Timing, sampling and provider effects
therefore cannot be separated from an explicit-parameter effect by this repeat.

Decision: retain V5 in production. D remains a candidate for improving scope, but the repeated word-class/sense failures
and missed stability/content gates do not justify promotion under the unchanged criteria. No production setting,
prompt, authored explanation, saved example or learning progress was modified.

The exact six run definitions, all 150 final outputs, request evidence, per-output reviews, CSV and comparison are private
under `var/exports/scope-workflow-explicit-max-20261105/`. Thirteen provider/probe tests passed in the specified Python
environment, and identity checks cover every primary request and verdict. This remains a selected, single-reviewer,
unblinded language evaluation. Invented specialist facts, learner outcomes and speech/browser behavior were not tested.

## D2 diagnosis and unmeasured proposal

The user requested returning to omitted reasoning_effort and analyzing how D could be improved. Production never acquired
the experimental max override: it existed only in the completed probe processes. A local mock transport in the running
worker exercised generate, chat and HTTP request assembly and confirmed the four outgoing fields: model, stream,
max_completion_tokens and messages. Neither reasoning_effort nor thinking was sent. Production remains lexical-pair-v5;
this check made no paid generation request or learning-state write.

The [D2 candidate](generator-d2-candidate.txt) was prepared as an unmeasured proposal based on the exact D prompt. Its
later [V5/D2 evaluation](generator-v5-d2-evaluation.md) did not justify promotion. At diagnosis time, all 150 D outputs from
the two experiments were accounted for: **19 failed end-to-end**.
Fourteen had a raw language-content failure, three otherwise valid outputs failed only scope/compactness, and two omitted
focus markers. These categories are exclusive; individual language failures can also contain a scope problem. The
diagnosis uses both parameter conditions to identify failure types, without treating the pooled counts as an effort-control
experiment or population accuracy estimate.

### What the evidence does and does not show

Some useful accuracy guidance was lost when V5 was shortened into D. Other requirements are already explicit in D and
were nevertheless violated. The latter are instruction-following failures, not evidence that a sentence was absent.
The following changes are hypotheses to test, rather than proven explanations of the model's internal behavior.

| Observed problem | Relevant D instruction | Diagnosis and D2 change |
| --- | --- | --- |
| germy becomes general dirtiness | explanation supplies sense; choose a native dictionary equivalent | D omitted V5's explicit definition-over-phonetics/synonyms guidance. The actual source lists dirty and unclean as supporting synonyms. D2 restores the authority of the definition and explicit grammatical specifications; related annotations cannot replace its distinguishing meaning. |
| Broad existential meaning becomes a philosophical-school affiliation | conventional native dictionary equivalent; complete meaning | D omitted V5's explicit breadth/register/distinction guard. D2 preserves the definition's specificity and chooses the native wording from the completed contextual statement, rather than fixing a dictionary translation before the scene. |
| Noun used as a modifier; adjective used adverbially | source-defined noun must be a noun head; preserve target word class | These requirements were already stated. D2 makes the grammatical frame the first construction decision and adds an unrelated positive noun-head illustration, rather than claiming another repeated prohibition will solve the issue. |
| Attempt becomes successful completion; preference or intention changes | same facts and outcomes; represent attempts and achieved results accurately | D already mentions these goals, but the final check is broad. D2 composes one statement and translates its actual assertions, explicitly comparing roles, negation, intention, preference, appearance, time/place and completion. An unrelated attempt illustration preserves unspecified success. |
| A short native focus loses a defining feature, or includes a scene category | compact lexical translation; deletion test | D2 makes completeness a prerequisite for compactness. The highlighted expression carries the distinguishing lexical meaning; independent scene detail stays outside. When a natural span cannot satisfy both, rephrase the sentence rather than trim away meaning. |
| Missing noun, classifier error or missing markers | idiomatic standalone utterances; count both marker pairs | D already requests valid language and exact tag counts. D2 retains the contract and gives the final check concrete objects: complete arguments, noun determiners/classifiers, agreement, and each actual string's markers. This is not deterministic enforcement. |

The three new illustrations use tenant, attempt and fragile. None is a focal or public regression entry. D2 contains no
word-specific rule or preferred answer for any failed benchmark word. The source data, two-string output schema and
single-call generation interface remain unchanged. Its 874 words are a deliberate restoration/reorganization of accuracy
guidance, compared with D's 750; brevity is not the sole optimization target.

### Proposed generation order

1. Establish the definition's learning meaning and the target expression's grammatical frame.
2. Compose a simple target statement, then express those same assertions in the native language using the contextual sense.
3. Mark complete lexical scope with meaning-preserving trimming and the existing phrase/construction branches.
4. Inspect both actual strings for language, equal assertions and exact output shape.

These are internal instructions within one model request. They do not create real stage boundaries, introduce an extra
LLM/validator call, expose a reasoning trace or guarantee that the model follows every step. The current application
already checks output structure; this proposal does not replace or relax that boundary.

### Proposal-stage checks and planned validation

At proposal time, three illustrative outputs passed the existing Generator pair validator, and a text check confirmed that
benchmark failure words are absent from D2. Those were static contract checks, **not live model results**; no paid D2 call
had then been made. Neither the candidate nor manual sentence corrections have been written into any card.

The proposed next comparison was to freeze D and D2, omit reasoning_effort for both, preserve task profile/budgets and
two-call concurrency, and collect the same 75 samples per prompt: replacement, initial and the full public regression.
The user subsequently selected V5 as the comparator instead; the completed experiment is linked above.
Retain every output and failure without best-of selection, hidden retries or hand editing. Review language and scope
separately and keep the existing criteria. A full-pass benchmark is a useful acceptance target, but finite samples cannot
establish that every future request will satisfy every requirement. The proposal made no improvement claim, and the later
measured comparison did not support promoting D2.

The 19 original failure records, their source explanations, reviews and source-file hashes are retained privately under
var/exports/generator-d2-analysis-20261105/, alongside the illustration checks and unmeasured-proposal manifest.
