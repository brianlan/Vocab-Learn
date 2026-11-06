"""User-bound authoring credentials. Store digests; reveal a new key once."""
import hashlib
import hmac
import re
import secrets
import uuid
from .models import AuthoringKey


def issue(owner, name=""):
    key_id = uuid.uuid4()
    token = "vl_" + key_id.hex + "." + secrets.token_urlsafe(32)
    key = AuthoringKey.objects.create(id=key_id, owner=owner, name=name,
                                     digest=hashlib.sha256(token.encode("ascii")).hexdigest())
    return key, token


def authenticate(authorization):
    pieces = authorization.split()
    if len(pieces) != 2 or pieces[0].lower() != "bearer":
        return None
    token = pieces[1]
    match = re.fullmatch(r"vl_([0-9a-f]{32})\.[A-Za-z0-9_-]{43}", token)
    if not match:
        return None
    key = AuthoringKey.objects.select_related("owner").filter(pk=uuid.UUID(hex=match[1]),
        revoked_at__isnull=True, owner__is_active=True).first()
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    valid = hmac.compare_digest(key.digest if key else "0" * 64, digest)
    return key if key and valid else None
