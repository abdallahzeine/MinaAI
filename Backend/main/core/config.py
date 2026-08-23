"""LLM configuration — static defaults plus runtime-tunable settings.

Static values are fallback defaults. Runtime settings (e.g. model, base URL,
API key, thinking level, system prompt) are stored in the DB Setting table so
they can be configured live through the /dev developer interface.
"""

import os
from typing import TypedDict

from .prompts import SYSTEM_PROMPT

# Static environment variable defaults
DEFAULT_LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai_compatible")
DEFAULT_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
DEFAULT_MODEL: str = os.getenv("LLM_MODEL", "")
DEFAULT_API_KEY: str = os.getenv("LLM_API_KEY", "")
DEFAULT_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
DEFAULT_CHAT_HISTORY_WINDOW: int = int(os.getenv("CHAT_HISTORY_WINDOW", "10"))
DEFAULT_LLAMA_CPP_BASE_URL: str = os.getenv("LLAMA_CPP_BASE_URL", "http://localhost:8080/v1")
DEFAULT_LLAMA_CPP_MODEL: str = os.getenv("LLAMA_CPP_MODEL", "gemma-4-it")

DEFAULT_THINKING_LEVEL: str = ""

# Static TTS defaults
DEFAULT_TTS_PROVIDER: str = os.getenv("TTS_PROVIDER", os.getenv("TTS_BACKEND", "audar"))
DEFAULT_TTS_BASE_URL: str = os.getenv("TTS_BASE_URL", "https://openrouter.ai/api/v1")
DEFAULT_TTS_MODEL: str = os.getenv("TTS_MODEL", "audarai/Audar-TTS-V1-Flash")
DEFAULT_TTS_VOICE: str = os.getenv("TTS_VOICE", "demo_female_1")
DEFAULT_TTS_API_KEY: str = os.getenv("TTS_API_KEY", "")
DEFAULT_TTS_SPEED: float = float(os.getenv("TTS_SPEED", "1.0"))
DEFAULT_TTS_EXTRA_PARAMS: str = os.getenv("TTS_EXTRA_PARAMS", "")

PRESET_CONFIGS: list[dict] = []


class RuntimeSettings(TypedDict):
    thinking_level: str


class DevSettings(TypedDict):
    provider: str
    base_url: str
    model: str
    api_key: str
    temperature: float
    chat_history_window: int
    thinking_level: str
    thinking_budget: int
    extra_params: str
    system_prompt: str
    tts_provider: str
    tts_base_url: str
    tts_model: str
    tts_voice: str
    tts_api_key: str
    tts_speed: float
    tts_extra_params: str


class Params(TypedDict):
    provider: str
    llama_cpp_base_url: str
    base_url: str
    llama_cpp_model: str
    model: str
    api_key: str
    temperature: float
    chat_history_window: int
    system_prompt: str
    thinking_level: str
    thinking_budget: int
    extra_params: str
    tts_provider: str
    tts_base_url: str
    tts_model: str
    tts_voice: str
    tts_api_key: str
    tts_speed: float
    tts_extra_params: str


def _get_setting(key: str, default: str) -> str:
    try:
        from ..models import Setting

        row = Setting.objects.get(key=key)
        return str(row.value or "").strip()
    except Exception:
        return default


def _set_setting(key: str, value: str) -> None:
    from ..models import Setting

    row, _ = Setting.objects.get_or_create(key=key)
    row.value = str(value)
    row.save()


def get_runtime_settings() -> RuntimeSettings:
    level = _get_setting("thinking_level", DEFAULT_THINKING_LEVEL)
    return {"thinking_level": level}


def set_runtime_settings(settings: RuntimeSettings) -> None:
    level = settings.get("thinking_level", DEFAULT_THINKING_LEVEL)
    _set_setting("thinking_level", str(level).strip())


def get_dev_settings() -> DevSettings:
    provider = _get_setting("llm_provider", DEFAULT_LLM_PROVIDER)
    base_url = _get_setting("llm_base_url", DEFAULT_BASE_URL)
    model = _get_setting("llm_model", DEFAULT_MODEL)
    api_key = _get_setting("llm_api_key", DEFAULT_API_KEY)
    temp_str = _get_setting("llm_temperature", str(DEFAULT_TEMPERATURE))
    window_str = _get_setting("chat_history_window", str(DEFAULT_CHAT_HISTORY_WINDOW))
    level = _get_setting("thinking_level", DEFAULT_THINKING_LEVEL)
    extra = _get_setting("extra_params", "")
    prompt = _get_setting("system_prompt", SYSTEM_PROMPT)

    # TTS Settings
    tts_provider = _get_setting("tts_provider", DEFAULT_TTS_PROVIDER)
    tts_base_url = _get_setting("tts_base_url", DEFAULT_TTS_BASE_URL)
    tts_model = _get_setting("tts_model", DEFAULT_TTS_MODEL)
    tts_voice = _get_setting("tts_voice", DEFAULT_TTS_VOICE)
    tts_api_key = _get_setting("tts_api_key", DEFAULT_TTS_API_KEY)
    tts_speed_str = _get_setting("tts_speed", str(DEFAULT_TTS_SPEED))
    tts_extra = _get_setting("tts_extra_params", DEFAULT_TTS_EXTRA_PARAMS)

    try:
        temperature = float(temp_str)
    except Exception:
        temperature = DEFAULT_TEMPERATURE

    try:
        chat_history_window = int(window_str)
    except Exception:
        chat_history_window = DEFAULT_CHAT_HISTORY_WINDOW

    try:
        tts_speed = float(tts_speed_str)
    except Exception:
        tts_speed = DEFAULT_TTS_SPEED

    return {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "temperature": temperature,
        "chat_history_window": chat_history_window,
        "thinking_level": level,
        "thinking_budget": -1,
        "extra_params": extra,
        "system_prompt": prompt or SYSTEM_PROMPT,
        "tts_provider": tts_provider,
        "tts_base_url": tts_base_url,
        "tts_model": tts_model,
        "tts_voice": tts_voice,
        "tts_api_key": tts_api_key,
        "tts_speed": tts_speed,
        "tts_extra_params": tts_extra,
    }


def set_dev_settings(settings: dict) -> None:
    if "provider" in settings and settings["provider"] is not None:
        _set_setting("llm_provider", str(settings["provider"]).strip())
    if "base_url" in settings and settings["base_url"] is not None:
        _set_setting("llm_base_url", str(settings["base_url"]).strip())
    if "model" in settings and settings["model"] is not None:
        _set_setting("llm_model", str(settings["model"]).strip())
    if "api_key" in settings and settings["api_key"] is not None:
        _set_setting("llm_api_key", str(settings["api_key"]).strip())
    if "temperature" in settings and settings["temperature"] is not None:
        _set_setting("llm_temperature", str(settings["temperature"]).strip())
    if "chat_history_window" in settings and settings["chat_history_window"] is not None:
        _set_setting("chat_history_window", str(settings["chat_history_window"]).strip())
    if "thinking_level" in settings and settings["thinking_level"] is not None:
        _set_setting("thinking_level", str(settings["thinking_level"]).strip())
    if "extra_params" in settings and settings["extra_params"] is not None:
        _set_setting("extra_params", str(settings["extra_params"]).strip())
    if "system_prompt" in settings and settings["system_prompt"] is not None:
        _set_setting("system_prompt", str(settings["system_prompt"]).strip())

    # TTS Settings
    if "tts_provider" in settings and settings["tts_provider"] is not None:
        _set_setting("tts_provider", str(settings["tts_provider"]).strip())
    if "tts_base_url" in settings and settings["tts_base_url"] is not None:
        _set_setting("tts_base_url", str(settings["tts_base_url"]).strip())
    if "tts_model" in settings and settings["tts_model"] is not None:
        _set_setting("tts_model", str(settings["tts_model"]).strip())
    if "tts_voice" in settings and settings["tts_voice"] is not None:
        _set_setting("tts_voice", str(settings["tts_voice"]).strip())
    if "tts_api_key" in settings and settings["tts_api_key"] is not None:
        _set_setting("tts_api_key", str(settings["tts_api_key"]).strip())
    if "tts_speed" in settings and settings["tts_speed"] is not None:
        _set_setting("tts_speed", str(settings["tts_speed"]).strip())
    if "tts_extra_params" in settings and settings["tts_extra_params"] is not None:
        _set_setting("tts_extra_params", str(settings["tts_extra_params"]).strip())


def resolve_params() -> Params:
    dev = get_dev_settings()
    return {
        "provider": dev["provider"],
        "llama_cpp_base_url": dev["base_url"],
        "base_url": dev["base_url"],
        "llama_cpp_model": dev["model"],
        "model": dev["model"],
        "api_key": dev["api_key"],
        "temperature": dev["temperature"],
        "chat_history_window": dev["chat_history_window"],
        "system_prompt": dev["system_prompt"],
        "thinking_level": dev["thinking_level"],
        "thinking_budget": dev["thinking_budget"],
        "extra_params": dev["extra_params"],
        "tts_provider": dev["tts_provider"],
        "tts_base_url": dev["tts_base_url"] or dev["base_url"],
        "tts_model": dev["tts_model"],
        "tts_voice": dev["tts_voice"],
        "tts_api_key": dev["tts_api_key"] or dev["api_key"],
        "tts_speed": dev["tts_speed"],
        "tts_extra_params": dev["tts_extra_params"],
    }
