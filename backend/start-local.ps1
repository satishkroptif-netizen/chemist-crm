# Chemist CRM - Local Backend Starter
# Run: .\start-local.ps1

$ErrorActionPreference = "Stop"
Write-Host "=== Chemist CRM Backend Setup ===" -ForegroundColor Cyan

# 1. Detect Python (prefer 3.11 for package compatibility)
$pythonCmd = "python"
$pythonArgs = @()
if (Get-Command "py" -ErrorAction SilentlyContinue) {
    $py311 = py -3.11 -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $py311) {
        $pythonCmd = "py"
        $pythonArgs = @("-3.11")
        Write-Host "Using Python 3.11 via py launcher" -ForegroundColor Green
    } else {
        $py311 = Get-Command "python3.11" -ErrorAction SilentlyContinue
        if ($py311) {
            $pythonCmd = "python3.11"
            $pythonArgs = @()
            Write-Host "Using Python 3.11" -ForegroundColor Green
        }
    }
}
if ($pythonCmd -eq "python" -and $pythonArgs.Count -eq 0) {
    Write-Host "Python 3.11 not found, using default python" -ForegroundColor Yellow
}

# 2. Create venv if missing
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    & $pythonCmd $pythonArgs -m venv venv
}

# 3. Activate venv
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
.\venv\Scripts\Activate.ps1

# 4. Install dependencies (prebuilt wheels only — no C++ compilation needed)
Write-Host "Installing Python packages..." -ForegroundColor Yellow
pip install --only-binary=:all: -r requirements.txt

# 5. Initialize database
Write-Host "Initializing database..." -ForegroundColor Yellow
& $pythonCmd $pythonArgs -c "import asyncio; from app.db.session import init_db; asyncio.run(init_db())" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "DB init attempted (may warn if tables already exist)" -ForegroundColor Gray
}

# 6. Start uvicorn
Write-Host "=== Starting Backend on http://localhost:8000 ===" -ForegroundColor Green
Write-Host "Swagger UI: http://localhost:8000/docs" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
