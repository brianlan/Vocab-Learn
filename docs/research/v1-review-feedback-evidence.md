# Evidence for two external reviewer claims

Checked on 2026-10-31. Scope is limited to the MiniMax reasoning-budget and browser microphone-permission claims in `/home/rlan/Downloads/reviewer-feedback.md`. This is not a review or revision of the overall plan.

## MiniMax reasoning, completion budget and timeout

**Verified:** MiniMax-M3.1-Flash always reasons. Disabling thinking or requesting `reasoning_effort=none` returns HTTP 400. Supported effort levels are `low`, `medium`, `high`, `xhigh`, and `max`; omitting the field defaults to `max`. The official compatibility guide explicitly states that reasoning tokens count toward legacy `max_tokens`, and too little budget can yield `finish_reason=length` with empty final `content`. [MiniMax OpenAI compatibility guide](https://platform.minimax.cn/docs/api-reference/text-openai-api).

For new Chat Completions integrations, the supported replacement parameter is **`max_completion_tokens`**; `max_tokens` is deprecated. The endpoint reference advises increasing the completion cap when generation terminates for length. The compatibility guide's explicit reasoning-budget warning is worded against the old parameter; it must not be interpreted as permission to budget only for visible JSON when using its replacement. [MiniMax Chat Completions reference](https://platform.minimax.cn/docs/api-reference/text-chat-openai).

**Comparison with the actual plan:** [Decide Replaceable ASR and Judge Boundaries](../planning/v1/issues/09-provider-configuration.md) already sets independent Judge/Generator completion budgets of **8192, including reasoning**, and total per-execution deadlines of **120 seconds**. It prohibits thinking-disabled overrides, treats empty/truncated output as processing failure, disables hidden retries, and explicitly calls the budgets provisional engineering defaults.

The reviewer is right that short final JSON does not prove a small total generation budget is sufficient. These sources do **not** establish that 8192 tokens or 120 seconds are inadequate, nor that either setting guarantees success. That remains a workload-validation question. An early real-provider check should use the selected effort, exact parameter name, frozen task inputs, complete expected unit schema, and actual deadlines; inspect completion status and final content rather than just HTTP success. No new numerical default is justified by this documentary check alone.

## Ignored microphone permission and cancellation

**Verified:** MDN states that the `getUserMedia()` promise may neither resolve nor reject if the user ignores the permission request. The W3C acquisition algorithm also expressly stalls at permission when the user never responds. A UI relying only on success/error callbacks can therefore remain pending without a platform-guaranteed deadline. [MDN getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia), [W3C getUserMedia algorithm](https://w3c.github.io/mediacapture-main/#dom-mediadevices-getusermedia).

The inspected standard API accepts media constraints and does **not** define an `AbortSignal` cancellation argument. Application cancellation or a timeout wrapper is therefore logical cancellation of that capture attempt; it should not be described as cancelling or dismissing the browser's outstanding permission request. [W3C API definition](https://w3c.github.io/mediacapture-main/#dom-mediadevices-getusermedia).

**Engineering implications, inferred from that lifecycle:**

- Keep a request identity/liveness check. Cancel, navigation within the app, or an application timeout invalidates the old acquisition attempt and restores usable UI without waiting for its promise.
- If that obsolete request later resolves, stop **every track** in its returned stream and do not start a recorder or attach it to a newer attempt. A timeout `Promise.race` alone leaves this cleanup obligation intact.
- A late rejection from an obsolete request must not overwrite the state of a newer request. Clear any application wait timer when its request finishes or becomes obsolete.
- Test ignored permission, Cancel followed by delayed permission grant, and an obsolete result arriving after another capture starts. An automatic timeout duration is a product choice; a cancellable UI need not invent a browser permission deadline.

Stopping a track sets its state to `ended`; manually stopping it does not emit the `ended` event. Releasing all tracks owned by this request does not promise that shared microphone hardware stops while another tab still uses it. [MDN track stop](https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrack/stop), [W3C track stop](https://w3c.github.io/mediacapture-main/#dom-mediastreamtrack-stop).

No provider requests, credential inspection, package installation, microphone requests, browser runs, certificate operations or container operations were performed. Actual model sufficiency and browser UI behavior remain untested; the primary sources establish the risks and API semantics only.
