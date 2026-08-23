import logging
import os
import threading
from django.apps import AppConfig
logger = logging.getLogger(__name__)
class MainConfig(AppConfig):
    name: str = "main"
    verbose_name = "Mina Main"
    def ready(self) -> None:
        import sys
        argv = " ".join(sys.argv).lower()
        if any(k in argv for k in ("migrate", "makemigrations", "collectstatic", "shell", "test", "check")):
            return
        if "runserver" in argv and os.environ.get("RUN_MAIN") != "true":
            return
        if os.environ.get("TTS_PREWARM", "1") not in ("1", "true", "True", "yes"):
            logger.info("TTS_PREWARM disabled - TTS will load lazily on first synthesize")
            return
        def _prewarm() -> None:
            try:
                from .core.llm import wait_for_llm_ready, warmup_llm
                from .core.tts import ensure_tts_warm

                if wait_for_llm_ready(timeout_s=15):
                    warmup_llm()

                ok = ensure_tts_warm()
                if ok:
                    logger.info("[MinaAI] Both models (TTS on GPU & LLM on CPU) are fully loaded, pre-warmed, and ready for input!")
                else:
                    logger.info("[TTS] Prewarm skipped or not ready; will load on first use")
            except Exception:
                logger.exception("Prewarm failed (non-fatal)")
        t = threading.Thread(target=_prewarm, name="tts-prewarm", daemon=True)
        t.start()
