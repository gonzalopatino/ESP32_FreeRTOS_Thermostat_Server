from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
import logging
import json

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

    # Successful response
    return JsonResponse(
        {
            "status": "ok",
            "echo": data,
        }
    )


def ping(request):
    return JsonResponse(
        {
            "status": "ok",
            "message": "api app wired",
        }
    )
