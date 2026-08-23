"""Pluggable TTS provider abstraction and Audar-TTS implementation.

Defines the BaseTTSProvider contract and registry so any text-to-speech
engine can be swapped cleanly, with Audar-TTS-V1 as the primary production engine.

Wiring:
- AudarTTSProvider is registered under 'audar' and is the default backend.
- The active backend is selected by the TTS_BACKEND environment variable (defaults to 'audar').
- get_tts_service() returns the singleton instance of the configured backend.
- ensure_tts_warm() preloads the configured backend during startup.

Consumer contract (see main.core.websocket):
    svc = get_tts_service()
    wav_bytes, sample_rate = svc.synthesize(text, progress_cb=cb)
On failure synthesize returns None and the caller falls back to transcript-only.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Callable, Optional, Tuple, Type

import numpy as np

from .audar_engine import OUT_SR, AudarTTSEngine, numpy_to_wav_bytes
from .text_batcher import split_into_batches

logger = logging.getLogger(__name__)


class BaseTTSProvider:
    """Abstract TTS provider. Subclass and register_provider(name, YourProvider).

    Lifecycle:
    - ensure_loaded(): load the model / acquire resources (idempotent).
    - is_available(): whether synthesis can run right now.
    - synthesize(): return (wav_bytes, sample_rate) or None on failure/empty.

    progress_cb(done, total) is invoked from the synthesizing thread to stream
    live batch progress to the client; ignore if not applicable to your engine.
    """

    def ensure_loaded(self, force: bool = False) -> bool:
        raise NotImplementedError

    def is_available(self) -> bool:
        raise NotImplementedError

    def interrupt(self) -> None:
        """Force interrupt any ongoing synthesis immediately."""
        pass

    def synthesize(
        self,
        gen_text: str,
        speed: float = 1.0,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> Optional[Tuple[bytes, int]]:
        raise NotImplementedError


class AudarTTSProvider(BaseTTSProvider):
    """Audar-TTS-V1-Flash provider with sentence batching & English surrounding."""

    def __init__(self) -> None:
        self.engine = AudarTTSEngine()
        self._lock = threading.Lock()

    def interrupt(self) -> None:
        """Force abort neural generation immediately."""
        self.engine.interrupt()

    def ensure_loaded(self, force: bool = False) -> bool:
        with self._lock:
            if not self.engine.is_loaded() or force:
                logger.info("[AudarTTSProvider] Loading Audar-TTS engine models...")
                self.engine.load_models()
                self.engine.warmup()
                logger.info("[AudarTTSProvider] Audar-TTS engine loaded and pre-warmed successfully")
            return self.engine.is_loaded()

    def is_available(self) -> bool:
        return self.engine.is_loaded()

    def synthesize(
        self,
        gen_text: str,
        speed: float = 1.0,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> Optional[Tuple[bytes, int]]:
        """Synthesize text by batching into sentences with Arabic surrounding for English."""
        if not gen_text or not gen_text.strip():
            return None

        # Reset any past interrupt flag
        self.engine.reset_interrupt()

        # Ensure model is ready
        if not self.is_available():
            self.ensure_loaded()

        # Split input into sentences / batches with English protection
        batches = split_into_batches(gen_text)
        if not batches:
            return None

        total_batches = len(batches)
        logger.info("[AudarTTSProvider] Synthesizing %d batches for text length %d", total_batches, len(gen_text))

        wave_chunks: list[np.ndarray] = []
        # 60ms natural pause between sentences @ 24kHz
        silence_samples = int(0.06 * OUT_SR)
        silence = np.zeros(silence_samples, dtype=np.float32)

        try:
            with self._lock:
                for idx, batch_text in enumerate(batches):
                    if self.engine._stop_event.is_set():
                        logger.info("[AudarTTSProvider] Synthesis aborted immediately on user stop request")
                        return None
                    logger.debug("[AudarTTSProvider] Batch %d/%d: %s", idx + 1, total_batches, batch_text)
                    try:
                        audio_chunk = self.engine.synthesize_batch(batch_text)
                        if audio_chunk is not None and len(audio_chunk) > 0:
                            if wave_chunks:
                                wave_chunks.append(silence)
                            wave_chunks.append(audio_chunk)
                    except Exception as e:
                        logger.exception("[AudarTTSProvider] Failed synthesizing batch %d: %s", idx + 1, e)

                    # Report progress
                    if progress_cb:
                        try:
                            progress_cb(idx + 1, total_batches)
                        except Exception:
                            logger.debug("Failed to invoke progress_cb", exc_info=True)

            if not wave_chunks:
                logger.warning("[AudarTTSProvider] All batches failed to produce audio")
                return None

            combined_audio = np.concatenate(wave_chunks)
            wav_bytes = numpy_to_wav_bytes(combined_audio, OUT_SR)
            return wav_bytes, OUT_SR

        except Exception as e:
            logger.exception("[AudarTTSProvider] Synthesis failed: %s", e)
            return None


class DisabledTTSProvider(BaseTTSProvider):
    """Silent/disabled TTS provider when voice synthesis is turned off."""

    def ensure_loaded(self, force: bool = False) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    def synthesize(
        self,
        gen_text: str,
        speed: float = 1.0,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> Optional[Tuple[bytes, int]]:
        return None


class OpenAITTSProvider(BaseTTSProvider):
    """Remote OpenAI-compatible /audio/speech TTS provider."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def ensure_loaded(self, force: bool = False) -> bool:
        return True

    def is_available(self) -> bool:
        return True

    def synthesize(
        self,
        gen_text: str,
        speed: float = 1.0,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        voice: Optional[str] = None,
        extra_params: Optional[str] = None,
    ) -> Optional[Tuple[bytes, int]]:
        if not gen_text or not gen_text.strip():
            return None

        import json
        import struct
        import urllib.error
        import urllib.request
        from .config import resolve_params

        params = resolve_params()
        target_base_url = (base_url or params.get("tts_base_url") or params.get("base_url") or "").rstrip("/")
        target_api_key = api_key if (api_key is not None and api_key != "") else (params.get("tts_api_key") or params.get("api_key") or "")
        target_model = model or params.get("tts_model") or "tts-1"
        target_voice = voice or params.get("tts_voice") or "alloy"
        spd = float(speed if speed is not None else (params.get("tts_speed") or 1.0))

        if not target_base_url:
            logger.warning("[OpenAITTSProvider] No Base URL configured for remote TTS")
            return None

        url = f"{target_base_url}/audio/speech"
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Mina AI",
        }
        if target_api_key:
            headers["Authorization"] = f"Bearer {target_api_key}"

        # OpenRouter accepts response_format 'pcm' (which returns standard 24kHz RIFF WAV) or 'mp3'; OpenAI supports 'wav'
        resp_fmt = "pcm" if "openrouter" in target_base_url.lower() else "wav"

        body: dict = {
            "model": target_model,
            "input": gen_text,
            "voice": target_voice,
            "speed": spd,
            "response_format": resp_fmt,
        }
        extra_str = extra_params if extra_params is not None else params.get("tts_extra_params", "")
        if extra_str and extra_str.strip():
            try:
                extra_json = json.loads(extra_str)
                if isinstance(extra_json, dict):
                    body.update(extra_json)
            except Exception:
                pass

        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                audio_bytes = resp.read()
                sr = 24000
                if len(audio_bytes) >= 28 and audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
                    try:
                        sr = struct.unpack("<I", audio_bytes[24:28])[0]
                    except Exception:
                        sr = 24000
                return audio_bytes, sr
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")[:400] if hasattr(e, "read") else str(e)
            logger.exception("[OpenAITTSProvider] Remote TTS synthesis failed HTTP %s: %s", e.code, err_msg)
            raise RuntimeError(f"HTTP {e.code}: {err_msg}")
        except Exception as e:
            logger.exception("[OpenAITTSProvider] Remote TTS synthesis failed: %s", e)
            raise


_REGISTRY: dict[str, Type[BaseTTSProvider]] = {
    "audar": AudarTTSProvider,
    "openai": OpenAITTSProvider,
    "openai_compatible": OpenAITTSProvider,
    "disabled": DisabledTTSProvider,
}
_REGISTRY_LOCK = threading.Lock()


def register_provider(name: str, cls: Type[BaseTTSProvider]) -> None:
    """Register a TTS provider class under name (e.g. 'audar', 'habibi'). Idempotent."""
    key = (name or "").strip().lower()
    if not key:
        raise ValueError("provider name must be non-empty")
    with _REGISTRY_LOCK:
        _REGISTRY[key] = cls


def get_provider_class(name: str) -> Optional[Type[BaseTTSProvider]]:
    key = (name or "").strip().lower()
    with _REGISTRY_LOCK:
        return _REGISTRY.get(key)


_INSTANCES: dict[str, BaseTTSProvider] = {}
_INSTANCES_LOCK = threading.Lock()


def get_tts_service() -> BaseTTSProvider:
    """Return the active TTS service singleton for the configured provider."""
    try:
        from .config import resolve_params
        params = resolve_params()
        backend = (params.get("tts_provider") or os.environ.get("TTS_BACKEND", "audar")).strip().lower()
    except Exception:
        backend = os.environ.get("TTS_BACKEND", "audar").strip().lower()

    if not backend:
        backend = "audar"

    cls = get_provider_class(backend)
    if cls is None:
        cls = AudarTTSProvider

    with _INSTANCES_LOCK:
        if backend not in _INSTANCES:
            _INSTANCES[backend] = cls()
        return _INSTANCES[backend]


def ensure_tts_warm() -> bool:
    """Preload and warm the configured TTS backend if any."""
    try:
        svc = get_tts_service()
        return svc.ensure_loaded()
    except Exception:
        logger.exception("[TTS] Prewarm failed (non-fatal)")
        return False
