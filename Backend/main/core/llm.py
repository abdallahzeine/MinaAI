import base64
import logging
import os
import shutil
import subprocess
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger(__name__)


def wait_for_llm_ready(timeout_s: float = 60, interval_s: float = 2.0) -> bool:
    """Block until llama.cpp / LLM reports health — single gate for TTS VRAM allocation.

    For online / remote endpoints (https://), passes immediately to avoid blocking TTS.
    For local endpoints, polls {base_url}/models and /health.
    """
    import time
    import urllib.request
    import urllib.error

    try:
        from .config import resolve_params

        params = resolve_params()
        base = (params.get("base_url") or "http://localhost:8080/v1").rstrip("/")
    except Exception:
        base = os.environ.get("LLAMA_CPP_BASE_URL", "http://localhost:8080/v1").rstrip("/")

    # If pointing to an online API (e.g. Google Gemini / OpenAI / Groq), skip local health gate
    if base.startswith("https://"):
        logger.info("[LLM] Online LLM endpoint configured (%s) — skipping local port health wait", base)
        return True

    root = base[:-3] if base.endswith("/v1") else base
    candidates = [f"{base}/models", f"{root}/health", base]

    try:
        timeout_s = float(os.environ.get("TTS_LLM_HEALTH_TIMEOUT", str(timeout_s)))
    except Exception:
        pass
    try:
        interval_s = float(os.environ.get("TTS_LLM_HEALTH_INTERVAL", str(interval_s)))
    except Exception:
        pass

    if os.environ.get("TTS_PREWARM_WAIT_FOR_LLM", "1") not in ("1", "true", "True", "yes"):
        logger.info("[TTS] TTS_PREWARM_WAIT_FOR_LLM disabled — prewarming immediately without LLM health gate")
        return True
    if timeout_s <= 0:
        return True

    logger.info("[TTS] Holding TTS prewarm until LLM health passes at %s (timeout %.0fs)", base, timeout_s)
    deadline = time.time() + timeout_s
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        for url in candidates:
            try:
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    code = getattr(resp, "status", 200)
                    if 200 <= code < 300:
                        body = resp.read().decode("utf-8", errors="ignore")[:2000] if "models" in url else ""
                        if "models" in url and body:
                            if '"data"' in body or '"object"' in body or '"id"' in body:
                                logger.info("[TTS] LLM health pass on %s (attempt %d) — proceeding to TTS load", url, attempt)
                                return True
                            logger.info("[TTS] LLM health pass on %s (attempt %d, status %d) — proceeding to TTS load", url, attempt, code)
                            return True
                        logger.info("[TTS] LLM health pass on %s (attempt %d, status %d) — proceeding to TTS load", url, attempt, code)
                        return True
            except urllib.error.HTTPError as e:
                logger.debug("[TTS] LLM health %s -> HTTP %s, retrying...", url, e.code)
                continue
            except Exception as e:
                logger.debug("[TTS] LLM health %s not ready: %s", url, e)
                continue
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        time.sleep(min(interval_s, max(0.5, remaining)))
    logger.warning("[TTS] LLM health did not pass within %.0fs — skipping TTS prewarm; will load lazily on first synthesize after LLM is ready", timeout_s)
    return False


def warmup_llm() -> bool:
    """Send a lightweight prompt to LLM to pre-warm KV cache and GPU compute graph."""
    import json
    import urllib.request

    try:
        from .config import resolve_params

        params = resolve_params()
        base = (params.get("base_url") or "").rstrip("/")
        model = params.get("model") or ""
        api_key = params.get("api_key") or ""
    except Exception:
        base = os.environ.get("LLM_BASE_URL", "").rstrip("/")
        model = os.environ.get("LLM_MODEL", "")
        api_key = os.environ.get("LLM_API_KEY", "")

    if not base or not model:
        return False

    url = f"{base}/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 2,
    }).encode("utf-8")

    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if 200 <= getattr(resp, "status", 200) < 300:
                logger.info("[LLM] LLM GPU pipeline warmed and ready for input (%s)", model)
                return True
    except Exception as e:
        logger.debug("[LLM] LLM warm-up request notice: %s", e)
    return False


def get_llama_llm(
    base_url: str,
    model: str,
    temperature: float,
    thinking_level: str | None = None,
    thinking_budget: int | None = None,
    api_key: str | None = None,
    extra_params: str | dict | None = None,
) -> "BaseChatModel":
    import json
    from langchain_openai import ChatOpenAI

    key = (api_key or "").strip() or "llama-cpp"
    kwargs: dict[str, object] = {
        "base_url": base_url,
        "api_key": key,
        "model": model,
        "temperature": temperature,
    }

    extra_body: dict[str, object] = {}

    if thinking_level is not None:
        if thinking_level == "off":
            extra_body["reasoning"] = "off"
        elif thinking_budget is not None and thinking_budget > 0:
            extra_body["reasoning"] = "on"
            extra_body["reasoning_budget"] = thinking_budget

    # Parse and merge custom extra_params if provided
    if extra_params:
        parsed_extra: dict = {}
        if isinstance(extra_params, dict):
            parsed_extra = extra_params
        elif isinstance(extra_params, str) and extra_params.strip():
            try:
                parsed_extra = json.loads(extra_params)
            except Exception:
                logger.debug("Failed to parse extra_params JSON: %s", extra_params)

        if isinstance(parsed_extra, dict):
            direct_keys = {"max_tokens", "top_p", "frequency_penalty", "presence_penalty", "n", "seed"}
            for k, v in parsed_extra.items():
                if k in direct_keys:
                    kwargs[k] = v
                else:
                    extra_body[k] = v

    if extra_body:
        kwargs["extra_body"] = extra_body

    return ChatOpenAI(**kwargs)


def transcode_webm_to_wav_b64(audio_b64: str, target_rate: int = 16000) -> str:
    if not audio_b64:
        return ""
    if "," in audio_b64 and audio_b64.startswith("data:"):
        audio_b64 = audio_b64.split(",", 1)[1]
    try:
        raw: bytes = base64.b64decode(audio_b64)
    except Exception:
        return ""
    if not raw:
        return ""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found — install with 'winget install ffmpeg'")
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as fin:
        fin.write(raw)
        fin_path: str = fin.name
    fd, fout_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", fin_path, "-ar", str(target_rate), "-ac", "1", "-f", "wav", fout_path],
            capture_output=True, timeout=15,
        )
        if result.returncode != 0:
            detail: str = result.stderr.decode(errors="ignore")[:500] if result.stderr else ""
            raise RuntimeError(f"ffmpeg transcode failed: {detail}")
        with open(fout_path, "rb") as f:
            wav_bytes: bytes = f.read()
        return base64.b64encode(wav_bytes).decode("ascii")
    finally:
        for p in (fin_path, fout_path):
            try:
                os.unlink(p)
            except Exception:
                pass
