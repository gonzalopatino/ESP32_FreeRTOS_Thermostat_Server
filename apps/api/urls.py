from django.urls import path
from . import views

urlpatterns = [
    # placeholder endpoint so we know this app is wired
    path("ping/", views.ping, name="api-ping"),
    path("telemetry/ingest/", views.ingest_telemetry, name="ingest-telemetry"),
    path("telemetry/recent/", views.recent_telemetry, name="recent-telemetry"),
]
