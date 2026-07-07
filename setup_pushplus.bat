@echo off
cd /d "%~dp0"
python setup_pushplus.py
if errorlevel 1 (
  pause
  exit /b 1
)
python monitor.py --test-notify
pause
