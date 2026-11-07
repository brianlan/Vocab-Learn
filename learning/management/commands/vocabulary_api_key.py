from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from learning import api_keys
from learning.models import AuthoringKey


class Command(BaseCommand):
    help = "Create, list or revoke a learner's Vocabulary API keys. New secrets are shown once."

    def add_arguments(self, parser):
        parser.add_argument("operation", choices=["create", "list", "revoke"])
        parser.add_argument("username")
        parser.add_argument("--name", default="")
        parser.add_argument("--id", dest="key_id")

    def handle(self, operation, username, name="", key_id=None, **options):
        user = get_user_model().objects.filter(username=username).first()
        if not user:
            raise CommandError("Learner account not found.")
        if operation == "create":
            if not user.is_active or len(name) > 100:
                raise CommandError("Choose an active learner and a key name of at most 100 characters.")
            key, token = api_keys.issue(user, name)
            self.stdout.write(f"Key ID: {key.pk}\nStore this secret securely; it is shown only now.\n{token}")
        elif operation == "list":
            for key in AuthoringKey.objects.filter(owner=user).order_by("created_at"):
                self.stdout.write(f"{key.pk}  {'revoked' if key.revoked_at else 'active'}  {key.name}")
        else:
            try:
                key = AuthoringKey.objects.filter(pk=key_id, owner=user).first() if key_id else None
            except (ValueError, TypeError, ValidationError):
                key = None
            if not key:
                raise CommandError("Specify an existing key with --id, belonging to this learner.")
            if not key.revoked_at:
                key.revoked_at = timezone.now()
                key.save(update_fields=["revoked_at"])
            self.stdout.write("Key revoked.")
