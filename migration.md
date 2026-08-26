# Backend Sync & Migration Guide

This guide explains how to sync the latest **Backend** changes (CPU-only GGUF TTS, direct neural synthesis, and updated dependencies) into any existing branch or fork while **keeping your custom frontend/UI untouched**.

---

## 1. What Changed in the Backend

- **TTS Engine Switched to GGUF / `llama-cpp-python`**:
  - Uses `Audar-TTS-V1-Flash-Q4_K_M.gguf` for fast quantized local inference.
  - Generates 24 kHz high-fidelity audio using `NeuCodec`.
- **CPU-Only Configuration**:
  - TTS is configured to run fully on CPU threads (`TTS_DEVICE=cpu` and `TTS_GPU_LAYERS=0`).
  - No dedicated GPU is required for speech synthesis.
- **Removed Sentence Batching**:
  - Removed `text_batcher.py`. TTS now synthesizes text directly in a single pass without splitting artifacts.
- **Lightweight Dependencies (`Backend/requirements.txt`)**:
  - Replaced heavy `transformers` / `torchao` dependencies with `llama-cpp-python>=0.3.0`.

---

## 2. Step-by-Step Sync Instructions (For Teammates / Custom UI Branches)

Run the following commands inside your local project repository:

### Step 1: Add Upstream Remote & Fetch
```bash
git remote add upstream https://github.com/abdallahzeine/MinaAI.git
git fetch upstream
```

---

### Step 2: Sync Backend & Scripts Only (Preserves Frontend UI)
To selectively bring in only the backend updates without modifying any frontend code:

```bash
# 1. Switch to your main/working branch
git checkout main

# 2. Pull only the updated backend core, requirements, and runner scripts
git checkout upstream/main -- Backend/main/core/ Backend/requirements.txt run.ps1 setup.ps1 .gitignore

# 3. Commit the synced backend files
git commit -m "sync: update backend to CPU-only GGUF TTS from upstream"
```

> **Note**: Your `frontend/` directory (e.g. `App.tsx`, `AdminPage.tsx`, CSS, logos, assets) will remain completely untouched.

---

### Step 3: Install / Update Python Dependencies
Activate your virtual environment and install the updated requirements:

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\pip install -r Backend\requirements.txt
```

**macOS / Linux:**
```bash
source .venv/bin/activate
pip install -r Backend/requirements.txt
```

---

### Step 4: Update `Backend/.env`
Ensure your `Backend/.env` contains the CPU settings for TTS:

```env
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
CORS_ALLOWED_ORIGINS=http://localhost:5173,https://localhost:5173
TTS_DEVICE=cpu
TTS_GPU_LAYERS=0
LLAMA_CPP_BASE_URL=http://localhost:8080/v1
```

---

### Step 5: Run the Project

**Windows:**
```powershell
.\run.ps1
```

**macOS / Linux:**
```bash
./run.sh
```

- **Backend API & WebSocket**: `http://127.0.0.1:8000`
- **Frontend App**: `http://127.0.0.1:5173`
- **TTS Synthesis**: Local CPU via `llama_cpp` @ 24 kHz
