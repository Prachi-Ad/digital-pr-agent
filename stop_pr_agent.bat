@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_app.ps1"
ping -n 3 127.0.0.1 >nul
