"""Bounded illustration backfill for one learner, mirroring queue_example_speech."""
import uuid
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from learning import illustrations
from learning.models import Card, ExampleIllustration


class Command(BaseCommand):
    help = "Queue illustrations for a learner's active Ready example pairs; previews with --dry-run."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=50)

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            user = get_user_model().objects.get(username=options["username"])
        except get_user_model().DoesNotExist:
            raise CommandError("Learner account not found.") from None
        if not illustrations.illustration_enabled():
            raise CommandError("ILLUSTRATION_ENDPOINT is not configured; illustration queueing is disabled.")
        if options["limit"] < 1:
            raise CommandError("--limit must be a positive number of illustrations.")
        cards = Card.objects.filter(deck__owner=user, kind="vocabulary", ready=True, archived=False,
            deck__archived=False, active_pair__isnull=False).select_related("active_pair").order_by("pk")
        missing = failed = queued = processing = ready = enqueued = 0
        for card in cards:
            # Re-read the active pair inside the enqueue transaction; a pair replaced since the
            # listing simply loses its references and is skipped by the worker, never published.
            pair = Card.objects.select_related("active_pair").get(pk=card.pk).active_pair
            row = ExampleIllustration.objects.filter(pair=pair).first()
            if row is not None and row.state == "done":
                ready += 1
            elif row is None:
                missing += 1
            elif row.state == "failed":
                failed += 1
            elif row.state == "queued":
                queued += 1
            elif row.state == "processing":
                processing += 1
            if options["dry_run"] or enqueued >= options["limit"]:
                continue
            if row is None:
                illustrations.enqueue_illustration(pair, backfill=True)
                enqueued += 1
            elif row.state == "failed":
                row.state, row.claim, row.error, row.error_category = "queued", uuid.uuid4(), "", ""
                row.execution += 1
                row.requested_at = timezone.now()
                row.save(update_fields=["state", "claim", "error", "error_category", "execution", "requested_at"])
                enqueued += 1
        if options["dry_run"]:
            self.stdout.write(f"Preview for {user.username}: missing {missing}, failed {failed}, "
                              f"queued {queued}, processing {processing}, ready {ready}. "
                              "Nothing was written or called.")
        else:
            self.stdout.write(f"Queued {enqueued} illustrations (missing {missing}, failed {failed}) for "
                              f"{user.username}; {queued} queued, {processing} processing and {ready} ready "
                              "were left in place. The worker renders each as capacity becomes available.")
