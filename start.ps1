# News Radar RSS — Startup local (desenvolvimento)
# Em producao use: docker compose up -d
# Uso: .\start.ps1

$ROOT = $PSScriptRoot
$VENV = "$ROOT\.venv\Scripts"
$PYTHON = "$VENV\python.exe"

Write-Host "=== News Radar RSS — Startup (dev local) ===" -ForegroundColor Cyan

# 1. PostgreSQL via Docker
Write-Host "[1/5] PostgreSQL..." -ForegroundColor Yellow
$pgRunning = docker ps --filter "name=news_radar_rss-postgres-1" --filter "status=running" -q 2>$null
if (-not $pgRunning) {
    docker compose -f "$ROOT\docker-compose.dev.yml" up -d
    Start-Sleep 3
    Write-Host "      OK" -ForegroundColor Green
} else {
    Write-Host "      ja rodando" -ForegroundColor Green
}

# 2. API server (necessario para n8n chamar o CLI)
Write-Host "[2/5] API server (porta 8888)..." -ForegroundColor Yellow
$apiRunning = try { (Invoke-WebRequest "http://localhost:8888/health" -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200 } catch { $false }
if (-not $apiRunning) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ROOT'; & '$PYTHON' api_server.py" -WindowStyle Minimized
    Start-Sleep 3
    Write-Host "      OK" -ForegroundColor Green
} else {
    Write-Host "      ja rodando" -ForegroundColor Green
}

# 3. Streamlit dashboard
Write-Host "[3/5] Dashboard (porta 8501)..." -ForegroundColor Yellow
$dashRunning = try { (Invoke-WebRequest "http://localhost:8501" -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200 } catch { $false }
if (-not $dashRunning) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ROOT'; & '$VENV\streamlit.exe' run dashboard.py --server.port 8501" -WindowStyle Minimized
    Start-Sleep 3
    Write-Host "      OK" -ForegroundColor Green
} else {
    Write-Host "      ja rodando" -ForegroundColor Green
}

# 4. n8n
Write-Host "[4/5] n8n (porta 5678)..." -ForegroundColor Yellow
$n8nRunning = try { (Invoke-WebRequest "http://localhost:5678" -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200 } catch { $false }
if (-not $n8nRunning) {
    $env:NEWS_RADAR_API_URL = "http://localhost:8888"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", '$env:NEWS_RADAR_API_URL="http://localhost:8888"; npx n8n' -WindowStyle Minimized
    Write-Host "      iniciando (~20s)..." -ForegroundColor Green
} else {
    Write-Host "      ja rodando" -ForegroundColor Green
}

# 5. Telegram poller (aprovacoes locais — em producao o n8n cuida via webhook)
Write-Host "[5/5] Telegram poller (dev)..." -ForegroundColor Yellow
$pollerRunning = Get-Process -Name "python*" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*telegram_poller*" }
if (-not $pollerRunning) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ROOT'; & '$PYTHON' scripts\telegram_poller.py" -WindowStyle Minimized
    Write-Host "      OK" -ForegroundColor Green
} else {
    Write-Host "      ja rodando" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Pronto! ===" -ForegroundColor Cyan
Write-Host "  Dashboard:  http://localhost:8501" -ForegroundColor White
Write-Host "  n8n:        http://localhost:5678" -ForegroundColor White
Write-Host "  API:        http://localhost:8888/health" -ForegroundColor White
Write-Host ""
Write-Host "  Para producao: docker compose up -d" -ForegroundColor Gray
Write-Host ""
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
