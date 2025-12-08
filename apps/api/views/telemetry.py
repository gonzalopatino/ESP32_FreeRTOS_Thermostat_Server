"""
Telemetry views - ingestion, querying, and CSV export.
"""

import csv
import json
import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from ..models import Device, TelemetrySnapshot, UserStorageProfile
from ..ratelimits import ratelimit_telemetry
from .helpers import (
    RECENT_TELEMETRY_LIMIT,
    _parse_bool,
    _parse_local,
    authenticate_device_from_header,
    check_and_send_temperature_alerts,
)

logger = logging.getLogger(__name__)


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

    # 1.5) Check storage quota before accepting telemetry
    try:
        storage_profile = device.owner.storage_profile
    except UserStorageProfile.DoesNotExist:
        # Create profile if it doesn't exist
        storage_profile = UserStorageProfile.objects.create(user=device.owner)
    
    if storage_profile.is_storage_full:
        return JsonResponse(
            {
                "status": "error",
                "code": "STORAGE_LIMIT_EXCEEDED",
                "message": f"Storage limit reached ({storage_profile.storage_limit_display}). "
                           "Please delete old telemetry data or upgrade your plan.",
            },
            status=507,  # Insufficient Storage
        )

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
    
    # Update cached storage usage (increment by estimated row size)
    # Full recalculation happens periodically or on data management page
    estimated_row_size = 300 + len(json.dumps(data)) if data else 400
    storage_profile.cached_usage_bytes += estimated_row_size
    storage_profile.save(update_fields=['cached_usage_bytes'])
    
    # Check temperature alerts and send emails if thresholds exceeded
    check_and_send_temperature_alerts(device, float(data["temp_inside_c"]))

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
