@echo off
setlocal
call "%~dp0stop_pr_agent.bat"
taskkill /IM cloudflared.exe /F >nul 2>&1
echo PR Agent and Cloudflare tunnel stopped.
