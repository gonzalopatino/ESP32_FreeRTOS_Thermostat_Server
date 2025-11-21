

# Register your models here.
from django.contrib import admin
from .models import Device, DeviceApiKey, TelemetrySnapshot


class DeviceApiKeyInline(admin.TabularInline):
    model = DeviceApiKey
    extra = 0
    readonly_fields = ("created_at", "expires_at", "is_active")
    can_delete = False

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("serial_number", "owner", "name", "created_at")
    search_fields = ("serial_number", "name", "owner__username")
    inlines = [DeviceApiKeyInline]


@admin.register(DeviceApiKey)
class DeviceApiKeyAdmin(admin.ModelAdmin):
    list_display = ("device", "created_at", "expires_at", "is_active")
    list_filter = ("is_active",)


# Optional: give yourself an easy way to eyeball telemetry in admin as well
@admin.register(TelemetrySnapshot)
class TelemetrySnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "device_id", "mode", "server_ts", "temp_inside_c", "setpoint_c")
    list_filter = ("mode",)
    search_fields = ("device_id",)
    ordering = ("-server_ts",)