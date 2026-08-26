# Mina AI - Windows launcher: llama.cpp + Django + Vite. Mirrors run.sh.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "[run] No .venv found - run .\setup.ps1 first" -ForegroundColor Red
    exit 1
}

# Django never reads Backend/.env itself; load it into this process.
if (Test-Path "Backend\.env") {
    Get-Content "Backend\.env" | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and ($line -match "^([^=]+)=(.*)$")) {
            $key = $matches[1].Trim()
            $val = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}
if (-not $env:TTS_DEVICE) { $env:TTS_DEVICE = "cpu" }
if (-not $env:TTS_GPU_LAYERS) { $env:TTS_GPU_LAYERS = "0" }

$llamaBin = $null
$serveArgs = @()
if (Get-Command "llama-server" -ErrorAction SilentlyContinue) {
    $llamaBin = "llama-server"
} elseif (Get-Command "llama" -ErrorAction SilentlyContinue) {
    $llamaBin = "llama"
    $serveArgs += "serve"
} else {
    Write-Host "[run] warning: llama.cpp not found on PATH - install it or run setup.ps1" -ForegroundColor Yellow
}

$model = if ($env:LLAMA_MODEL) { $env:LLAMA_MODEL } else { "unsloth/gemma-4-E2B-it-qat-GGUF:UD-Q4_K_XL" }

if ($llamaBin) {
    $fullArgs = $serveArgs + @("-hf", $model, "--ctx-size", "32768", "--reasoning", "on", "--sleep-idle-seconds", "-1", "-ngl", "0")
    Write-Host "[run] $llamaBin $($serveArgs -join ' ') with $model (CPU mode -ngl 0)" -ForegroundColor Cyan
    Start-Process -FilePath $llamaBin -ArgumentList $fullArgs -WorkingDirectory $PSScriptRoot

    Write-Host "[run] Waiting for LLM health on http://127.0.0.1:8080/health ..." -ForegroundColor Cyan
    for ($i = 0; $i -lt 60; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8080/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
            if ($resp.StatusCode -eq 200) {
                Write-Host "[run] LLM healthy" -ForegroundColor Green
                try {
                    $warmupBody = '{"model":"llama-cpp-model","messages":[{"role":"user","content":"hi"}],"max_tokens":2}'
                    Invoke-RestMethod -Uri "http://127.0.0.1:8080/v1/chat/completions" -Method Post -Body $warmupBody -ContentType "application/json" -TimeoutSec 15 -ErrorAction SilentlyContinue | Out-Null
                    Write-Host "[run] LLM GPU pipeline warmed and ready for input" -ForegroundColor Green
                } catch {}
                break
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
}

Write-Host "[run] Starting Django on 127.0.0.1:8000..." -ForegroundColor Cyan
Start-Process -FilePath "$PSScriptRoot\.venv\Scripts\python.exe" -ArgumentList "Backend\manage.py","runserver","127.0.0.1:8000" -WorkingDirectory $PSScriptRoot

Write-Host "[run] Starting Vite on 127.0.0.1:5173..." -ForegroundColor Cyan
Start-Process -FilePath "npm.cmd" -ArgumentList "--prefix","frontend","run","dev","--","--host","127.0.0.1","--port","5173" -WorkingDirectory $PSScriptRoot

Write-Host "[run] LLM :8080 | Django :8000 | Vite :5173" -ForegroundColor Green
