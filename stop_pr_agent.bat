@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$pids = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; if ($pids) { foreach ($pidToStop in $pids) { Stop-Process -Id $pidToStop -Force -ErrorAction SilentlyContinue }; Write-Host 'PR Agent stopped.' } else { Write-Host 'No app was found listening on port 8501.' }"
timeout /t 2 >nul
