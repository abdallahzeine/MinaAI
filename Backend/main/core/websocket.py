import asyncio
import base64
import json
import logging
import queue
from typing import Any, override

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.urls import re_path

from .agent import stream_audio, stream_text

logger = logging.getLogger(__name__)


@database_sync_to_async
def _get_or_create_conversation(session_id: str):
    from ..models import Conversation
    conv, _ = Conversation.objects.get_or_create(session_id=session_id)
    return conv


def _error_frame(message: str, detail: str | None = None) -> str:
    payload: dict[str, str] = {"type": "error", "message": message}
    if detail:
        payload["detail"] = detail
    return json.dumps(payload)


def _avatar_state_frame(phase: str) -> str:
    return json.dumps({"type": "avatar_state", "state": {"phase": phase, "emotion": "neutral"}})


class ChatConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._stream_task: asyncio.Task[None] | None = None
        self._disconnected = False
        self.session_id = "default"

    @override
    async def connect(self):
        self.session_id = self.scope["url_route"]["kwargs"].get("session_id") or "default"
        await self.accept()
        try:
            await _get_or_create_conversation(self.session_id)
        except Exception:
            logger.exception("failed to get or create conversation for session %s", self.session_id)
            # Fail silently: do not leak static error strings to client/LLM context

    @override
    async def disconnect(self, code: int):
        self._disconnected = True
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
            try:
                await self._stream_task
            except (asyncio.CancelledError, Exception):
                pass
            self._stream_task = None

    @override
    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        if text_data is None:
            return
        try:
            data: dict[str, object] = json.loads(text_data)
        except Exception:
            logger.exception("invalid json received for session %s", self.session_id)
            return
        t: object = data.get("type")
        if t == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))
            return
        if t in ("stop", "cancel"):
            try:
                from .tts import get_tts_service
                get_tts_service().interrupt()
            except Exception:
                pass
            if self._stream_task and not self._stream_task.done():
                logger.info("Force-terminating generation process for session %s on user stop request", self.session_id)
                self._stream_task.cancel()
                try:
                    await self._stream_task
                except (asyncio.CancelledError, Exception):
                    pass
                self._stream_task = None
            await self._safe_send(_avatar_state_frame("idle"))
            await self._safe_send(json.dumps({"type": "stopped"}))
            return
        if t in ("audio", "input"):
            if self._stream_task and not self._stream_task.done():
                # Surface the drop: otherwise the client's optimistic loading spinner never ends
                await self._safe_send(_error_frame("Previous request is still being processed — please try again"))
                return
            sid: str = str(data.get("session_id") or self.session_id)
            if t == "audio":
                audio_b64: str = str(data.get("audio") or "")
                self._stream_task = asyncio.ensure_future(self._handle_stream("audio", (audio_b64, sid)))
            else:
                text: str = str(data.get("text") or data.get("input") or "")
                self._stream_task = asyncio.ensure_future(self._handle_stream("text", (text, sid)))
            return
        logger.warning("unknown message type %s for session %s", t, self.session_id)
        return

    async def _safe_send(self, payload: str) -> bool:
        try:
            await self.send(text_data=payload)
        except Exception:
            logger.exception("failed to send websocket frame for session %s", self.session_id)
            return False
        return True

    async def _synthesize_reply(self, text: str) -> tuple[str, int] | None:
        # Progress frames flow from the synth worker thread into this queue
        # (thread-safe), and are drained on the event loop so tts_progress
        # messages always precede the final speaking_done/audio frames.
        progress_q: queue.Queue[str] = queue.Queue()

        def _progress_cb(done: int, total: int) -> None:
            progress_q.put(json.dumps({"type": "tts_progress", "done": done, "total": total}))

        async def _drain_progress() -> None:
            while not progress_q.empty():
                await self._safe_send(progress_q.get_nowait())

        try:
            from .tts import get_tts_service

            svc = get_tts_service()
            synth_fut = asyncio.ensure_future(
                sync_to_async(svc.synthesize, thread_sensitive=False)(text, progress_cb=_progress_cb)
            )
            while True:
                try:
                    await asyncio.wait_for(asyncio.shield(synth_fut), timeout=0.1)
                    break
                except asyncio.TimeoutError:
                    await _drain_progress()
            await _drain_progress()
            result = synth_fut.result()
        except Exception:
            logger.exception("TTS synthesis failed for session %s — fallback to transcript-only", self.session_id)
            return None
        if result is None:
            logger.warning("TTS synthesize returned None for session %s — fallback to transcript-only", self.session_id)
            return None
        wav_bytes, sr = result
        if not wav_bytes or len(wav_bytes) <= 44:  # valid WAV header + data required
            logger.warning("TTS returned empty wav for session %s", self.session_id)
            return None
        sample_rate = int(sr)
        logger.info("TTS success for session %s: %d bytes @ %d Hz for %d chars", self.session_id, len(wav_bytes), sample_rate, len(text))
        return base64.b64encode(wav_bytes).decode("ascii"), sample_rate

    async def _handle_stream(self, kind: str, args: tuple[str, str]) -> None:
        try:
            await self.send(text_data=_avatar_state_frame("thinking"))
            accumulated = ""
            # Transport errors isolated: stream call wrapped so failures don't leak to LLM context/history
            try:
                async for chunk in stream_audio(*args) if kind == "audio" else stream_text(*args):
                    if self._disconnected:
                        break
                    if not chunk:
                        continue
                    accumulated += chunk
                    await self.send(text_data=json.dumps({"type": "speaking", "text": chunk}))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("stream failed for session %s kind %s", self.session_id, kind)
                # Surface class-name-only detail to the client; never leak internals or
                # inject error text into LLM context/history.
                if not self._disconnected:
                    await self._safe_send(_error_frame("Failed to process your request — please try again", detail=type(exc).__name__))
                    await self._safe_send(_avatar_state_frame("idle"))
                return
            if self._disconnected:
                return
            if not accumulated.strip():
                # Empty reply — nothing to synthesize, return to idle
                await self._safe_send(_avatar_state_frame("idle"))
                await self.send(text_data=json.dumps({"type": "speaking_done", "text": accumulated}))
                return

            synthesized = await self._synthesize_reply(accumulated)

            if self._disconnected:
                return

            if synthesized is not None:
                wav_b64, sample_rate = synthesized
                # Forward as new audio event together with transcript.
                # Frontend will play via <audio>, set avatar to speaking while playing and idle when ends,
                # preserving lip-sync (SpeakingEngine). Mute is simple pause on audio element.
                # Send speaking_done first for transcript persistence, then avatar speaking, then audio.
                await self._safe_send(json.dumps({"type": "speaking_done", "text": accumulated}))
                await self._safe_send(_avatar_state_frame("speaking"))
                audio_sent = await self._safe_send(
                    json.dumps(
                        {
                            "type": "audio",
                            "audio": wav_b64,
                            "text": accumulated,
                            "transcript": accumulated,
                            "sample_rate": sample_rate,
                            "format": "wav",
                        }
                    )
                )
                if not audio_sent and not self._disconnected:
                    # Client already saw speaking_done + avatar speaking; without this
                    # fallback it would wait for the audio frame forever.
                    await self._safe_send(_error_frame("Voice delivery failed — reply shown as text only"))
                    await self._safe_send(_avatar_state_frame("idle"))
                # Do NOT send idle on success — frontend returns to idle when audio ends (or on pause/mute)
            else:
                # Failure path: deliver transcript, surface TTS failure, return avatar to idle
                await self._safe_send(_error_frame("Voice synthesis failed — reply shown as text only"))
                await self._safe_send(_avatar_state_frame("idle"))
                await self.send(text_data=json.dumps({"type": "speaking_done", "text": accumulated}))
        except asyncio.CancelledError:
            logger.info("Stream cancelled/discarded for session %s", self.session_id)
            return
        except Exception as exc:
            logger.exception("WebSocket _handle_stream failed for session %s", self.session_id)
            # Generic error surfacing without leaking internals to LLM
            if not self._disconnected:
                await self._safe_send(_error_frame("Failed to process your request — please try again", detail=type(exc).__name__))
                await self._safe_send(_avatar_state_frame("idle"))
        finally:
            self._stream_task = None


websocket_urlpatterns: list[Any] = [
    # re_path is typed for HTTP views by django-stubs; Channels uses it for
    # ASGI consumers per the official docs, so the overload mismatch is expected.
    re_path(r"^ws/chat/(?P<session_id>[\w:-]+)/$", ChatConsumer.as_asgi()),  # type: ignore[arg-type]
]
