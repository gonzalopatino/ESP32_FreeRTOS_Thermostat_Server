"""
ThermostatRTOS Platform - JSON API Endpoints

This module provides JSON API endpoints for programmatic access:
    - ping: Health check endpoint
    - register_device: Register new IoT thermostat devices
    - list_devices: Retrieve user's registered devices
    - list_device_keys: View API keys for a device
    - rotate_device_key: Generate new API key for a device
    - revoke_device_key: Deactivate an API key

All endpoints return JSON responses and require session authentication.

Author:     Gonzalo Patino
Created:    2025
Course:     Southern New Hampshire University
License:    Academic Use Only - See LICENSE file
"""

import json

from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.http import require_POST

from ..models import Device, DeviceApiKey
from ..ratelimits import ratelimit_key_rotation, ratelimit_register
from .helpers import api_login_required


def ping(request):
    """Health check endpoint."""
    return JsonResponse(
        {
            "status": "ok",
            "message": "api app wired",
        }
    )


@require_POST
@api_login_required
@ratelimit_register
def register_device(request):
    """
    Register a thermostat to the logged-in user, or rotate its API key.

    Body (JSON):
    {
        "serial_number": "SN-123...",
        "name": "Living Room"    # optional
    }

    Responses:
    - 200 with device + api_key if success
    - 400 if serial missing or already claimed by another user
    - 401 if not authenticated
    """
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    serial = (payload.get("serial_number") or "").strip()
    name = (payload.get("name") or "").strip()

    if not serial:
        return HttpResponseBadRequest("Field 'serial_number' is required")

    # Truncate to our DB max length just in case
    serial = serial[:64]

    # Check if a device with this serial already exists
    existing = Device.objects.filter(serial_number=serial).first()

    if existing and existing.owner != request.user:
        return JsonResponse(
            {"detail": "This device serial is already registered to another user."},
            status=400,
        )

    if existing is None:
        # New device, claim it for this user
        device = Device.objects.create(
            owner=request.user,
            serial_number=serial,
            name=name,
        )
    else:
        # Already owned by this user: optionally update name
        device = existing
        if name:
            device.name = name
            device.save(update_fields=["name"])

    # Deactivate any existing keys for this device (key rotation)
    device.api_keys.update(is_active=False)

    # Create a new key valid for 1 year
    api_key_obj, raw_key = DeviceApiKey.create_for_device(device, ttl_days=365)

    return JsonResponse(
        {
            "device": {
                "id": device.id,
                "serial_number": device.serial_number,
                "name": device.name,
                "owner": device.owner.username,
                "created_at": device.created_at.isoformat(),
            },
            "api_key": raw_key,  # shown once to the caller
            "expires_at": api_key_obj.expires_at.isoformat(),
        }
    )


@api_login_required
def list_devices(request):
    """
    Return all devices owned by the logged-in user.

    GET /api/devices/

    Response:
    {
        "count": N,
        "results": [
            {
                "id": 1,
                "serial_number": "SN-ESP32-THERMO-001",
                "name": "Living Room Thermostat",
                "created_at": "...iso8601..."
            },
            ...
        ]
    }
    """
    devices = Device.objects.filter(owner=request.user).order_by("created_at")

    results = []
    for d in devices:
        results.append(
            {
                "id": d.id,
                "serial_number": d.serial_number,
                "name": d.name,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "last_seen": d.last_seen.isoformat() if d.last_seen else None,
            }
        )

    return JsonResponse(
        {
            "count": len(results),
            "results": results,
        }
    )


@api_login_required
def list_device_keys(request, device_id: int):
    """
    List all API keys for a device owned by the current user.

    GET /api/devices/<device_id>/keys/
    """
    if request.method != "GET":
        return HttpResponseBadRequest("Only GET allowed")

    device = Device.objects.filter(id=device_id, owner=request.user).first()
    if device is None:
        return JsonResponse(
            {"detail": "Device not found or not owned by this user."},
            status=404,
        )

    keys = device.api_keys.order_by("-created_at")

    results = []
    for k in keys:
        results.append(
            {
                "id": k.id,
                "created_at": k.created_at.isoformat() if k.created_at else None,
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                "is_active": k.is_active,
            }
        )

    return JsonResponse(
        {
            "device_id": device.id,
            "serial_number": device.serial_number,
            "count": len(results),
            "results": results,
        }
    )


@require_POST
@api_login_required
@ratelimit_key_rotation
def revoke_device_key(request, device_id, key_id):
    """
    Revoke (deactivate) a specific API key for a device owned by the current user.

    URL:
        POST /api/devices/<device_id>/keys/<key_id>/revoke/

    Auth:
        - Session login required (api_login_required)
        - Device must belong to request.user
    """
    # Ensure the device exists and belongs to the current user
    device = Device.objects.filter(id=device_id, owner=request.user).first()
    if device is None:
        return JsonResponse(
            {"detail": "Device not found or not owned by this user."},
            status=404,
        )

    # Find the key for this device
    api_key_obj = DeviceApiKey.objects.filter(id=key_id, device=device).first()
    if api_key_obj is None:
        return JsonResponse(
            {"detail": "Key not found for this device."},
            status=404,
        )

    # Deactivate it (idempotent: calling again keeps it inactive)
    if api_key_obj.is_active:
        api_key_obj.is_active = False
        api_key_obj.save(update_fields=["is_active"])

    return JsonResponse(
        {
            "device_id": device.id,
            "serial_number": device.serial_number,
            "key": {
                "id": api_key_obj.id,
                "created_at": api_key_obj.created_at.isoformat(),
                "expires_at": api_key_obj.expires_at.isoformat()
                if api_key_obj.expires_at
                else None,
                "is_active": api_key_obj.is_active,
            },
        }
    )


@require_POST
@api_login_required
@ratelimit_key_rotation
def rotate_device_key(request, device_id):
    """
    Rotate the API key for a device owned by the current user.

    URL:
        POST /api/devices/<device_id>/keys/rotate/

    Behavior:
        - Ensures the device belongs to request.user
        - Marks all existing keys as inactive
        - Creates a new key valid for 1 year
        - Returns the new raw key (shown once)
    """
    # Ensure the device exists and belongs to this user
    device = Device.objects.filter(id=device_id, owner=request.user).first()
    if device is None:
        return JsonResponse(
            {"detail": "Device not found or not owned by this user."},
            status=404,
        )

    # Deactivate all existing keys for this device
    device.api_keys.update(is_active=False)

    # Create a new active key valid for 1 year
    api_key_obj, raw_key = DeviceApiKey.create_for_device(device, ttl_days=365)

    return JsonResponse(
        {
            "device": {
                "id": device.id,
                "serial_number": device.serial_number,
                "name": device.name,
                "created_at": device.created_at.isoformat(),
            },
            "api_key": raw_key,  # only time you see this value
            "expires_at": api_key_obj.expires_at.isoformat()
            if api_key_obj.expires_at
            else None,
        }
    )
