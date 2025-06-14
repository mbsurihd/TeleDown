Set-Location $PSScriptRoot

.venv\Scripts\Activate.ps1
python.exe main.py
deactivate
Read-Host "Press Entery to exit..."
