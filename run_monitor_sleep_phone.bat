@echo off
cd /d "%~dp0"
python monitor.py --config config_sleep_phone.json
pause
