Set-Location "$PSScriptRoot\.."

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "未找到虚拟环境 Python: $python"
    exit 1
}

& $python -m pip install -r requirements.txt
& $python -m pip install pyinstaller

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name cninfo_downloader `
    --distpath . `
    --workpath build `
    --specpath . `
    app/main.py

Write-Host "打包完成: cninfo_downloader/cninfo_downloader.exe"
