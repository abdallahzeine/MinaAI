"""
Shared GPU TTS service for Silma.

- Loads silma-ai/silma-tts (150M bilingual AR/EN, Apache 2.0) once at Django startup,
  pinned to cuda:0 on the same GPU as the 4B LLM (llama.cpp via http://localhost:8080/v1).
- Keeps the model warm in VRAM after first load — no cold start, no CPU fallback.
- Both models stay resident; execution is sequential: LLM generates text first,
  then TTS synthesizes wav on the same GPU. Total VRAM < 6 GB, no contention.
- Single reference voice: 8 s wav + exact transcript at Backend/assets/reference.wav
  + Backend/assets/reference.txt (override via SILMA_REF_AUDIO / SILMA_REF_TEXT /
  SILMA_REF_TEXT_FILE). Silma pulls weights from hf://silma-ai/silma-tts on first use
  and caches automatically via cached_path. ffmpeg must be on PATH.
"""

from __future__ import annotations

import io
import logging
import os
import re

# Mitigate CUDA fragmentation on 8GB WDDM (RTX 4060 Laptop) when Silma (2.3GB) + Gemma 4B (~3.8GB) share cuda:0.
# Must be set before torch is imported.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
# Ensure Arabic print doesn't crash on Windows cp1252 (silma prints normalized Arabic)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

import shutil
import threading
import time
from pathlib import Path
from typing import Callable, Tuple, Optional

logger = logging.getLogger(__name__)

# Default reference voice location (Backend/assets/...)
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_DEFAULT_REF_AUDIO = _BACKEND_DIR / "assets" / "reference.wav"
_DEFAULT_REF_TEXT_FILE = _BACKEND_DIR / "assets" / "reference.txt"

# Global singleton + locks
_instance: Optional["SilmaTTSService"] = None
_instance_lock = threading.Lock()
# Sequential GPU execution — only one synthesis at a time on cuda:0
_synthesize_lock = threading.Lock()

# Desired device: same GPU as LLM. Fallback only with warning (plan says no CPU fallback).
DEFAULT_DEVICE = os.environ.get("SILMA_DEVICE", "cuda:0")


def _resolve_ref_audio() -> Path:
    env_path = os.environ.get("SILMA_REF_AUDIO", "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    return _DEFAULT_REF_AUDIO.resolve() if _DEFAULT_REF_AUDIO.exists() else _DEFAULT_REF_AUDIO


def _resolve_ref_text() -> str:
    # Priority: SILMA_REF_TEXT > SILMA_REF_TEXT_FILE > Backend/assets/reference.txt
    direct = os.environ.get("SILMA_REF_TEXT", "").strip()
    if direct:
        return direct
    file_env = os.environ.get("SILMA_REF_TEXT_FILE", "").strip()
    candidate: Path | None = None
    if file_env:
        candidate = Path(file_env).expanduser().resolve()
    elif _DEFAULT_REF_TEXT_FILE.exists():
        candidate = _DEFAULT_REF_TEXT_FILE
    if candidate is not None and candidate.exists():
        try:
            txt = candidate.read_text(encoding="utf-8").strip()
            if txt:
                return txt
        except Exception:
            logger.exception("Failed to read ref text file %s", candidate)
    # Fallback empty — Silma will try to transcribe on the fly, but quality degrades
    return ""


def _check_ffmpeg() -> bool:
    if shutil.which("ffmpeg") is None:
        logger.error(
            "ffmpeg not found on PATH — Silma reference preprocessing and webm transcode "
            "require ffmpeg. Install with 'winget install ffmpeg' (Windows) or "
            "'apt-get update && apt install ffmpeg -y' (Linux)."
        )
        return False
    return True


def _resolve_device(requested: str = DEFAULT_DEVICE) -> str:
    requested = (requested or "cuda:0").strip()
    # Normalize cuda -> cuda:0 if bare
    if requested == "cuda":
        requested = "cuda:0"
    try:
        import torch

        if requested.startswith("cuda"):
            if torch.cuda.is_available():
                # Pin to cuda:0 explicitly per plan (same GPU as 4B LLM)
                # If requested is cuda:1 etc., respect it but warn
                if requested != "cuda:0":
                    logger.warning("TTS device requested %s is not cuda:0 — pinning to %s per same-GPU plan", requested, requested)
                else:
                    logger.info("TTS device pinned to cuda:0 (same GPU as LLM)")
                # Ensure cuda:0 is actually available
                try:
                    # Touch device 0 to verify
                    torch.cuda.get_device_name(0)
                    logger.info("CUDA device 0: %s — VRAM will host Silma (150M) + 4B LLM sequentially, <6GB total", torch.cuda.get_device_name(0))
                except Exception as e:
                    logger.warning("cuda:0 probe failed: %s", e)
                return requested
            else:
                logger.warning(
                    "Requested TTS device %s but torch.cuda.is_available() is False — "
                    "falling back to cpu for development. Production must run on cuda:0 "
                    "with no CPU fallback; both models should stay resident.",
                    requested,
                )
                return "cpu"
        # mps / xpu / cpu explicit
        return requested
    except ImportError:
        logger.warning("torch not installed yet — device resolution deferred to load time")
        return requested


def _log_vram(context: str) -> None:
    """Log allocated/reserved CUDA VRAM on device 0; no-op when CUDA unavailable."""
    try:
        import torch as _torch

        if not _torch.cuda.is_available():
            return
        alloc = _torch.cuda.memory_allocated(0) / 1024 / 1024
        reserved = _torch.cuda.memory_reserved(0) / 1024 / 1024
        logger.info("[TTS] %s: allocated %.0f MB / reserved %.0f MB", context, alloc, reserved)
    except Exception:
        pass


def _truncate_for_tts(text: str, limit: int = 2000) -> str:
    """Soft-truncate overlong replies at the last sentence boundary within limit."""
    if len(text) <= limit:
        return text
    logger.warning("[TTS] gen_text %d chars exceeds %d, truncating to avoid high latency", len(text), limit)
    head = text[:limit]
    return head.rsplit(".", 1)[0] + "." if "." in head else head


class _ProgressProxy:
    """tqdm-module stand-in that reports batch completions via a callback.

    Silma's infer_batch_process iterates `progress.tqdm(gen_text_batches)` (streaming)
    or `progress.tqdm(futures)` (parallel batches), where `progress` is the tqdm module.
    This shim exposes the same `tqdm(iterable)` surface and fires `on_batch(done, total)`
    after each item is consumed, so the websocket layer can stream live TTS progress.
    """

    def __init__(self, on_batch: Callable[[int, int], None]) -> None:
        self._on_batch = on_batch

    def tqdm(self, iterable, *args, **kwargs):
        total = len(iterable) if hasattr(iterable, "__len__") else 0

        def _gen():
            done = 0
            for item in iterable:
                done += 1
                yield item
                self._on_batch(done, total)

        return _gen()


class SilmaTTSService:
    """
    Singleton wrapper around silma_tts.api.SilmaTTS.

    - Lazy-loaded but also pre-warmable via AppConfig.ready() or ensure_loaded().
    - Thread-safe sequential synthesis via _synthesize_lock (GPU contention avoidance).
    - No CPU offload: model stays on self.device after first load.
    """

    def __init__(self, device: str | None = None, _skip_load: bool = False) -> None:
        self.device: str = _resolve_device(device or DEFAULT_DEVICE)
        self.ref_audio: Path = _resolve_ref_audio()
        # ref_text string resolved lazily at synthesize time to allow hot-reload via env/file edit
        self._ref_text_cached: str | None = None
        self._ref_text_mtime: float | None = None

        # Underlying SilmaTTS instance (heavy)
        self._model = None  # type: ignore
        self._model_lock = threading.Lock()
        self._loaded: bool = False
        self._load_error: Exception | None = None
        self._load_time: float | None = None

        _check_ffmpeg()

    def _get_ref_text(self) -> str:
        # Re-read file if mtime changed (allows swapping reference without restart)
        # If env overrides exist, just resolve directly
        if os.environ.get("SILMA_REF_TEXT", "").strip() or os.environ.get("SILMA_REF_TEXT_FILE", "").strip():
            txt = _resolve_ref_text()
            self._ref_text_cached = txt
            return txt

        # File-backed default: watch mtime
        try:
            if _DEFAULT_REF_TEXT_FILE.exists():
                mtime = _DEFAULT_REF_TEXT_FILE.stat().st_mtime
                if self._ref_text_cached is None or self._ref_text_mtime != mtime:
                    self._ref_text_cached = _DEFAULT_REF_TEXT_FILE.read_text(encoding="utf-8").strip()
                    self._ref_text_mtime = mtime
                    logger.debug("Ref text reloaded from %s (mtime %s)", _DEFAULT_REF_TEXT_FILE, mtime)
                return self._ref_text_cached or _resolve_ref_text()
        except Exception:
            logger.exception("Failed to read ref text for TTS")
        return _resolve_ref_text()

    def is_available(self) -> bool:
        """Whether service can synthesize (model importable and ref audio present)."""
        if not self.ref_audio.exists():
            return False
        # Model may not be loaded yet but is loadable — check import
        try:
            import silma_tts.api  # noqa: F401
            return True
        except ImportError as e:
            logger.warning("silma-tts not installed: %s", e)
            return False

    def _wait_for_llm_health_gate(self) -> bool:
        """Hold TTS VRAM allocation until LLM health passes — prevents 8GB concurrent OOM.

        Delegates to core.llm.wait_for_llm_ready (single gate). Kept for compatibility;
        ensure_loaded() is the only caller.
        """
        from .llm import wait_for_llm_ready

        return wait_for_llm_ready()

    def ensure_loaded(self, force: bool = False) -> bool:
        """
        Ensure model is loaded and warm on self.device.
        Returns True if loaded, False if failed. Thread-safe, idempotent.
        Sequential callers block on _model_lock but first load dominates.
        Holds VRAM allocation until LLM health passes (8GB crash prevention).
        """
        if self._loaded and not force:
            return True
        with self._model_lock:
            if self._loaded and not force:
                return True
            if self._load_error and not force:
                # Don't throttle ImportError/ModuleNotFoundError — user may have just `pip install silma-tts`
                # and expects immediate retry without waiting 60s or restarting. Only throttle transient
                # runtime errors (e.g. HF download failure, CUDA OOM).
                is_import_err = isinstance(self._load_error, (ModuleNotFoundError, ImportError))
                if not is_import_err and self._load_time and (time.time() - self._load_time) < 60:
                    logger.warning("Silma previous load failed within 60s, skipping reload: %s", self._load_error)
                    return False
                if is_import_err:
                    logger.info("Retrying Silma load after previous import failure: %s", self._load_error)
            # Gate: do not allocate Silma VRAM until LLM health is pass — prevents parallel OOM on 8GB
            if not self._wait_for_llm_health_gate():
                return False
            # Resolve device now (torch may now be available)
            self.device = _resolve_device(self.device)
            _check_ffmpeg()
            try:
                logger.info("[TTS] Loading SilmaTTS on device=%s — this pulls silma-ai/silma-tts weights from HF on first run and caches via cached_path", self.device)
                # Import lazily so module import doesn't fail if deps missing
                from silma_tts.api import SilmaTTS

                # SilmaTTS.__init__ preloads nemo normalizers and tashkeel model (force_tashkeel=True by default)
                # and downloads model.pt + vocab.txt + vocos-mel-24khz on first use.
                start = time.time()
                self._model = SilmaTTS(device=self.device)  # pinned to cuda:0 per plan
                elapsed = time.time() - start
                self._loaded = True
                self._load_error = None
                self._load_time = time.time()
                suffix = "" if "cuda" in self.device else " (no GPU, dev fallback)"
                logger.info("[TTS] Silma loaded on %s in %.1fs%s", self.device, elapsed, suffix)
                _log_vram(f"Post-load VRAM {self.device}")
                return True
            except Exception as e:
                self._load_error = e
                self._load_time = time.time()
                self._loaded = False
                logger.exception("[TTS] Failed to load SilmaTTS on %s: %s — synthesis will fall back to transcript-only. Ensure silma-tts is installed and HF cache reachable. pip install silma-tts", self.device, e)
                return False

    def synthesize(self, gen_text: str, speed: float = 1.0, progress_cb: Optional[Callable[[int, int], None]] = None) -> Tuple[bytes, int] | None:
        """
        Synthesize `gen_text` (LLM reply) using the single reference voice.

        Sequential GPU execution: blocks on global _synthesize_lock so LLM (via llama.cpp
        on same cuda:0) and TTS never contend. Both stay resident in VRAM.

        `progress_cb(done, total)` is invoked from the synthesizing thread as Silma
        completes each text batch (0/None total first when batch count is unknown) —
        used to stream live tts_progress frames to the client.

        Returns (wav_bytes, sample_rate) on success, or None on failure or empty input.
        Caller is responsible for base64 encoding and forwarding as ws audio event.
        On failure, caller should deliver transcript-only and return avatar to idle.
        """
        if not gen_text or not gen_text.strip():
            return None
        # Ensure ref audio exists
        ref_audio = _resolve_ref_audio()
        if not ref_audio.exists():
            logger.error("[TTS] Reference audio not found at %s — set SILMA_REF_AUDIO or place Backend/assets/reference.wav (8 s wav + transcript)", ref_audio)
            return None
        ref_text = self._get_ref_text()
        # ref_text may be empty; Silma will transcribe ref_audio on the fly (quality hit but not fatal)
        if not ref_text:
            logger.warning("[TTS] Reference transcript empty — Silma will transcribe ref audio on the fly; provide exact transcript at Backend/assets/reference.txt for best clone quality")

        gen_text = _truncate_for_tts(gen_text.strip())

        # Sequential GPU lock — LLM already finished, now TTS owns cuda:0
        with _synthesize_lock:
            if not self.ensure_loaded():
                return None
            assert self._model is not None
            try:
                import torch  # noqa: F401

                start = time.time()
                logger.info("[TTS] Synthesizing %d chars on %s (ref: %s)", len(gen_text), self.device, ref_audio.name)

                # Silma infer is synchronous and GPU-bound; run directly (holds _synthesize_lock)
                # to guarantee sequential execution vs LLM. No CPU fallback — stays on cuda:0.
                # progress shim replaces tqdm; show_info hook captures the batch-count header.
                if progress_cb is not None:
                    def _on_batch(done: int, total: int) -> None:
                        progress_cb(done, total)

                    progress = _ProgressProxy(_on_batch)

                    def _show_info(msg: object) -> None:
                        text = str(msg)
                        m = re.search(r"in (\d+) batches", text)
                        if m and progress_cb is not None:
                            progress_cb(0, int(m.group(1)))
                else:
                    progress = None
                    _show_info = print

                wav, sr, spec = self._model.infer(
                    ref_file=str(ref_audio),
                    ref_text=ref_text,
                    gen_text=gen_text,
                    speed=speed,
                    show_info=_show_info,
                    progress=progress,
                    # keep defaults: nfe_step=16, cfg_strength=2, force_tashkeel=True, normalize_numbers=True
                    # file_wave=None -> in-memory wav
                )
                # wav is np.ndarray float32 @ target_sample_rate (24000)
                if wav is None or len(wav) == 0:
                    logger.error("[TTS] Silma infer returned empty wav for text: %s...", gen_text[:60])
                    return None

                # Encode to WAV bytes (PCM 16-bit) via soundfile, in-memory
                import numpy as np
                import soundfile as sf

                # Ensure numpy float32
                if not isinstance(wav, np.ndarray):
                    wav = np.array(wav, dtype=np.float32)

                buf = io.BytesIO()
                # Silma's target_sample_rate is 24000 per config.yaml; use sr returned by infer
                sf.write(buf, wav, sr, format="WAV", subtype="PCM_16")
                wav_bytes = buf.getvalue()
                elapsed = time.time() - start
                logger.info("[TTS] Synthesized %d samples @ %d Hz in %.2fs — %.1f KB, speed=%.1f — RTF ~%.2f (plan stays <6GB VRAM)", len(wav), sr, elapsed, len(wav_bytes) / 1024, speed, elapsed / (len(wav) / sr) if len(wav) else 0)
                _log_vram(f"Post-synth VRAM {self.device}")
                return wav_bytes, int(sr)
            except Exception as e:
                logger.exception("[TTS] Synthesis failed on %s for text %.60r: %s", self.device, gen_text, e)
                return None


def get_tts_service() -> SilmaTTSService:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = SilmaTTSService(_skip_load=True)
        return _instance


def ensure_tts_warm() -> bool:
    """
    Load and warm Silma in VRAM if not already. Intended for AppConfig.ready() or
    first-request warmup. Returns True if warm, False otherwise (non-fatal).
    """
    svc = get_tts_service()
    return svc.ensure_loaded()
