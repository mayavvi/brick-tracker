@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Installing dependencies...
python -m pip install -r requirements.txt || goto :error

echo [2/3] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/3] Building PEAK.exe...
python -m PyInstaller --noconfirm peak.spec || goto :error

echo.
echo Done. Launch: dist\PEAK\PEAK.exe
exit /b 0

:error
echo.
echo Build failed.
exit /b 1
