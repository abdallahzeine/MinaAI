# TTS Refactor Plan — Remove the Old TTS Library and Make TTS Pluggable

Goal: strip the one specific TTS library out of the codebase entirely (its name must never appear again in backend or root files), and replace it with a clean, generic TTS abstraction so any engine / library that produces audio can be dropped in and swapped at will.

Decisions locked in:
- TTS module shape: pure abstraction, no default provider. `get_tts_service()` raises until a backend is registered.
- Reference voice assets (`Backend/assets/reference.wav`, `reference.txt`): kept.
- `.env`: touched, `SILMA_*` keys renamed to `TTS_*`.
- Frontend files: NOT touched (existing brand mentions in comments remain).

---

## Backend

### `Backend/main/core/tts.py` — full rewrite
Replace the entire file with a pluggable provider abstraction. Contents (narrative):
- Module docstring describing the abstraction and the consumer contract.
- `BaseTTSProvider` base class declaring the contract: `ensure_loaded(force=False)`, `is_available()`, `synthesize(gen_text, speed, progress_cb) -> (wav_bytes, sample_rate) | None`. Methods raise `NotImplementedError`.
- A provider registry: an internal dict, a `register_provider(name, cls)` function, and a `get_provider_class(name)` lookup. Names are normalized (stripped, lowercased).
- A module-level singleton holder plus lock.
- `get_tts_service()` factory: reads `TTS_BACKEND` env var, raises `RuntimeError` if unset or if the named backend is not registered, otherwise instantiates and caches the singleton.
- `ensure_tts_warm()`: calls `get_tts_service()`; if no backend is configured it catches the `RuntimeError`, logs, and returns `False` (so startup prewarm is a non-fatal no-op until an engine is plugged in). On a configured backend it calls `ensure_loaded()` and returns its result, swallowing non-fatal errors.
- No device/ref-audio/ffmpeg/progress-shim helpers — those belong to a concrete engine, added later.
- Zero mentions of the old library name.

### `Backend/main/apps.py` — de-brand + rename env
Rewrite the `ready()` prewarm block:
- `SILMA_PREWARM` env var → `TTS_PREWARM`.
- All log strings referencing the old brand → `TTS`.
- Thread name `silma-prewarm` → `tts-prewarm`.
- Still calls `ensure_tts_warm()` (now a no-op until a backend is registered).

### `Backend/main/core/llm.py` — rename env + de-brand logs
The `wait_for_llm_ready()` function logic is generic LLM-readiness polling and stays unchanged. Only identifiers/strings change:
- `SILMA_LLM_HEALTH_TIMEOUT` → `TTS_LLM_HEALTH_TIMEOUT`.
- `SILMA_LLM_HEALTH_INTERVAL` → `TTS_LLM_HEALTH_INTERVAL`.
- `SILMA_PREWARM_WAIT_FOR_LLM` → `TTS_PREWARM_WAIT_FOR_LLM`.
- All capitalized brand mentions in log strings → `TTS`.

### `Backend/requirements.txt` — drop dependency
- Remove the `silma-tts` line. Add no replacement (the abstraction ships with no engine).

### `Backend/assets/README.md` — rewrite generic
Replace the library-specific guide with a generic reference-voice doc:
- Title and intro framed around "cloning-based TTS engines" generically.
- Describe `reference.wav` / `reference.txt` as optional assets.
- Override env vars become `TTS_REF_AUDIO`, `TTS_REF_TEXT`, `TTS_REF_TEXT_FILE`.
- Note that non-cloning engines ignore these assets.
- Short "how to plug in an engine" note pointing to `BaseTTSProvider` + `register_provider` + `TTS_BACKEND`.

### `Backend/.env` — rename keys
- Every `SILMA_*` key → `TTS_*` (same suffix). No other keys changed.
- Do NOT add a `TTS_BACKEND` line (leave unset = no default).

### `Backend/main/core/websocket.py` — no change
The consumer contract (`get_tts_service().synthesize(text, progress_cb=...)`) is preserved, so the websocket needs no edit. When no backend is configured, `get_tts_service()` raises inside the existing try/except and the consumer falls back to transcript-only (existing behavior).

---

## Root scripts/docs

### `README.md`
- Replace all `SILMA_DEVICE` → `TTS_DEVICE`.
- Replace all capitalized brand mentions → `TTS`.

### `setup.ps1`
- Replace all `SILMA_DEVICE` → `TTS_DEVICE`.

### `setup.sh`
- Replace all `SILMA_DEVICE` → `TTS_DEVICE`.
- Replace capitalized brand mention in the "audio errors on mps" comment → `TTS`.

### `run.sh`
- Replace all `SILMA_DEVICE` → `TTS_DEVICE`.

### `run.ps1`
- Already clean. No change.

---

## Frontend
- No files touched. Existing brand mentions in `App.tsx` / `App.css` comments remain. The audio contract is unchanged so they keep working.

---

## How to plug in an engine later (generic, no code)
1. Add one provider file under `main/core/` (e.g. `tts_piper.py`).
2. Implement `BaseTTSProvider` (the three methods).
3. Call `register_provider("name", YourProvider)` at import time (e.g. wired from `apps.py`).
4. Set `TTS_BACKEND=name` in `.env`.
5. Restart Django. `get_tts_service()` now returns your engine; the websocket layer is untouched.

---

## Verification
1. Run a case-insensitive search for the old brand across the repo, excluding `.venv`, `__pycache__`, and `frontend` — expect zero matches.
2. Run the repo's Python typecheck (pyrefly) on the changed backend files.

## Out of scope / not done here
- No concrete TTS engine is added. The abstraction ships with no default provider, so voice replies will fall back to transcript-only until an engine is registered.
- No git commits.
- No frontend edits.
