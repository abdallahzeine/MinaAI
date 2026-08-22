from django.urls import URLPattern, path

from .views import AdminAnalyticsView, ClearHistoryView, HealthCheckView, RuntimeSettingsView

urlpatterns: list[URLPattern] = [
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("settings/", RuntimeSettingsView.as_view(), name="runtime-settings"),
    path("chat/<str:session_id>/clear/", ClearHistoryView.as_view(), name="clear-history"),
    path("admin/analytics/", AdminAnalyticsView.as_view(), name="admin-analytics"),
]
