# Vocabulary phrase compatibility research

Reviewed: 2026-11-04. Scope: English usage from primary dictionary/publisher sources and concrete compatibility questions for the current Vocabulary contract. This note records evaluation and general design recommendations without changing the implementation. A separate live-generator probe covers 18 requests: 15 phrase fixtures and three neutral compare controls. Its explanations are evaluation fixtures, not recovered original card explanations. The [saved live results](vocabulary-phrase-generation-results.json) and manual review below distinguish structural validity from teaching quality.

## Current application boundary

The authored expression and explanation define the intended sense. Generated examples illustrate that sense; they do not replace the explanation. Recognition accepts conventional equivalents; Production asks for the authored expression or an appropriate form. [Authored-meaning decision](../adr/0002-authored-vocabulary-meaning.md), [current judgment rules](../../learning/providers.py#L156).

Each generated sentence has exactly one marked, contiguous highlight. The prompt allows inflection while preserving lexical identity and excludes independent participants and objects from the highlight. Neither Generator nor Judge explicitly defines realization of `one's`, `sb/sth` or ellipsis slots. The parser preserves the selected position, but checking marker shape does not establish correct sense or grammatical realization of a pattern. [Generator and validation](../../learning/providers.py#L201), [judgment rules](../../learning/providers.py#L156), [highlight-position decision](../adr/0005-preserve-highlight-positions.md).

## Compare: preferences overlap

| Authored pattern | Supported usage | Evaluation implication |
| --- | --- | --- |
| `compare ... to ...` | Often likens one thing to another; also permits ordinary examination of similarities and differences. Oxford lists both `with/to` for the general sense and `to` for likening. [Oxford: compare](https://www.oxfordlearnersdictionaries.com/definition/english/compare_1) | An explanation meaning “liken” needs a likeness/analogy context. A general comparison using `to` is not inherently wrong English. |
| `compare ... with ...` | Examines similarities and differences; it does not mean “find differences only.” [Merriam-Webster: compare](https://www.merriam-webster.com/dictionary/compare) | Do not manufacture a strict “to = similarities, with = differences” rule. |
| `compare ... against ...` | Can evaluate something relative to a reference, target or benchmark. Oxford and Collins give this comparative sense of `against`; Cambridge's own assessment guidance uses `compare against` for evaluating performance relative to peers. [Oxford: against, sense 6](https://www.oxfordlearnersdictionaries.com/definition/english/against), [Collins: against, sense 12](https://www.collinsdictionary.com/dictionary/english/against), [Cambridge assessment guidance](https://www.cambridge.org/insight/blog/complete-assessment-cycle) | Benchmarking is a useful context, not an exclusive definition or proof that other comparison prepositions are impossible. |

American Heritage explicitly describes acceptance of both `to` and `with` for both kinds of comparison, with preferences. Its 2014 panel preferred `to` strongly for an analogy (95% versus 55% acceptance), while both were widely accepted for assessing a forged signature against an original (76% for `to`, 84% for `with`). These are judgments on those sentences, not universal usage frequencies. [American Heritage usage note](https://www.ahdictionary.com/word/search.html?q=compare).

**Application inference:** grammatical acceptability, authored sense, and recall of a particular authored pattern are separate checks. A Chinese cue meaning simply “compare” may naturally permit several English prepositions. An alternative can be good English while remaining partial under the current Production policy. Conversely, an analogy entry illustrated only by numerical comparison can miss its authored sense even when its preposition is grammatical.

## “Do one's studies” needs context

Oxford distinguishes possessive plural `studies` for a person's formal learning, subject names such as women's studies (which can take `do`), and countable research studies (which can also take `do`). Its learning examples favor verbs such as continue, pursue and complete. [Oxford: study noun, senses 2–4](https://www.oxfordlearnersdictionaries.com/definition/english/study_1).

Do not label `do one's studies` categorically ungrammatical: OUP publishes a staff member's recollection using “do my studies” for schoolwork at a library. This is attested usage, not a dictionary ruling that the phrase is a preferred fixed idiom across varieties. [OUPblog: Why we love libraries](https://blog.oup.com/2014/05/national-library-information-week-australia/).

**Editorial inference:** for an entry meaning ordinary learning, `study` is a straightforward teaching alternative; for formal education, `pursue/continue one's studies` is dictionary-supported. That does not authorize silently changing the authored target. Evaluate whether the generated situation matches the supplied explanation, especially whether it wrongly turns a learner's studies into scientific investigations. [Oxford: study verb](https://www.oxfordlearnersdictionaries.com/definition/english/study_2).

## Pattern notation is not literal sentence text

- **`one's`:** a possessive slot changes with its referent. Merriam-Webster's `make up one's mind` entry illustrates forms with `my`, `his` and `your`, including an inflected verb. A concrete sentence need not contain the literal characters `one's`. [Merriam-Webster entry](https://www.merriam-webster.com/dictionary/make%20up%20one%27s%20mind).
- **`sb/sth`:** Cambridge explains these as somebody/something and uses their position to describe where an object can occur. Replacing them requires an appropriate person/thing and the right word order. [Cambridge dictionary explanation](https://dictionaryblog.cambridge.org/2014/09/24/an-introduction-to-phrasal-verbs/).
- **`...` or `…`:** in an authored pattern, these can signal material to supply, but the dots alone do not specify its grammatical category or whether it is optional. Treating `compare ... to ...` as two object slots is an interpretation supported by Oxford's explicit `A`/`B` construction, not a universal parser rule. Ellipsis also has ordinary omission/punctuation meanings. [Oxford: compare](https://www.oxfordlearnersdictionaries.com/definition/english/compare_1), [Oxford: ellipsis](https://www.oxfordlearnersdictionaries.com/definition/english/ellipsis).
- **Separated phrasal verbs:** a separable verb can have an object between its verb and particle; a personal pronoun must occupy that position. Other multiword verbs do not allow separation. The dictionary construction matters. [Cambridge: phrasal and prepositional verbs](https://dictionaryblog.cambridge.org/2020/01/29/let-down-and-look-after-the-difference-between-phrasal-verbs-and-prepositional-verbs/).

## Concrete conflicts to evaluate before deciding

The following contract inferences guided the live probe; observations follow in the empirical section:

| Candidate | What the probe should establish |
| --- | --- |
| `do one's studies` → `did her studies` | Does the generator substitute the possessive, inflect naturally, and retain the learning sense? |
| `compare ... to/with/against ...` | Does it instantiate both objects and preserve the authored sense? Does highlighting include the full construction, omit a required preposition, or include objects that the prompt otherwise excludes? |
| `let sb down` → `let him down` | One contiguous highlight cannot mark just `let` and `down` while excluding `him`. A joined noun-object form may avoid the gap in some examples, so this does not establish that all phrasal verbs are unsupported. |
| Several compare entries sharing a broad native equivalent | Does the context actually distinguish the intended sense? Keep valid English alternatives separate from exact authored-expression recall. |
| A weak or ambiguous authored explanation | Does the generator request clarification rather than select an unrelated sense or silently repair the target? |

Inspect complete sentences, both selected highlights and the explanation together. A successful shape check is insufficient evidence of phrase compatibility; a few successful generations do not establish coverage. Use the observed results below when deciding whether to revise the generic expression contract; this investigation itself changes no application behavior.

The dictionary review made no model API calls. The separate empirical probe made 18 calls and changed no application code or learner data. No corpus frequencies were measured; publisher quotations establish attestation, not general prevalence.


## Live evaluation of the deployed prompt

The deployed Generator profile used `MiniMax-M3.1-Flash` and `lexical-pair-v3`. Each fixture received one call with its authored expression, an independently written English explanation, Target Language English and Native Language Chinese. Three additional compare fixtures shared exactly the same neutral explanation. At most two requests ran concurrently; there were no retries, inserted cards, progress changes or configuration changes. The saved JSON includes source fixtures, complete generated final objects, parsed positions, rendered HTML, elapsed times, non-secret profile metadata and the prompt hash. These are not the learner's unprovided original explanations.

All **18/18** calls passed the existing structural validator. That means they supplied one usable marked span per sentence and met shape/language/leak checks; it does not establish complete construction coverage, sense accuracy, highlight alignment or a production reliability rate.

Selected spans from the fifteen sense-specific fixtures are reproduced below. Brackets identify the model's selected expression, not editorial corrections.

| Authored expression | Selected English expression | Selected Chinese expression | Manual observation |
| --- | --- | --- | --- |
| `do one’s studies` | does his studies | 用功读书 | Possessive realization and inflection work in this sample. Do not infer a universal fixed-idiom judgment from this example. |
| `at the beginning` | At the beginning | 一开始 | Appropriate continuous phrase. |
| `point out` | pointed out | 指出 | Appropriate phrasal verb and inflection. |
| `introduce ... to ...` | introduced Lucy to me | 把露西介绍给我 | Instantiates both participants; requires treating filled slots as necessary parts of the construction. |
| `share sth with sb` | share these cookies with me | 分给我 | Slots are realized; native wording is less explicit about shared participation. |
| `pick sb. up` | pick up | 接 | Valid noun-object placement, but this sample avoids the separated/pronoun construction. |
| `leave … behind` | left the dog behind | 留下 | Keeps the particle and realizes the object inside a continuous English span. |
| `as a result` | as a result | 因此 | The road closure and longer-route consequence provide context. |
| `give sb. an idea of ...` | gives viewers an idea of | 有个大概的印象 | Native selected span omits the causative/recipient frame, though the full native sentence contains it. |
| `it is somebody's job to do sth.` | It is the nurse's job to record each patient's temperature | 记录每位病人的体温是护士的职责 | Selects the entire realized clause; reasonable for a clause-level target, but the prompt does not explicitly define that case. |
| `only recently` | only recently | 最近才 | Preserves the temporal emphasis. |
| `in demand` | in demand | 需求很大 | Preserves demand rather than a generic popularity gloss. |
| `compare ... to ...` | compared to | 比作 | Rainbow/bridge analogy follows the supplied likening explanation. |
| `compare ... with ...` | compare with | 比较 | Ordinary product comparison fits the sense, but the sentence gives no concrete comparison dimension. |
| `compare ... against ...` | compared against | 比较 | A passing mark supplies the benchmark; native syntax is somewhat stiff. |

The three neutral controls reveal why the explanation and complete highlight both matter:

- `to`: `We [compared the first plan to the second plan] yesterday.` This is an ordinary comparison, consistent with dictionary usage rather than an obligatory metaphor.
- `with`: `We [compare the red bike with the blue bike].` Both objects are inside the selected span.
- `against`: `We [compare] the new design against the old one.` The required preposition is visible in the sentence but omitted from the selected target. Chinese selection is only 比较. The shape validator accepts this because it does not verify construction coverage.

The outcome is partial compatibility: ordinary continuous phrases and many slot realizations work, but complete construction selection and bilingual selection granularity are not consistently defined or enforced. A long highlight is not automatically wrong when the authored target is itself a clause; the evaluation must follow target granularity.

## General rules to consider, without per-word exceptions

The user's constraint is explicit: do not encode special requirements for individual words. Keep the expressions above as evaluation fixtures, not branches or mandatory dictionary translations inside the prompt.

1. **Realize dictionary slots.** Treat possessives, person/thing placeholders and pattern ellipses as slots to fill with grammatical referents and actions, preserving required agreement, inflection and argument order. Do not print placeholder abbreviations as ordinary sentence text.
2. **Preserve the construction.** The selected expression must retain its essential fixed parts, particles, prepositions and relationships. Appropriate grammatical realizations are allowed; replacing the construction with its head verb can lose the learning goal.
3. **Define focus by target granularity.** For a separated construction, one minimal contiguous span can include the necessary filled argument between fixed parts. For a clause-level target, the whole realized clause may be necessary. Exclude unrelated modifiers and circumstances. This can fit the existing single-span representation; multiple independent spans would be a separate product decision.
4. **Align the selected meaning across languages.** Match the full selected learning goal, including causative/recipient/temporal relationships, while using natural language. Context outside a highlight cannot always replace a missing part of the selected construction.
5. **Let the authored explanation define sense.** Generate a situation that illustrates that sense with enough context to learn it. Do not invent categorical distinctions between constructions whose usage overlaps. A vague shared explanation can legitimately produce overlapping contexts.
6. **Verify assessment separately.** A later Production check should cover natural slot realizations, inflected forms and acceptable variants without requiring literal abbreviations or accidental example names. No ASR or Judge calls were included in this evaluation.

The current prompt contains historical word-specific examples and preferences. Under the new constraint, a later rewrite should express their underlying principles generally; illustrative fixtures should not become per-lexeme rules. No prompt, parser, schema, grading rule or deployment was changed in this investigation.
