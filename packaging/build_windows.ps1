# 在 Windows 上打出 dist\WestlakeDock\WestlakeDock.exe
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -3 -m venv .venv
}
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller pillow

.\.venv\Scripts\python.exe packaging\make_icon.py
.\.venv\Scripts\python.exe -m PyInstaller packaging\WestlakeDock.spec --noconfirm --clean `
    --distpath dist --workpath build\pyinstaller

Write-Host ''
Write-Host '输出：dist\WestlakeDock\WestlakeDock.exe'
