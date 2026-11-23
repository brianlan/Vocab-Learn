import uuid
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from learning import work
from learning.models import Card, SpeechClip


class Command(BaseCommand):
    help = "Queue speech clips for a learner's active Ready example pairs; previews with --dry-run."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            user = get_user_model().objects.get(username=options["username"])
        except get_user_model().DoesNotExist:
            raise CommandError("Learner account not found.") from None
        cards = Card.objects.filter(deck__owner=user, kind="vocabulary", ready=True, archived=False,
            deck__archived=False, active_pair__isnull=False).select_related("active_pair").order_by("pk")
        missing = failed = enqueued = 0
        for card in cards:
            # Re-read the active pair inside the enqueue transaction; a pair replaced since the
            # listing simply loses its references and is skipped by the worker, never published.
            pair = Card.objects.select_related("active_pair").get(pk=card.pk).active_pair
            clips = {clip.side: clip for clip in pair.speech_clips.all()}
            for side in ("target", "native"):
                clip = clips.get(side)
                if clip is None:
                    missing += 1
                elif clip.state == "failed":
                    failed += 1
                if options["dry_run"]:
                    continue
                if clip is None:
                    work.enqueue_speech(pair, backfill=True)
                    enqueued += 1
                elif clip.state == "failed":
                    clip.state, clip.claim, clip.error, clip.error_category = "queued", uuid.uuid4(), "", ""
                    clip.execution += 1
                    clip.requested_at = timezone.now()
                    clip.save(update_fields=["state", "claim", "error", "error_category", "execution", "requested_at"])
                    enqueued += 1
        completed = sum(clip.state == "done" for card in cards for pair in [card.active_pair] for clip in pair.speech_clips.all())
        if options["dry_run"]:
            self.stdout.write(f"Preview for {user.username}: missing sides {missing}, failed sides {failed}, "
                              f"already completed {completed}. Nothing was written or called.")
        else:
            self.stdout.write(f"Queued {enqueued} sides (missing {missing}, failed {failed}) for {user.username}; "
                              f"{completed} sides already completed were left in place. "
                              "The worker synthesizes each side as capacity becomes available.")
