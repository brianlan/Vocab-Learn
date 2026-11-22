# StepAudio integration and production release

**Development verified; production deployment waits for maintainer review and merge.**

## Delivered behavior

`AUDIO_ASSESS_PROVIDER=stepfun` selects `stepaudio-3-chat-preview` over HTTP Chat Completions. The request matches the [evaluated StepAudio setup](stepaudio3-prompt-experiment.md): MP3 data URI, text-only output, JSON mode and provider-default reasoning. Only final answer content enters the existing validator. StepAudio Responses configuration is rejected before dispatch.

The exact supplied Production, Recognition and Generic prompts are stored in `learning/audio_prompts.py`, selected by frozen task kind/direction, with bundle version `spoken-audio-v5-candidate-1` recorded in execution provenance. This replaces the prior shared prompt for all providers. Qwen/Doubao transports remain supported, but their grading quality with these prompts differs from StepAudio. Unset provider still defaults to Qwen: deployments switch explicitly with the correct provider credential.

No schema migration, progress reset, history rewrite or regrading is included. Audio retention, 15-second Stop-to-result budget, explicit retries, one-call execution and A–E mapping remain unchanged.

## Verification

- Full Django suite: **246 tests passed**, using `/tmp/vocab-stepaudio-tests-20261122` as isolated data storage (66.691 seconds).
- Tests cover StepAudio endpoint/model defaults, rejected Responses mode, no cross-provider key fallback, MP3 request shape, exact prompt hashes/routing, Generic multi-unit IDs, reasoning exclusion and unassessable/invalid-answer failures without retries.
- Development Compose configuration resolves StepAudio settings for both web and worker using dummy credentials; no production services were started.
- Live formal-adapter replay: **15/16 expected outcomes**, one call per case. For the thirteen existing fixtures, complete request-body hashes exactly match the earlier private experiment. No transport or format failures occurred in this replay.

| Case | Expected | Observed | Result |
|---|---|---|---|
| human-tinker | complete | complete | passed |
| human-mortal | complete | complete | passed |
| human-dissect | complete | complete | passed |
| shrink-smaller | complete | complete | passed |
| shrink-contract | complete | complete | passed |
| thinker-en-us | incorrect | incorrect | passed |
| mobile-en-us | incorrect | incorrect | passed |
| human-neuroticism | complete | complete | passed |
| human-neurocism | incorrect | complete | wrong_grade |
| recognition-correct | complete | complete | passed |
| recognition-wrong | incorrect | incorrect | passed |
| handyman-en-us | partial | partial | passed |
| human-silence | unassessable | unassessable | passed |
| 01-call-off | complete | complete | passed |
| 02-cancel | partial | partial | passed |
| 06-dont-know | incorrect | incorrect | passed |

The failed replay was the shortened **neurocism** recording: the model returned complete and described the missing sounds as ordinary elision. This is an observed false positive despite the unchanged prompt/request, not a transport defect. The earlier 41-call experiment also had one 15-second timeout. Some dissect feedback describes the utterance as dissected. These limitations must remain visible when deciding whether to deploy.

Private live evidence: `/home/rlan/.local/share/vocab-learn/audio-eval/20261122-stepaudio3-integration/`. Credentials and audio are excluded from Git.

## Production configuration after merge

On `rlan@192.168.71.97`, update the existing production `.env` during the release window:

```dotenv
AUDIO_ASSESS_PROVIDER=stepfun
AUDIO_ASSESS_API_MODE=chat_completions
AUDIO_ASSESS_ENDPOINT=https://api.stepfun.com/v1/chat/completions
AUDIO_ASSESS_MODEL=stepaudio-3-chat-preview
AUDIO_ASSESS_API_KEY=<StepFun API key>
AUDIO_ASSESS_MAX_COMPLETION_TOKENS=8192
```

Replace the existing audio provider, mode, endpoint, model and key values rather than appending duplicates. The privately supplied `STEPFUN_API_KEY` is the source credential; the application reads it through `AUDIO_ASSESS_API_KEY`, not a new fallback environment variable. Never put the actual value in a PR or command output. Empty endpoint/model values also resolve to the StepAudio defaults. Remove `AUDIO_ASSESS_THINKING` or `AUDIO_ASSESS_REASONING_EFFORT` overrides if present; audio reasoning settings are adapter-owned. Keep all unrelated model credentials and the existing timeout settings.

## Release and rollback

1. Wait for maintainer review and merge. Deploy the merged commit, not the unmerged branch.
2. Follow [operations](../operations.md#delivered-cold-backup-and-restore): preserve the current image/config privately and take the production cold backup before changing the service.
3. Update only the audio settings above, stop writers, build/select the merged image, run the ordinary migration command and recreate web/worker. There are no new migrations in this change; retain the live production database in place.
4. Check health and startup configuration, then verify one Production answer and one Recognition answer on the site. Check provenance for StepAudio and the new prompt version. Never regrade historical attempts as a smoke test.
5. If rollback is needed, restore the previous application image and its matching audio configuration. Merely selecting Qwen on the new image retains the new prompts. No database restore is needed for this code-only change; preserve learning performed since release.

No production configuration or service has been changed as part of development. Browser recording and concurrent live-provider load were not retested; the observed timeout and malformed-word false positive remain model risks.
