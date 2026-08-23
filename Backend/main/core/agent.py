from collections.abc import AsyncIterator, Sequence
import asyncio
import json
import logging
from typing import override

from langchain_core.tools import tool

from asgiref.sync import sync_to_async
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, message_to_dict, messages_from_dict

from .config import Params, resolve_params
from .llm import get_llama_llm, transcode_webm_to_wav_b64

logger = logging.getLogger(__name__)

ContentPart = dict[str, str | dict[str, str]] | str


@tool
def save_contact_info(
    formal_name: str | None = None,
    position: str | None = None,
    company_name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
) -> str:
    """Save networking contact details incrementally. Call whenever the user shares any piece of contact info at any moment. Additive: each call adds/updates only provided fields, you can call multiple times across turns with partial data."""
    return "ok"


def _get_contact_tool() -> list:
    return [save_contact_info]


def _execute_contact_tool_calls(session_id: str, tool_calls: list[dict] | None) -> None:
    """Execute save_contact_info calls additively and silently. Never raises, never touches LLM context."""
    if not tool_calls:
        return
    try:
        from ..models import LEAD_FIELDS, save_lead_silently

        for tc in tool_calls:
            try:
                args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                if not isinstance(args, dict):
                    continue
                # Filter to allowed fields and drop empty
                filtered = {k: v for k, v in args.items() if k in LEAD_FIELDS and v not in (None, "", "null")}
                if not filtered:
                    continue
                save_lead_silently(session_id, filtered)
            except Exception:
                continue  # Silence contract: this function never raises.
    except Exception:
        return  # Silence contract: this function never raises.


async def _aexecute_contact_tool_calls(session_id: str, tool_calls: list[dict] | None) -> None:
    """Async version for streaming paths. Silent, never raises, never touches LLM context."""
    if not tool_calls:
        return
    try:
        from ..models import LEAD_FIELDS, save_lead_silently

        for tc in tool_calls:
            try:
                args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                if not isinstance(args, dict):
                    continue
                filtered = {k: v for k, v in args.items() if k in LEAD_FIELDS and v not in (None, "", "null")}
                if not filtered:
                    continue
                await sync_to_async(save_lead_silently)(session_id, filtered)
            except Exception:
                continue  # Silence contract: this function never raises; CancelledError is BaseException and propagates.
    except Exception:
        return  # Silence contract: this function never raises; CancelledError is BaseException and propagates.


class DjangoChatMessageHistory(BaseChatMessageHistory):
    messages: list[BaseMessage]

    def __init__(self, session_id: str, window_size: int | None = None, _skip_load: bool = False):
        self.session_id = session_id
        self.window_size = window_size
        self.messages = [] if _skip_load else self._load()

    def _load(self) -> list[BaseMessage]:
        from ..models import ChatMessage, Conversation
        try:
            conv: Conversation = Conversation.objects.get(session_id=self.session_id)
        except Conversation.DoesNotExist:
            return []
        qs = ChatMessage.objects.filter(conversation=conv).order_by("created_at")
        if self.window_size is not None:
            qs = ChatMessage.objects.filter(conversation=conv).order_by("-created_at")[: self.window_size]
            qs = list(reversed(list(qs)))
        else:
            qs = list(qs)
        result: list[BaseMessage] = []
        for row in qs:
            data = row.data
            if isinstance(data, dict) and "type" in data and "data" in data:
                try:
                    result.extend(messages_from_dict([data]))
                    continue
                except Exception:
                    logger.debug("Malformed stored message data; falling back to row.type", exc_info=True)
            mapping: dict[str, type[BaseMessage]] = {"human": HumanMessage, "ai": AIMessage, "system": SystemMessage}
            cls = mapping.get(row.type)
            result.append(cls(content=row.content) if cls else HumanMessage(content=row.content))
        return result

    @override
    async def aget_messages(self) -> list[BaseMessage]:
        return await sync_to_async(lambda: self._load())()

    @override
    def add_messages(self, messages: Sequence[BaseMessage]) -> None:
        from django.db import transaction
        from ..models import ChatMessage, Conversation
        if not messages:
            return
        conv, _ = Conversation.objects.get_or_create(session_id=self.session_id)
        objs: list[ChatMessage] = [
            ChatMessage(
                conversation=conv,
                type=message_to_dict(m).get("type", m.type),
                content=m.content if isinstance(m.content, str) else str(m.content),
                data=message_to_dict(m),
            )
            for m in messages
        ]
        with transaction.atomic():
            ChatMessage.objects.bulk_create(objs)

    @override
    async def aadd_messages(self, messages: Sequence[BaseMessage]) -> None:
        await sync_to_async(self.add_messages)(messages)

    @override
    def clear(self) -> None:
        from ..models import ChatMessage, Conversation
        try:
            conv = Conversation.objects.get(session_id=self.session_id)
        except Conversation.DoesNotExist:
            return
        ChatMessage.objects.filter(conversation=conv).delete()

    @override
    async def aclear(self) -> None:
        await sync_to_async(self.clear)()


def get_llm() -> BaseChatModel:
    p = resolve_params()
    return get_llama_llm(
        base_url=p.get("base_url") or p.get("llama_cpp_base_url") or "",
        model=p.get("model") or p.get("llama_cpp_model") or "",
        temperature=p["temperature"],
        api_key=p.get("api_key"),
        extra_params=p.get("extra_params"),
    )


def _get_llm_with_thinking(params: Params) -> BaseChatModel:
    """LLM bound with the runtime thinking level (reasoning + token budget)."""
    return get_llama_llm(
        base_url=params.get("base_url") or params.get("llama_cpp_base_url") or "",
        model=params.get("model") or params.get("llama_cpp_model") or "",
        temperature=params["temperature"],
        thinking_level=params["thinking_level"],
        thinking_budget=params["thinking_budget"],
        api_key=params.get("api_key"),
        extra_params=params.get("extra_params"),
    )


def _extract_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                parts.append(part["text"])
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts)
    if content is not None:
        return str(content)
    return ""


def _collect_tool_calls(chunk: object, tool_call_buffer: dict[int, dict], final_tool_calls: list[dict]) -> None:
    """Collect streamed tool chunks, direct tool_calls, and OpenAI additional_kwargs into buffers."""
    try:
        chunks = getattr(chunk, "tool_call_chunks", None) or []
        for tc in chunks:
            if isinstance(tc, dict):
                idx = tc.get("index", 0) or 0
                buf = tool_call_buffer.setdefault(idx, {"name": "", "args": "", "id": ""})
                if tc.get("name"):
                    buf["name"] = (buf["name"] or "") + tc["name"]
                if tc.get("args"):
                    buf["args"] = (buf["args"] or "") + tc["args"]
                if tc.get("id"):
                    buf["id"] = tc["id"]
            else:
                idx = getattr(tc, "index", 0) or 0
                buf = tool_call_buffer.setdefault(idx, {"name": "", "args": "", "id": ""})
                if getattr(tc, "name", None):
                    buf["name"] = (buf["name"] or "") + (tc.name or "")
                if getattr(tc, "args", None):
                    buf["args"] = (buf["args"] or "") + (tc.args or "")
                if getattr(tc, "id", None):
                    buf["id"] = tc.id or buf["id"]
        direct = getattr(chunk, "tool_calls", None) or []
        if direct:
            for dc in direct:
                if isinstance(dc, dict):
                    final_tool_calls.append(dc)
                else:
                    final_tool_calls.append({"name": getattr(dc, "name", ""), "args": getattr(dc, "args", {}) or {}, "id": getattr(dc, "id", "")})
        add_kwargs = getattr(chunk, "additional_kwargs", None) or {}
        if isinstance(add_kwargs, dict) and add_kwargs.get("tool_calls"):
            for dc in add_kwargs["tool_calls"]:
                if isinstance(dc, dict):
                    func = dc.get("function", {})
                    try:
                        args = func.get("arguments", "{}")
                        args_dict = json.loads(args) if isinstance(args, str) else args
                    except Exception:
                        logger.debug("Unparseable streamed tool arguments", exc_info=True)
                        args_dict = {}
                    final_tool_calls.append({"name": func.get("name", ""), "args": args_dict, "id": dc.get("id", "")})
    except Exception:
        logger.debug("Tool call collection failed for chunk", exc_info=True)


async def _save_turn(history: DjangoChatMessageHistory, human_content: str | list[ContentPart], accumulated: str) -> None:
    try:
        await history.aadd_messages([HumanMessage(content=human_content), AIMessage(content=accumulated)])  # type: ignore[arg-type]
    except Exception:
        logger.exception("Failed to persist turn")


def _flush_buffered_calls(tool_call_buffer: dict[int, dict], final_tool_calls: list[dict]) -> None:
    for buf in tool_call_buffer.values():
        if not buf.get("name") or buf["name"] != "save_contact_info":
            continue
        args_str = buf.get("args", "") or ""
        try:
            args = json.loads(args_str) if isinstance(args_str, str) and args_str.strip() else {}
            if not isinstance(args, dict):
                args = {}
        except Exception:
            logger.debug("Unparseable buffered tool arguments", exc_info=True)
            continue
        if args:
            final_tool_calls.append({"name": buf["name"], "args": args, "id": buf.get("id", "")})


async def _stream_with_tools(
    human_content: str | list[ContentPart], session_id: str, history_human_content: str
) -> AsyncIterator[str]:
    params = resolve_params()
    history = DjangoChatMessageHistory(session_id=session_id, window_size=params["chat_history_window"], _skip_load=True)
    hist_messages = await history.aget_messages()
    messages: list[BaseMessage] = []
    if params["system_prompt"]:
        messages.append(SystemMessage(content=params["system_prompt"]))
    messages.extend(hist_messages)
    messages.append(HumanMessage(content=human_content))  # type: ignore[arg-type]
    llm = _get_llm_with_thinking(params)
    llm_with_tools = llm.bind_tools(_get_contact_tool())
    accumulated = ""
    tool_call_buffer: dict[int, dict] = {}
    final_tool_calls: list[dict] = []
    try:
        async for chunk in llm_with_tools.astream(messages):
            text = _extract_text(getattr(chunk, "content", None))
            if text:
                accumulated += text
                yield text
            _collect_tool_calls(chunk, tool_call_buffer, final_tool_calls)
    except Exception:
        logger.exception("LLM stream failed mid-turn")
        # Re-raise so the caller (websocket) surfaces a client error frame.
        # _save_turn runs after this try, so nothing enters LLM history on failure.
        raise
    await _save_turn(history, history_human_content, accumulated)
    try:
        _flush_buffered_calls(tool_call_buffer, final_tool_calls)
        if final_tool_calls:
            try:
                _queued_calls = list(final_tool_calls)
                _sid_q = session_id
                task = asyncio.create_task(_aexecute_contact_tool_calls(_sid_q, _queued_calls))
                task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
            except Exception:
                logger.exception("Failed to queue tool calls")
    except Exception:
        logger.exception("Failed to flush tool calls")


async def stream_text(input_text: str, session_id: str) -> AsyncIterator[str]:
    async for delta in _stream_with_tools(input_text, session_id, input_text):
        yield delta


async def stream_audio(audio_b64: str, session_id: str) -> AsyncIterator[str]:
    wav_b64 = ""
    if audio_b64:
        try:
            wav_b64 = await sync_to_async(transcode_webm_to_wav_b64)(audio_b64, 16000)
        except Exception:
            logger.warning("Audio transcode failed; sending original audio to model", exc_info=True)
            wav_b64 = ""
        if not wav_b64:
            wav_b64 = audio_b64
    human_content: list[ContentPart] = [{"type": "text", "text": "Respond to this audio. Transcribe if needed and answer concisely:"}]
    if wav_b64:
        human_content.append({"type": "input_audio", "input_audio": {"data": wav_b64, "format": "wav"}})
    else:
        human_content.append({"type": "text", "text": "[empty audio]"})
    async for delta in _stream_with_tools(human_content, session_id, "[voice input]"):
        yield delta
