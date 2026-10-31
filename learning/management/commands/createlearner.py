import getpass
import os
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = "Create a private learner account; password is prompted or read from a named environment variable."
    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--password-env")
    def handle(self, username, password_env=None, **options):
        user = get_user_model()(username=username)
        password = os.getenv(password_env, "") if password_env else getpass.getpass("Password: ")
        if not password_env and password != getpass.getpass("Confirm password: "):
            raise CommandError("Passwords do not match.")
        try:
            validate_password(password, user)
            user.full_clean(exclude=["password"])
        except ValidationError as e:
            raise CommandError(" ".join(e.messages)) from None
        user.set_password(password)
        user.save()
        self.stdout.write("Learner account created.")
