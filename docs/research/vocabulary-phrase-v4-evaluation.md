# Vocabulary expression generation: v4 evaluation

## Change and scope

`learning/providers.py` now uses `lexical-pair-v4` for Generator. It interprets dictionary slots, preserves complete multiword constructions and aligns the scope of both highlighted expressions. It uses general grammatical and semantic requirements, with no word-specific translation rules. The existing two-string wire contract, offset parser, validation and rendering are unchanged. Judge remains `lexical-meaning-v3`.

The scope is a candidate prompt change and an isolated live evaluation. The running web/worker services were not redeployed. No user cards, stored example pairs, jobs, learning records or production configuration were written by the probes. The spec describes the intended v4 behavior; the observations below distinguish that contract from actual model compliance.

## Method

All calls used the deployed Generator endpoint, model and budget configuration, with the candidate provider module injected only into the read-only probe process. Model: `MiniMax-M3.1-Flash`. Each round made one independent call per fixture, two concurrently, without automatic retries. No failed result was discarded. Each saved record includes the temporary source explanation, original final JSON, parsed spans/offsets where valid, rendered HTML, elapsed time and non-secret profile metadata. Each round saves its exact prompt and SHA-256.

The first 18 fixtures exactly reuse the earlier v3 probe: 15 expressions with sense-specific English explanations, plus three comparison patterns sharing one neutral explanation. Nine additional fixtures cover two pronoun-object realizations and seven prior single-word concerns. The explanations are hand-authored evaluation data, not the learner's unprovided original explanations. The pronoun fixtures deliberately specify that discourse context; this is not a word-specific production rule.

## Iterations and limits

| Round | Structurally accepted | Observations |
| --- | --- | --- |
| [Initial v4 candidate](vocabulary-phrase-v4-round1-results.json) | 26/27 | One missing native marker; an invented native location; some overly broad focuses and long tails. |
| [Second candidate](vocabulary-phrase-v4-round2-results.json) | 25/27 | Two missing-marker outputs; some native spans omit participants or absorb an independent object/degree modifier. |
| [Final candidate](vocabulary-phrase-v4-results.json) | 26/27 | See individual semantic observations below; shape acceptance is not semantic approval. |

The final revision adds an explicit marked JSON template and clarifies that both selected spans must cover corresponding participant roles; objects and degree modifiers outside a single-word target remain outside its native focus. Earlier refinements prohibit invented facts and request shorter examples and punctuation outside focuses. These requirements are general, not branches for particular expressions.

There were 81 paid generation calls across three rounds. A different prompt and one random sample per fixture cannot establish a reliability improvement, an accuracy rate or guaranteed behavior. Earlier failures remain visible. The existing validator rejects missing markers; it does not prove grammatical accuracy, sense or bilingual alignment. No parser relaxation, automatic repair or retry loop was added.

## Final-round output

All 15 requested sense-specific expression fixtures produced structurally accepted outputs in the final round. Filled slots, separated pronouns and complete clause targets are represented. This does not mean all 15 are semantically flawless: the full `give ... an idea of ...` construction is retained, but the time circumstance is selected on only one side; the sharing sentence loses an explicit possessive. The neutral `against` control was rejected for missing markers. In the regression set, the native `adventure` focus still includes an unnecessary copula and classifier. The candidate improves the explicit contract but does not consistently enforce it. Further quality work should retain these failures as evidence rather than add per-word exceptions or relax validation.

Bold text represents the model's focus tags, without editorial correction. For rejected output, the original unmarked text is retained. The notes are manual assessments, separate from structural validation.

### Requested expressions

| Target | Temporary explanation | Target sentence | Native sentence | Review |
| --- | --- | --- | --- | --- |
| do one’s studies | To spend time studying and doing academic work. | I **do my studies** after dinner. | 我晚饭后**做自己的功课**。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| at the beginning | During the first part or start of an event or period. | **At the beginning** of the movie, the lights went out. | 电影**一开始**，灯就灭了。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| point out | To draw someone's attention to a fact, detail, or problem. | Could you **point out** the mistake in my drawing? | 你能**指出**我画作中的错误吗？ | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| introduce ... to ... | To tell two people each other's names so they can meet; introduce one person to another. | At the party, Anna **introduced her brother Tom to her friend Li**. | 在聚会上，安娜**把她的哥哥汤姆介绍给她的朋友李**。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| share sth with sb | To let another person use or have part of something with you. | Could you **share your umbrella with me** when it rains? | 下雨的时候，你能**和我共用一把伞**吗？ | Shared participation and full construction are clear; the native sentence loses the explicit possessive your by saying an umbrella. |
| pick sb. up | To go to a place to collect someone, often in a car, and take them somewhere. | I will **pick my sister up** at the station. | 我会去车站**接妹妹**。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| leave … behind | To go away without taking someone or something with you, intentionally or by accident. | I packed all my things, but I still **left my passport behind**. | 我把东西都收拾好了，可还是**把护照落下了**。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| as a result | Because of what happened before; used to introduce the consequence. | The gate was locked, and **as a result**, the workers could not enter the yard. | 大门被锁上了，**因此**工人们无法进入院子。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| give sb. an idea of ... | To help someone gain an approximate understanding or impression of something. | If you watch this short video, it **gives you an idea of what the old town looks like** in winter. | 如果你看这段短视频，它**能让你对老城冬天是什么样子有个大致印象**。 | Causative/recipient meaning and the full construction are retained, but winter is outside the target focus and inside the native focus; the example is also longer than necessary. |
| it is somebody's job to do sth. | To be someone's responsibility to perform a particular task. | **It is Anna's job to water the plants**. | **给植物浇水是安娜的职责**。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| only recently | Not until a short time before now; emphasizes that something did not happen earlier. | The museum **only recently** opened its new wing. | 博物馆**直到最近才**开放了新展厅。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| in demand | Wanted or needed by many people, especially for work, goods, or skills. | Graphic design skills are **in demand** among small businesses. | 平面设计技能在小企业中**很抢手**。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| compare ... to ... | To describe one thing as similar to another, often with an imaginative analogy. | You can **compare a rainbow to a colorful bridge**. | 你可以**把彩虹比作一座彩色的桥**。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| compare ... with ... | To examine two things side by side to identify similarities and differences, such as comparing two products. | Customers can **compare this phone with that phone**. | 顾客可以**把这部手机和那部手机作比较**。 | Preserves with and both objects. The general comparison sense is suitable, but no concrete comparison dimension is illustrated. |
| compare ... against ... | To evaluate something by checking it against a reference value, standard, or benchmark. | **Compare this phone against last year's model**. | **把这款手机和去年的型号作比较**。 | Preserves against and both arguments; last year's model supplies a reference, though an explicit benchmark dimension would make the intended sense clearer. |

### Neutral explanation controls

| Target | Temporary explanation | Target sentence | Native sentence | Review |
| --- | --- | --- | --- | --- |
| compare ... to ... | To examine two things to see how they are similar or different. | Please **compare the new plan to the old plan**. | 请**将新方案与旧方案进行比较**。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| compare ... with ... | To examine two things to see how they are similar or different. | Please **compare these two plans with the one we used last year** before the meeting. | 请在开会前**把这两个计划与我们去年用的那个计划作比较**。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| compare ... against ... | To examine two things to see how they are similar or different. | Compare this report against last year's report to see whether the figures are different. | 把这份报告和去年的报告作比较，看看数字是否不同。 | Rejected: neither sentence contains focus markers. The unchanged validator prevents this pair from being accepted. |

### Pronoun-object checks

| Target | Temporary explanation | Target sentence | Native sentence | Review |
| --- | --- | --- | --- | --- |
| pick sb. up | To go to a place to collect someone and take them somewhere. The person being collected is already known and referred to by an object pronoun. | I **pick her up** at the station and take her home. | 我去车站**接她**，然后送她回家。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| leave … behind | To go away without taking someone with you. The person is already known and referred to by an object pronoun. | We went to the park and **left him behind**. | 我们去了公园，**把他留下了**。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |

### Single-word regression checks

| Target | Temporary explanation | Target sentence | Native sentence | Review |
| --- | --- | --- | --- | --- |
| absorb | If something absorbs liquid, it soaks it up and holds it. | The sponge **absorbs** the spilled water. | 海绵**吸收**了洒出的水。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| adventure | An exciting, unusual, sometimes risky journey or experience. | Climbing the old tower was an **adventure** for the children. | 对孩子们来说，爬那座旧塔真**是一次冒险**。 | Native focus includes the copula and quantity/classifier (是一次) rather than just the lexical meaning 冒险. The old over-broad selection problem is not fully resolved. |
| abnormal | Different from what is usual or expected, especially in a strange or worrying way. | The doctor said that the patient's heartbeat was **abnormal**. | 医生说病人的心跳**异常**。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| adopt | Legally take another person's child into your family and raise them as your own. | The couple legally **adopted** a child and are raising her as their own. | 这对夫妇依法**收养**了一个孩子，并把她当作自己的孩子抚养。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| account | An arrangement with a bank to keep money there and take some out when needed. | I opened a bank **account** so I can keep money there and take it out when needed. | 我在银行开了一个**账户**，可以把钱存在那里，需要时再取出来。 | Conventional lexical focus is correct, but the sentence still contains a long definition-like purpose tail. |
| abrupt | An abrupt change or action is very sudden, often unpleasantly so. | His **abrupt** departure surprised us. | 他**突然**离开，这让我们很吃惊。 | Reviewed for authored sense, grammatical realization, full construction coverage and bilingual focus alignment; no material issue identified in this sample. |
| absorptive | Having the ability or capacity to absorb liquid. | This sponge is **absorptive**, so it quickly soaks up spilled tea. | 这块海绵**能吸收液体**，所以很快就能吸掉洒出的茶。 | Expresses the capacity/property naturally using a modal phrase rather than reducing it to an action noun. |

## Verification and remaining boundaries

- Full Django suite: 75 tests passed in 23.758 seconds after the initial change. The final provider suite passed all 11 tests in 0.166 seconds; the final JSON summary records both runs.
- A provider integration regression test covers filled pronoun slots and clause-level targets through generation parsing, provenance and rendered spans. It verifies application handling, not LLM semantics.
- No schema, queue, scheduler, direction, Judge or UI change. Old examples and frozen presentations are not regenerated or reassessed.
- No spoken-answer/ASR evaluation, physical microphone/browser session or Spanish phrase evaluation was run for this change. In particular, Generator results do not establish that the unchanged Judge handles every realized construction as intended.

The earlier language-usage research and v3 baseline remain in [Vocabulary phrase compatibility](vocabulary-phrase-compatibility.md). Distinct explanations can guide the comparison senses; a neutral explanation need not force artificial exclusive distinctions between prepositions.
