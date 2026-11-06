import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class Deck(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name


class AuthoringKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, blank=True)
    digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)


class Card(models.Model):
    deck = models.ForeignKey(Deck, on_delete=models.CASCADE, related_name="cards")
    kind = models.CharField(max_length=12, choices=[("generic", "Generic"), ("vocabulary", "Vocabulary")])
    question = models.TextField(blank=True)
    answer = models.TextField(blank=True)
    word = models.TextField(blank=True)
    explanation = models.TextField()
    target_language = models.CharField(max_length=12, blank=True)
    native_language = models.CharField(max_length=12, blank=True)
    identity = models.CharField(max_length=64)
    source_version = models.PositiveIntegerField(default=1)
    progress_version = models.PositiveIntegerField(default=0)
    archived = models.BooleanField(default=False)
    ready = models.BooleanField(default=True)
    due = models.DateTimeField(default=timezone.now, db_index=True)
    deferred_until = models.DateTimeField(null=True, blank=True, db_index=True)
    collection = models.CharField(max_length=8, default="Normal")
    streak = models.PositiveSmallIntegerField(default=0)
    fsrs = models.JSONField(default=dict)
    review_count = models.PositiveIntegerField(default=0)
    active_pair = models.ForeignKey("ExamplePair", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    cue_pair = models.ForeignKey("ExamplePair", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    cue_direction = models.CharField(max_length=12, blank=True)
    direction_block = models.JSONField(default=list)
    direction_index = models.PositiveSmallIntegerField(default=0)
    rotation_token = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["deck", "identity"], name="unique_card_identity_per_deck")]

    @property
    def title(self):
        return self.word if self.kind == "vocabulary" else self.question

    @property
    def available_at(self):
        return max(self.due, self.deferred_until or self.due)


class ExamplePair(models.Model):
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="pairs")
    source_version = models.PositiveIntegerField()
    target_sentence = models.TextField()
    target_highlight = models.TextField()
    target_highlight_start = models.PositiveIntegerField()
    native_sentence = models.TextField()
    native_highlight = models.TextField()
    native_highlight_start = models.PositiveIntegerField()
    provenance = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)


class Presentation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    scope_deck = models.ForeignKey(Deck, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    card = models.ForeignKey(Card, on_delete=models.CASCADE)
    source_version = models.PositiveIntegerField()
    progress_version = models.PositiveIntegerField()
    snapshot = models.JSONField()
    budget = models.PositiveIntegerField()
    invalidated = models.BooleanField(default=False)
    clock_claimed = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)


class Attempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    presentation = models.OneToOneField(Presentation, on_delete=models.CASCADE, related_name="attempt")
    action = models.CharField(max_length=8)
    state = models.CharField(max_length=20)
    submitted_at = models.DateTimeField(default=timezone.now)
    audio_expires_at = models.DateTimeField(null=True)
    audio_name = models.CharField(max_length=80, blank=True)
    duration = models.FloatField(null=True)
    transcript = models.TextField(blank=True)
    asr_provenance = models.JSONField(default=dict)
    judge_provenance = models.JSONField(default=dict)
    grade = models.CharField(max_length=1, blank=True)
    reason = models.TextField(blank=True)
    outcomes = models.JSONField(default=list)
    next_due = models.DateTimeField(null=True)
    error = models.CharField(max_length=300, blank=True)
    error_stage = models.CharField(max_length=20, blank=True)
    error_category = models.CharField(max_length=24, blank=True)
    retryable = models.BooleanField(default=True)
    execution = models.PositiveIntegerField(default=1)
    claim = models.UUIDField(default=uuid.uuid4)
    deadline = models.DateTimeField(null=True, db_index=True)


class ScoredReview(models.Model):
    attempt = models.OneToOneField(Attempt, on_delete=models.CASCADE)
    card = models.ForeignKey(Card, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    grade = models.CharField(max_length=1)
    reviewed_at = models.DateTimeField(db_index=True)
    next_due = models.DateTimeField()
    snapshot = models.JSONField()
    fsrs_log = models.JSONField()
    duration = models.FloatField(null=True)
    budget = models.PositiveIntegerField()


class GenerationJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="generation_jobs")
    source_version = models.PositiveIntegerField()
    mode = models.CharField(max_length=8, default="initial")
    token = models.UUIDField(default=uuid.uuid4)
    state = models.CharField(max_length=12, default="queued")
    execution = models.PositiveIntegerField(default=1)
    claim = models.UUIDField(default=uuid.uuid4)
    requested_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    deadline = models.DateTimeField(null=True, blank=True, db_index=True)
    result = models.ForeignKey(ExamplePair, null=True, on_delete=models.SET_NULL, related_name="+")
    provenance = models.JSONField(default=dict)
    error = models.CharField(max_length=300, blank=True)
    error_category = models.CharField(max_length=24, blank=True)
    retryable = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["state", "requested_at"], name="generation_queue_order")]
