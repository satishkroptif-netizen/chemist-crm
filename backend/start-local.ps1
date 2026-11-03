# Chemist CRM - Local Backend Starter
# Run: .\start-local.ps1

$ErrorActionPreference = "Stop"
Write-Host "=== Chemist CRM Backend Setup ===" -ForegroundColor Cyan

# 1. Create venv if missing
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

# 2. Activate venv
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
.\venv\Scripts\Activate.ps1

# 3. Install dependencies (prebuilt wheels only — no C++ compilation needed)
Write-Host "Installing Python packages..." -ForegroundColor Yellow
pip install --only-binary=:all: -r requirements.txt

# 4. Initialize database
Write-Host "Initializing database..." -ForegroundColor Yellow
python -c "import asyncio; from app.db.session import init_db; asyncio.run(init_db())" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "DB init attempted (may warn if tables already exist)" -ForegroundColor Gray
}

# 5. Start uvicorn
Write-Host "=== Starting Backend on http://localhost:8000 ===" -ForegroundColor Green
Write-Host "Swagger UI: http://localhost:8000/docs" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
