# Round-two evidence: worker deadlines and resource release

Reviewed on 2026-10-31 against the local-worker warning in `/home/rlan/Downloads/reviewer-feedback.md` (line 159). Scope: official Python 3.11 and HTTPX contracts, plus proposed acceptance evidence. This note does not adopt new behavior, change the selected worker architecture, or claim a running implementation has this defect.

## Verified API facts

| Mechanism | What its timeout/cancellation actually guarantees |
| --- | --- |
| `Future.cancel()` | Returns false for a running call; it cannot stop the running thread's callable. |
| `Future.result(timeout=...)` | Bounds the caller's wait for a result and raises TimeoutError when that wait expires. It does not terminate the work. |
| Executor shutdown | `cancel_futures=True` cancels work that has not started, not running calls. `wait=False` does not make running threads disappear; Python still waits for pending work before process exit. |

These distinctions are explicit in the [Python 3.11 Future contract](https://docs.python.org/3.11/library/concurrent.futures.html#future-objects) and [executor shutdown contract](https://docs.python.org/3.11/library/concurrent.futures.html#concurrent.futures.Executor.shutdown). Wrapping a synchronous HTTP call in a future and catching a timeout is therefore not a running-thread kill mechanism.

HTTPX distinguishes connect, read, write and pool timeouts. Read/write limits concern waiting for individual chunks; the pool limit concerns acquiring a connection. Its default is a network-inactivity timeout. **Inference:** a peer that keeps delivering chunks before each read limit, or a sequence of phases/calls, can exceed an intended whole-operation duration without violating an individual timeout. `httpx.Timeout(...)` is not by itself an end-to-end wall-clock deadline for conversion plus ASR plus judgment. [Official HTTPX timeout definitions](https://www.python-httpx.org/advanced/timeouts/).

Subprocess APIs must be distinguished:

- `subprocess.run(timeout=...)` kills **and waits for** the child on expiry, then raises TimeoutExpired. Python notes that process creation itself cannot always be interrupted immediately. [Python run contract](https://docs.python.org/3.11/library/subprocess.html#subprocess.run).
- `Popen.communicate(timeout=...)` raises TimeoutExpired **without killing** the child. The documented cleanup is to kill it and finish `communicate()`, which drains communication and waits for termination. A timeout or a kill request alone is not the complete cleanup sequence. [Python communicate contract](https://docs.python.org/3.11/library/subprocess.html#subprocess.Popen.communicate).
- `Popen.wait(timeout=...)` can also time out with the child still running. Waiting with full stdout/stderr pipes can deadlock; `communicate()` addresses that pipe-draining problem. The documented kill methods target the child, not a general promise to terminate every descendant process. [Python wait](https://docs.python.org/3.11/library/subprocess.html#subprocess.Popen.wait), [Python kill](https://docs.python.org/3.11/library/subprocess.html#subprocess.Popen.kill).

These are documentation guarantees, not execution tests performed here.

## Assessment of the reviewer warning

**The technical distinction is valid.** Invalidating a database execution claim can fence off a late result and protect grading/progress. That state transition does not itself interrupt a blocked callable, terminate/reap a conversion child, drain pipes, close a response, or return a connection/worker permit. Unless the execution path observes cancellation and actually unwinds, capacity can remain occupied after its result has become unusable.

Consequently, separate three observables: the request/UI can stop waiting; an obsolete result cannot commit; and the execution resources become available again within a documented cleanup bound. Proving one does not prove the others. Starting fresh pools indefinitely can hide exhaustion while accumulating abandoned work.

This does not establish that a new broker or queue framework is necessary. The acceptance property concerns the chosen local worker's execution boundary and cleanup, regardless of how durable jobs are stored. This research does not select threads, processes, a cancellation technique, or new timeout values.

## Proposed hung-slot-then-normal-job acceptance evidence

The following is a test proposal, not an adopted requirement or a report of passing tests:

1. Run the configured local-worker path with **one execution slot**, or occupy every configured slot with controlled faults. Queue a normal job behind the faulted work. Preserve the same bounded worker service/pool; do not let a spare slot or an unrelated executor make the test pass.
2. Exercise conversion and provider boundaries separately. Include an HTTP response that progresses often enough to avoid an inactivity timeout but outlasts the configured total execution deadline. Use controlled fakes/local test fixtures during implementation, not a paid provider.
3. Keep the injected operation blocked beyond the expected recovery window unless the actual cleanup mechanism stops it. Measure from the specified execution/deadline anchor through the documented cleanup grace. Merely returning TimeoutError or marking the database row expired is insufficient.
4. Assert that obsolete work no longer owns its constrained execution resources, its child has terminated and been reaped where applicable, and its connection/permits are usable again. Then assert the queued normal job **starts and commits its expected result** within the deadline-plus-cleanup-plus-normal-job budget, without a manual restart or unbounded capacity increase. A bounded automatic worker replacement may satisfy the property if that is the chosen implementation.
5. Assert the old claim/output still cannot commit learning or generation changes after recovery. If the fault is later released, its late completion must remain fenced off. Repeat a small number of fault/recovery cycles to expose accumulating orphan calls, children or leaked capacity rather than accepting one lucky recovery.

Record the injected boundary, configured capacity, timeout/cleanup budgets, timestamps, cleanup evidence and normal-job outcome. An application shutdown that hangs waiting for abandoned futures must not be mistaken for successful cleanup. The implementation may need more precise process/transport accounting, but this proposal does not prescribe its internals.

## Limits

Only primary documentation and the supplied warning were read. No futures, processes, HTTP services, fault injectors or application workers were run; no process was killed. No packages, accepted contracts, main-worktree files or tracker state were changed. Actual cancellation, bounded cleanup and subsequent-job throughput remain implementation evidence to collect.
