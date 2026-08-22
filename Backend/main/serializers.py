import re
from typing import override

from rest_framework import serializers

from .core.config import THINKING_LEVELS


class RuntimeSettingsSerializer(serializers.Serializer):
    thinking_level = serializers.ChoiceField(choices=THINKING_LEVELS)

SESSION_ID_RE: re.Pattern[str] = re.compile(r"^[\w:-]+$")


class ChatRequestSerializer(serializers.Serializer):
    session_id = serializers.CharField(max_length=128)
    input = serializers.CharField(required=False, allow_blank=True, default="")
    clear_history = serializers.BooleanField(required=False, default=False)

    def validate_session_id(self, value: str) -> str:
        if not SESSION_ID_RE.match(value):
            raise serializers.ValidationError("session_id may only contain letters, digits, underscore, hyphen and colon.")
        return value

    @override
    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if attrs.get("clear_history"):
            return attrs
        if not attrs.get("input"):
            raise serializers.ValidationError({"input": "input is required when clear_history is false."})
        return attrs
