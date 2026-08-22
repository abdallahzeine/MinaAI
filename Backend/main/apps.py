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
        if any(k in argv for k in ("migrate", "makemigrations", "collectstatic", "shell", "test")):
            return
        if os.environ.get("SILMA_PREWARM", "1") not in ("1", "true", "True", "yes"):
            logger.info("SILMA_PREWARM disabled - Silma will load lazily on first synthesize")
            return
        def _prewarm() -> None:
            try:
                from .core.tts import ensure_tts_warm
                ok = ensure_tts_warm()
                if ok:
                    logger.info("[TTS] Prewarm complete - Silma warm in VRAM on cuda:0 (after LLM health pass)")
                else:
                    logger.warning("[TTS] Prewarm not available after LLM ready (silma-tts missing or ref wav missing); will retry on first use")
            except Exception:
                logger.exception("Silma prewarm failed (non-fatal)")
        t = threading.Thread(target=_prewarm, name="silma-prewarm", daemon=True)
        t.start()
