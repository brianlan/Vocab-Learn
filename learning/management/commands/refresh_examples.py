from concurrent.futures import ThreadPoolExecutor
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from learning import providers, work
from learning.models import Card


class Command(BaseCommand):
    help = "Correct a learner's Ready Vocabulary examples without resetting progress or changing frozen reviews."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        try:
            user = get_user_model().objects.get(username=options["username"])
        except get_user_model().DoesNotExist:
            raise CommandError("Learner account not found.") from None
        version = providers.PROMPT_VERSIONS["GENERATOR"]
        cards = [card for card in Card.objects.filter(deck__owner=user, deck__archived=False,
            archived=False, kind="vocabulary", ready=True).select_related("active_pair").order_by("pk")
            if card.active_pair and card.active_pair.provenance.get("prompt_version") != version]
        self.stdout.write(f"Examples needing correction: {len(cards)}. Not-ready cards are excluded.")
        if options["dry_run"] or not cards:
            return
        try:
            profile = providers.profile("GENERATOR")
        except providers.StageError as error:
            raise CommandError(str(error)) from None

        def generate(card):
            source = {key: getattr(card, key) for key in ["word", "explanation", "target_language", "native_language"]}
            try:
                data, provenance = providers.generate(source, profile)
                return data, provenance, ""
            except providers.StageError as error:
                return None, None, str(error)

        corrected = failed = changed = 0
        # Only provider I/O is concurrent; database writes stay serial and source-fenced.
        with ThreadPoolExecutor(max_workers=2) as executor:
            for card, (data, provenance, error) in zip(cards, executor.map(generate, cards)):
                if error:
                    failed += 1
                    self.stderr.write(f"Card {card.pk}: {error}")
                    continue
                pair = work.save_corrected_pair(card.pk, card.source_version, card.active_pair_id, data, provenance)
                if pair:
                    corrected += 1
                    self.stdout.write(f"Card {card.pk}: corrected.")
                else:
                    changed += 1
                    self.stdout.write(f"Card {card.pk}: source or active pair changed; kept the newer state.")
        self.stdout.write(f"Corrected {corrected}; failed {failed}; changed concurrently {changed}.")
        if failed:
            raise CommandError("Some examples could not be corrected. Rerun explicitly to retry only the remaining cards.")
