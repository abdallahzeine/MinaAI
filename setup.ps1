# Mina AI - Windows zero-to-ready setup. Idempotent, re-runs safely, touches no git.
# Run: powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = "Stop"
function Info($m) { Write-Host "[setup] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[setup] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[setup] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "[setup] $m" -ForegroundColor Red; exit 1 }

# winget installs update PATH for new shells only; refresh it here
function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user    = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

Info "1/6 winget deps (idempotent)"
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { Fail "winget missing - install App Installer from the Microsoft Store." }
winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
try {
    winget install -e --id llamacpp.llamacpp --accept-package-agreements --accept-source-agreements
} catch {
    Warn "llama.cpp winget id failed - install manually from https://github.com/ggml-org/llama.cpp/releases"
}
# Django 6 needs Python >= 3.12; torch/torchao ship 3.12 wheels.
if (-not (Get-Command py -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
    try {
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    } catch {
        Warn "Python 3.12 winget id failed - install manually: winget install -e --id Python.Python.3.12"
    }
}
# Vite 8 needs Node 20.19+ or 22.12+.
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    try {
        winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    } catch {
        Warn "Node LTS winget id failed - install manually: winget install -e --id OpenJS.NodeJS.LTS"
    }
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
        Warn "could not locate ffmpeg.exe - add it to PATH manually"
    }
}

Info "2/6 Node check (Vite 8 needs Node 20.19+ or 22.12+)"
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Fail "node missing - open a new terminal so PATH refreshes, or install Node LTS" }
$nodeVer = (& node -v) -replace '^v', ''
$parts = $nodeVer.Split('.') | ForEach-Object { [int]$_ }
$nodeOk = ($parts[0] -gt 22) -or ($parts[0] -eq 22 -and $parts[1] -ge 12) -or ($parts[0] -eq 20 -and $parts[1] -ge 19)
if (-not $nodeOk) { Fail "Node too old: v$nodeVer - Vite 8 needs 20.19+ or 22.12+ (winget install -e --id OpenJS.NodeJS.LTS)" }

Info "3/6 Python 3.12 venv + requirements"
$py = Get-Command "py" -ErrorAction SilentlyContinue
if (-not (Test-Path .venv)) {
    $venvCreated = $false
    if ($py) {
        Info "Trying py -3.12 -m venv .venv ..."
        $oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        & $py.Source -3.12 -m venv .venv 2>&1 | Write-Host
        $pyExit = $LASTEXITCODE
        $ErrorActionPreference = $oldEAP
        if (($pyExit -eq 0) -and (Test-Path .\.venv\Scripts\python.exe)) { $venvCreated = $true; Ok "Created venv with py -3.12" } else { Info "py -3.12 failed (exit $pyExit), falling back to default python..." }
    }
    if (-not $venvCreated) {
        $pyCmd = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pyCmd) { Fail "No Python found - install Python 3.12: winget install -e --id Python.Python.3.12" }
        Info "Creating venv with: $($pyCmd.Source) ($(& $pyCmd.Source --version))"
        & $pyCmd.Source -m venv .venv
        if (-not (Test-Path .\.venv\Scripts\python.exe)) { Fail "venv creation failed with $($pyCmd.Source)" }
        Ok "Created venv with fallback python ($(& .\.venv\Scripts\python.exe --version))"
    }
}
if (-not (Test-Path .\.venv\Scripts\python.exe)) { Fail ".venv missing - venv creation failed (tried py -3.12 then fallback python)" }
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv pip install -r Backend\requirements.txt --python .\.venv\Scripts\python.exe
} else {
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -r Backend\requirements.txt
}

Info "4/6 Frontend deps from committed lockfile"
npm ci --prefix frontend

Info "5/6 Backend\.env (GPU TTS / CPU LLM defaults)"
if (-not (Test-Path Backend\.env)) {
    @'
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
CORS_ALLOWED_ORIGINS=http://localhost:5173,https://localhost:5173
TTS_DEVICE=cpu
TTS_GPU_LAYERS=0
LLAMA_CPP_BASE_URL=http://localhost:8080/v1
'@ | Set-Content -Path Backend\.env -Encoding utf8
    Ok "Created Backend\.env (TTS_DEVICE=cpu)"
}

Info "6/6 Django migrations (creates Backend\db.sqlite3)"
.\.venv\Scripts\python.exe Backend\manage.py migrate

Ok "Done - start with:  .\run.ps1  (open a new terminal if python/node/ffmpeg were just installed)"
