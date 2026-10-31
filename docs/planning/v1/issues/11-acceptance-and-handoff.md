# Define V1 Acceptance Examples and Implementation Handoff

Id: 11
Parent: [Vocab-Learn Browser V1 Decision Map](../map.md)
Type: grilling
Labels: wayfinder:grilling
Mode: HITL
Status: resolved
Assignee: /root
Blocked by: 10, 19

Planning archive: the approved rules, fixtures and 45 cases are consolidated in the [V1 Development Specification](../../../specs/v1.md). Maintain subsequent development requirements and case updates there; this file preserves the reviewer-approved baseline.

## Question

Once upstream decisions are settled, which observable examples establish that V1 fully satisfies the requirements and is ready for implementation? Agree a short acceptance set covering all three front/back paths, voice-only success, five feedback levels, Normal/Forgot timing, three-success graduation, account isolation, manual/CSV entry, statistics, and Compose data recovery.

Include non-English learning content alongside English-only UI/system messages, English code/comments/documentation, ASR/LLM failures or malformed responses, duplicate submissions, cross-day review, and persistence after restart. No additional UI language or selector is required.

Include a multi-blank card answered in one spoken response, a short-sentence answer, AI assessment against one reference answer, and independent progress for two cards targeting the same vocabulary.

Verify immediate reference reveal after submission while processing is still pending, no post-reveal recording replacement, readonly transcript display, cancellation only before submission, same-recording retries, and proceeding unassessed after a technical failure. Next card stays unavailable until assessment or an explicit unassessed exit.

Verify that C is unchanged by speed, a wrong or missing blank makes the whole card B, target recall at the timing boundary is E, and a Cancel does not reset the question clock. Skip remains ungraded and outside accuracy. Next review must format the committed scheduler due time, including an already due item, and must not use the prototype's illustrative interval table.

Exercise the agreed Forgot timeline with a fixed clock: A/B entry, C resetting an existing Forgot streak, success one/two scheduling exactly 24 hours later, success three graduating with preserved FSRS state, missed days preserving streak, and early/duplicate reviews failing to add a success. Normal C must not change application collection. Verify due-only queue priority and session-only deferral of skipped/unassessed cards.

Frontend quality is part of acceptance: carry the user-reviewed visual direction across learning, deck management, accounts, and statistics. Verify coherent typography, spacing, colors, readable card content, keyboard focus, and clear recording/loading/result/error states on the target desktop browsers.

Include Markdown question/explanation from manual entry and quoted multiline UTF-8/BOM CSV: bold, paired underline, formatted multi-blanks, and escaped/code/link literal markers. Check that both display and judging use the same actual blanks; arbitrary HTML, forged cloze elements, unsafe links, and remote image markup must not execute or load. Inline presentation-only changes preserve progress under the stated default, while real content/answer/blank changes reset it and retain history.

Check batch rollback on invalid CSV, duplicate skipping without overwrites, deployer-created account isolation, archive/restore schedule retention, and immutable historical metrics. One card reviewed twice must produce one distinct card and two scored reviews; Skip/technical failures must not affect target recall accuracy.

Distinguish business rules verified offline with fake responses, microphone behavior requiring a real browser, and actual model connectivity requiring valid credentials. Fake responses cannot establish unknown provider capabilities.

Verify independently configured ASR, Judge, and Generator profiles: changing one task's endpoint/model/key/budget must not affect another, while both LLM tasks retain identical MiniMax defaults when no overrides are supplied. Model changes do not rewrite stored examples or completed grades.

Use [Define Generic and Vocabulary Card Learning Units](14-generic-and-vocabulary-units.md), [Define Vocabulary-Direction Grading and Timing](16-vocabulary-grading.md), and [Define Vocabulary Example Pairs and Rotation](15-vocabulary-example-lifecycle.md) for recognition versus production correctness, retained/rotated paired examples, no target leakage on production fronts, generation failure/retry, review ownership, source edits, and preservation of assessed example revisions. Keep Generic Card entry and grading behavior distinct.

The learning-unit, grading, and example-lifecycle decisions are now settled. Include equivalent native wording as complete, partial meaning as C, contextually unsuitable listed synonyms as B, a non-cloze Generic whole-answer unit, and malformed output with missing units as unassessed. Check that both review directions contribute to the one Forgot streak, that C uses Partial recall copy, and that Recall accuracy retains its D/E-over-A-E formula.

Add lifecycle cases for fixed questions/directions across refresh and Skip, one slot per A-E result, unchanged slots on technical failure, no E rotation while still in Forgot, third-D versus third-E graduation, late-candidate rejection, and generation fallback without a score penalty. Reject same-language Vocabulary inputs before source import writes. A valid import survives later provider generation failures, while unprepared sources remain out of study/Due now. Source learning-content edits reset progress but retain old assessed history; wrapper-only Markdown edits preserve it.

Produce acceptance and handoff conditions consistent with existing decisions, not implementation tickets or production code. If an implementation-relevant question remains, create its decision ticket and update dependencies instead of declaring the map finished.

## Accepted V1 acceptance and handoff

Revision: reviewer-follow-up-2. Status: reviewer-approved planning baseline, as confirmed by the user; application acceptance has not been executed. The user authorized incorporating both rounds of reviewer recommendations. The completion/interruption prerequisite is resolved in [Attempt completion and interruption](19-attempt-completion-and-interruption.md).

At approval, this file served as the reviewable implementation entry point, with policy summaries and fixed cases for a reviewer receiving only this file. Linked decisions held the detailed rules. The consolidated specification is now the current development contract. Case results and implementation evidence must be filled in during development; none below claims a passing application test.

### Delivery boundary

Implement in this repository on Python 3.11/Django 5.2 LTS, with English UI/code/documentation, Fieldnotes styling, private accounts, Generic and Vocabulary Cards, and SQLite on local Docker volumes. One application image runs web and bounded worker processes. Caddy supplies LAN-only private HTTPS; client trust/local name resolution are required. ASR, Judge, and Generator have independent configurations. MiniMax defaults and no LiteLLM remain selected.

Use [Generic CSV](../../../examples/cloze-cards.csv), [Vocabulary CSV](../../../examples/vocabulary-cards.csv), and [authoring notes](../../../examples/README.md). Public ingress, other UI languages, same-language Vocabulary training, additional learning modes, model fallback, and a marketplace remain outside V1. This document revision does not implement or deploy the application.

Generic CSV has exactly the unique headers question, answer, explanation; Vocabulary CSV has word, explanation, native_language, target_language. Order may vary; required fields are nonblank, with UTF-8/BOM, standard quoting and multiline content supported. Question/explanation support safe Markdown; answer/word remain plaintext. Initial Vocabulary pairs are English/Chinese, English/Spanish and Spanish/Chinese; Generic content remains language-independent.

Default ASR is MiniMax asr-1.0; Judge and Generator independently default to MiniMax-M3.1-Flash. Their separate endpoints, model IDs, keys and budgets remain server-managed. MINIMAX_API_KEY supplies only the default MiniMax origin; stage overrides and another origin require the configured task credentials. Learner UI has no key/provider settings.

### Review-critical rules

| Topic | Required rule |
| --- | --- |
| Card identity | One Vocabulary Card shares Recognition/Production progress, due time, streak and direction sequence. Distinct valid card instances, including two meanings of the same word, remain independent. Duplicates follow authored identity, not a global word key. |
| First preparation versus rotation | Save valid sources before generation. No valid first pair means a visible Preparing/failed-retry state, no study eligibility and no Due now contribution. A later replacement failure retains the old valid pair and its learning state. |
| Durable generation | Save source plus initial preparation intent/request time/deadline atomically; likewise save an eligible E plus replacement intent. Initial GENERATION_TIMEOUT_SECONDS is 300 per execution, including unclaimed queue time, call and validation/save; GENERATOR_TIMEOUT_SECONDS is a separate 120-second call cap bounded by remaining time. Worker discovery and web/library status/Retry expiry make unstarted/crashed work recoverable without silently repeating an uncertain paid call. Pair/Ready persistence and result replay are idempotent and source-revision guarded. |
| Review units | Render visible blanks and construct ordered judgment units from the same parsed representation. Unit count and identity must match. Zero-blank Generic uses one whole-answer unit. A valid judgment marking a learner's missing answer gives B; provider output missing an expected unit is Not assessed. |
| Generic goal | The authored reference is the recall target. A suitable different expression is C, while equivalent spelling, appropriate forms and natural full-sentence delivery can still be complete. F-G2 specifically retrieves call off; cancel is meaningful but only a suitable substitute. State this goal in the real Judge prompt. Fake partial-output mapping is not evidence of semantic classification. |
| Scored effects | Define learning state L as progress version/FSRS memory, due, collection, streak, direction position, rotation intent, scored reviews, and scored accuracy counts. A technical/unassessed event leaves L unchanged. Operational attempt/error/transcript metadata can still change. |
| Terminal outcome | Assessed and closed-unassessed are competing atomic terminal outcomes. First commit wins. Exit-first rejects all late scored effects; grade-first returns its saved grade and due time. A terminal attempt cannot be retried. A retryable technical failure is nonterminal. |
| Concurrent attempts | Compare attempt state/execution claim plus source revision, the example revision frozen on the presentation and expected logical progress version. Two distinct attempts cannot both consume one progress version. Edits/archives invalidate old work without altering previous completed history. Candidate storage cannot invalidate a locked presentation through unrelated metadata or parent-pointer changes. |
| Rotation boundary | Serialize activation and new-presentation selection. A candidate arriving after the old pair is locked stays pending: no active-pair switch, cue/reference/direction/clock change or false-stale grade. Skip/closed-unassessed retains that cue lock. A later C/D/A/B clears older eligibility; a later qualifying E supersedes it with a fresh intent, discarding its parked candidate. Authorized activation preserves logical progress version, FSRS memory/due, collection, streak, direction position, scored rows and statistics; active example revision and rotation intent may change. |
| Queue and run | Only due, ready, active cards are eligible: due Forgot, then reviewed due Normal, then ready unseen Normal; within a tier use earliest due then stable ID. Explicit Start review/new run creates R1; refresh/reconnect/Resume retains its identity and saved Skip/closed-unassessed deferrals. Finish shows no selectable cards without changing due times or auto-starting R2. Only explicit new run clears run-local deferrals. Global Due now may remain positive. |
| Waiting and Retry | Initial ASSESSMENT_TIMEOUT_SECONDS is 300 per execution, including queue waiting, conversion, ASR and Judge. Stage caps remain ASR 60/Judge 120 seconds, bounded by remaining total time. Web status/exit routes enforce expiry even without a worker. Explicit Retry gets a new execution claim/deadline, not a new response or audio-retention window. |
| Worker capacity | Claim expiry alone is insufficient: bound actual cleanup/recovery of conversion children, provider I/O and slot permits. Initial WORKER_CLEANUP_GRACE_SECONDS is 10 after expiry. Prove a healthy queued job completes after every configured slot is faulted, without manual restart or unbounded pools. A Future wait timeout or HTTPX inactivity limits alone are not a whole-execution deadline. Remote computation/billing cancellation is not promised. |
| Confirmed exit | Healthy checking keeps Next disabled. Failure/status-communication error or the waiting deadline exposes recovery. The server confirms assessed or closed-unassessed before the UI claims that outcome. A lost exit response is recovered idempotently. Tab close, cancelled fetch or disconnected UI alone does not close the server attempt. |
| Presentation clock | Same-presentation refresh preserves valid elapsed time and permission exclusions; same-page Cancel never resets it. An unrecoverable clock becomes an explicit unscored interruption, with an explicit Restart question creating a new presentation using the same cue/direction. Genuine later reviews have new clocks. Submitted timing is frozen. |
| Two time measures | Recall duration ends at browser Stop & check and excludes permission/upload/provider/retry waiting. Scheduling uses the original server UTC receipt of the accepted submission/action, never Judge completion. A 24-hour step means exactly receipt + 24 hours. |
| Pending permission | Cancel is usable while getUserMedia remains pending. Invalidate an obsolete request. Late grants stop every returned track without recording; late rejections cannot overwrite newer UI. Logical cancellation does not dismiss the browser permission prompt. |
| Profile changes | Queued work snapshots settings when dispatched; an in-flight call retains that snapshot. Explicit Retry can use current settings while recording/question/timing remain fixed. Model changes do not rewrite saved examples or completed grades. |
| Recording durability | Persist successful transcript data before relying on judge-only recovery. Delete audio after the assessed result commits, not merely after ASR returns. Failed/interrupted audio expires at original submitted_at + 24 hours; retry/restart/restore never extend it. Closed-unassessed remains terminal even if text exists. |
| Saved UI state | Next review shows the committed scheduler timestamp, including Due now; no prototype interval table. Restore preserves progress/due/example state, making an overdue ready card due again. |
| Delivered backup | Every restore case uses artifacts created by the exact delivered cold-backup command or versioned operator steps, including stopping writers, durable-volume/manifest handling and audio exclusion. Record that procedure version. A special test-only snapshot cannot certify the deployed instructions; online backup is outside V1. |

The 300-second execution budgets and 10-second cleanup grace are initial engineering defaults, not measured service promises. At or after execution expiry, uncommitted work fails technically and its claim is invalid; a result already committed before expiry remains authoritative. No timer or callback can fabricate a successful unassessed exit while the server is unreachable.

| Grade | English copy | Goal-aware rule | FSRS rating |
| --- | --- | --- | --- |
| A | Needs a refresh | Explicit Forgot action | Again |
| B | Needs practice | Wrong/missing required answer under a valid complete judgment | Again |
| C | Partial recall | No incorrect unit, but the goal remains materially partial or only a suitable substitute was recalled | Again |
| D | Correct recall | All units complete, response duration above T | Good |
| E | Quick recall | All units complete, response duration at/below T | Easy |

Skip/closed-unassessed have no rating or scored accuracy contribution. For Vocabulary Recognition, complete native meaning satisfies the goal; Production requires the target expression or appropriate form. The initial budget is T = max(12, ceil(5*N + Q/20 + R/5)) seconds, where N is the actual blank count or 1 for a whole-answer task, Q counts visible non-whitespace Unicode code points excluding actual blanks/Markdown syntax/hidden back content, and R counts the frozen reference. Never let speed upgrade partial/incorrect meaning.

### Fixed input fixtures

These are hand-authored test contexts, not claimed Generator output or exact sentences a live Generator must reproduce. Learning content below is deliberately multilingual; all surrounding system instructions and feedback remain English.

<!-- learning-fixtures:start -->

| Fixture | Frozen authored source / displayed context | Reference or highlighted expression |
| --- | --- | --- |
| F-G0 | Generic question: What is two plus two? | Answer: four. No actual blanks; one whole-answer unit; initial fast budget T = 12 seconds. |
| F-GS | Generic question: Why did you postpone the meeting? | Answer: To give everyone more time to prepare. A whole spoken sentence is the reference; explanation defines postpone as moving an event to a later time. |
| F-G2 | Generic question: I had to **{{blank}}** the meeting because I was <u>{{blank}}</u>. | One reference: call off; feeling unwell. The goal is recall of these authored expressions: cancel is a suitable substitute for unit 1, not the target. Visible/judged units are 1 and 2, addressed by one utterance. |
| F-V1 | Word: misunderstanding; target English/native Chinese. Explanation: A misunderstanding is a problem caused when people do not understand each other correctly. Target sentence: A small misunderstanding made them stop talking to each other. Native sentence: 一场小小的误会让他们不再和对方说话了。 | Highlight misunderstanding / 误会. Recognition accepts complete native meanings such as 误会 or 彼此理解错了; Production retrieves misunderstanding. |
| F-V2 | Same English word/sense and target sentence as F-V1; native Spanish. Native sentence: Un pequeño malentendido hizo que dejaran de hablarse. | Highlight misunderstanding / malentendido. Native complete equivalents include malentendido or entenderse mal. |
| F-V3 | Word: malentendido; target Spanish/native Chinese. Target sentence: Un pequeño malentendido hizo que dejaran de hablarse. Native sentence as F-V1. | Highlight malentendido / 误会. |
| F-VP | Word: postpone; target English/native Chinese. Explanation: reschedule an event specifically to a later time, without cancelling it. Sentence: We postponed the meeting from Monday to Friday. Native: 我们把会议从星期一推迟到星期五。 | Highlight postponed / 推迟. Recognition: 推迟 is complete; 改时间 is the deliberately partial fixture because it omits the required later-time meaning; 取消 contradicts the sense. |
| F-VBANK | Word: bank; target English/native Chinese; intended sense land beside a river. Source note mentions shore and financial institution, explicitly noting the latter is another sense. Sentence: We sat on the bank of the river. Native: 我们坐在河岸上。 | Highlight bank / 河岸. Production bank is complete; contextually suitable shore is C; financial institution is B despite being mentioned in the source note. |
| F-VBANK2 | A distinct bank source; intended sense a financial institution. Sentence: The bank approved my loan. Native: 银行批准了我的贷款。 | Highlight bank / 银行. It is not a duplicate of F-VBANK and has independent progress. |

<!-- learning-fixtures:end -->

F-MD is this exact Generic question source, with one reference answer alpha; beta:

~~~~markdown
Use **{{blank}}**, then <u>{{blank}}</u>.

Literal marker: \{{blank}}.
Inline code: `{{blank}}`.

~~~text
{{blank}}
~~~

[guide](https://example.test/{{blank}})

<span class="cloze-blank" data-blank="99">fake</span>
~~~~

Only two actual blanks exist, with ordered identities 1 and 2. Escaped/code/link-destination markers and the authored counterfeit span add no judgment unit or live cloze element. Expected IDs come from the parsed question, not a second regex or a reparse of rendered HTML.

Use controlled clocks: t0 = 2030-01-01T12:00:00Z is server acceptance, epsilon = 0.01 seconds, and r is the expected progress version. Inject deterministic provider responses or scheduler results where a case isolates application behavior. Real FSRS integration retains its defaults/fuzzing and separately verifies saved library state; a fixed test result is not a production interval table.

### Core acceptance cases

| Case | Preconditions and input | Expected observable result |
| --- | --- | --- |
| ENTRY-CSV-DEDUP | Independent empty deck D; import F-V1/F-V2, including BOM/multiline variants. Repeat exactly that import into D. | First import creates two sources; repeat skips two without overwrite or additional executable generation work. Generic three-column and Vocabulary four-column schemas remain distinct; errors are English and record-specific. |
| ENTRY-CSV-ROLLBACK | Independent deck Atomic contains only known source Z (F-G0); F-V1/F-V2 are absent, including archives. Import valid F-V1, valid F-V2, then invalid C (F-V3 with native Spanish, making Spanish/Spanish). | Failure leaves F-V1/F-V2 absent and Z unchanged, with no generation intent or provider call from this batch. The first two rows would genuinely create new sources if C were valid; duplicates in other decks cannot make this test pass. No partial success feedback. |
| PREP-INITIAL | Imported F-V1/F-V2; Generator succeeds only for F-V1. Retry F-V2 using a complete valid pair. | Both sources remain. Initially ready/Due now counts include only F-V1; F-V2 is visible with failure/retry and never opens an empty question. Retry readies the same F-V2, adding no duplicate or scored review. |
| FLOW-ACTIONS | Separate eligible F-G0 presentations exercise Skip, Speak/Stop, and Forgot; race duplicate/conflicting front actions for the same presentation. | Skip reveals with no score; Speak commits fixed audio then reveals before processing; Forgot reveals and commits A. One front action wins per presentation; no later action overwrites it. Only a spoken submission can yield B-E. |
| GENERIC-WHOLE | Speak F-G0; ASR returns four and a complete whole-answer judgment. Speak the full F-GS reference in a separate eligible presentation. | Zero gaps do not block entry/judgment. One whole-answer unit is assessed; phrase/sentence references remain valid. Typed transcript edits cannot submit a grade. |
| GENERIC-MULTI | Speak F-G2 once: call off, feeling unwell. Fake judgment reports both units complete. Variant: cancel, feeling unwell, with a valid partial/suitable-substitute outcome on unit 1 and complete unit 2. | One immutable recording addresses all blanks. Complete case is D/E by budget; substitute case is C at both short and long times. No separately scheduled blank items. This tests application mapping, not the model's semantic decision. |
| GENERIC-TARGET-LIVE | Give the real default Judge frozen F-G2 units/reference, the explicit authored-expression recall goal, and controlled ASR text call off, feeling unwell versus cancel, feeling unwell. Also include natural full-sentence delivery using the targets. | Target units are complete; cancel makes unit 1 partial/suitable substitute while unit 2 stays complete, yielding C regardless of speed. Full-sentence delivery does not force a literal transcript match. Record real outputs and investigate prompt/model disagreement; a prelabelled fake cannot pass this case. End-to-end audio/ASR evidence remains separately required. |
| VOCAB-GRADING | Test frozen F-V1/F-V2 equivalent native responses, F-VP complete/partial/incorrect responses, and F-VBANK target/suitable substitute/wrong-sense responses. | Full native equivalents receive D/E by time; F-VP partial is C regardless of speed and wrong sense is B. F-VBANK substitute is C; wrong-sense listed expression is B. Natural concise equivalents do not require verbatim dictionary recitation. |
| LANGUAGE-DIRECTIONS | F-V1, F-V2 and F-V3 each run Recognition and Production. Separately test all three front actions. Reject target Spanish/native Spanish before writes. | Cover three language pairs, two goals and three action paths as distinct dimensions. ASR hint follows expected response language. Production front/title/payload does not reveal its target; both directions share one card's progress. |
| SRS-TIMELINE | A/B at t0, due success one at t0 + 1 minute, then due successes two/three at their saved due times. Also test Forgot C, missed days, Normal C, future/duplicate attempts. | A/B yields Forgot 0 due t0 + 1 minute. Success one/two each yields +24 elapsed hours; success three graduates with saved FSRS memory/due. C resets only an existing Forgot streak; Normal C stays Normal. Missed days preserve streak; future/duplicate/stale work cannot add success. |
| PAIR-ROTATION | Normal E; first/second Forgot E; third-success D versus E; failed replacement; delayed candidate after B or source edit. | Normal E unlocks a new entire pair for a later review. First/second Forgot E keep it frozen. Third D graduates with old pair; third E unlocks replacement. Failed replacement uses old valid pair; stale work never activates. Activation alone preserves logical progress version, FSRS memory/due, collection, streak, direction position, scored rows/statistics; active pair revision and rotation intent may change at the authorized boundary. |
| QUEUE-RUN | At fixed t0, run R1 has A due Forgot, B reviewed due Normal, C future Normal, D Preparing, E archived, F ready unseen Normal, G future Forgot. In separate branches Skip A or commit closed-unassessed A. Refresh/reconnect/Resume R1, then defer B/F until nothing is selectable. Finally explicitly start R2. Include a within-tier earlier-due/stable-ID tie variant. | Order is A before B before F; C/D/E/G never appear. A is excluded only from R1 after either deferral, with progress/cue/direction unchanged. Resume preserves deferrals. Finished R1 stays finished on refresh and does not auto-create R2, even though global Due now remains positive. Explicit R2 makes A eligible first again with its retained cue/direction. Due timestamps are never rewritten by run operations. |
| DIRECTION-BLOCK | Fix a shuffled two-slot block. Refresh, Cancel, Skip and failed processing; then commit A-E once. Continue through both slots. | Retain cue/direction until a scored result; only one committed A-E consumes a slot. Wrong answers and Forgot also consume one. A new example does not reshuffle the block. After both slots, next shuffled block has one of each direction. |
| ACCOUNT-METRICS | Two nonstaff learner accounts; cross-owner detail/mutation/status/import requests; two scored reviews of one card plus Skip/error; archive one reviewed card. Trusted deployer account administration is separate. | Ownership applies throughout learner views, including metrics. Framework login/logout/reset/CSRF/session behavior holds. Counts are one distinct card/two reviews, with D/E-over-A-E accuracy excluding Skip/errors. Archive removes active eligibility but preserves historical counts. Dates use Asia/Shanghai over stored UTC. |
| PROVIDER-CONTRACT | Fake native MiniMax and OpenAI-compatible ASR endpoints; expected language hints; HTTP-200 embedded error, rate/auth failure, empty transcript, malformed/missing units, refusal, length termination and empty final text. Also return one whole-response JSON fence and separate reasoning text. | Correct multipart route/header versus form placement; safe stage-specific errors with unchanged L. Valid fenced JSON can parse; arbitrary prose/reasoning is not a judgment. Retry uses fixed input/cached transcript only while nonterminal; no hidden retries, fallback, exposed secrets or typed-answer bypass. |
| AUDIO-NORMALIZE | Complete target-browser recordings with their actual MIME, plus invalid/undecodable input and files beyond the configured 500-second/50-MB ceiling. | Decode and normalize accepted input to mono 16-kHz 16-bit PCM WAV before ASR; changing an extension/MIME is not conversion. Invalid/excess input fails technically without truncating an answer or changing L. Final MediaRecorder data is collected before submission. |
| MARKDOWN-UI | Manual and CSV question/explanation use F-MD and ordinary formatting; try unsafe HTML/links/images. Navigate all selected desktop pages. | Safe bold/underline, Unicode, code and lists; no executable injected HTML, remote image loads, or fabricated blanks. Fieldnotes styling, readable content, keyboard focus, recording/loading/error states and English UI are consistent across login/library/review/statistics. |

### Race, interruption, and recovery cases

These cases inspect learning state L before and after the controlled event, not only HTTP success or the number of provider requests. Operational failure rows are allowed; additional scored effects are not.

For restore cases, establish the specified durable stage with controlled faults, then run the delivered cold-backup procedure. Verify the resulting artifact actually contains that stage. Restore it into fresh volumes using the delivered steps, with the original hostname/CA identity and required versions. A manually assembled database copy is not equivalent evidence.

| Case | Controlled order / fault | Expected observable result |
| --- | --- | --- |
| EXIT-FIRST | A status-communication failure exposes recovery while original Judge work is still valid. Server commits Proceed unassessed, then the old result arrives. Repeat exit and attempt Retry on the old ID. | Terminal closed-unassessed. L is unchanged; no late grade/statistics/slot/rotation effect. Exit is idempotent; old ID cannot retry. A legitimate later review has a new attempt while retaining pending cue/direction. |
| GRADE-FIRST | Worker commits assessment before the exit transaction. Simulate the UI not yet having received the result. | Exit returns that stored assessment and due. UI shows the actual grade, not a contradictory unassessed state. Exactly one scored result. |
| EXIT-ACK | Exit commits but its HTTP response is lost; also test tab close or fetch cancellation without an exit commit. | Read/repeat recovers the committed terminal result. An unconfirmed disconnection is not presented as a confirmed neutral exit; eligible work may finish until its deadline. |
| NEVER-STARTED | Accepted execution at t0 is never claimed. Poll at t0 + 300 seconds with no worker. | Web route invalidates the expired execution and exposes Retry/Proceed unassessed; Next is not permanently blocked by a dead worker. L is unchanged. |
| EXPIRED-EXECUTION | Timeout/failure invalidates execution e1. Explicit Retry starts e2. Deliver e1's late ASR/Judge result before/after e2 completes. | Old claim cannot satisfy e2 or alter L. e2 uses frozen input and its own deadline. Retry changes neither original receipt time nor audio expiry. No hidden provider retry/fallback. |
| PAIR-LOCK-RACE | A prior eligible Normal E authorized rotation I0 for ready pair P0; its failed execution left I0 retryable. Explicit Retry at next due time minus 1 second starts a valid 300-second execution. At due time the presentation locks P0 because no candidate is ready. Deliver P1 two seconds later, then submit a complete P0 answer while all claims/revisions remain valid. Run fast E and slow D branches, plus Skip/closed-unassessed retention variants. | P1 is parked under I0; active P0, displayed question/reference, direction, clock and logical progress version do not change merely on arrival. The valid P0 response commits once instead of becoming stale because of candidate metadata. D clears I0; eligible E creates I1, discarding I0/P1 rather than silently reauthorizing it. Skip/closed-unassessed retains the unresolved P0 lock; P1 cannot activate between those attempts. |
| GEN-UNSTARTED | At t0 commit a new source plus initial preparation intent/request/deadline, then crash before the in-memory wakeup or dispatch. In one branch restart the worker before expiry; in another leave it down and request library/status at t0 + 300 seconds. | Durable work is discoverable without that wakeup and executes if still valid. With no worker, the web route makes expiry visible and exposes explicit Retry; no permanent silent Preparing. Source remains, no empty question/Due now contribution, and expired unclaimed work cannot later activate. |
| GEN-CLAIMED | Claim initial generation g1, crash before a valid pair commits, reach its execution deadline, then explicitly Retry as g2. Deliver a late g1 result before/after g2's valid result. | Status/Retry expires g1 without requiring a live worker. g2 uses the current source/intent and a new claim/deadline. g1 cannot save/activate or satisfy g2; no silent repeat of uncertain paid work. Until g2 succeeds, initial preparation stays outside study; a rotation variant retains the old ready pair. |
| GEN-COMMITTED | Commit the valid initial pair and Ready/active link, then crash before work acknowledgment. Restart/replay that job. Repeat for a saved rotation candidate while a presentation is locked. | Return/reuse the one accepted saved result without another provider call, pair revision, scored row or active-pair duplication. Initial Ready/pair persistence is atomic; rotation replay respects the retained lock rather than forcing activation. |
| GEN-STALE | Submit generation for source revision 1; change its learning content to revision 2 while work is pending, then deliver the old valid pair. Also deliver a result for a superseded rotation identity. | Old output cannot make revision 2 Ready or replace its pair, and superseded rotation cannot activate. Revision 2 keeps its own preparation/retry path. Completed historical snapshots and independent cards remain unchanged. |
| WORKER-CAPACITY | In an isolated test set one worker slot (or occupy every configured slot), execution budget 5 seconds and cleanup grace 1 second. Fault work starts at second 0; enqueue a healthy 1-second job at second 4, giving it its own deadline at second 9. Separately stall a conversion child and a provider stream that stays active below inactivity timeouts. | Faulted work expires at second 5; actual cleanup/reaping, I/O/permit release or bounded automatic replacement finishes by second 6. Healthy work completes by second 7, before its own deadline. Record resource/capacity evidence, not just an expired claim or success through a spare slot. No manual restart/unbounded pools; an injected late old result is still fenced. Production defaults remain 300/10 seconds. |
| TWO-ATTEMPTS | Two tabs create different attempt IDs against card progress version r and both yield complete results; commit each possible winner order. | Only one consumes r and creates a scored review/streak/slot change. The loser is stale/unassessed. Same-attempt deduplication alone does not pass. |
| SOURCE-EDIT | F-G0 is submitted at source revision 1. Another tab changes question/reference to two plus three/five and creates revision 2/fresh progress. Deliver the valid old judgment. | New progress stays fresh; old result cannot score/advance it. Prior completed history remains. Equivalent late-work protection applies across archive/restore. |
| SAME-WORD | F-VBANK and F-VBANK2 are distinct valid ready cards. Review only F-VBANK. | The other card's due, memory, collection/streak, direction, pair and history are unchanged. Shared word text does not merge their identities. |
| UNIT-IDENTITY | Parse/render F-MD and capture actual visible cloze IDs plus expected Judge unit IDs. F-G2 valid output marks unit 2 unanswered; another output omits unit 2 entirely. | Exact visible/expected sets are both {1,2}. Learner-missing case is whole-card B; provider-missing case is Not assessed with unchanged L/accuracy. |
| CLOCK-BOUNDARY | F-G0 complete response at 11.99, 12.00 and 12.01 seconds; F-VP's labelled partial response at 2 and 60 seconds. | Complete outcomes are E, E and D. Partial stays C. Recorded budget/duration explain the result. |
| CLOCK-REFRESH | Same presentation: 9 seconds elapsed, refresh gap 2 seconds, then 1 second to Stop, with no permission wait. Include same-page Cancel and a separately new review. | Same presentation retains 12 total seconds rather than resetting. Cancel does not reset. A genuinely new presentation gets its own clock; cue/direction retention is independent. |
| CLOCK-LOST | Refresh cannot restore valid timing or an open permission-wait interval. | Old presentation is explicitly interrupted/unscored, with usable Restart question or Skip/Forgot paths. Only explicit new presentation starts a clock. No fabricated duration/E result; submitted attempts instead retain frozen timing. |
| DELAY-ANCHOR | Complete response duration 11 seconds, T=12; Forgot streak 0, server receipt t0. Vary only ASR/Judge completion delay. Then vary upload delay so server receipt is t1. | All complete responses remain E. First-success due is t0 + 24 hours regardless of processing delay; in the upload variant it is t1 + 24 hours. The separate response duration remains 11 seconds. |
| PERMISSION-PENDING | Permission promise never settles; Cancel; start a newer acquisition; deliver old grant/rejection. Also test denial/device failure. | Waiting UI is cancellable without a callback. Old grants stop every track, never record; old rejections do not replace new state. Permission wait is excluded; no wrong-answer grade. |
| RESTORE-NO-AUDIO | Use the delivered cold-backup command/steps after fixed submission but before durable transcript; audio volume is excluded. Restore with absent audio. | Explicit technical/retry-expired state and unassessed exit/new-review path, not permanent Pending or B. No replacement recording is accepted for that old ID. Evidence identifies the actual backup procedure/artifact versions. |
| RESTORE-TRANSCRIPT | Back up with the delivered procedure after durable ASR text but before Judge completion. Restore with original audio absent and a nonterminal attempt. | Judge-only Retry uses saved text and frozen prompt; ASR is not called. If the attempt was already closed-unassessed, it remains closed instead. No private test-only snapshot substitutes for the delivered procedure. |
| RESTORE-COMMITTED | Result/L committed but worker acknowledgment absent; use the delivered cold-backup procedure, restore and replay request. | Return saved grade/due. No second scored row, schedule update, slot consumption, or rotation trigger. Durable volume/manifest and CA recovery follow the same operator steps. |
| AUDIO-COMMIT | Pause/crash after ASR returns but before transcript save; separately crash after transcript save before grade; then after grade commit before cleanup. | The only audio is not deleted merely on ASR return. Durable transcript enables later recovery. After a scored commit, cleanup can safely remove audio and result replay still works. Original expiry remains an independent limit. |
| AUDIO-TTL | Retry/restart/restore near original t0 + 24 hours; then use expired/missing audio. | Submission/expiry do not move. No new ASR after expiry; cached-text Judge retry remains allowed only for nonterminal attempts. Expiry never alters L. Startup/periodic deletion respects powered-off-server limitations; backups exclude audio. |
| NEXT-REVIEW | Persist a scheduler due S and redisplay/retry result. For B at t0 use S=t0 + 1 minute and read at t0 + 2 minutes. | UI derives from saved S, not grade-specific prototype constants. The elapsed example shows Due now without rewriting S or adding a review. |
| ARCHIVE-RESTORE | Archive an overdue ready card with saved progress, pair and direction; restore it. Test wrapper-only and real source edits separately. | Restore retains state and re-enters eligibility at its saved due. Wrapper-only edits preserve progress; learning-content edits reset it and invalidate old work while preserving completed snapshots. |
| PROFILE-DISPATCH | Change only Judge settings; run queued/dispatched/new-Retry cases. Repeat for Generator and ASR; retain completed grades/examples. | Other profiles do not change. In-flight call retains dispatch metadata; queued/new execution uses settings at dispatch. Cached ASR keeps provenance. No retroactive regrading/regeneration and no cross-origin default-key leakage. |

### Required verification layers and evidence record

| Layer | Required evidence |
| --- | --- |
| Offline application | Controlled fake transports, canonical unit/identity checks, actual file-backed SQLite race tests, atomic commits and recovery. Use both orderings in competing-result cases and actual different attempt IDs. Include worker capacity/resource recovery with all configured slots faulted; mocked claim expiry alone is insufficient. |
| Target browser | CDP where suitable plus actual desktop Chrome/Edge microphone/private-certificate checks, pending permissions, stale streams, immutable recording/reveal, focus and Fieldnotes screenshots. |
| Real provider | Exact selected profiles/defaults, real browser audio conversion/ASR in English/Spanish/Chinese, default Judge unit-complete responses and qualitative grading including GENERIC-TARGET-LIVE, and Generator quality for all three supported pairs. |
| Deployment | Actual image, LAN binding/hostname/CA trust, persistent restart, temporary-audio cleanup, and fresh-volume restore at each listed processing stage from artifacts produced by the exact delivered cold-backup procedure. Record the procedure version and manifest/exclusions. |

Each executed variant records: case ID, implementation/image revision, fixture/source/example/progress revisions, exact input/clock/fault order, expected UI and L changes or nonchanges, observed result, test/log/screenshot reference, and pass/fail/blocked status. Rotation records enumerate preserved progress/scored fields and permitted pair/intent changes rather than requiring whole-L equality. Capacity cases include occupied slots, deadlines and cleanup evidence; restore cases identify the delivered procedure version and artifact. A blocked or unrun layer is disclosed, not counted as passed. A live-generated pair is reviewed for the intended sense, alignment, simple context, valid highlights and no Production answer leakage; it need not equal the hand-authored fixture sentence.

Existing 192 FSRS integration cases, 57 Markdown checks and bounded prototype CDP checks retain only their recorded scope. They do not prove live-model grading, the production app, actual client certificate trust or restoration. Do not invent a language-accuracy percentage from these small cases. Agree fixture labels/rubrics before live evaluation, record model disagreement for investigation, and resolve representative core-case failures before declaring V1 usable.

### Implementation order and capability gate

1. At the start of implementation, run a small real-capability probe in parallel with the first minimal fake-provider review slice: real browser recording to normalized audio to default ASR/Judge, plus valid Generator output for each supported language pair and both review goals. Freeze the actual profile parameters, sample inputs, expected meanings/unit outputs and deadlines in its evidence.
2. The current Judge/Generator defaults are independently configured 8192 completion tokens including reasoning, 120-second stage deadlines, and default MiniMax reasoning behavior. Use max_completion_tokens. Do not assume short final JSON means little total generation; inspect final content/finish reason and validated units. Adjust the documented profile only on evidence, preserving the selected default model unless explicitly changed.
3. Build out framework/schema/auth/source/rendering and a complete fake-backed review/atomic-progress path, then integrate durable worker/provider execution, supporting Fieldnotes pages/metrics, and Compose/TLS/cleanup/restore. Keep the real-provider probe early rather than postponing the core feasibility risk until broad UI work is finished.
4. If account access, conversion, unit-complete output or representative meanings fail the probe, report the blocker and resolve it before broad construction. Keep a full live/browser/deployment pass before application acceptance.

The probe is an implementation-phase gate, not a claim it ran during planning and not an instruction to make paid calls during this documentation revision. The handoff reports setup/account reset, both import schemas, three task settings, LAN root trust/name resolution, Compose/restart, expiry behavior and backup/restore. Detailed rules remain in their linked decisions; this checklist makes their pass/fail expectations explicit.

### Reviewer follow-up traceability

| Reviewer topic | Explicit coverage in this revision |
| --- | --- |
| Initial versus replacement generation failure | PREP-INITIAL and PAIR-ROTATION; source success and ready/due eligibility are separate |
| Exit/late result and indefinite processing | EXIT-FIRST, GRADE-FIRST, EXIT-ACK, NEVER-STARTED, EXPIRED-EXECUTION; terminal/state rules above |
| Distinct concurrent attempts and content edits | TWO-ATTEMPTS, SOURCE-EDIT and saved revision tuple |
| Independent same-word cards | SAME-WORD with two nonduplicate authored senses |
| Visible/judged units and two missing-unit meanings | F-MD, UNIT-IDENTITY, GENERIC-WHOLE and GENERIC-MULTI |
| Refresh, Cancel, speed boundary and time anchors | CLOCK-BOUNDARY, CLOCK-REFRESH, CLOCK-LOST and DELAY-ANCHOR |
| Saved Next review, archive restore, profile history | NEXT-REVIEW, ARCHIVE-RESTORE and PROFILE-DISPATCH |
| Actions, language pairs, partial meaning, unsuitable synonym | FLOW-ACTIONS, LANGUAGE-DIRECTIONS and VOCAB-GRADING |
| Early real-capability check and MiniMax budget | Implementation order/capability gate; current defaults disclosed rather than guessed inadequate |
| Restore in-flight work and audio deletion/expiry | RESTORE-NO-AUDIO, RESTORE-TRANSCRIPT, RESTORE-COMMITTED, AUDIO-COMMIT and AUDIO-TTL |
| Fixed evidence and indefinitely pending permissions | Named fixtures/case variants, evidence record, PERMISSION-PENDING |

### Second-review follow-up traceability

| Reviewer topic | Explicit coverage in this revision |
| --- | --- |
| Candidate arrives after the old question is locked | PAIR-LOCK-RACE; frozen presentation identity stays valid, candidate stays pending and cannot cause a false-stale result |
| Rollback must detect actual partial writes | ENTRY-CSV-DEDUP and independent ENTRY-CSV-ROLLBACK; two absent valid sources, a later invalid row, preserved Z and no generation leakage |
| Due tiers and current/new run deferrals | QUEUE-RUN; explicit run lifecycle, resume persistence, no automatic restart of an exhausted run |
| Generation before dispatch, after claim, after commit and after edit | GEN-UNSTARTED, GEN-CLAIMED, GEN-COMMITTED, GEN-STALE; atomic intent, 300-second whole-execution budget and web-driven expiry/retry |
| Expired work must return bounded worker capacity | WORKER-CAPACITY; all slots occupied, real cleanup/recovery evidence, healthy queued job completes before its own deadline |
| Generic call off versus cancel and fake-provider limits | Explicit Generic goal, F-G2, offline GENERIC-MULTI mapping and separate GENERIC-TARGET-LIVE classification; accepted C is preserved |
| Rotation invariants versus entire L equality | Rotation boundary and PAIR-ROTATION enumerate stable progress/scored fields while permitting active-pair/intent transitions |
| Actual delivered backup procedure | Delivered backup rule, all three RESTORE cases and deployment evidence; exact versioned cold-backup steps produce the artifacts |

## Comments

The earlier external-review assessment separated existing rules needing acceptance cases from missing lifecycle details. The user then explicitly requested applying those recommended document revisions and sending this file for another reviewer pass. Completion/interruption semantics and upstream contracts were synchronized, while this handoff remained claimed until review approval. No application implementation or runtime acceptance tests have been performed by this documentation task.

The user subsequently authorized applying the [second-review assessment](../../../reviews/v1-reviewer-feedback-assessment-round2.md). Revision reviewer-follow-up-2 incorporates its recommended cases and synchronizes scheduling/run, generation, worker, grading, configuration and backup rules upstream. The Generic call-off/cancel outcome remains C under the accepted authored-target rubric, with real semantic classification separated from fake mapping. This revision defines 45 named cases; none is a claimed application pass.

## Answer

The user confirmed that the reviewer approved revision reviewer-follow-up-2. The documented V1 requirements, boundaries, implementation order and 45 acceptance cases are accepted as the planning handoff. This resolves the final decision ticket and completes the decision map; no further in-scope planning question is outstanding. Runtime implementation and the real-provider, browser and deployment acceptance layers remain future development work, not results implied by this approval.
