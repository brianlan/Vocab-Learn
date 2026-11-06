from django.core.management.base import BaseCommand, CommandError
from learning.worker import run_worker
from learning.providers import profile, StageError

class Command(BaseCommand):
    help = "Process persisted assessments and example preparation with bounded concurrency."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--concurrency", type=int)

    def handle(self, *args, **options):
        if options["concurrency"] is not None and not 1 <= options["concurrency"] <= 16:
            raise CommandError("Concurrency must be between 1 and 16.")
        try:
            for task in ["ASR", "JUDGE", "GENERATOR", "DEFINITION"]:
                profile(task)
        except StageError as e:
            raise CommandError(str(e)) from None
        self.stdout.write("Worker ready. Assessments have queue priority.")
        run_worker(once=options["once"], concurrency=options["concurrency"])
