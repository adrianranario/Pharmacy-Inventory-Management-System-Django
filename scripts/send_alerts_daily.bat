@echo off
setlocal
cd /d "C:\Users\Adrian\Pharmacy-Inventory-Management-System-Django"
if not exist "logs" mkdir "logs"
echo [%DATE% %TIME%] Starting pharmacy alert digest >> "logs\send_alerts.log"
".\venv\Scripts\python.exe" manage.py send_alerts >> "logs\send_alerts.log" 2>&1
exit /b %ERRORLEVEL%
