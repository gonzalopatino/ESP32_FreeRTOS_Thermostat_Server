"""
ThermostatRTOS Platform - Database Models

This module defines the data models for the ThermostatRTOS platform:
    - StoragePlan: User storage tier definitions
    - UserStorageProfile: Per-user storage quota tracking
    - Device: IoT thermostat device registration
    - DeviceApiKey: Secure API key management with SHA-256 hashing
    - TelemetrySnapshot: Temperature and HVAC state telemetry records
    - DeviceAlertSettings: Configurable temperature alert thresholds

Author:     Gonzalo Patino
Created:    2025
Course:     Southern New Hampshire University
License:    Academic Use Only - See LICENSE file
"""

from datetime import timedelta
import hashlib
import secrets


from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Sum
from django.db.models.functions import Coalesce

from django.conf import settings
from django.utils.timezone import now


User = get_user_model()


# ============================================================================
# STORAGE PLANS
# ============================================================================

class StoragePlan:
    """Storage plan definitions with limits in bytes."""
    FREE = 'free'
    STANDARD = 'standard'
    PREMIUM = 'premium'
    
    CHOICES = [
        (FREE, 'Free (2 GB)'),
        (STANDARD, 'Standard (10 GB)'),
        (PREMIUM, 'Premium (1 TB)'),
    ]
    
    # Limits in bytes
    LIMITS = {
        FREE: 2 * 1024 * 1024 * 1024,        # 2 GB
        STANDARD: 10 * 1024 * 1024 * 1024,   # 10 GB
        PREMIUM: 1024 * 1024 * 1024 * 1024,  # 1 TB
    }
    
    @classmethod
    def get_limit_bytes(cls, plan):
        return cls.LIMITS.get(plan, cls.LIMITS[cls.FREE])
    
    @classmethod
    def get_limit_display(cls, plan):
        """Returns human-readable limit."""
        limit = cls.get_limit_bytes(plan)
        if limit >= 1024 * 1024 * 1024 * 1024:
            return f"{limit // (1024 * 1024 * 1024 * 1024)} TB"
        elif limit >= 1024 * 1024 * 1024:
            return f"{limit // (1024 * 1024 * 1024)} GB"
        elif limit >= 1024 * 1024:
            return f"{limit // (1024 * 1024)} MB"
        return f"{limit} bytes"


class UserStorageProfile(models.Model):
    """
    Tracks a user's storage plan and cached usage.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="storage_profile",
    )
    
    plan = models.CharField(
        max_length=20,
        choices=StoragePlan.CHOICES,
        default=StoragePlan.FREE,
    )
    
    # Cached storage usage (updated periodically or on data changes)
    cached_usage_bytes = models.BigIntegerField(default=0)
    usage_last_calculated = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "User Storage Profile"
        verbose_name_plural = "User Storage Profiles"
    
    def __str__(self):
        return f"{self.user.username} - {self.get_plan_display()}"
    
    @property
    def storage_limit_bytes(self):
        return StoragePlan.get_limit_bytes(self.plan)
    
    @property
    def storage_limit_display(self):
        return StoragePlan.get_limit_display(self.plan)
    
    @property
    def usage_percentage(self):
        if self.storage_limit_bytes == 0:
            return 100
        return min(100, (self.cached_usage_bytes / self.storage_limit_bytes) * 100)
    
    @property
    def is_storage_full(self):
        return self.cached_usage_bytes >= self.storage_limit_bytes
    
    @property
    def remaining_bytes(self):
        return max(0, self.storage_limit_bytes - self.cached_usage_bytes)
    
    def calculate_actual_usage(self):
        """
        Calculate actual storage usage from all user's telemetry data.
        This queries the database to get the actual size.
        """
        from django.db import connection
        
        # Get all device serial numbers for this user
        device_serials = list(
            Device.objects.filter(owner=self.user).values_list('serial_number', flat=True)
        )
        
        if not device_serials:
            return 0
        
        # Calculate approximate row size in bytes
        # This is an estimation based on typical telemetry snapshot fields
        # For more accuracy, you could use pg_total_relation_size in PostgreSQL
        total_bytes = 0
        
        for serial in device_serials:
            snapshots = TelemetrySnapshot.objects.filter(device_id=serial)
            count = snapshots.count()
            
            if count > 0:
                # Estimate ~500 bytes per row (including indexes and overhead)
                # Actual size varies based on raw_payload size
                # For more accuracy, sample a few rows and measure their JSON size
                sample = snapshots.order_by('-server_ts')[:100]
                
                avg_payload_size = 0
                for s in sample:
                    if s.raw_payload:
                        import json
                        avg_payload_size += len(json.dumps(s.raw_payload))
                
                if sample:
                    avg_payload_size = avg_payload_size / len(sample)
                
                # Base row size (fixed fields) + average payload + index overhead
                base_row_size = 200  # Fixed fields
                index_overhead = 100  # B-tree index overhead per row
                row_size = base_row_size + avg_payload_size + index_overhead
                
                total_bytes += int(count * row_size)
        
        return total_bytes
    
    def refresh_usage_cache(self):
        """Recalculate and cache the storage usage."""
        self.cached_usage_bytes = self.calculate_actual_usage()
        self.usage_last_calculated = timezone.now()
        self.save(update_fields=['cached_usage_bytes', 'usage_last_calculated'])
        return self.cached_usage_bytes
    
    def format_bytes(self, bytes_val):
        """Format bytes to human-readable string."""
        if bytes_val >= 1024 * 1024 * 1024:
            return f"{bytes_val / (1024 * 1024 * 1024):.2f} GB"
        elif bytes_val >= 1024 * 1024:
            return f"{bytes_val / (1024 * 1024):.2f} MB"
        elif bytes_val >= 1024:
            return f"{bytes_val / 1024:.2f} KB"
        return f"{bytes_val} bytes"
    
    @property
    def usage_display(self):
        return self.format_bytes(self.cached_usage_bytes)
    
    @property
    def remaining_display(self):
        return self.format_bytes(self.remaining_bytes)




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
    
    # Device's local IP address (reported in telemetry)
    last_ip = models.GenericIPAddressField(null=True, blank=True)

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

