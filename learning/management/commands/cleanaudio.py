from django.core.management.base import BaseCommand
from learning.work import cleanup_audio

class Command(BaseCommand):
    help = "Delete assessed, expired and abandoned temporary recordings."
    def handle(self, *args, **options):
        cleanup_audio()
        self.stdout.write("Temporary audio cleanup complete.")
