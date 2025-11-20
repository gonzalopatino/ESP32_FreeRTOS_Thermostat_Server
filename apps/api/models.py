from django.db import models


from django.db import models


class TelemetrySnapshot(models.Model):
    device_id = models.CharField(max_length=64)

    # Core thermostat state
    mode = models.CharField(max_length=16)              # "OFF", "HEAT", "COOL", "AUTO"
    temp_inside_c = models.FloatField()
    temp_outside_c = models.FloatField(null=True, blank=True)
    setpoint_c = models.FloatField()
    hysteresis_c = models.FloatField(null=True, blank=True)

    # What the thermostat decided to do
    output = models.CharField(
        max_length=16,
        blank=True,                                     # "HEAT_ON", "COOL_ON", "OFF"
        help_text="Current actuator output state",
    )

    # You don't actually measure humidity, so this will stay null,
    # but we keep the column to avoid migration complexity if you
    # already created it.
    humidity_percent = models.FloatField(null=True, blank=True)

    # Raw payload for debugging
    raw_payload = models.JSONField(null=True, blank=True)

    # Timestamps
    device_ts = models.DateTimeField(null=True, blank=True)
    server_ts = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["device_id", "server_ts"]),
        ]

    def __str__(self):
        return f"{self.device_id} @ {self.server_ts.isoformat()}"

