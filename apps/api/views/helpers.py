"""
Shared helper functions, decorators, and utilities for views.
"""

import logging
import os
from functools import wraps

from django.conf import settings
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..models import Device, DeviceApiKey, DeviceAlertSettings, TelemetrySnapshot

logger = logging.getLogger(__name__)

# How many samples to show in "Recent telemetry" views by default
RECENT_TELEMETRY_LIMIT = 20


# ---------------------------------------------------------------------------
# Email Alert Functions
# ---------------------------------------------------------------------------

def check_and_send_temperature_alerts(device, temperature_c):
    """
    Check if the temperature exceeds alert thresholds and send email if needed.
    Respects cooldown periods to avoid spamming.
    """
    try:
        alert_settings = device.alert_settings
    except DeviceAlertSettings.DoesNotExist:
        return  # No alert settings configured
    
    if not alert_settings.alerts_enabled:
        return  # Alerts disabled
    
    recipient = alert_settings.get_recipient_email()
    if not recipient:
        logger.warning("No recipient email for device %s alerts", device.serial_number)
        return
    
    alerts_sent = []
    
    # Check high temperature alert
    if (alert_settings.high_temp_enabled and 
        temperature_c >= alert_settings.high_temp_threshold and
        alert_settings.can_send_high_alert()):
        
        subject = f"🔴 High Temperature Alert - {device.name or device.serial_number}"
        message = (
            f"Temperature alert for your thermostat device.\n\n"
            f"Device: {device.name or device.serial_number}\n"
            f"Current Temperature: {temperature_c:.1f}°C\n"
            f"High Threshold: {alert_settings.high_temp_threshold:.1f}°C\n\n"
            f"The temperature has exceeded your configured high threshold.\n\n"
            f"--\nThermostatRTOS Alert System"
        )
        
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                fail_silently=False,
            )
            alert_settings.last_high_alert_sent = timezone.now()
            alert_settings.save(update_fields=["last_high_alert_sent"])
            alerts_sent.append("high")
            logger.info("Sent high temp alert for device %s to %s", device.serial_number, recipient)
        except Exception as e:
            logger.error("Failed to send high temp alert for device %s: %s", device.serial_number, e)
    
    # Check low temperature alert
    if (alert_settings.low_temp_enabled and 
        temperature_c <= alert_settings.low_temp_threshold and
        alert_settings.can_send_low_alert()):
        
        subject = f"🔵 Low Temperature Alert - {device.name or device.serial_number}"
        message = (
            f"Temperature alert for your thermostat device.\n\n"
            f"Device: {device.name or device.serial_number}\n"
            f"Current Temperature: {temperature_c:.1f}°C\n"
            f"Low Threshold: {alert_settings.low_temp_threshold:.1f}°C\n\n"
            f"The temperature has dropped below your configured low threshold.\n\n"
            f"--\nThermostatRTOS Alert System"
        )
        
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                fail_silently=False,
            )
            alert_settings.last_low_alert_sent = timezone.now()
            alert_settings.save(update_fields=["last_low_alert_sent"])
            alerts_sent.append("low")
            logger.info("Sent low temp alert for device %s to %s", device.serial_number, recipient)
        except Exception as e:
            logger.error("Failed to send low temp alert for device %s: %s", device.serial_number, e)
    
    return alerts_sent


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _recent_telemetry_qs_for_device(device, limit: int = RECENT_TELEMETRY_LIMIT):
    """
    Return a queryset of the most recent telemetry snapshots for a device,
    capped to the given limit (newest first).
    """
    limit = max(1, int(limit))
    qs = (
        TelemetrySnapshot.objects
        .filter(device_id=device.serial_number)
        .order_by("-server_ts")
    )
    return qs[:limit]


def api_login_required(view_func):
    """
    Decorator for JSON API views that require a logged-in user (session-based).
    Returns HTTP 401 JSON instead of redirecting to login HTML.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "Authentication required"}, status=401)
        return view_func(request, *args, **kwargs)
    return _wrapped


def authenticate_device_from_header(request):
    """
    Authenticate a device using an Authorization header of the form:
        Authorization: Device <serial_number>:<api_key>

    Returns (device, error_response):
      - (Device instance, None) on success
      - (None, JsonResponse) on failure
    """
    auth_header = request.META.get("HTTP_AUTHORIZATION", "").strip()
    prefix = "Device "

    if not auth_header.startswith(prefix):
        return None, JsonResponse(
            {"detail": "Missing or invalid Authorization header"},
            status=401,
        )

    token = auth_header[len(prefix):].strip()
    try:
        serial, raw_key = token.split(":", 1)
    except ValueError:
        return None, JsonResponse(
            {"detail": "Invalid device credentials format"},
            status=401,
        )

    serial = serial.strip()
    raw_key = raw_key.strip()

    if not serial or not raw_key:
        return None, JsonResponse(
            {"detail": "Invalid device credentials format"},
            status=401,
        )

    # 1. ALWAYS hash the key first (constant time)
    key_hash = DeviceApiKey.hash_key(raw_key)

    # 2. Single combined query (no early return on missing device)
    api_key_obj = (
        DeviceApiKey.objects.filter(
            device__serial_number=serial,
            key_hash=key_hash,
            is_active=True,
        )
        .select_related("device")
        .order_by("-expires_at")
        .first()
    )

    # 3. Generic error for ALL failures
    if api_key_obj is None or not api_key_obj.is_valid():
        return None, JsonResponse(
            {"detail": "Invalid device credentials"},
            status=403,
        )

    # 4. Return device from the key object
    return api_key_obj.device, None


def _get_owned_device_or_404(user, device_id: int) -> Device:
    """
    Ensure the device exists and belongs to this user.
    Raises 404 if not found or not owned.
    """
    return get_object_or_404(Device, id=device_id, owner=user)


def _parse_bool(value: str) -> bool:
    """Parse a string value to boolean."""
    if value is None:
        return False
    return value.lower() in ("1", "true", "yes", "y", "on")


def _parse_local(dt_str):
    """
    Parse a datetime-local string (from the browser) and make it
    timezone-aware in the current Django timezone.
    """
    if not dt_str:
        return None
    dt = parse_datetime(dt_str)
    if not dt:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt
