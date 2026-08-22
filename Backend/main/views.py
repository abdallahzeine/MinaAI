from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .core.agent import DjangoChatMessageHistory
from .core.config import (
    THINKING_BUDGETS,
    THINKING_LEVELS,
    get_runtime_settings,
    resolve_params,
    set_runtime_settings,
)
from .serializers import RuntimeSettingsSerializer


def _settings_payload() -> dict:
    s = get_runtime_settings()
    level: str = s["thinking_level"]
    return {
        "thinking_level": level,
        "thinking_budget": THINKING_BUDGETS[level],
        "allowed_levels": list(THINKING_LEVELS),
    }


class HealthCheckView(APIView):
    def get(self, request: Request) -> Response:
        return Response({"status": "ok", "app": "main"})


class RuntimeSettingsView(APIView):
    def get(self, request: Request) -> Response:
        return Response(_settings_payload())

    def put(self, request: Request) -> Response:
        ser = RuntimeSettingsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        set_runtime_settings(ser.validated_data)
        return Response(_settings_payload())


class AdminAnalyticsView(APIView):
    def get(self, request: Request) -> Response:
        from .core.admin_analytics import build_admin_analytics

        payload = build_admin_analytics()
        return Response(payload)


class ClearHistoryView(APIView):
    def delete(self, request: Request, session_id: str) -> Response:
        params = resolve_params()
        h: DjangoChatMessageHistory = DjangoChatMessageHistory(session_id=session_id, window_size=params["chat_history_window"])
        h.clear()
        return Response({"status": "cleared"})
