# TrendCast Execution Helper
param(
    [string]$Command = "test"
)

$VenvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found at $VenvPython. Please set up .venv first."
    exit 1
}

$env:PYTHONPATH = $PSScriptRoot
Push-Location $PSScriptRoot

try {
    switch ($Command) {
        "test" {
            & $VenvPython -m pytest -v tests
        }
        "lint" {
            & $VenvPython -m ruff check src tests demo app.py
        }
        "typecheck" {
            & $VenvPython -m mypy --config-file pyproject.toml src
        }
        "ingest" {
            & $VenvPython -m src.ingest
        }
        "clean" {
            & $VenvPython -m src.clean
        }
        "evaluate" {
            & $VenvPython -m src.evaluate
        }
        "app" {
            & $VenvPython -m streamlit run app.py
        }
        default {
            Write-Host "Unknown command: $Command. Available: test, lint, typecheck, ingest, clean, evaluate, app"
            exit 1
        }
    }
}
finally {
    Pop-Location
}
