import re
from typing import override

from rest_framework import serializers

class RuntimeSettingsSerializer(serializers.Serializer):
    thinking_level = serializers.CharField(max_length=64, required=False, allow_blank=True)


class DevSettingsSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=["openai_compatible", "llama_cpp"], required=False, default="openai_compatible")
    base_url = serializers.CharField(max_length=512, required=False, allow_blank=True)
    model = serializers.CharField(max_length=256, required=False, allow_blank=True)
    api_key = serializers.CharField(max_length=512, required=False, allow_blank=True)
    temperature = serializers.FloatField(min_value=0.0, max_value=2.0, required=False)
    chat_history_window = serializers.IntegerField(min_value=0, max_value=100, required=False)
    thinking_level = serializers.CharField(max_length=64, required=False, allow_blank=True)
    extra_params = serializers.CharField(required=False, allow_blank=True)
    system_prompt = serializers.CharField(required=False, allow_blank=True)
    tts_provider = serializers.CharField(max_length=64, required=False, allow_blank=True, default="audar")
    tts_base_url = serializers.CharField(max_length=512, required=False, allow_blank=True, default="https://openrouter.ai/api/v1")
    tts_model = serializers.CharField(max_length=256, required=False, allow_blank=True, default="audarai/Audar-TTS-V1-Flash")
    tts_voice = serializers.CharField(max_length=128, required=False, allow_blank=True, default="demo_female_1")
    tts_api_key = serializers.CharField(max_length=512, required=False, allow_blank=True, default="")
    tts_speed = serializers.FloatField(min_value=0.25, max_value=3.0, required=False, default=1.0)
    tts_extra_params = serializers.CharField(required=False, allow_blank=True, default="")


class TestConnectionSerializer(serializers.Serializer):
    base_url = serializers.CharField(max_length=512)
    model = serializers.CharField(max_length=256)
    api_key = serializers.CharField(max_length=512, required=False, allow_blank=True, default="")
    extra_params = serializers.CharField(required=False, allow_blank=True, default="")
    prompt = serializers.CharField(max_length=256, required=False, allow_blank=True, default="Hello! Respond with: OK")


class ModelInfoSerializer(serializers.Serializer):
    base_url = serializers.CharField(max_length=512)
    model = serializers.CharField(max_length=256, required=False, allow_blank=True, default="")
    api_key = serializers.CharField(max_length=512, required=False, allow_blank=True, default="")


class FetchTTSVoicesSerializer(serializers.Serializer):
    base_url = serializers.CharField(max_length=512)
    model = serializers.CharField(max_length=256, required=False, allow_blank=True, default="")
    api_key = serializers.CharField(max_length=512, required=False, allow_blank=True, default="")


class TTSModelInfoSerializer(serializers.Serializer):
    base_url = serializers.CharField(max_length=512)
    model = serializers.CharField(max_length=256, required=False, allow_blank=True, default="")
    api_key = serializers.CharField(max_length=512, required=False, allow_blank=True, default="")


class TestTTSSerializer(serializers.Serializer):
    provider = serializers.CharField(max_length=64, required=False, default="audar")
    model = serializers.CharField(max_length=256, required=False, allow_blank=True, default="")
    voice = serializers.CharField(max_length=128, required=False, default="demo_female_1")
    speed = serializers.FloatField(min_value=0.25, max_value=3.0, required=False, default=1.0)
    text = serializers.CharField(max_length=500, required=False, default="مرحبا بكم، هذا اختبار لتوليد الصوت بالذكاء الاصطناعي.")
    extra_params = serializers.CharField(required=False, allow_blank=True, default="")
    base_url = serializers.CharField(max_length=512, required=False, allow_blank=True, default="")
    api_key = serializers.CharField(max_length=512, required=False, allow_blank=True, default="")

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
