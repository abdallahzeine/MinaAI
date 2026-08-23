"""Voice registry and reference loader for TTS providers.

Contains reference voice profiles for Audar-TTS and dialect voices,
and handles custom reference clips and transcripts.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
VOICES_DIR = ASSETS_DIR / "voices"


class VoiceProfile(TypedDict):
    file: str
    path: str
    text: str
    desc: str
    category: str


VOICE_REGISTRY: dict[str, dict[str, str]] = {
    # Audar Expressive Voices
    "demo_male_1": {
        "file": "demo_male_1.wav",
        "text": "مرحبا، أنا هنا لمساعدتك في تحويل النصوص إلى كلام طبيعي وواضح.",
        "desc": "Male - Warm, confident (Audar)",
        "category": "Expressive (Audar)",
    },
    "demo_female_1": {
        "file": "demo_female_1.wav",
        "text": "أهلاً بك، يسعدني التحدث إليك وتجربة نبرات الصوت المختلفة.",
        "desc": "Female - Vibrant, joyful (Audar)",
        "category": "Expressive (Audar)",
    },
    "demo_male_2": {
        "file": "demo_male_2.wav",
        "text": "تحياتي، هذا نموذج صوتي ناعم وهادئ لأداء العبارات المختلفة.",
        "desc": "Male - Soft, intimate (Audar)",
        "category": "Expressive (Audar)",
    },
    "demo_female_2": {
        "file": "demo_female_2.wav",
        "text": "مرحباً بكم جميعاً في هذا العرض التوضيحي لصوت أنثوي مرح.",
        "desc": "Female - Velvety, playful (Audar)",
        "category": "Expressive (Audar)",
    },
    # Dialect Voices
    "Najdi": {
        "file": "Najdi.wav",
        "text": "تكفى طمني انا اليوم ماني بنايم ولا هو بداخل عيني النوم الين اتطمن عليه.",
        "desc": "Saudi Najdi (النجدية)",
        "category": "Dialect",
    },
    "Hijazi": {
        "file": "Hijazi.wav",
        "text": "ابغاك تحقق معاه بس بشكل ودي لانه سلطان يمر بظروف صعبة شوية.",
        "desc": "Saudi Hijazi (الحجازية)",
        "category": "Dialect",
    },
    "Gulf": {
        "file": "Gulf.wav",
        "text": "وين تو الناس متى تصحى ومتى تفطر وتغير يبيلك ساعة يعني بالله تروح الشغل الساعة عشره.",
        "desc": "Saudi / Gulf (الخليجية)",
        "category": "Dialect",
    },
    "MSA": {
        "file": "MSA.mp3",
        "text": "كان اللعيب حاضرًا في العديد من الأنشطة والفعاليات المرتبطة بكأس العالم، مما سمح للجماهير بالتفاعل معه والتقاط الصور التذكارية.",
        "desc": "Modern Standard Arabic (الفصحى)",
        "category": "Dialect",
    },
    "EGY": {
        "file": "EGY.mp3",
        "text": "ايه الكلام. بقولك ايه. استخدم صوتي في المحادثات. استخدمه هيعجبك اوي.",
        "desc": "Egyptian (اللهجة المصرية)",
        "category": "Dialect",
    },
    "UAE": {
        "file": "UAE.wav",
        "text": "قمنا نشتريها بشكل متكرر أو لما نلقى ستايل يعجبنا وحياناً هذا الستايل ما نحبه.",
        "desc": "Emirati (اللهجة الإماراتية)",
        "category": "Dialect",
    },
    "MAR": {
        "file": "MAR.mp3",
        "text": "إذا بغيتي شي صوت باللهجة المغربية للإعلانات ديالك هذا أحسن واحد غادي تلقاه.",
        "desc": "Moroccan / Darija (الدارجة المغربية)",
        "category": "Dialect",
    },
    "IRQ": {
        "file": "IRQ.wav",
        "text": "يعني ااا ما نقدر ناخذ وقت أكثر، ااا لأنه شروط كلش يحتاجلها وقت.",
        "desc": "Iraqi (اللهجة العراقية)",
        "category": "Dialect",
    },
    "ALG": {
        "file": "ALG.wav",
        "text": "أنيا هكا باغية ناكل هكا أني ن نشوف فيها الحاجة هذيكا.",
        "desc": "Algerian (اللهجة الجزائرية)",
        "category": "Dialect",
    },
}


def get_default_voice_info() -> VoiceProfile:
    """Resolve the voice profile to use based on env vars or default fallback."""
    voice_env = os.environ.get("TTS_VOICE", "").strip()
    ref_audio_env = os.environ.get("TTS_REF_AUDIO", "").strip()
    ref_text_env = os.environ.get("TTS_REF_TEXT", "").strip()

    # If explicit file path is provided via TTS_REF_AUDIO
    if ref_audio_env:
        p = Path(ref_audio_env)
        if p.exists():
            text = ref_text_env
            if not text:
                ref_txt_file = os.environ.get("TTS_REF_TEXT_FILE", "").strip()
                if ref_txt_file and Path(ref_txt_file).exists():
                    text = Path(ref_txt_file).read_text(encoding="utf-8").strip()
            if not text:
                sidecar_txt = p.with_suffix(".txt")
                if sidecar_txt.exists():
                    text = sidecar_txt.read_text(encoding="utf-8").strip()
            return {
                "file": p.name,
                "path": str(p),
                "text": text or "Reference speech prompt",
                "desc": f"Custom audio ({p.name})",
                "category": "Custom",
            }

    # If voice name is specified in TTS_VOICE
    if voice_env and voice_env in VOICE_REGISTRY:
        return get_voice_info(voice_env)

    # Check for custom reference.wav in Backend/assets/
    default_ref_wav = ASSETS_DIR / "reference.wav"
    default_ref_txt = ASSETS_DIR / "reference.txt"
    if default_ref_wav.exists():
        text = ""
        if default_ref_txt.exists():
            text = default_ref_txt.read_text(encoding="utf-8").strip()
        return {
            "file": "reference.wav",
            "path": str(default_ref_wav),
            "text": text or "تكفى طمني انا اليوم ماني بنايم ولا هو بداخل عيني النوم الين اتطمن عليه.",
            "desc": "Default reference clip",
            "category": "Default",
        }

    # Fallback to demo_male_1
    return get_voice_info("demo_male_1")


def get_voice_info(voice_name: str) -> VoiceProfile:
    """Returns voice metadata, file path, and reference transcript for a named voice."""
    if voice_name in VOICE_REGISTRY:
        raw = VOICE_REGISTRY[voice_name]
        voice_path = VOICES_DIR / raw["file"]
        if not voice_path.exists():
            # Check assets root as fallback
            alt_path = ASSETS_DIR / raw["file"]
            if alt_path.exists():
                voice_path = alt_path
        return {
            "file": raw["file"],
            "path": str(voice_path),
            "text": raw["text"],
            "desc": raw["desc"],
            "category": raw["category"],
        }

    p = Path(voice_name)
    if p.exists():
        return {
            "file": p.name,
            "path": str(p),
            "text": "Reference speech prompt",
            "desc": f"Custom voice ({p.stem})",
            "category": "Custom",
        }

    raise KeyError(f"Voice '{voice_name}' not found in registry and file does not exist.")
