from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
import logging
import json

from .models import TelemetrySnapshot
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

API_KEY = "super-secret-token"  # Later we move this to settings


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
