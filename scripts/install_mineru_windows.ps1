# MinerU Windows Installation Script
# Run: powershell -ExecutionPolicy Bypass -File scripts/install_mineru_windows.ps1

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MinerU Windows Installation Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Ensure pip is up to date
Write-Host "[1/4] Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip
Write-Host "pip upgraded successfully." -ForegroundColor Green
Write-Host ""

# Step 2: Install uv (fast Python package installer)
Write-Host "[2/4] Installing uv..." -ForegroundColor Yellow
python -m pip install uv
Write-Host "uv installed successfully." -ForegroundColor Green
Write-Host ""

# Step 3: Install MinerU with all dependencies
Write-Host "[3/4] Installing MinerU[all] — this may take 10-30 minutes..." -ForegroundColor Yellow
Write-Host "MinerU downloads model files and has many dependencies (PyTorch, etc)." -ForegroundColor Gray
Write-Host ""

uv pip install -U "mineru[all]" --system

Write-Host ""
Write-Host "MinerU installed successfully." -ForegroundColor Green
Write-Host ""

# Step 4: Verify installation
Write-Host "[4/4] Verifying installation..." -ForegroundColor Yellow

$mineruOk = $false
$magicPdfOk = $false

try {
    $mineruVersion = mineru --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  mineru CLI: OK — $mineruVersion" -ForegroundColor Green
        $mineruOk = $true
    }
} catch {
    Write-Host "  mineru CLI: not found" -ForegroundColor Red
}

try {
    $magicPdfVersion = magic-pdf --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  magic-pdf CLI: OK — $magicPdfVersion" -ForegroundColor Green
        $magicPdfOk = $true
    }
} catch {
    Write-Host "  magic-pdf CLI: not found" -ForegroundColor Red
}

Write-Host ""

if ($mineruOk -or $magicPdfOk) {
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  MinerU installation successful!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor White
    Write-Host "  1. Restart the backend (start_backend.bat)" -ForegroundColor White
    Write-Host "  2. Verify: open http://localhost:8000/api/integrations/mineru/status" -ForegroundColor White
    Write-Host "  3. Upload a PDF/DOCX/image to test" -ForegroundColor White
} else {
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "  Installation may have issues." -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor White
    Write-Host "  - Ensure Python 3.10+ is in PATH" -ForegroundColor White
    Write-Host "  - Try: pip install magic-pdf" -ForegroundColor White
    Write-Host "  - See: https://github.com/opendatalab/MinerU" -ForegroundColor White
    Write-Host "  - The backend will still work for txt/md/json/csv uploads" -ForegroundColor White
}

Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
