@echo off
title DHCP Server & Network IP Manager
color 0A
echo ========================================================
echo       DHCP SERVER & NETWORK IP MANAGER (PYTHON)
echo ========================================================
echo.
echo Ekkinei o DHCP Server kai to Web Dashboard...
echo Anoigma ston browser: http://localhost:8080
echo.
start http://localhost:8080
py server.py
if errorlevel 1 (
    python server.py
)
pause
