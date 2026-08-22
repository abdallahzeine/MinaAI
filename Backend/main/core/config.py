"""LLM configuration — static defaults plus runtime-tunable settings.

Static values are the fallback defaults. Runtime settings (e.g. thinking
level) are stored in the DB via the settings endpoint so they can be changed
without redeploying; `resolve_params()` merges both into one dict.
"""

import os
from typing import TypedDict

from .prompts import SYSTEM_PROMPT

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "llama_cpp")
LLAMA_CPP_BASE_URL: str = os.getenv("LLAMA_CPP_BASE_URL", "http://localhost:8080/v1")
LLAMA_CPP_MODEL: str = os.getenv("LLAMA_CPP_MODEL", "llama-cpp-model")
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
CHAT_HISTORY_WINDOW: int = int(os.getenv("CHAT_HISTORY_WINDOW", "10"))

# Reasoning/thinking level passed to the LLM: "off", "low", "medium", "high".
# "off" disables reasoning entirely; the rest map to an increasing token
# budget for the thinking phase (unrestricted is reserved for "high").
THINKING_LEVELS: tuple[str, ...] = ("off", "low", "medium", "high")
DEFAULT_THINKING_LEVEL: str = "medium"

# Token budget applied per thinking level (llama.cpp --reasoning-budget).
THINKING_BUDGETS: dict[str, int] = {
    "off": 0,
    "low": 256,
    "medium": 1024,
    "high": -1,
}


class RuntimeSettings(TypedDict):
    thinking_level: str


def get_runtime_settings() -> RuntimeSettings:
    from ..models import Setting

    default: RuntimeSettings = {"thinking_level": DEFAULT_THINKING_LEVEL}
    try:
        row = Setting.objects.get(key="thinking_level")
        value: str = str(row.value)
        if value in THINKING_LEVELS:
            default["thinking_level"] = value
    except Setting.DoesNotExist:
        pass
    except Exception:
        # Never let a settings read break the LLM path; fall back to defaults.
        pass
    return default


def set_runtime_settings(settings: RuntimeSettings) -> None:
    from ..models import Setting

    level = settings["thinking_level"]
    if level not in THINKING_LEVELS:
        raise ValueError(f"thinking_level must be one of {', '.join(THINKING_LEVELS)}")
    row, _ = Setting.objects.get_or_create(key="thinking_level")
    row.value = level
    row.save()


class Params(TypedDict):
    provider: str
    llama_cpp_base_url: str
    llama_cpp_model: str
    temperature: float
    chat_history_window: int
    system_prompt: str
    thinking_level: str
    thinking_budget: int


def _get_system_prompt() -> str:
    """Load system_prompt from DB Setting if present, otherwise fall back to prompts.SYSTEM_PROMPT.

    Fail silently on any DB error so that errors never enter LLM context.
    """
    try:
        from ..models import Setting

        row = Setting.objects.get(key="system_prompt")
        value = str(row.value or "").strip()
        if value:
            return value
    except Setting.DoesNotExist:
        pass
    except Exception:
        pass
    return SYSTEM_PROMPT


def resolve_params() -> Params:
    runtime = get_runtime_settings()
    level = runtime["thinking_level"]
    return {
        "provider": LLM_PROVIDER,
        "llama_cpp_base_url": LLAMA_CPP_BASE_URL,
        "llama_cpp_model": LLAMA_CPP_MODEL,
        "temperature": LLM_TEMPERATURE,
        "chat_history_window": CHAT_HISTORY_WINDOW,
        "system_prompt": _get_system_prompt(),
        "thinking_level": level,
        "thinking_budget": THINKING_BUDGETS[level],
    }
