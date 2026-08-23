import time
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .core.agent import DjangoChatMessageHistory
from .core.config import (
    PRESET_CONFIGS,
    get_dev_settings,
    get_runtime_settings,
    resolve_params,
    set_dev_settings,
    set_runtime_settings,
)
from .serializers import (
    DevSettingsSerializer,
    ModelInfoSerializer,
    RuntimeSettingsSerializer,
    TestConnectionSerializer,
)


def _settings_payload() -> dict:
    s = get_runtime_settings()
    level: str = s["thinking_level"]
    return {
        "thinking_level": level,
    }


class HealthCheckView(APIView):
    def get(self, request: Request) -> Response:
        return Response({"status": "ok", "app": "main"})


class RuntimeSettingsView(APIView):
    def get(self, request: Request) -> Response:
        return Response(_settings_payload())

    def put(self, request: Request) -> Response:
        ser = RuntimeSettingsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        set_runtime_settings(ser.validated_data)
        return Response(_settings_payload())


class DevSettingsView(APIView):
    def get(self, request: Request) -> Response:
        from .core.voices import VOICE_REGISTRY
        settings = get_dev_settings()
        voices_list = [
            {"id": k, "desc": v.get("desc", k), "category": v.get("category", "General")}
            for k, v in VOICE_REGISTRY.items()
        ]
        return Response({
            "settings": settings,
            "presets": PRESET_CONFIGS,
            "voices": voices_list,
        })

    def put(self, request: Request) -> Response:
        from .core.voices import VOICE_REGISTRY
        ser = DevSettingsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        set_dev_settings(ser.validated_data)
        updated = get_dev_settings()
        voices_list = [
            {"id": k, "desc": v.get("desc", k), "category": v.get("category", "General")}
            for k, v in VOICE_REGISTRY.items()
        ]
        return Response({
            "status": "ok",
            "settings": updated,
            "presets": PRESET_CONFIGS,
            "voices": voices_list,
        })


class DevTestConnectionView(APIView):
    def post(self, request: Request) -> Response:
        ser = TestConnectionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        base_url = ser.validated_data["base_url"].rstrip("/")
        model = ser.validated_data["model"]
        api_key = ser.validated_data.get("api_key", "").strip()
        prompt = ser.validated_data.get("prompt", "Hello! Reply in one short sentence.")

        import json
        import urllib.error
        import urllib.request

        url = f"{base_url}/chat/completions"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        body_dict = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 50,
        }
        extra_str = ser.validated_data.get("extra_params", "").strip()
        if extra_str:
            try:
                extra_json = json.loads(extra_str)
                if isinstance(extra_json, dict):
                    body_dict.update(extra_json)
            except Exception:
                pass

        payload = json.dumps(body_dict).encode("utf-8")

        start = time.time()
        try:
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                status_code = getattr(resp, "status", 200)
                body = resp.read().decode("utf-8", errors="ignore")
                latency_ms = int((time.time() - start) * 1000)
                try:
                    data = json.loads(body)
                    reply = (
                        data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        or body[:200]
                    )
                except Exception:
                    reply = body[:200]

                return Response({
                    "status": "ok",
                    "latency_ms": latency_ms,
                    "model": model,
                    "reply": reply,
                    "status_code": status_code,
                })
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")[:400] if hasattr(e, "read") else str(e)
            return Response(
                {"status": "error", "message": f"HTTP {e.code}: {err_body}", "status_code": e.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
class DevModelInfoView(APIView):
    def post(self, request: Request) -> Response:
        ser = ModelInfoSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        base_url = ser.validated_data["base_url"].rstrip("/")
        target_model = ser.validated_data.get("model", "").strip()
        api_key = ser.validated_data.get("api_key", "").strip()

        import json
        import urllib.error
        import urllib.request

        url = f"{base_url}/models"
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                raw = json.loads(body)

                models_list = raw.get("data", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
                available_ids = [m.get("id") for m in models_list if isinstance(m, dict) and m.get("id")]

                matched_item = None
                target_clean = target_model.strip()
                if target_clean:
                    # 1. Exact match
                    for m in models_list:
                        if isinstance(m, dict) and m.get("id") == target_clean:
                            matched_item = m
                            break
                    # 2. Case-insensitive match
                    if not matched_item:
                        for m in models_list:
                            if isinstance(m, dict) and str(m.get("id", "")).lower() == target_clean.lower():
                                matched_item = m
                                break
                    # 3. Suffix / slug match (e.g. user entered "gemini-3.7-flash" for "google/gemini-3.7-flash")
                    if not matched_item:
                        for m in models_list:
                            if isinstance(m, dict):
                                mid = str(m.get("id", "")).lower()
                                cslug = str(m.get("canonical_slug", "")).lower()
                                if mid.endswith(f"/{target_clean.lower()}") or cslug == target_clean.lower():
                                    matched_item = m
                                    break

                # 4. If still not matched, attempt direct single model lookup
                if not matched_item and target_clean:
                    try:
                        single_url = f"{base_url}/models/{target_clean}"
                        single_req = urllib.request.Request(single_url, headers=headers)
                        with urllib.request.urlopen(single_req, timeout=8) as single_resp:
                            single_body = single_resp.read().decode("utf-8", errors="ignore")
                            single_data = json.loads(single_body)
                            if isinstance(single_data, dict):
                                matched_item = single_data.get("data") if "data" in single_data and isinstance(single_data["data"], dict) else single_data
                    except Exception:
                        pass

                supported_params = []
                context_length = None
                architecture = {}
                default_params = {}
                reasoning_info = {}

                if matched_item and isinstance(matched_item, dict):
                    supported_params = matched_item.get("supported_parameters", []) or []
                    raw_defaults = matched_item.get("default_parameters", {}) or {}
                    default_params = {k: v for k, v in raw_defaults.items() if v is not None} if isinstance(raw_defaults, dict) else {}
                    reasoning_info = matched_item.get("reasoning", {}) or {}
                    context_length = matched_item.get("context_length") or matched_item.get("top_provider", {}).get("context_length")
                    architecture = matched_item.get("architecture", {}) or {}

                input_modalities = []
                output_modalities = []
                if isinstance(architecture, dict) and architecture:
                    input_modalities = architecture.get("input_modalities") or []
                    output_modalities = architecture.get("output_modalities") or []
                    if not input_modalities and "modality" in architecture:
                        mod_str = str(architecture["modality"])
                        if "->" in mod_str:
                            parts = mod_str.split("->", 1)
                            input_modalities = [p.strip() for p in parts[0].split("+") if p.strip()]
                            output_modalities = [p.strip() for p in parts[1].split("+") if p.strip()]

                accepts_audio = any("audio" in str(m).lower() for m in input_modalities)

                # Rely solely on what the API response metadata indicates (no regex or name guessing)
                supports_thinking = bool(
                    "reasoning" in supported_params
                    or "thinking" in supported_params
                    or (isinstance(matched_item, dict) and bool(matched_item.get("reasoning")))
                )

                not_matched_msg = (
                    f"Model '{target_clean}' is not listed in this endpoint's /models catalog (Endpoint did not return capability metadata)."
                    if target_clean and not matched_item
                    else None
                )

                return Response({
                    "status": "ok",
                    "target_model": target_model,
                    "matched": matched_item is not None,
                    "supports_thinking": supports_thinking,
                    "supported_parameters": supported_params,
                    "default_parameters": default_params,
                    "reasoning_info": reasoning_info,
                    "context_length": context_length,
                    "architecture": architecture,
                    "input_modalities": input_modalities,
                    "output_modalities": output_modalities,
                    "accepts_audio": accepts_audio,
                    "not_matched_message": not_matched_msg,
                    "raw_metadata": matched_item or {},
                })
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")[:400] if hasattr(e, "read") else str(e)
            return Response(
                {"status": "error", "message": f"HTTP {e.code}: {err_body}", "status_code": e.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


def _extract_voices_from_api(base_url: str, api_key: str, model: str = "") -> tuple[list[dict], Optional[str], Optional[str]]:
    """Query endpoint API and/or probe /audio/speech to pull supported voices."""
    import json
    import re
    import urllib.error
    import urllib.request

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Mina AI",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    extracted_voices: list[dict] = []
    detected_format: Optional[str] = "24 kHz WAV"
    detected_provider: Optional[str] = None

    model_clean = (model or "").strip().lower()

    # 1. Try standard voice listing endpoints
    candidate_paths = ["/audio/voices", "/voices", "/v1/audio/voices", "/v1/voices"]
    for path in candidate_paths:
        try:
            url = f"{base_url}{path}"
            req = urllib.request.Request(url, headers={"Accept": "application/json", **({"Authorization": f"Bearer {api_key}"} if api_key else {})})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("voices") or data.get("data") or (data if isinstance(data, list) else [])
                if isinstance(items, list) and items:
                    for it in items:
                        if isinstance(it, dict):
                            vid = it.get("id") or it.get("voice_id") or it.get("name")
                            name = it.get("name") or it.get("description") or vid
                            if vid:
                                extracted_voices.append({"id": str(vid), "name": str(name)})
                        elif isinstance(it, str):
                            extracted_voices.append({"id": it, "name": it})
                    if extracted_voices:
                        break
        except Exception:
            continue

    # 2. Probe /audio/speech if voices are still empty and model is given
    if not extracted_voices and model_clean:
        try:
            speech_url = f"{base_url}/audio/speech"
            probe_payload = json.dumps({"model": model, "input": "test", "voice": "__probe_voices__"}).encode("utf-8")
            req = urllib.request.Request(speech_url, data=probe_payload, headers=headers)
            with urllib.request.urlopen(req, timeout=6):
                pass
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            match = re.search(r"Supported voices:\s*([^.\"]+)", err_body, re.IGNORECASE)
            if match:
                raw_list = [v.strip() for v in match.group(1).split(",") if v.strip()]
                for vid in raw_list:
                    # Clean up names for UI (e.g. flux-alexis-en -> Alexis (EN))
                    display_name = vid
                    if vid.startswith("flux-") and vid.endswith("-en"):
                        core = vid[5:-3].capitalize()
                        display_name = f"{core} (EN)"
                    extracted_voices.append({"id": vid, "name": display_name})
        except Exception:
            pass

    # 3. Known catalogues fallback for Deepgram Flux & OpenAI
    if not extracted_voices:
        if "flux" in model_clean or "deepgram" in model_clean:
            detected_provider = "Deepgram Flux (OpenRouter)"
            flux_voice_ids = [
                "flux-alexis-en", "flux-bree-en", "flux-brittany-en", "flux-brooke-en", "flux-bruce-en",
                "flux-cliff-en", "flux-cole-en", "flux-colin-en", "flux-conor-en", "flux-donovan-en",
                "flux-drew-en", "flux-elise-en", "flux-gemma-en", "flux-haley-en", "flux-hannah-en",
                "flux-heather-en", "flux-jack-en", "flux-kai-en", "flux-kelsey-en", "flux-kit-en",
                "flux-maeve-en", "flux-marcelo-en", "flux-marcus-en", "flux-meena-en", "flux-meghan-en",
                "flux-miles-en", "flux-naveen-en", "flux-paige-en", "flux-priya-en", "flux-rufus-en",
                "flux-sean-en", "flux-sharon-en", "flux-sienna-en", "flux-tanner-en", "flux-wade-en",
                "flux-wes-en",
            ]
            for vid in flux_voice_ids:
                core = vid[5:-3].capitalize()
                extracted_voices.append({"id": vid, "name": f"{core} (EN)"})
        elif "tts-1" in model_clean or "openai" in model_clean:
            detected_provider = "OpenAI Speech API"
            openai_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer", "sage", "coral", "ash"]
            for vid in openai_voices:
                extracted_voices.append({"id": vid, "name": vid.capitalize()})

    if "flux" in model_clean:
        detected_provider = "Deepgram Flux"
    elif "openrouter" in base_url.lower():
        detected_provider = "OpenRouter /audio/speech"
    elif not detected_provider:
        detected_provider = "OpenAI-Compatible Audio API"

    return extracted_voices, detected_provider, detected_format


class DevTTSModelInfoView(APIView):
    def post(self, request: Request) -> Response:
        from .serializers import TTSModelInfoSerializer

        ser = TTSModelInfoSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        base_url = ser.validated_data["base_url"].rstrip("/")
        target_model = ser.validated_data.get("model", "").strip()
        api_key = ser.validated_data.get("api_key", "").strip()

        voices, provider_name, detected_format = _extract_voices_from_api(base_url, api_key, target_model)

        default_voice = voices[0]["id"] if voices else ("flux-alexis-en" if "flux" in target_model.lower() else "alloy")

        return Response({
            "status": "ok",
            "target_model": target_model,
            "matched": bool(voices or target_model),
            "provider_name": provider_name,
            "format": detected_format or "24 kHz WAV",
            "sample_rate": 24000,
            "default_voice": default_voice,
            "voices": voices,
            "supported_voices_count": len(voices),
            "message": f"Successfully pulled {len(voices)} voices from API." if voices else "No voice list returned by endpoint. Enter voice ID manually.",
        })


class DevTestTTSView(APIView):
    def post(self, request: Request) -> Response:
        import base64
        import time
        from .serializers import TestTTSSerializer
        from .core.tts import AudarTTSProvider, OpenAITTSProvider, get_tts_service

        ser = TestTTSSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        text = ser.validated_data.get("text", "مرحبا بكم، هذا اختبار لتوليد الصوت بالذكاء الاصطناعي.")
        speed = float(ser.validated_data.get("speed", 1.0))
        provider = ser.validated_data.get("provider", "audar").strip().lower()
        model = ser.validated_data.get("model", "").strip()
        voice = ser.validated_data.get("voice", "").strip()
        extra_params = ser.validated_data.get("extra_params", "").strip()
        base_url = ser.validated_data.get("base_url", "").strip()
        api_key = ser.validated_data.get("api_key", "").strip()

        start = time.time()
        try:
            if provider in ("openai", "openai_compatible") or (provider != "audar" and (base_url or model)):
                svc = OpenAITTSProvider()
                res = svc.synthesize(
                    text,
                    speed=speed,
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    voice=voice,
                    extra_params=extra_params,
                )
            else:
                svc = get_tts_service()
                res = svc.synthesize(text, speed=speed)

            if res is None:
                return Response(
                    {"status": "error", "message": "TTS synthesis returned no audio."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            wav_bytes, sr = res
            b64_audio = base64.b64encode(wav_bytes).decode("utf-8")
            latency_ms = int((time.time() - start) * 1000)
            return Response({
                "status": "ok",
                "audio_b64": f"data:audio/wav;base64,{b64_audio}",
                "sample_rate": sr,
                "latency_ms": latency_ms,
            })
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class DevTTSVoicesView(APIView):
    def post(self, request: Request) -> Response:
        from .serializers import FetchTTSVoicesSerializer

        ser = FetchTTSVoicesSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        base_url = ser.validated_data["base_url"].rstrip("/")
        model = ser.validated_data.get("model", "").strip()
        api_key = ser.validated_data.get("api_key", "").strip()

        voices, _, _ = _extract_voices_from_api(base_url, api_key, model)

        return Response({
            "status": "ok",
            "voices": voices,
            "count": len(voices),
            "message": f"Loaded {len(voices)} voices from API." if voices else "Endpoint did not return a voices catalog. Enter any voice name directly.",
        })


class AdminAnalyticsView(APIView):
    def get(self, request: Request) -> Response:
        from .core.admin_analytics import build_admin_analytics

        payload = build_admin_analytics()
        return Response(payload)


class ClearHistoryView(APIView):
    def delete(self, request: Request, session_id: str) -> Response:
        params = resolve_params()
        h: DjangoChatMessageHistory = DjangoChatMessageHistory(
            session_id=session_id, window_size=params["chat_history_window"]
        )
        h.clear()
        return Response({"status": "cleared"})
