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
    """Block until llama.cpp reports health — single gate for TTS VRAM allocation.

    Polls {LLAMA_CPP_BASE_URL}/models and /health. Returns True if LLM becomes
    ready within timeout, False otherwise (caller should skip prewarm and fall
    back to lazy load). Keeps the richer body check from apps.py (sniffs
    response body for '"data"'/'"object"'/'"id"' on /v1/models).
    """
    import time
    import urllib.request
    import urllib.error

    try:
        from .config import LLAMA_CPP_BASE_URL

        base = (LLAMA_CPP_BASE_URL or "http://localhost:8080/v1").rstrip("/")
    except Exception:
        base = os.environ.get("LLAMA_CPP_BASE_URL", "http://localhost:8080/v1").rstrip("/")

    root = base[:-3] if base.endswith("/v1") else base
    candidates = [f"{base}/models", f"{root}/health", base]

    try:
        timeout_s = float(os.environ.get("SILMA_LLM_HEALTH_TIMEOUT", str(timeout_s)))
    except Exception:
        pass
    try:
        interval_s = float(os.environ.get("SILMA_LLM_HEALTH_INTERVAL", str(interval_s)))
    except Exception:
        pass

    if os.environ.get("SILMA_PREWARM_WAIT_FOR_LLM", "1") not in ("1", "true", "True", "yes"):
        logger.info("[TTS] SILMA_PREWARM_WAIT_FOR_LLM disabled — prewarming immediately without LLM health gate")
        return True
    if timeout_s <= 0:
        return True

    logger.info("[TTS] Holding Silma prewarm until LLM health passes at %s (timeout %.0fs)", base, timeout_s)
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
                                logger.info("[TTS] LLM health pass on %s (attempt %d) — proceeding to Silma load", url, attempt)
                                return True
                            logger.info("[TTS] LLM health pass on %s (attempt %d, status %d) — proceeding to Silma load", url, attempt, code)
                            return True
                        logger.info("[TTS] LLM health pass on %s (attempt %d, status %d) — proceeding to Silma load", url, attempt, code)
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
    logger.warning("[TTS] LLM health did not pass within %.0fs — skipping Silma prewarm; will load lazily on first synthesize after LLM is ready", timeout_s)
    return False


def get_llama_llm(
    base_url: str,
    model: str,
    temperature: float,
    thinking_level: str | None = None,
    thinking_budget: int | None = None,
) -> "BaseChatModel":
    from langchain_openai import ChatOpenAI

    kwargs: dict[str, object] = {"base_url": base_url, "api_key": "llama-cpp", "model": model, "temperature": temperature}
    if thinking_level is not None:
        # reasoning=off maps to a 0 budget (skip thinking); on maps to the
        # configured token budget for the thinking phase.
        kwargs["extra_body"] = {
            "reasoning": "off" if thinking_level == "off" else "on",
            "reasoning_budget": thinking_budget if thinking_budget is not None else -1,
        }
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
