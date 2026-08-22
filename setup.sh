#!/usr/bin/env bash
# Mina AI - macOS zero-to-ready setup (Apple Silicon focus).
# Idempotent: safe to re-run. Does not touch git.
set -euo pipefail
cd "$(dirname "$0")"

info() { printf '\033[1;34m[setup]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[setup]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[setup]\033[0m %s\n' "$*" >&2; exit 1; }

info "1/6 Homebrew + system deps (brew install is idempotent)"
command -v brew >/dev/null 2>&1 || fail "Homebrew missing - install from https://brew.sh and re-run."
brew install python@3.12 ffmpeg llama.cpp node
# brew llama.cpp enables Metal by default on Apple Silicon - no extra flags needed.

# Python 3.12 is mandatory: requirements pin numpy<=1.26.4 (no 3.13+ wheels) and Django 6 needs >=3.12.
# python@3.12 is keg-only, so resolve it via brew --prefix.
PYTHON_BIN="$(brew --prefix python@3.12)/bin/python3.12"
[ -x "$PYTHON_BIN" ] || fail "python3.12 not found at $PYTHON_BIN"

info "2/6 Node check (Vite 8 needs >= 20.19)"
(( $(node -p 'process.versions.node.split(".")[0]') >= 20 )) || fail "Node too old: $(node -v)"

info "3/6 Python venv + requirements"
[ -x .venv/bin/python ] || "$PYTHON_BIN" -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r Backend/requirements.txt
# nemo_text_processing compiles pynini the first time - slow, not a hang.

info "4/6 Frontend deps from committed lockfile"
npm ci --prefix frontend

info "5/6 Backend/.env (Apple Silicon defaults - sourced by run.sh)"
if [ ! -f Backend/.env ]; then
  cat > Backend/.env <<'EOF'
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
CORS_ALLOWED_ORIGINS=http://localhost:5173,https://localhost:5173
# Apple Silicon: try the GPU first; set to 'cpu' if Silma audio errors on mps
SILMA_DEVICE=mps
LLAMA_CPP_BASE_URL=http://localhost:8080/v1
EOF
  ok "Created Backend/.env (SILMA_DEVICE=mps)"
else
  ok "Backend/.env exists - left untouched"
fi

info "6/6 Django migrations (creates Backend/db.sqlite3)"
.venv/bin/python Backend/manage.py migrate

ok "Done - start everything with:  ./run.sh"