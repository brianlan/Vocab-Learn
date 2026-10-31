import os
from django.core.wsgi import get_wsgi_application
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vocab.settings")
application = get_wsgi_application()

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from learning.providers import profile, StageError
if not settings.DEBUG:
    try:
        for task in ["ASR", "JUDGE", "GENERATOR"]:
            profile(task)
    except StageError as error:
        raise ImproperlyConfigured(str(error)) from None
