from django.urls import path
from . import views

urlpatterns = [
    path("ping/", views.ping, name="api-ping"),

    # Auth
    path("auth/register/", views.register_user, name="register-user"),
    path("auth/login/", views.login_user, name="login-user"),
    path("auth/logout/", views.logout_user, name="logout-user"),

    # Devices
    path("devices/register/", views.register_device, name="register-device"),
    path("devices/", views.list_devices, name="list_devices"),

    path("devices/<int:device_id>/keys/",views.list_device_keys, name="list_device_keys",),

    # Telemetry
    path("telemetry/ingest/", views.ingest_telemetry, name="ingest-telemetry"),
    path("telemetry/", views.telemetry_query, name="telemetry-query"),
    path("telemetry/recent/", views.recent_telemetry, name="recent-telemetry"),

    
]

