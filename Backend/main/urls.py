from django.urls import URLPattern, path

from .views import (
    AdminAnalyticsView,
    ClearHistoryView,
    DevModelInfoView,
    DevSettingsView,
    DevTestConnectionView,
    DevTestTTSView,
    DevTTSModelInfoView,
    DevTTSVoicesView,
    HealthCheckView,
    RuntimeSettingsView,
)

urlpatterns: list[URLPattern] = [
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("settings/", RuntimeSettingsView.as_view(), name="runtime-settings"),
    path("dev/settings/", DevSettingsView.as_view(), name="dev-settings"),
    path("dev/test-connection/", DevTestConnectionView.as_view(), name="dev-test-connection"),
    path("dev/model-info/", DevModelInfoView.as_view(), name="dev-model-info"),
    path("dev/tts-model-info/", DevTTSModelInfoView.as_view(), name="dev-tts-model-info"),
    path("dev/test-tts/", DevTestTTSView.as_view(), name="dev-test-tts"),
    path("dev/tts-voices/", DevTTSVoicesView.as_view(), name="dev-tts-voices"),
    path("chat/<str:session_id>/clear/", ClearHistoryView.as_view(), name="clear-history"),
    path("admin/analytics/", AdminAnalyticsView.as_view(), name="admin-analytics"),
]
