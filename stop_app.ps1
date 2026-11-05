# Stop the local Digital PR Agent (Streamlit on this project).
# Uses the process command line instead of Get-NetTCPConnection, which can
# hang on some Windows network stacks and report no listener.
$stopped = 0
$processes = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object {
        $_.CommandLine -like '*vista-pr-agent\.venv\Scripts\python.exe*' -and
        $_.CommandLine -like '*streamlit run*app.py*'
    }

foreach ($process in $processes) {
    try {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
        Write-Host "Stopped process $($process.ProcessId)."
        $stopped++
    } catch {
        Write-Host "Could not stop process $($process.ProcessId): $($_.Exception.Message)"
    }
}

if ($stopped -eq 0) {
    Write-Host "The PR Agent is not running."
} else {
    Write-Host "PR Agent stopped."
}
