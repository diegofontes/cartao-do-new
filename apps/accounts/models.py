import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from django.contrib.auth.models import AbstractUser
from django.core import signing
from django.db import models
from django.db.models import UniqueConstraint
from django.db.models.functions import Lower

from apps.common.models import BaseModel


class User(BaseModel, AbstractUser):
    """Custom User with UUID primary key and timestamps.

    Uses Django's AbstractUser to minimize migration risk but promotes
    email as the primary identifier in views/forms. Adds
    `email_verified_at` and enforces case-insensitive uniqueness on email.
    """

    email = models.EmailField("email address", blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    class Meta(AbstractUser.Meta):
        constraints = [
            UniqueConstraint(
                Lower("email"), name="accounts_user_email_lower_uniq", violation_error_message="E-mail já cadastrado"
            )
        ]

    def save(self, *args, **kwargs):
        # Normalize email: strip, lower, NFKC via casefold-like behavior
        if self.email:
            self.email = str(self.email).strip().lower()
        return super().save(*args, **kwargs)


class TrustedDevice(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="trusted_devices")
    device_id = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=["user", "device_id"])]

    @classmethod
    def create_for(cls, user, days=30):
        device_id = secrets.token_urlsafe(24)
        td = cls.objects.create(
            user=user,
            device_id=device_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=days),
        )
        return td

    @staticmethod
    def make_cookie(user_id: str, device_id: str) -> str:
        return signing.Signer().sign(f"{user_id}:{device_id}")

    @staticmethod
    def parse_cookie(value: str) -> tuple[str, str] | None:
        try:
            raw = signing.Signer().unsign(value)
            user_id, device_id = raw.split(":", 1)
            return user_id, device_id
        except Exception:
            return None


class EmailChallenge(BaseModel):
    PURPOSE_LOGIN = "login_2fa"
    PURPOSE_SIGNUP = "signup_verify"
    PURPOSE_RESET = "reset"
    PURPOSE_CHOICES = [
        (PURPOSE_LOGIN, "Login 2FA"),
        (PURPOSE_SIGNUP, "Signup Verify"),
        (PURPOSE_RESET, "Reset Password"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_challenges")
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    sent_to = models.EmailField()
    code_hash = models.CharField(max_length=64)  # SHA-256 hex
    attempts_left = models.PositiveSmallIntegerField(default=5)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "purpose", "created_at"]),
        ]

    @staticmethod
    def _hash(code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()

    @classmethod
    def generate_code(cls) -> str:
        return f"{secrets.randbelow(10**6):06d}"

    @classmethod
    def create_for(cls, user: User, purpose: str, ttl_minutes: int = 10) -> tuple["EmailChallenge", str]:
        code = cls.generate_code()
        ch = cls.objects.create(
            user=user,
            purpose=purpose,
            sent_to=(user.email or "").strip().lower(),
            code_hash=cls._hash(code),
            attempts_left=5,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
        )
        return ch, code

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    def consume_with_code(self, code: str) -> bool:
        if self.consumed_at is not None:
            return False
        if self.is_expired():
            return False
        if self.attempts_left <= 0:
            return False
        ok = self.code_hash == self._hash(code)
        self.attempts_left = max(0, self.attempts_left - 1)
        if ok:
            self.consumed_at = datetime.now(timezone.utc)
        self.save(update_fields=["attempts_left", "consumed_at"])
        return ok
