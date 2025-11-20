from django.db import models


class TelemetrySnapshot(models.Model):

    #Properties
    device_id = models.CharField(max_length=64)
    mode = models.CharField(max_length=16)
    temp_inside_c = models.FloatField()
    setpoint_c = models.FloatField()
    temp_outside_c = models.FloatField(null=True, blank=True)
    humidity_percent = models.FloatField(null=True, blank=True)


    # Raw payload for debugging (optional)
    raw_payload = models.JSONField(null=True, blank=True)

    # Timestamps
    device_ts = models.DateTimeField(null=True, blank=True)  # if device sends ISO timestamp
    server_ts = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["device_id", "server_ts"]),
        ]

    def __str__(self):
        return f"{self.device_id} @ {self.server_ts.isoformat()}"
