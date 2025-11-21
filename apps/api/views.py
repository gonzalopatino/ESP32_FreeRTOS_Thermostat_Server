import json
from functools import wraps

from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils.timezone import now

import logging

from .models import TelemetrySnapshot
from django.utils.dateparse import parse_datetime

from django.utils.timezone import now
from django.db.models import Q
import os
from dotenv import load_dotenv
from datetime import timedelta

from .models import TelemetrySnapshot, Device, DeviceApiKey


logger = logging.getLogger(__name__)

API_KEY = os.getenv("TELEMETRY_API_KEY")



#Helper function
def api_login_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"detail": "Authentication required"}, status=401)
        return view_func(request, *args, **kwargs)
    return _wrapped



def recent_telemetry(request):
    try:
        limit = int(request.GET.get("limit", "50"))
    except ValueError:
        limit = 50
    limit = max(1, min(limit, 500))

    device_id = request.GET.get("device_id")

    qs = TelemetrySnapshot.objects.all().order_by("-server_ts")
    if device_id is None and qs.exists():
        device_id = qs.first().device_id
        qs = qs.filter(device_id=device_id)

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
                "device_ts": device_ts_local or (
                    device_ts_utc.isoformat() if device_ts_utc else None
                ),

                # if you want to keep UTC around for dashboards / SQL
                "device_ts_utc": device_ts_utc.isoformat() if device_ts_utc else None,

                "server_ts": s.server_ts.isoformat() if s.server_ts else None,
            }
        )

    return JsonResponse(
        {
            "count": len(data),
            "device_id": device_id,
            "data": data,
        }
    )



@csrf_exempt
def ingest_telemetry(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Only POST allowed")

    key = request.headers.get("X-API-Key")
    if key != API_KEY:
        return HttpResponseBadRequest("Invalid or missing API key")

    try:
        body = request.body.decode("utf-8")
        data = json.loads(body)
    except Exception as e:
        return HttpResponseBadRequest(f"Invalid JSON: {e}")

    required = ["device_id", "mode", "setpoint_c", "temp_inside_c"]
    missing = [field for field in required if field not in data]
    if missing:
        return HttpResponseBadRequest(
            f"Missing required fields: {', '.join(missing)}"
        )

    # Optional fields from CONTROL
    temp_outside_c = data.get("temp_outside_c")
    hysteresis_c = data.get("hysteresis_c")
    output = data.get("output")  # "HEAT_ON", "COOL_ON", "OFF", etc.
    humidity = data.get("humidity_percent")  # will normally be absent

    # Optional device timestamp
    device_ts_raw = data.get("timestamp")
    device_ts = parse_datetime(device_ts_raw) if device_ts_raw else None

    snapshot = TelemetrySnapshot.objects.create(
        device_id=data["device_id"],
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

    return JsonResponse(
        {
            "status": "ok",
            "id": snapshot.id,
            "server_ts": snapshot.server_ts.isoformat(),
        }
    )

def _parse_bool(value: str) -> bool:
    if value is None:
        return False
    return value.lower() in ("1", "true", "yes", "y", "on")


def telemetry_query(request):
    if request.method != "GET":
        return HttpResponseBadRequest("Only GET is allowed")

    qs = TelemetrySnapshot.objects.all()

    # Filter by device
    device_id = request.GET.get("device_id")
    if device_id:
        qs = qs.filter(device_id=device_id)

    # Time filters: start / end / range
    start_param = request.GET.get("start")
    end_param = request.GET.get("end")
    range_param = request.GET.get("range")

    if start_param:
        start_dt = parse_datetime(start_param)
        if not start_dt:
            return HttpResponseBadRequest("Invalid 'start' datetime")
        qs = qs.filter(server_ts__gte=start_dt)

    if end_param:
        end_dt = parse_datetime(end_param)
        if not end_dt:
            return HttpResponseBadRequest("Invalid 'end' datetime")
        qs = qs.filter(server_ts__lte=end_dt)

    # Only apply 'range' if explicit start/end not given
    if range_param and not (start_param or end_param):
        try:
            if range_param.endswith("h"):
                hours = float(range_param[:-1])
                window_start = now() - timedelta(hours=hours)
            elif range_param.endswith("d"):
                days = float(range_param[:-1])
                window_start = now() - timedelta(days=days)
            else:
                return HttpResponseBadRequest(
                    "Invalid 'range' format, use like '24h' or '7d'"
                )
        except ValueError:
            return HttpResponseBadRequest(
                "Invalid 'range' format, use like '24h' or '7d'"
            )
        qs = qs.filter(server_ts__gte=window_start)

    # Latest vs limit
    latest_flag = _parse_bool(request.GET.get("latest"))
    if latest_flag:
        qs = qs.order_by("-server_ts")[:1]
    else:
        limit_param = request.GET.get("limit")
        try:
            limit = int(limit_param) if limit_param else 100
        except ValueError:
            return HttpResponseBadRequest("Invalid 'limit', must be an integer")
        limit = max(1, min(limit, 1000))
        qs = qs.order_by("-server_ts")[:limit]

    # Serialize snapshots
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
    


def ping(request):
    return JsonResponse(
        {
            "status": "ok",
            "message": "api app wired",
        }
    )


@csrf_exempt
@require_POST
@api_login_required
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



