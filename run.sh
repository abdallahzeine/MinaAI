#!/usr/bin/env bash
# Mina AI - macOS launcher: llama.cpp (Metal) + Django + Vite. Mirrors run.ps1.
set -euo pipefail
cd "$(dirname "$0")"

[ -x .venv/bin/python ] || { echo "No .venv - run ./setup.sh first"; exit 1; }

# Django never reads Backend/.env itself; load it into this process.
if [ -f Backend/.env ]; then set -a; . ./Backend/.env; set +a; fi
export SILMA_DEVICE="${SILMA_DEVICE:-mps}"

# Homebrew ships llama-server; the unified 'llama' binary needs the 'serve' subcommand.
if command -v llama-server >/dev/null 2>&1; then LLAMA_BIN="llama-server"; SERVE_ARGS=()
elif command -v llama >/dev/null 2>&1; then LLAMA_BIN="llama"; SERVE_ARGS=(serve)
else echo "llama.cpp not found - run ./setup.sh"; exit 1; fi

MODEL="${LLAMA_MODEL:-unsloth/gemma-4-E4B-it-qat-GGUF:UD-Q4_K_XL}"
echo "[run] $LLAMA_BIN ${SERVE_ARGS[*]} with $MODEL"
"$LLAMA_BIN" "${SERVE_ARGS[@]}" -hf "$MODEL" --ctx-size 32768 --reasoning on --sleep-idle-seconds -1 -ngl 99 &
LLM_PID=$!

# Wait for LLM health so Django's TTS prewarm gate does not time out.
# First run downloads the model from HF (~3GB) - the loop is non-fatal.
for _ in $(seq 1 60); do
  curl -sf http://localhost:8080/health >/dev/null 2>&1 && { echo "[run] LLM healthy"; break; }
  sleep 2
done

.venv/bin/python Backend/manage.py runserver 127.0.0.1:8000 &
DJANGO_PID=$!
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 &
VITE_PID=$!

trap 'echo "[run] stopping..."; kill $LLM_PID $DJANGO_PID $VITE_PID 2>/dev/null; wait 2>/dev/null' INT TERM
echo "[run] LLM :8080 | Django :8000 | Vite :5173 - Ctrl+C stops all"
wait