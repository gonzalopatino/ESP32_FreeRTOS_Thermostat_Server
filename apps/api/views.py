from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
import logging
import json

from .models import TelemetrySnapshot
from django.utils.dateparse import parse_datetime

from django.utils.timezone import now
from django.db.models import Q
import os
from dotenv import load_dotenv


logger = logging.getLogger(__name__)

API_KEY = os.getenv("TELEMETRY_API_KEY")



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

    


def ping(request):
    return JsonResponse(
        {
            "status": "ok",
            "message": "api app wired",
        }
    )
