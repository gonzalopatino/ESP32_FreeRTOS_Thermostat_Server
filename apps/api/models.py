from datetime import timedelta
import hashlib
import secrets


from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

from django.conf import settings
from django.utils.timezone import now


User = get_user_model()




class Device(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="devices",
        on_delete=models.CASCADE,
    )
    serial_number = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # NEW: last time we heard from this device
    last_seen = models.DateTimeField(null=True, blank=True)

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


class DeviceAlertSettings(models.Model):
    """
    Stores email alert settings for a device.
    Allows users to configure temperature thresholds for notifications.
    """
    device = models.OneToOneField(
        Device,
        on_delete=models.CASCADE,
        related_name="alert_settings",
    )
    
    # Email notifications toggle
    alerts_enabled = models.BooleanField(default=False)
    
    # High temperature alert
    high_temp_enabled = models.BooleanField(default=False)
    high_temp_threshold = models.FloatField(default=30.0)  # °C
    
    # Low temperature alert
    low_temp_enabled = models.BooleanField(default=False)
    low_temp_threshold = models.FloatField(default=10.0)  # °C
    
    # Rate limiting - don't spam emails
    min_alert_interval_minutes = models.IntegerField(default=30)
    last_high_alert_sent = models.DateTimeField(null=True, blank=True)
    last_low_alert_sent = models.DateTimeField(null=True, blank=True)
    
    # Email recipient (defaults to device owner's email)
    custom_email = models.EmailField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Device Alert Settings"
        verbose_name_plural = "Device Alert Settings"

    def __str__(self):
        return f"Alert settings for {self.device.serial_number}"
    
    def get_recipient_email(self):
        """Returns the email to send alerts to."""
        if self.custom_email:
            return self.custom_email
        return self.device.owner.email
    
    def can_send_high_alert(self):
        """Check if enough time has passed since last high temp alert."""
        if not self.last_high_alert_sent:
            return True
        elapsed = timezone.now() - self.last_high_alert_sent
        return elapsed >= timedelta(minutes=self.min_alert_interval_minutes)
    
    def can_send_low_alert(self):
        """Check if enough time has passed since last low temp alert."""
        if not self.last_low_alert_sent:
            return True
        elapsed = timezone.now() - self.last_low_alert_sent
        return elapsed >= timedelta(minutes=self.min_alert_interval_minutes)

