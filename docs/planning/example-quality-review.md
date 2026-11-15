# Example quality review — implementation plan

Implementation of issue #4: one mandatory Example Quality Review after example generation,
accepting, repairing or replacing the whole pair before deterministic validation and persistence.

## Decisions carried into the implementation

- One reviewer call per usable generator candidate. The call diagnoses, repairs and internally
  rechecks; there is no second review call, no third model call and no unreviewed fallback.
- Accepted pairs stay byte-identical; repaired pairs may replace both sentences with an unrelated
  scene retaining the authored expression, sense and word class.
- Fail closed on rejection, timeout, malformed output or failed final validation. New cards stay
  unready; existing pairs and completed teaching details are preserved. Retry is explicit.
- Default roles: `glm-5.3-flash` generation (Zhipu `zhipu` protocol, explicit key) →
  `MiniMax-M3.1-Flash` review (MiniMax `minimax` protocol). Both send explicit thinking
  (`enabled` / `adaptive`) and `reasoning_effort=max`; each role is independently configurable via
  `GENERATOR_*` / `EXAMPLE_REVIEWER_*` including exchanged providers.
- `GENERATION_TIMEOUT_SECONDS=420`, starting at worker claim, shared by optional vocabulary
  completion, generation and review. No stage gets a fresh window; claimed deadlines stay fixed.

## Wire contracts

Generator (unchanged): exactly two nonempty bounded sentence strings; source clarification output
fails before review. Repairable focus-marker defects are permitted through to review.

Reviewer (`EXAMPLE_REVIEWER`, prompt `example-review-v1`):

```json
{"verdict":"accept|repair|reject",
 "issues":[{"rule":"scope","detail":"Concrete input defect"}],
 "pair":{"target_sentence":"...","native_sentence":"..."}}
```

- Exact envelope keys; at most 8 findings; rules limited to `source`, `alignment`, `scope`,
  `language`, `cue`, `format`.
- `accept`: empty findings and strings identical to the candidate.
- `repair`: nonempty findings and a changed pair (compared on trimmed strings).
- `reject`: nonempty findings and `pair` null; retryable quality failure, not invalid content.
- Only the source plus candidate are sent; generator identity, earlier scores, expected repairs and
  learning history are excluded.

Final deterministic checks (markers, Chinese script, answer leakage, rotation non-repetition) run
after review and attribute to `EXAMPLE_REVIEWER` when they fail.

## Module boundaries

- `learning/providers.py` keeps the deep module: callers receive the final validated pair and
  provenance or a `StageError`. `generate(source, p=None, *, reviewer=None, budget_seconds=None)`;
  omitting `reviewer` never bypasses review; omitted profiles resolve task configuration.
- `learning/work.py` keeps all database writes, claim/source/archive/deadline fences and rotation
  non-repetition fences. It passes the remaining claimed budget into `generate` and records the
  planned reviewer profile (`example_reviewer`) before calls.
- Successful provenance: top-level generator profile (existing readers unchanged) plus a nested
  `reviewer` block with profile, prompt version, verdict and findings. No credentials or hidden
  reasoning are stored. The public preparation phase stays `examples`.

## Dialects

The configured protocol — never the model name — selects the request dialect:

| Protocol | Budget key | Thinking values |
| --- | --- | --- |
| `zhipu` | `max_tokens` | `enabled`, `disabled` |
| `minimax` | `max_completion_tokens` | `adaptive`, `disabled` |
| `openai` | `max_completion_tokens` | `enabled`, `adaptive`, `disabled` |

Unsupported protocol/thinking/effort combinations fail profile validation at worker/WSGI startup.
MiniMax-key fallback stays origin-restricted; the Zhipu origin requires an explicit task key.
Judge and Definition requests remain unchanged (no thinking/effort fields).

## Refresh and probes

- `refresh_examples` eligibility now compares both the generator prompt version and the nested
  reviewer prompt version; legacy pairs without reviewer provenance are eligible.
- `scripts/probe_generation.py` keeps the raw generator mode and adds `--review`, a clearly
  identified full-pipeline evaluation path recording verdicts and reviewer provenance.
- `scripts/probe_providers.py` generation checks run the reviewed pipeline; its limits text states
  that reviewer verdicts are not ground truth.

## Tests

`learning/tests` covers: reviewer contract variants (accept/repair/full rewrite/marker
repair/rejection/malformed envelopes/altered accept/unchanged repair/failed final validation/
rotation repetition/timeout), no-third-call and no-fallback assertions, both request dialects and
role exchanges, credential origin restriction, secret-free provenance, shrinking shared budget,
unrelated-task payload preservation, durable preparation (readiness only after review; definition
preserved across review failure and retry), commit fences with an outstanding review, refresh
eligibility for legacy/old-reviewer pairs, the reviewed probe path and the real-worker stalled
review capacity regression.

## Semantic evaluation

Mocked transport tests prove workflow contracts, not linguistic accuracy. Live evaluation uses
`scripts/probe_generation.py --live [--review]` on the regression corpus with independent human
judgment of final cues; reviewer verdicts are never treated as ground truth. Raw results stay in
ignored private directories; only sanitized aggregates are published.

Recorded run (2026-11-15, `docs/implementation/example-quality-review-results.json`, review round 2):
the available development credentials are MiniMax, so the live pass used the exchanged
MiniMax→MiniMax role configuration with explicit `adaptive` thinking and `reasoning_effort=max` —
the role exchange the configuration contract promises. The default GLM generation role is covered by
request-dialect contract tests, not by this live run. One paired run records each case's
pre-review candidate and its reviewed final: 24/25 reviewed (23 accept, 1 repair — `justice`'s
native focus became the lexical noun 公道; 1 fail-closed reviewer output failure, `past`).
Independent judgment against the corpus checks: 22 good candidates, 2 bad (`existential`,
`prevention` — both accepted by the reviewer, i.e. bad→bad), 0 good→bad, 0 bad→good. Semantic
replays into review: the known-bad `elicit`/逗笑 candidate, a wrong-sense `bank`, a wrong-word-class
`monthly`, and an unrepairable-scope `porous` — all repaired this run (the `elicit` repair fixes
alignment by shifting the target to an achieved result; earlier replays of the same candidate were
accepted, so repair is not deterministic). Token usage is not recorded (the provider contract does
not surface usage fields); the dedicated-card walkthrough is substituted by named automated tests
for lack of an interactive dev-stack session — both disclosed in the evidence file.
