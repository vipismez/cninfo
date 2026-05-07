Set-Location "$PSScriptRoot\.."

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "未找到虚拟环境 Python: $python"
    exit 1
}

& $python -m app.main
