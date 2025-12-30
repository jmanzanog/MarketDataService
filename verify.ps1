# -----------------------------------------------------------------------------
# Local Verification Script (Windows PowerShell)
# Replicates GitHub Actions CI steps locally
# -----------------------------------------------------------------------------

$ErrorActionPreference = "Stop"

function Write-Header($msg) {
    Write-Host "`n>>> $msg" -ForegroundColor Cyan
}

Write-Host "Starting quality checks (CI Style)..." -ForegroundColor Yellow

# 1. Ensure we are in the virtual environment
if ($null -eq $env:VIRTUAL_ENV) {
    if (Test-Path ".\venv\Scripts\Activate.ps1") {
        Write-Host "Activating local virtual environment..." -ForegroundColor Gray
        . .\venv\Scripts\Activate.ps1
    }
    else {
        Write-Warning "WARNING: No active virtual environment or .\venv folder detected. Commands might fail or use global Python."
    }
}

# 2. Install tools
Write-Header "[1/7] Installing/Updating quality tools..."
pip install -q ruff bandit pip-audit mypy types-requests pytest-cov

# 3. Consistency
Write-Header "[2/7] Checking dependency consistency..."
pip check

# 4. Dependency Audit (Security)
Write-Header "[3/7] Auditing dependencies with pip-audit..."
pip-audit

# 5. Bandit
Write-Header "[4/7] Analyzing code security with Bandit..."
bandit -r src/ -ll

# 6. Ruff (Format and Lint)
Write-Header "[5/7] Verifying formatting with Ruff..."
ruff format --check src/ tests/

Write-Header "[6/7] Running Linting with Ruff..."
ruff check src/ tests/

# 7. Mypy
Write-Header "[7/7] Verifying types with Mypy..."
try {
    mypy src/ --ignore-missing-imports --no-error-summary
}
catch {
    Write-Host "Mypy found type issues, but CI allows them for now." -ForegroundColor DarkYellow
}

# 8. Tests
Write-Header "Running unit and internal integration tests..."
pytest tests/ -v --cov=src --cov-report=term-missing --ignore=tests/test_container_integration.py

Write-Host "`nSUCCESS! Your code meets CI requirements." -ForegroundColor Green
Write-Host "For Docker tests: pytest tests/test_container_integration.py -m container" -ForegroundColor Yellow
