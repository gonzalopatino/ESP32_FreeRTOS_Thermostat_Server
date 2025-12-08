"""
Views package for the API app.

This module re-exports all views for backward compatibility with existing imports.
Views are organized into submodules:
  - helpers: Shared utilities, decorators, and alert functions
  - auth: HTML and JSON authentication views
  - dashboard: HTML dashboard views (devices, settings, data management)
  - api: JSON API endpoints for device and key management
  - telemetry: Telemetry ingestion, querying, and export
"""

# Re-export from helpers
from .helpers import (
    RECENT_TELEMETRY_LIMIT,
    api_login_required,
    authenticate_device_from_header,
    check_and_send_temperature_alerts,
    _get_owned_device_or_404,
    _parse_bool,
    _parse_local,
    _recent_telemetry_qs_for_device,
)

# Re-export from auth
from .auth import (
    login_user,
    logout_user,
    logout_view,
    register_page,
    register_user,
    user_settings,
)

# Re-export from dashboard
from .dashboard import (
    about,
    dashboard_device_detail,
    dashboard_devices,
    dashboard_register_device,
    data_management,
)

# Re-export from api
from .api import (
    list_device_keys,
    list_devices,
    ping,
    register_device,
    revoke_device_key,
    rotate_device_key,
)

# Re-export from telemetry
from .telemetry import (
    ingest_telemetry,
    recent_telemetry,
    telemetry_export_csv,
    telemetry_query,
)

# Re-export ratelimited_error from ratelimits (used in urls.py)
from ..ratelimits import ratelimited_error

__all__ = [
    # Helpers
    "RECENT_TELEMETRY_LIMIT",
    "api_login_required",
    "authenticate_device_from_header",
    "check_and_send_temperature_alerts",
    "_get_owned_device_or_404",
    "_parse_bool",
    "_parse_local",
    "_recent_telemetry_qs_for_device",
    # Auth
    "login_user",
    "logout_user",
    "logout_view",
    "register_page",
    "register_user",
    "user_settings",
    # Dashboard
    "about",
    "dashboard_device_detail",
    "dashboard_devices",
    "dashboard_register_device",
    "data_management",
    # API
    "list_device_keys",
    "list_devices",
    "ping",
    "register_device",
    "revoke_device_key",
    "rotate_device_key",
    # Telemetry
    "ingest_telemetry",
    "recent_telemetry",
    "telemetry_export_csv",
    "telemetry_query",
    # Ratelimits
    "ratelimited_error",
]
