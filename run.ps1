# Clean launcher for GradePanel (Windows PowerShell).
# Avoids the "cannot import name 'list_batches'" class of errors caused by stale bytecode
# or a long-running Streamlit process holding old modules.
#
# Usage:  ./run.ps1        (stop any previous run with Ctrl+C in its terminal first)

# Don't write .pyc files -> no stale bytecode can be picked up later.
$env:PYTHONDONTWRITEBYTECODE = "1"

# Purge any existing compiled caches.
Get-ChildItem -Path . -Recurse -Directory -Filter __pycache__ -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Launching GradePanel (fresh, no bytecode cache)..." -ForegroundColor Green
streamlit run app.py
