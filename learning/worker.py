"""A bounded supervisor; each job owns a killable process group, including FFmpeg."""
import multiprocessing
import os
import signal
import time
from datetime import timedelta
from django.conf import settings
from django.db import connections
from django.utils import timezone


def execute(kind, job_id, claim, paths):
    os.setsid()
    os.environ.update(paths)
    import django
    django.setup()
    from .illustrations import process_illustration
    from .work import process_assessment, process_generation, process_speech, fail
    from .providers import StageError
    def interrupted(signum, frame):
        raise StageError("worker", "Execution was stopped before completion. Retry explicitly.")
    signal.signal(signal.SIGTERM, interrupted)
    try:
        (process_assessment if kind == "assessment" else process_generation if kind == "generation"
         else process_speech if kind == "speech" else process_illustration)(job_id, claim)
    except StageError as error:
        fail(kind, job_id, claim, error)
    except Exception:
        # Never expose provider bodies, paths or credentials through exception strings.
        fail(kind, job_id, claim, StageError("worker", "Processing was interrupted. Retry the fixed input or continue unassessed."))
    finally:
        connections.close_all()


def terminate(process, grace):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        if process.is_alive():
            process.terminate()
    process.join(timeout=min(1, grace/4))
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if process.is_alive():
        process.kill()
    process.join(timeout=min(0.5, grace/2))


def run_worker(once=False, concurrency=None):
    from .illustrations import claim_illustration, cleanup_illustrations, expire_illustration
    from .models import Attempt
    from .review import expire_attempt
    from .work import claim_work, claim_speech, expire_generations, expire_speech, cleanup_audio, cleanup_speech, fail
    from .providers import StageError
    context = multiprocessing.get_context("spawn")
    active = []
    stopping = False
    last_cleanup = 0
    def stop(signum, frame):
        nonlocal stopping
        stopping = True
    old_handlers = {s: signal.signal(s, stop) for s in [signal.SIGTERM, signal.SIGINT]}
    try:
        while not stopping:
            now = timezone.now()
            for item in active[:]:
                kind, job_id, claim, deadline, process = item
                if not process.is_alive() or now >= deadline:
                    terminate(process, settings.WORKER_CLEANUP_GRACE_SECONDS)
                    fail(kind, job_id, claim, StageError("worker", "Execution ended or expired before committing a result. Retry explicitly.", "timeout"))
                    active.remove(item)
            for a in Attempt.objects.filter(state__in=["submitted", "processing"], deadline__lte=now):
                expire_attempt(a)
            # Invalidate legacy/config-shrunk executions carrying a deadline beyond the current budget.
            for a in Attempt.objects.filter(state__in=["submitted", "processing"],
                    deadline__gt=now+timedelta(seconds=settings.ASSESSMENT_TIMEOUT_SECONDS)):
                expire_attempt(a)
            expire_generations()
            expire_speech()
            expire_illustration()
            if time.monotonic()-last_cleanup >= 60:
                cleanup_audio()
                try:
                    cleanup_speech()
                except OSError as fault:
                    # A speech-storage problem must never interrupt assessments or preparation.
                    print(f"Speech cleanup stopped early ({fault.__class__.__name__}); it will retry on the next pass.",
                        flush=True)
                try:
                    cleanup_illustrations()
                except OSError as fault:
                    print(f"Illustration cleanup stopped early ({fault.__class__.__name__}); it will retry on the next pass.",
                        flush=True)
                last_cleanup = time.monotonic()
            slots = concurrency or settings.WORKER_CONCURRENCY
            paths = {"DATABASE_PATH": str(connections["default"].settings_dict["NAME"]), "AUDIO_DIR": str(settings.AUDIO_DIR), "TTS_DIR": str(settings.TTS_DIR), "ILLUSTRATIONS_DIR": str(settings.ILLUSTRATIONS_DIR)}
            # Assessments and preparation share the main slots; speech and illustration each own
            # one dedicated slot, so a stalled render or synthesis never delays an assessment and
            # neither media kind is blocked by the other's or a main execution.
            while sum(item[0] in ("assessment", "generation") for item in active) < slots:
                job = claim_work()
                if not job:
                    break
                connections.close_all()
                process = context.Process(target=execute, args=(*job[:3], paths))
                process.start()
                active.append((*job, process))
            if sum(item[0] == "speech" for item in active) < 1:
                clip = claim_speech()
                if clip:
                    connections.close_all()
                    process = context.Process(target=execute, args=("speech", *clip[:2], paths))
                    process.start()
                    active.append(("speech", *clip, process))
            if sum(item[0] == "illustration" for item in active) < 1:
                row = claim_illustration()
                if row:
                    connections.close_all()
                    process = context.Process(target=execute, args=("illustration", *row[:2], paths))
                    process.start()
                    active.append(("illustration", *row, process))
            if once and not active:
                break
            time.sleep(0.2)
    finally:
        for kind, job_id, claim, deadline, process in active:
            terminate(process, settings.WORKER_CLEANUP_GRACE_SECONDS)
            fail(kind, job_id, claim, StageError("worker", "The worker stopped before completion. Retry explicitly."))
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
        connections.close_all()
