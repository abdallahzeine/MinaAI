# MinaAI — Quick Start (using setup/run scripts)

Two script pairs do everything. Windows: `setup.ps1` + `run.ps1`. macOS: `setup.sh` + `run.sh`.

## Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

What it does: installs Python 3.12 / Node LTS / ffmpeg / llama.cpp via winget, fixes ffmpeg on PATH, creates `.venv`, installs Python + frontend deps, writes `Backend\.env` (GPU defaults, `TTS_DEVICE=cuda:0`), runs Django migrations.

```powershell
.\run.ps1
```

What it does: starts llama.cpp (Gemma 4B GGUF from HF), Django on `:8000`, Vite on `:5173`.

## macOS (Apple Silicon)

```bash
./setup.sh
```

What it does: installs `python@3.12 ffmpeg llama.cpp node` via Homebrew (llama.cpp with Metal), creates `.venv`, installs Python + frontend deps, writes `Backend/.env` (`TTS_DEVICE=mps`), runs Django migrations. Re-running is safe (idempotent).

```bash
./run.sh
```

What it does: loads `Backend/.env` into the process, starts llama.cpp (`llama-server` or `llama serve`), waits for LLM health on `:8080`, then starts Django on `:8000` and Vite on `:5173`. **Ctrl+C stops all three.**

## Notes + config

- **First run downloads model** (Gemma 2B GGUF) from Hugging Face via `-hf`. The Windows script doesn't wait for LLM health, so TTS prewarm may time out on first run — just start again after the download finishes (TTS loads lazily otherwise).
- **Change model**: set `LLAMA_MODEL` before running (both scripts use `unsloth/gemma-4-E2B-it-qat-GGUF:UD-Q4_K_XL` by default). In PowerShell: `$env:LLAMA_MODEL="org/repo:quant"` then `.\run.ps1`.
- **`Backend/.env`** (created by setup, never overwritten): `DJANGO_DEBUG`, `CORS_ALLOWED_ORIGINS`, `TTS_DEVICE`, `LLAMA_CPP_BASE_URL`. Edit it anytime:
  - Windows: `TTS_DEVICE=cuda:0`
  - macOS: `TTS_DEVICE=mps` (set `cpu` if TTS audio errors on mps)
- **App**: open `http://localhost:5173` (proxies `/api` and `/ws` to Django automatically).
- **Windows first-time terminal**: if setup just installed Python/Node/ffmpeg, open a new terminal before `.\run.ps1`.
- **Windows stop**: `.\run.ps1` launches detached process windows — close those windows or `Stop-Process` by name.

## Ports

| Service | Port |
|---|---|
| llama.cpp (LLM, health at `/health`) | 8080 |
| Django (API + WebSocket) | 8000 |
| Vite frontend | 5173 |