"""Audar-TTS-V1-Flash Inference Engine for Backend.

Handles model loading, voice reference encoding, prompt construction,
neural speech token generation, and NeuCodec audio synthesis.
"""

from __future__ import annotations

import io
import logging
import os
import re
import time
from pathlib import Path
from typing import Callable, Optional, Tuple

import numpy as np
import soundfile as sf
import torch

from .voices import VoiceProfile, get_default_voice_info, get_voice_info

logger = logging.getLogger(__name__)

REF_SR = 16_000   # Reference clip sample rate (for codec encoding)
OUT_SR = 24_000   # Generated output audio sample rate (24 kHz)
MODEL_REPO = "audarai/Audar-TTS-V1-Flash"
CODEC_REPO = "neuphonic/neucodec"

# Supported expression tags for Flash
EXPRESSION_TAGS = [
    "[laughs]",
    "[curious]",
    "[excited]",
    "[sighs]",
    "[exhales]",
    "[mischievously]",
    "[whispers]",
    "[sarcastic]",
]

GEN_DEFAULTS = dict(
    do_sample=True,
    temperature=1.0,
    top_k=40,
    top_p=0.9,
    repetition_penalty=1.1,
    min_new_tokens=50,
)

_SPEECH_RE = re.compile(r"<\|speech_(\d+)\|>")


class ForceStopCriteria:
    """Hugging Face compatible stopping criteria to force-abort generation immediately."""

    def __init__(self, stop_event):
        self.stop_event = stop_event

    def __call__(self, input_ids, scores, **kwargs) -> bool:
        return self.stop_event.is_set()


class AudarTTSEngine:
    """Audar-TTS engine wrapper managing model weights, codec, and generation."""

    def __init__(self, device: Optional[str] = None, log_callback: Optional[Callable[[str], None]] = None):
        self.log = log_callback or (lambda msg: logger.info("[AudarEngine] %s", msg))
        import threading
        self._stop_event = threading.Event()

        if device is None:
            env_dev = os.environ.get("TTS_DEVICE", "").strip()
            if env_dev:
                self.device = env_dev
            elif torch.cuda.is_available():
                self.device = "cuda:0"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"
        else:
            self.device = device

        if "cuda" in self.device and torch.cuda.is_bf16_supported():
            self.dtype = torch.bfloat16
        elif "cuda" in self.device:
            self.dtype = torch.float16
        else:
            self.dtype = torch.float32

        self.model = None
        self.tokenizer = None
        self.codec = None
        self.cached_ref_codes: dict[str, list[int]] = {}
        self.active_voice = "demo_male_1"
        self.active_ref_wav: Optional[str] = None
        self.active_ref_text = ""
        self._is_loaded = False

    def interrupt(self) -> None:
        """Instantly interrupt and force-abort ongoing neural generation."""
        self._stop_event.set()

    def reset_interrupt(self) -> None:
        """Reset the interrupt flag for fresh synthesis."""
        self._stop_event.clear()

    def is_loaded(self) -> bool:
        return self._is_loaded and self.model is not None and self.codec is not None

    def load_models(self) -> None:
        """Loads both Transformers model/tokenizer and NeuCodec."""
        if self.is_loaded():
            return

        from transformers import AutoModelForCausalLM, AutoTokenizer
        from neucodec import NeuCodec
        import warnings

        warnings.filterwarnings("ignore", category=FutureWarning)
        warnings.filterwarnings("ignore", category=UserWarning)

        self.log(f"Device target: {self.device} (Precision: {self.dtype})")

        # 1. Load Tokenizer & LM Backbone
        self.log(f"Loading Audar-TTS backbone from {MODEL_REPO} (subfolder='transformers')...")
        t0 = time.time()
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_REPO, subfolder="transformers")
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_REPO,
            subfolder="transformers",
            torch_dtype=self.dtype,
            low_cpu_mem_usage=True,
        ).eval().to(self.device)
        self.log(f"Backbone loaded in {time.time() - t0:.2f}s.")

        # 2. Load NeuCodec (with open mirror fallback)
        self.log("Loading Audio Codec...")
        t0 = time.time()
        codec = None
        for repo_candidate in [CODEC_REPO, "nguyensu27/neucodec", "eugenehp/neucodec"]:
            try:
                from huggingface_hub import hf_hub_download
                ckpt_path = hf_hub_download(repo_id=repo_candidate, filename="pytorch_model.bin")
                codec = NeuCodec(24_000, 480)
                state_dict = torch.load(ckpt_path, map_location="cpu")
                ignore_keys = ["fc_post_s", "SemanticDecoder"]
                state_dict = {
                    k: v for k, v in state_dict.items()
                    if not any(ign in k for ign in ignore_keys)
                }
                codec.load_state_dict(state_dict, strict=False)
                self.log(f"Codec loaded successfully from {repo_candidate} in {time.time() - t0:.2f}s.")
                break
            except Exception as ex:
                self.log(f"Notice: {repo_candidate} not accessible ({ex}), trying fallback mirror...")

        if codec is None:
            raise RuntimeError("Failed to load NeuCodec from available repositories.")

        self.codec = codec.eval().to(self.device)

        # 3. Initialize default reference voice
        self.set_default_voice()
        self._is_loaded = True

    def warmup(self) -> None:
        """Prime PyTorch execution graphs and NeuCodec decoder so first inference has 0 cold-start delay."""
        if not self.is_loaded():
            self.load_models()
        self.log("Pre-warming TTS generation pipeline...")
        t0 = time.time()
        try:
            # Perform a fast mini forward pass and codec decode to warm kernels and memory buffers
            _ = self.synthesize_batch("مرحبا", max_new_tokens=30)
            self.log(f"TTS pipeline pre-warmed and ready for input in {time.time() - t0:.2f}s.")
        except Exception as e:
            self.log(f"TTS pre-warm step notice: {e}")

    def set_default_voice(self) -> None:
        """Sets the active voice reference clip based on environment / defaults."""
        vinfo = get_default_voice_info()
        self.active_ref_wav = vinfo["path"]
        self.active_ref_text = vinfo["text"]
        self.active_voice = vinfo["file"]
        self._ensure_ref_cached()

    def set_voice(self, voice_id_or_path: str, ref_text: Optional[str] = None) -> None:
        """Sets the active voice reference clip from registry or custom path."""
        try:
            info = get_voice_info(voice_id_or_path)
            self.active_ref_wav = info["path"]
            self.active_ref_text = ref_text or info["text"]
            self.active_voice = voice_id_or_path
        except KeyError:
            self.active_ref_wav = voice_id_or_path
            self.active_ref_text = ref_text or "Reference speech prompt"
            self.active_voice = Path(voice_id_or_path).stem

        self._ensure_ref_cached()

    def _ensure_ref_cached(self) -> None:
        """Pre-encode reference codes for instant reuse across batches."""
        if not self.active_ref_wav or not os.path.exists(self.active_ref_wav):
            return
        mtime = os.path.getmtime(self.active_ref_wav)
        cache_key = f"{self.active_ref_wav}_{mtime}"
        if cache_key not in self.cached_ref_codes and self.codec is not None:
            self.log(f"Encoding reference voice: {self.active_voice} ({Path(self.active_ref_wav).name})")
            self.cached_ref_codes[cache_key] = self.encode_reference(self.active_ref_wav)

    def encode_reference(self, ref_wav_path_or_array) -> list[int]:
        """Encodes reference audio clip into discrete speech codes."""
        import librosa
        if isinstance(ref_wav_path_or_array, (str, Path)):
            wav_data, _ = librosa.load(str(ref_wav_path_or_array), sr=REF_SR, mono=True)
        else:
            wav_data = ref_wav_path_or_array

        wav_tensor = torch.from_numpy(wav_data.astype(np.float32))[None, None, :]
        codec_device = next(self.codec.parameters()).device
        with torch.no_grad():
            codes = self.codec.encode_code(wav_tensor.to(codec_device)).squeeze().tolist()
        return codes

    def build_prompt(self, target_text: str, ref_text: str, ref_codes: list[int]) -> str:
        """Constructs prompt structure identical to official Audar-TTS protocol."""
        ref_tokens_str = "".join(f"<|speech_{c}|>" for c in ref_codes)
        return (
            "user: Convert the text to speech:"
            f"<|REF_TEXT_START|>{ref_text}<|REF_TEXT_END|>"
            f"<|REF_SPEECH_START|>{ref_tokens_str}<|REF_SPEECH_END|>"
            f"<|TARGET_TEXT_START|>{target_text}<|TARGET_TEXT_END|>"
            "\nassistant:<|TARGET_CODES_START|>"
        )

    def synthesize_batch(
        self,
        target_text: str,
        temperature: float = 1.0,
        max_new_tokens: int = 1500,
    ) -> np.ndarray:
        """Synthesize a single text batch into a 24 kHz numpy waveform."""
        if not self.is_loaded():
            self.load_models()

        assert self.model is not None
        assert self.tokenizer is not None
        assert self.codec is not None

        # 1. Reference Audio Codes
        mtime = os.path.getmtime(self.active_ref_wav) if self.active_ref_wav and os.path.exists(self.active_ref_wav) else ""
        cache_key = f"{self.active_ref_wav}_{mtime}"
        if cache_key in self.cached_ref_codes:
            ref_codes = self.cached_ref_codes[cache_key]
        else:
            if not self.active_ref_wav or not os.path.exists(self.active_ref_wav):
                raise FileNotFoundError(f"Reference voice audio not found: {self.active_ref_wav}")
            ref_codes = self.encode_reference(self.active_ref_wav)
            self.cached_ref_codes[cache_key] = ref_codes

        # 2. Prompt Building & Tokenization
        prompt = self.build_prompt(target_text, self.active_ref_text, ref_codes)
        input_ids = self.tokenizer.encode(prompt, add_special_tokens=False, return_tensors="pt").to(self.device)
        tce = self.tokenizer.convert_tokens_to_ids("<|TARGET_CODES_END|>")

        if self._stop_event.is_set():
            raise RuntimeError("Generation force-stopped by user")

        from transformers import StoppingCriteriaList

        stop_criteria = StoppingCriteriaList([ForceStopCriteria(self._stop_event)])
        gen_config = {
            **GEN_DEFAULTS,
            "temperature": temperature,
            "max_new_tokens": max_new_tokens,
            "eos_token_id": tce,
            "pad_token_id": 151643,
            "stopping_criteria": stop_criteria,
        }

        # 3. Speech Token Generation (LM Backbone)
        with torch.no_grad():
            output_ids = self.model.generate(
                input_ids,
                **gen_config
            )

        if self._stop_event.is_set():
            raise RuntimeError("Generation force-stopped by user")

        # 4. Extract speech tokens
        gen_tokens_text = self.tokenizer.decode(output_ids[0, input_ids.shape[1]:], skip_special_tokens=False)
        codes = [int(x) for x in _SPEECH_RE.findall(gen_tokens_text)]

        if not codes:
            raise RuntimeError(f"Model emitted no speech tokens for text: '{target_text[:40]}...'")

        # 5. Waveform Reconstruction with NeuCodec (24 kHz)
        codec_device = next(self.codec.parameters()).device
        with torch.no_grad():
            codes_tensor = torch.tensor(codes, dtype=torch.long)[None, None, :].to(codec_device)
            wav_tensor = self.codec.decode_code(codes_tensor)
            audio_data = wav_tensor.cpu().numpy()[0, 0, :].astype(np.float32)

        return audio_data


def numpy_to_wav_bytes(audio_array: np.ndarray, sample_rate: int = OUT_SR) -> bytes:
    """Convert float32 numpy audio waveform to 16-bit PCM WAV bytes."""
    buf = io.BytesIO()
    # Normalize if peak exceeds 1.0 to prevent clipping
    max_val = np.max(np.abs(audio_array)) if len(audio_array) > 0 else 0
    if max_val > 1.0:
        audio_array = audio_array / max_val * 0.98
    sf.write(buf, audio_array, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()
