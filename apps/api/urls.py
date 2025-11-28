from django.urls import path
from . import views
from .views import telemetry_query, ingest_telemetry

urlpatterns = [
    path("ping/", views.ping, name="api-ping"),

    # Auth
    path("auth/register/", views.register_user, name="register-user"),
    path("auth/login/", views.login_user, name="login-user"),
    path("auth/logout/", views.logout_user, name="logout-user"),

    # Devices
    path("devices/register/", views.register_device, name="register-device"),
    path("devices/", views.list_devices, name="list_devices"),


    #Device Key Management
    path("devices/<int:device_id>/keys/",views.list_device_keys, name="list_device_keys",),
    path("devices/<int:device_id>/keys/<int:key_id>/revoke/",views.revoke_device_key,name="revoke_device_key",),
    path("devices/<int:device_id>/keys/rotate/", views.rotate_device_key, name="rotate_device_key",
    ),

    # Telemetry
    path("telemetry/ingest/", views.ingest_telemetry, name="ingest-telemetry"),
    path("telemetry/", views.telemetry_query, name="telemetry-query"),
    path("telemetry/recent/", views.recent_telemetry, name="recent-telemetry"),
    path("telemetry/query/", views.telemetry_query, name="telemetry_query"),
    path("telemetry/export/", views.telemetry_export_csv, name="telemetry_export_csv"),
    # New dashboard page
    path(
        "dashboard/devices/",
        views.dashboard_devices,
        name="dashboard_devices",
    ),

    
]

