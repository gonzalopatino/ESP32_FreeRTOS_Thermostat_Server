"""
Views for the API and dashboard pages.
Organized imports for clarity and maintenance.
"""

# Standard library imports
import csv
import json
import logging
import os
from datetime import timedelta
from functools import wraps
from zoneinfo import ZoneInfo

# Third-party imports
from dotenv import load_dotenv

# Django auth imports
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.views import LoginView  # currently unused, kept for future

# Django core framework imports
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods

# Local application imports
from .models import Device, DeviceApiKey, TelemetrySnapshot
from .ratelimits import (
    ratelimit_login,
    ratelimit_register,
    ratelimit_telemetry,
    ratelimit_key_rotation,
    ratelimited_error,
)
from apps.api.signing import decode_serial, encode_serial


logger = logging.getLogger(__name__)
API_KEY = os.getenv("TELEMETRY_API_KEY")
User = get_user_model()

# How many samples to show in "Recent telemetry" views by default
RECENT_TELEMETRY_LIMIT = 20


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


# ---------------------------------------------------------------------------
# HTML auth views
# ---------------------------------------------------------------------------

def register_page(request):
    """
    Simple HTML registration view using Django's UserCreationForm.
    After successful registration, redirect to login page.
    """
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("login")  # name of the login URL
    else:
        form = UserCreationForm()

    return render(request, "registration/register.html", {"form": form})


@login_required
def logout_view(request):
    """
    HTML logout for dashboard users.

    Logs out the current user and redirects to the login page.
    """
    logout(request)
    return redirect("login")


@login_required
@require_http_methods(["GET", "POST"])
def user_settings(request):
    """
    User account settings page.
    
    Allows users to update their profile information:
    - Username
    - Email address
    - First name
    - Last name
    - Password (optional)
    """
    user = request.user
    
    if request.method == "POST":
        # Get form data
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        current_password = request.POST.get("current_password", "")
        new_password = request.POST.get("new_password", "")
        confirm_password = request.POST.get("confirm_password", "")
        
        errors = []
        
        # Validate username
        if not username:
            errors.append("Username is required.")
        elif username != user.username:
            # Check if username is already taken
            if User.objects.filter(username=username).exclude(pk=user.pk).exists():
                errors.append("This username is already taken.")
        
        # Validate email
        if not email:
            errors.append("Email address is required.")
        elif email != user.email:
            # Check if email is already taken
            if User.objects.filter(email=email).exclude(pk=user.pk).exists():
                errors.append("This email address is already in use.")
        
        # Validate password change (if attempting)
        if new_password or confirm_password:
            if not current_password:
                errors.append("Current password is required to set a new password.")
            elif not user.check_password(current_password):
                errors.append("Current password is incorrect.")
            elif new_password != confirm_password:
                errors.append("New passwords do not match.")
            elif len(new_password) < 8:
                errors.append("New password must be at least 8 characters long.")
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            # Update user fields
            user.username = username
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            
            # Update password if provided
            if new_password:
                user.set_password(new_password)
                user.save()
                # Re-authenticate to maintain session
                login(request, user)
                messages.success(request, "Your password has been updated. You have been re-authenticated.")
            else:
                user.save()
                messages.success(request, "Your account settings have been updated.")
            
            return redirect("user_settings")
    
    return render(request, "dashboard/settings.html", {"user": user})


# ---------------------------------------------------------------------------
# Dashboard HTML views
# ---------------------------------------------------------------------------

@login_required
def dashboard_devices(request):
    """
    Dashboard landing page: list devices for the logged-in user.
    """
    devices = (
        Device.objects
        .filter(owner=request.user)
        .annotate(
            active_key_count=Count(
                "api_keys",
                filter=Q(api_keys__is_active=True),
            )
        )
        .prefetch_related("api_keys")
        .order_by("id")
    )

    context = {
        "devices": devices,
    }
    return render(request, "dashboard/devices.html", context)


@login_required
def dashboard_register_device(request):
    """
    HTML form to register or claim a device for the logged-in user.

    This is the view behind the 'Register New Device' navbar tab.
    """
    if request.method == "POST":
        serial = request.POST.get("serial_number", "").strip()
        name = request.POST.get("name", "").strip()

        if not serial:
            messages.error(request, "Serial number is required.")
            return redirect("dashboard_register_device")

        # Try to find an existing device with this serial
        try:
            device = Device.objects.get(serial_number=serial)
            if device.owner != request.user:
                messages.error(
                    request,
                    "This device serial is already registered to another user.",
                )
                return redirect("dashboard_register_device")
            # Device is already owned by this user, optional rename
            if name:
                device.name = name
                device.save()
        except Device.DoesNotExist:
            # Create a new device and assign to this user
            device = Device.objects.create(
                owner=request.user,
                serial_number=serial,
                name=name,
            )

        # Rotate keys: deactivate all previous keys
        device.api_keys.update(is_active=False)

        # Create a fresh API key and get the raw value once
        api_key_obj, raw_key = DeviceApiKey.create_for_device(device, ttl_days=365)

        messages.success(
            request,
            (
                f"Device '{device.serial_number}' registered. "
                f"Copy this API key now, you will not see it again: {raw_key}"
            ),
        )

        # After successful registration, go back to dashboard list
        return redirect("dashboard_devices")

    # GET – show the registration form
    return render(request, "dashboard/register_device.html")


@login_required
def dashboard_device_detail(request, device_id: int):
    """
    Device detail page for the dashboard, including API key management
    and recent telemetry preview.
    """
    # Ensure the device belongs to the logged-in user
    device = get_object_or_404(Device, id=device_id, owner=request.user)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "rotate":
            # Deactivate all existing keys
            device.api_keys.update(is_active=False)
            # Create a new key with 1-year TTL
            api_key_obj, raw_key = DeviceApiKey.create_for_device(
                device, ttl_days=365
            )
            messages.success(
                request,
                (
                    "API key rotated. Copy this new key now, "
                    f"you will not see it again: {raw_key}"
                ),
            )
            return redirect("dashboard_device_detail", device_id=device.id)

        elif action == "revoke":
            key_id = request.POST.get("key_id")
            try:
                key = device.api_keys.get(id=key_id)
            except DeviceApiKey.DoesNotExist:
                messages.error(request, "API key not found for this device.")
            else:
                if not key.is_active:
                    messages.info(request, "This API key is already inactive.")
                else:
                    key.is_active = False
                    key.save()
                    messages.success(request, "API key revoked.")
            return redirect("dashboard_device_detail", device_id=device.id)

        elif action == "update_device":
            new_name = (request.POST.get("name") or "").strip()
            if not new_name:
                messages.error(request, "Device name cannot be empty.")
            else:
                device.name = new_name
                device.save(update_fields=["name"])
                messages.success(request, "Device name updated.")
            return redirect("dashboard_device_detail", device_id=device.id)

        elif action == "delete_device":
            serial = device.serial_number

            # Delete related API keys
            device.api_keys.all().delete()

            # Delete telemetry snapshots for this device (because not FK)
            TelemetrySnapshot.objects.filter(device_id=serial).delete()

            # Finally delete the device itself
            device.delete()

            messages.success(
                request,
                f"Device '{serial}' and all its telemetry have been deleted.",
            )
            return redirect("dashboard_devices")

    # GET (or fallthrough after POST handling) – show device info and telemetry
    snapshots = _recent_telemetry_qs_for_device(device)
    keys = device.api_keys.order_by("-created_at")

    context = {
        "device": device,
        "snapshots": snapshots,
        "keys": keys,
    }
    return render(request, "dashboard/device_detail.html", context)


@login_required
def telemetry_export_csv(request):
    """
    Export telemetry history for a single device as CSV.

    Query parameters:
      - device_id: the device serial number (required)
      - start: optional datetime-local from the datepicker
      - end: optional datetime-local from the datepicker
      - tz: optional IANA timezone name (e.g. America/Vancouver)
    """
    device_id = request.GET.get("device_id")
    start_param = request.GET.get("start")
    end_param = request.GET.get("end")

    if not device_id:
        return HttpResponse("Missing device_id", status=400)

    # Make sure this device belongs to the logged-in user
    device = Device.objects.filter(
        serial_number=device_id,
        owner=request.user,
    ).first()
    if device is None:
        return HttpResponse("Device not found or not owned", status=404)

    # Base queryset
    qs = TelemetrySnapshot.objects.filter(device_id=device.serial_number)

    # Timezone for "local" columns
    tz_name = request.GET.get("tz")
    if tz_name:
        try:
            local_tz = ZoneInfo(tz_name)
        except Exception:
            # Fallback instead of 400
            local_tz = timezone.get_current_timezone()
    else:
        local_tz = timezone.get_current_timezone()

    # Parse datetime-local strings from the browser and make them aware
    def _parse_picker(value):
        if not value:
            return None
        dt = parse_datetime(value)
        if not dt:
            return None
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, local_tz)
        return dt

    start_dt = _parse_picker(start_param)
    end_dt = _parse_picker(end_param)

    # Apply filters
    if start_param:
        if not start_dt:
            return HttpResponse("Invalid 'start' datetime", status=400)
        qs = qs.filter(server_ts__gte=start_dt)

    if end_param:
        if not end_dt:
            return HttpResponse("Invalid 'end' datetime", status=400)
        qs = qs.filter(server_ts__lte=end_dt)

    # Default to last 24h if no range picked
    if not start_param and not end_param:
        window_start = timezone.now() - timedelta(hours=24)
        qs = qs.filter(server_ts__gte=window_start)

    qs = qs.order_by("server_ts")

    # Prepare CSV response
    filename = f"{device.serial_number}_telemetry.csv"
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)

    # Header row
    writer.writerow(
        [
            "server_ts_utc",
            "server_ts_local",
            "device_ts_utc",
            "device_ts_local",
            "temp_inside_c",
            "temp_outside_c",
            "setpoint_c",
            "hysteresis_c",
            "humidity_percent",
            "mode",
            "output",
        ]
    )

    # Data rows
    for s in qs:
        # Server timestamps
        if s.server_ts:
            server_ts_utc = s.server_ts.isoformat()
            server_ts_local = timezone.localtime(
                s.server_ts, local_tz
            ).strftime("%Y-%m-%d %H:%M:%S")
        else:
            server_ts_utc = ""
            server_ts_local = ""

        # Device timestamps
        if s.device_ts:
            device_ts_utc = s.device_ts.isoformat()
            device_ts_local = timezone.localtime(
                s.device_ts, local_tz
            ).strftime("%Y-%m-%d %H:%M:%S")
        else:
            device_ts_utc = ""
            device_ts_local = ""

        writer.writerow(
            [
                server_ts_utc,
                server_ts_local,
                device_ts_utc,
                device_ts_local,
                s.temp_inside_c,
                s.temp_outside_c,
                s.setpoint_c,
                s.hysteresis_c,
                s.humidity_percent,
                s.mode,
                s.output,
            ]
        )

    return response


@login_required
def about(request):
    """Simple About / metadata page."""
    return render(request, "about.html")


# ---------------------------------------------------------------------------
# JSON auth endpoints
# ---------------------------------------------------------------------------


@require_POST
@ratelimit_register
def register_user(request):
    """
    Simple JSON registration endpoint.

    Body:
    {
        "username": "gonzalo",
        "password": "secret123",
        "email": "optional@example.com"
    }

    On success:
    - Creates a new user
    - Logs them in (session cookie)
    - Returns basic user info
    """
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    email = (payload.get("email") or "").strip()

    if not username or not password:
        return HttpResponseBadRequest("Fields 'username' and 'password' are required")

    if User.objects.filter(username=username).exists():
        return JsonResponse(
            {"detail": "Username already taken"},
            status=400,
        )

    user = User.objects.create_user(
        username=username,
        password=password,
        email=email or None,
    )

    # Log the user in so Postman gets a session cookie
    login(request, user)

    return JsonResponse(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        },
        status=201,
    )



@ratelimit_login
@require_POST
def login_user(request):
    """
    JSON login endpoint.

    Body:
    {
        "username": "gonzalo",
        "password": "secret123"
    }

    On success:
    - Logs in the user (session cookie)
    - Returns basic user info
    """
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    if not username or not password:
        return HttpResponseBadRequest("Fields 'username' and 'password' are required")

    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse(
            {"detail": "Invalid credentials"},
            status=400,
        )

    login(request, user)

    return JsonResponse(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        }
    )



@require_POST
def logout_user(request):
    """
    Log out the current user (session-based).
    """
    logout(request)
    return JsonResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Telemetry JSON endpoints
# ---------------------------------------------------------------------------


@login_required
def recent_telemetry(request):
    """
    JSON endpoint: recent telemetry for a device, capped to latest N samples.
    Used by the 'Recent telemetry' table or other lightweight widgets.

    Security:
      - Only returns telemetry for devices owned by the logged-in user.

    Query params:
      - device_id: optional serial. If omitted, uses the latest device
        that belongs to this user and that has data.
      - limit: optional int <= RECENT_TELEMETRY_LIMIT
        (defaults to RECENT_TELEMETRY_LIMIT).
    """
    try:
        requested_limit = int(request.GET.get("limit", RECENT_TELEMETRY_LIMIT))
    except ValueError:
        requested_limit = RECENT_TELEMETRY_LIMIT

    limit = max(1, min(requested_limit, RECENT_TELEMETRY_LIMIT))

    device_serial = request.GET.get("device_id", None)

    # All device serials owned by this user
    user_device_serials = Device.objects.filter(owner=request.user).values_list(
        "serial_number", flat=True
    )

    # Base queryset: telemetry, newest first, for user-owned devices only
    base_qs = TelemetrySnapshot.objects.filter(
        device_id__in=user_device_serials
    ).order_by("-server_ts")

    if device_serial:
        # Make sure this device exists and is owned by this user
        device = Device.objects.filter(
            serial_number=device_serial,
            owner=request.user,
        ).first()
        if device is None:
            # Either not found or not owned
            return JsonResponse(
                {"detail": "Device not found or not owned"}, status=404
            )
        qs = base_qs.filter(device_id=device.serial_number)
        resolved_serial = device.serial_number
    else:
        # No device specified: use the latest device that has data and is owned by this user
        first_snapshot = base_qs.first()
        if not first_snapshot:
            # No telemetry at all for this user
            return JsonResponse(
                {"count": 0, "device_id": None, "data": []}
            )
        resolved_serial = first_snapshot.device_id
        qs = base_qs.filter(device_id=resolved_serial)

    qs = qs[:limit]

    data = []
    for s in qs:
        raw = s.raw_payload or {}
        device_ts_local = raw.get("timestamp")
        device_ts_utc = s.device_ts
        data.append(
            {
                "id": s.id,
                "device_id": s.device_id,
                "mode": s.mode,
                "temp_inside_c": s.temp_inside_c,
                "temp_outside_c": s.temp_outside_c,
                "setpoint_c": s.setpoint_c,
                "hysteresis_c": s.hysteresis_c,
                "output": s.output,
                "humidity_percent": s.humidity_percent,
                # what the ESP32 actually sent, with its timezone offset
                "device_ts": device_ts_local
                or (device_ts_utc.isoformat() if device_ts_utc else None),
                # keep UTC around for dashboards / SQL
                "device_ts_utc": device_ts_utc.isoformat() if device_ts_utc else None,
                "server_ts": s.server_ts.isoformat() if s.server_ts else None,
            }
        )

    return JsonResponse(
        {
            "count": len(data),
            "device_id": resolved_serial,
            "data": data,
        }
    )

@csrf_exempt
@require_POST
@ratelimit_telemetry
def ingest_telemetry(request):
    """
    Ingest telemetry from an authenticated device.

    Devices must send:
        Authorization: Device <serial_number>:<api_key>

    Body (JSON) example:
    {
        "mode": "AUTO",
        "setpoint_c": 22.0,
        "temp_inside_c": 25.5,
        "temp_outside_c": 5.0,
        "hysteresis_c": 0.5,
        "humidity_percent": 40.0,
        "output": "HEAT_ON",
        "timestamp": "2025-11-21T06:30:00Z"
    }
    """
    # 1) Authenticate device from Authorization header
    device, error_response = authenticate_device_from_header(request)
    if error_response is not None:
        return error_response

    # 2) Parse JSON body
    try:
        body = request.body.decode("utf-8")
        data = json.loads(body or "{}")
    except Exception as e:
        return HttpResponseBadRequest(f"Invalid JSON: {e}")

    # 3) Validate required fields (device_id is no longer accepted from client)
    required = ["mode", "setpoint_c", "temp_inside_c"]
    missing = [field for field in required if field not in data]
    if missing:
        return HttpResponseBadRequest(
            f"Missing required fields: {', '.join(missing)}"
        )

    # 4) Optional fields from CONTROL
    temp_outside_c = data.get("temp_outside_c")
    hysteresis_c = data.get("hysteresis_c")
    output = data.get("output")  # "HEAT_ON", "COOL_ON", "OFF", etc.
    humidity = data.get("humidity_percent")  # may be absent

    # 5) Optional device timestamp
    device_ts_raw = data.get("timestamp")
    device_ts = parse_datetime(device_ts_raw) if device_ts_raw else None

    # 6) Persist snapshot; linked to this device
    snapshot = TelemetrySnapshot.objects.create(
        device_id=device.serial_number,
        mode=data["mode"],
        temp_inside_c=float(data["temp_inside_c"]),
        temp_outside_c=float(temp_outside_c) if temp_outside_c is not None else None,
        setpoint_c=float(data["setpoint_c"]),
        hysteresis_c=float(hysteresis_c) if hysteresis_c is not None else None,
        output=output or "",
        humidity_percent=float(humidity) if humidity is not None else None,
        device_ts=device_ts,
        raw_payload=data,
    )

    # Update device.last_seen for dashboards
    device.last_seen = now()
    device.save(update_fields=["last_seen"])

    logger.info(
        "Ingested telemetry from device %s (snapshot id=%s)",
        device.serial_number,
        snapshot.id,
    )

    return JsonResponse(
        {
            "status": "ok",
            "id": snapshot.id,
            "server_ts": snapshot.server_ts.isoformat() if snapshot.server_ts else None,
        }
    )


@login_required
def telemetry_query(request):
    """
    Flexible telemetry query endpoint for charts and history views.
    Supports device, start/end, range, and latest flags.

    Security:
      - Only returns telemetry for devices owned by the logged-in user.
    """
    if request.method != "GET":
        return HttpResponseBadRequest("Only GET is allowed")

    # Restrict to telemetry for devices owned by this user
    user_device_serials = Device.objects.filter(owner=request.user).values_list(
        "serial_number", flat=True
    )
    qs = TelemetrySnapshot.objects.filter(device_id__in=user_device_serials)

    # Filter by device
    device_id = request.GET.get("device_id")
    if device_id:
        # Ensure the device exists and is owned by this user
        device = Device.objects.filter(
            serial_number=device_id,
            owner=request.user,
        ).first()
        if device is None:
            return HttpResponseBadRequest("Device not found or not owned")
        qs = qs.filter(device_id=device.serial_number)

    # Time filters: start / end / range
    start_param = request.GET.get("start")
    end_param = request.GET.get("end")
    range_param = request.GET.get("range")

    explicit_range = bool(start_param or end_param)

    # Explicit start / end from datepicker
    if start_param:
        start_dt = _parse_local(start_param)
        if not start_dt:
            return HttpResponseBadRequest("Invalid 'start' datetime")
        qs = qs.filter(server_ts__gte=start_dt)

    if end_param:
        end_dt = _parse_local(end_param)
        if not end_dt:
            return HttpResponseBadRequest("Invalid 'end' datetime")
        qs = qs.filter(server_ts__lte=end_dt)

    # Only apply "range" when there is NO explicit start/end
    if range_param and not explicit_range:
        try:
            if range_param.endswith("h"):
                hours = float(range_param[:-1])
                window_start = timezone.now() - timedelta(hours=hours)
            elif range_param.endswith("d"):
                days = float(range_param[:-1])
                window_start = timezone.now() - timedelta(days=days)
            else:
                return HttpResponseBadRequest(
                    "Invalid 'range' format, use like '24h' or '7d'"
                )
        except ValueError:
            return HttpResponseBadRequest(
                "Invalid 'range' format, use like '24h' or '7d'"
            )
        qs = qs.filter(server_ts__gte=window_start)

    latest_flag = _parse_bool(request.GET.get("latest"))

    if latest_flag:
        # realtime card: newest snapshot only
        qs = qs.order_by("-server_ts")[:1]
    else:
        # history / chart
        if explicit_range:
            # User picked real dates, give them the full window (capped)
            qs = qs.order_by("server_ts")[:10000]  # safety cap
        else:
            # Default case, no explicit range: still use a limit
            limit_param = request.GET.get("limit")
            try:
                limit = int(limit_param) if limit_param else 100
            except ValueError:
                return HttpResponseBadRequest("Invalid 'limit', must be an integer")
            limit = max(1, min(limit, 1000))
            qs = qs.order_by("server_ts")[:limit]

    # Serialize
    results = []
    for s in qs:
        results.append(
            {
                "id": s.id,
                "device_id": s.device_id,
                "mode": s.mode,
                "temp_inside_c": s.temp_inside_c,
                "temp_outside_c": s.temp_outside_c,
                "setpoint_c": s.setpoint_c,
                "hysteresis_c": s.hysteresis_c,
                "humidity_percent": getattr(s, "humidity_percent", None),
                "output": getattr(s, "output", None),
                "device_ts": s.device_ts.isoformat() if s.device_ts else None,
                "server_ts": s.server_ts.isoformat() if s.server_ts else None,
                "raw_payload": s.raw_payload,
            }
        )

    return JsonResponse(
        {
            "count": len(results),
            "results": results,
        }
    )


# ---------------------------------------------------------------------------
# Device and API key management JSON endpoints
# ---------------------------------------------------------------------------

def ping(request):
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
def list_device_keys(request, device_id: int):
    """
    List all API keys for a device owned by the current user.

    GET /api/devices/<device_id>/keys/
    """
    if request.method != "GET":
        return HttpResponseBadRequest("Only GET allowed")

    device = _get_owned_device_or_404(request.user, device_id)
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
