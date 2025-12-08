"""
ThermostatRTOS Platform - Rate Limiting Decorators

This module provides rate limiting decorators to protect API endpoints
from abuse and brute-force attacks:
    - ratelimit_login: 5 attempts per minute
    - ratelimit_register: 3 registrations per hour per IP
    - ratelimit_telemetry: 60 requests per minute per device
    - ratelimit_key_rotation: 5 key rotations per hour per device

Author:     Gonzalo Patino
Created:    2025
Course:     Southern New Hampshire University
License:    Academic Use Only - See LICENSE file
"""

from functools import wraps
from django.conf import settings
from django.http import JsonResponse
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited


def get_client_ip(request):
    """Extract client IP from request, handling proxies."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def get_device_key(request):
    """Extract device key from request for device-specific rate limiting."""
    # Check header first, then query params
    device_key = request.META.get("HTTP_X_DEVICE_KEY")
    if not device_key:
        device_key = request.GET.get("device_key") or request.POST.get("device_key")
    return device_key or get_client_ip(request)


# Rate limit decorators for specific endpoints
def ratelimit_login(view_func):
    """Rate limit: 5 attempts per minute for login."""
    return ratelimit(
        key="ip",
        rate=getattr(settings, "RATELIMIT_LOGIN", "5/m"),
        method=["POST"],
        block=True,
    )(view_func)


def ratelimit_register(view_func):
    """Rate limit: 3 registrations per hour per IP."""
    return ratelimit(
        key="ip",
        rate=getattr(settings, "RATELIMIT_REGISTER", "3/h"),
        method=["POST"],
        block=True,
    )(view_func)


def ratelimit_telemetry(view_func):
    """Rate limit: 60 requests per minute per device."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Apply rate limit using device key
        decorated = ratelimit(
            key=lambda group, req: get_device_key(req),
            rate=getattr(settings, "RATELIMIT_TELEMETRY", "60/m"),
            method=["POST"],
            block=True,
        )(view_func)
        return decorated(request, *args, **kwargs)
    return wrapper


def ratelimit_key_rotation(view_func):
    """Rate limit: 5 key rotations per hour per device."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        decorated = ratelimit(
            key=lambda group, req: get_device_key(req),
            rate=getattr(settings, "RATELIMIT_KEY_ROTATION", "5/h"),
            method=["POST"],
            block=True,
        )(view_func)
        return decorated(request, *args, **kwargs)
    return wrapper


def ratelimited_error(request, exception=None):
    """Custom view for rate limit exceeded errors."""
    return JsonResponse(
        {
            "error": "rate_limit_exceeded",
            "message": "Too many requests. Please try again later.",
        },
        status=429,
    )
