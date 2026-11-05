# Scope-workflow prompt experiment

This experiment applies the user-provided writing-for-agents skill to the Generator prompt: information hierarchy,
co-location, positive instructions, local completion criteria, pruning, and a shared leading term, Scope. It tests the
five words selected by the user: swift, match, deterioration, germy, and hybrid. The [candidate text](generator-scope-workflow-candidate.txt)
is an experimental prompt, not the deployed Generator. Production retains lexical-pair-v5.

Decision, 2026-11-05: the candidate improves the selected scope/compactness outcome, but is **not promoted** because
language quality and broader regression acceptance did not preserve the baseline. It remains a reviewable experiment;
production retains v5 and saved examples remain as they were.

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
