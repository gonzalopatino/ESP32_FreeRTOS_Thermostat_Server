from datetime import timedelta
import hashlib
import secrets


from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone



User = get_user_model()




class Device(models.Model):
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="devices",
    )
    serial_number = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        label = self.name or self.serial_number
        return f"{label} (owner={self.owner.username})"


class DeviceApiKey(models.Model):
    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    key_hash = models.CharField(max_length=128)  # store hex digest, not raw key
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["device", "is_active", "expires_at"]),
        ]

    def __str__(self):
        return f"API key for {self.device.serial_number} (active={self.is_active})"

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def is_valid(self) -> bool:
        return self.is_active and self.expires_at > timezone.now()
    
    @classmethod
    def create_for_device(cls, device, ttl_days: int = 365):
        """
        Create a new API key for the given device.

        Returns a tuple: (DeviceApiKey instance, raw_key_string).

        Only the hash is stored in the database, the raw key is meant to be
        shown exactly once to the user and then forgotten.
        """
        # Generate a URL-safe random key, long enough to be hard to guess
        raw_key = secrets.token_urlsafe(32)  # ~43 chars

        key_hash = cls.hash_key(raw_key)
        expires_at = timezone.now() + timedelta(days=ttl_days)

        obj = cls.objects.create(
            device=device,
            key_hash=key_hash,
            expires_at=expires_at,
            is_active=True,
        )
        return obj, raw_key



class TelemetrySnapshot(models.Model):
    device_id = models.CharField(max_length=64)

    # Core thermostat state
    mode = models.CharField(max_length=16)              # "OFF", "HEAT", "COOL", "AUTO"
    temp_inside_c = models.FloatField()
    temp_outside_c = models.FloatField(null=True, blank=True)
    setpoint_c = models.FloatField()
    hysteresis_c = models.FloatField(null=True, blank=True)

    # What the thermostat decided to do
    output = models.CharField(
        max_length=16,
        blank=True,                                     # "HEAT_ON", "COOL_ON", "OFF"
        help_text="Current actuator output state",
    )

    # You don't actually measure humidity, so this will stay null,
    # but we keep the column to avoid migration complexity if you
    # already created it.
    humidity_percent = models.FloatField(null=True, blank=True)

    # Raw payload for debugging
    raw_payload = models.JSONField(null=True, blank=True)

    # Timestamps
    device_ts = models.DateTimeField(null=True, blank=True)
    server_ts = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["device_id", "server_ts"]),
        ]

    def __str__(self):
        return f"{self.device_id} @ {self.server_ts.isoformat()}"

