# Mina AI - Windows zero-to-ready setup. Idempotent, re-runs safely, touches no git.
# Run: powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = "Stop"
function Info($m) { Write-Host "[setup] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[setup] $m" -ForegroundColor Green }
function Fail($m) { Write-Host "[setup] $m" -ForegroundColor Red; exit 1 }

# winget installs update PATH for new shells only; refresh it here
function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user    = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

Info "1/5 winget deps (idempotent)"
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { Fail "winget missing - install App Installer from the Microsoft Store." }
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
try {
    winget install -e --id llamacpp.llamacpp --accept-package-agreements --accept-source-agreements
} catch {
    Write-Host "[setup] warning: llama.cpp winget id failed - install manually from https://github.com/ggml-org/llama.cpp/releases" -ForegroundColor Yellow
}
Refresh-Path

# Gyan.FFmpeg does not add itself to PATH - fix that here
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    $found = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        $bin = Split-Path $found.FullName
        [Environment]::SetEnvironmentVariable("Path", "$env:Path;$bin", "User")
        $env:Path += ";$bin"
        Ok "Added ffmpeg to PATH: $bin"
    } else {
        Write-Host "[setup] warning: could not locate ffmpeg.exe - add it to PATH manually" -ForegroundColor Yellow
    }
}

Info "2/5 Python 3.12 venv + requirements"
$py = Get-Command "py" -ErrorAction SilentlyContinue
if (-not (Test-Path .venv)) {
    if ($py) { & $py.Source -3.12 -m venv .venv } else { python -m venv .venv }
}
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r Backend\requirements.txt

Info "3/5 Frontend deps from committed lockfile"
npm ci --prefix frontend

Info "4/5 Backend\.env (Windows GPU defaults)"
if (-not (Test-Path Backend\.env)) {
    @'
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
CORS_ALLOWED_ORIGINS=http://localhost:5173,https://localhost:5173
SILMA_DEVICE=cuda:0
LLAMA_CPP_BASE_URL=http://localhost:8080/v1
'@ | Set-Content -Path Backend\.env -Encoding utf8
    Ok "Created Backend\.env (SILMA_DEVICE=cuda:0)"
}

Info "5/5 Django migrations (creates Backend\db.sqlite3)"
.\.venv\Scripts\python.exe Backend\manage.py migrate

Ok "Done - start with:  .\run.ps1  (open a new terminal if python/node/ffmpeg were just installed)"