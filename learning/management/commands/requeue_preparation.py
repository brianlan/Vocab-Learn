from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, OuterRef, Subquery
from learning import work
from learning.models import GenerationJob


class Command(BaseCommand):
    help = "Explicitly requeue a learner's failed initial preparation, preserving Ready cards and learning progress."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            user = get_user_model().objects.get(username=options["username"])
        except get_user_model().DoesNotExist:
            raise CommandError("Learner account not found.") from None
        latest = GenerationJob.objects.filter(card_id=OuterRef("card_id"), source_version=OuterRef("source_version"),
            mode="initial").order_by("-requested_at", "-pk").values("pk")[:1]
        jobs = list(GenerationJob.objects.filter(pk=Subquery(latest), state="failed", mode="initial",
            card__deck__owner=user, card__deck__archived=False, card__archived=False, card__ready=False,
            source_version=F("card__source_version")).order_by("requested_at", "pk"))
        self.stdout.write(f"Eligible failed initial tasks: {len(jobs)}; with prior dispatch metadata: {sum(bool(job.provenance) for job in jobs)}.")
        if options["dry_run"]:
            return
        requeued = sum(work.retry_generation(job).state == "queued" for job in jobs)
        self.stdout.write(f"Requeued {requeued} tasks. The worker will prepare their examples as capacity becomes available.")
