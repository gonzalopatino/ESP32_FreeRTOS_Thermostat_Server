from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
import logging
import json

from .models import TelemetrySnapshot
from django.utils.dateparse import parse_datetime

from django.utils.timezone import now
from django.db.models import Q


logger = logging.getLogger(__name__)

API_KEY = "super-secret-token"  # Later we move this to settings


def recent_telemetry(request):
    """
    Return recent telemetry snapshots as JSON.
    Supports:
        - ?Limit=50      how many records
        - ?device_id=..     filter by device
    """
    try:
        limit = int (request.GET.get("limit", "50"))
    except ValueError:
        limit = 50

    # Hard cap so someone cannot ask for a million rows
    limit = max(1, min(limit, 500))

    device_id = request.GET.get("device_id")

    qs = TelemetrySnapshot.objects.all().order_by("-server_ts")
    if device_id:
        qs = qs.filter(device_id=device_id)
    
    qs = qs [:limit]

    data = []

    for s in qs:
        data.append(
            {
                "id": s.id,
                "device_id": s.device_id,
                "mode": s.mode,
                "temp_inside_c": s.temp_inside_c,
                "setpoint_c": s.setpoint_c,
                "temp_outside_c": s.temp_outside_c,
                "humidity_percent": s.humidity_percent,
                "device_ts": s.device_ts.isoformat() if s.device_ts else None,
                "server_ts": s.server_ts.isoformat() if s.server_ts else None,
            }
        )
    return JsonResponse (
        {
            "count" : len(data),
            "device_id": device_id,
            "data": data,

        }
    )

@csrf_exempt
def ingest_telemetry(request):
    # Only POST allowed
    if request.method != "POST":
        return HttpResponseBadRequest("Only POST allowed")

    # Header-based auth
    key = request.headers.get("X-API-Key")
    if key != API_KEY:
        return HttpResponseBadRequest("Invalid or missing API key")

    # Parse JSON body
    try:
        body = request.body.decode("utf-8")
        data = json.loads(body)
    except Exception as e:
        return HttpResponseBadRequest(f"Invalid JSON: {e}")

    # Required fields
    required = ["device_id", "mode", "setpoint_c", "temp_inside_c"]
    missing = [field for field in required if field not in data]
    if missing:
        return HttpResponseBadRequest(
            f"Missing required fields: {', '.join(missing)}"
        )

    # Log for now instead of saving to DB
    logger.info("Telemetry received: %s", data)

    # Parse optional timestamp
    device_ts_raw = data.get("timestamp")
    device_ts = None
    if device_ts_raw:
        device_ts = parse_datetime(device_ts_raw)

    # Save to DB
    snapshot = TelemetrySnapshot.objects.create(
        device_id=data["device_id"],
        mode=data["mode"],
        setpoint_c=float(data["setpoint_c"]),
        temp_inside_c=float(data["temp_inside_c"]),
        temp_outside_c=float(data.get("temp_outside_c")) if data.get("temp_outside_c") else None,
        humidity_percent=float(data.get("humidity_percent")) if data.get("humidity_percent") else None,
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
