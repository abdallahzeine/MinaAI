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

# Python 3.12 is mandatory: Django 6 needs >= 3.12 and torch/torchao ship 3.12 wheels.
# python@3.12 is keg-only, so resolve it via brew --prefix.
PYTHON_BIN="$(brew --prefix python@3.12)/bin/python3.12"
[ -x "$PYTHON_BIN" ] || fail "python3.12 not found at $PYTHON_BIN"

info "2/6 Node check (Vite 8 needs Node 20.19+ or 22.12+)"
command -v node >/dev/null 2>&1 || fail "node missing - brew install node and re-run."
node -e 'const v=process.versions.node.split(".").map(Number);process.exit((v[0]>22||(v[0]===22&&v[1]>=12)||(v[0]===20&&v[1]>=19))?0:1)' \
  || fail "Node too old: $(node -v) - Vite 8 needs 20.19+ or 22.12+ (brew upgrade node)"

info "3/6 Python venv + requirements"
[ -x .venv/bin/python ] || "$PYTHON_BIN" -m venv .venv
if command -v uv >/dev/null 2>&1; then
  uv pip install -r Backend/requirements.txt --python .venv/bin/python
else
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r Backend/requirements.txt
fi

info "4/6 Frontend deps from committed lockfile"
npm ci --prefix frontend

info "5/6 Backend/.env (Apple Silicon defaults - sourced by run.sh)"
if [ ! -f Backend/.env ]; then
  cat > Backend/.env <<'EOF'
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
CORS_ALLOWED_ORIGINS=http://localhost:5173,https://localhost:5173
# Apple Silicon: try the GPU first; set to 'cpu' if TTS audio errors on mps
TTS_DEVICE=mps
LLAMA_CPP_BASE_URL=http://localhost:8080/v1
EOF
  ok "Created Backend/.env (TTS_DEVICE=mps)"
else
  ok "Backend/.env exists - left untouched"
fi

info "6/6 Django migrations (creates Backend/db.sqlite3)"
.venv/bin/python Backend/manage.py migrate

ok "Done - start everything with:  ./run.sh"
