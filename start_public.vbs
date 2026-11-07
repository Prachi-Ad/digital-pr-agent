Option Explicit

Dim shell, fso, projectDir, pythonExe, appPath, cloudflared, tokenFile, token
Dim i

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonExe = projectDir & "\.venv\Scripts\python.exe"
appPath = projectDir & "\app.py"
cloudflared = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\cloudflared\cloudflared.exe"
tokenFile = projectDir & "\data\tunnel_token.txt"

shell.CurrentDirectory = projectDir

' Start Streamlit only if it is not already answering.
If Not ServerReady() Then
  shell.Run Chr(34) & pythonExe & Chr(34) & " -m streamlit run " & Chr(34) & appPath & Chr(34) & " --server.headless true --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false", 0, False
  For i = 1 To 30
    WScript.Sleep 1000
    If ServerReady() Then Exit For
  Next
End If

' Start the Cloudflare tunnel if it is not already running.
If fso.FileExists(cloudflared) And fso.FileExists(tokenFile) Then
  If Not CloudflaredRunning() Then
    token = Trim(fso.OpenTextFile(tokenFile, 1).ReadAll)
    If Len(token) > 0 Then
      shell.Environment("PROCESS")("TUNNEL_TOKEN") = token
      shell.Run Chr(34) & cloudflared & Chr(34) & " tunnel run", 0, False
    End If
  End If
End If

Function ServerReady()
  Dim request
  ServerReady = False
  On Error Resume Next
  Set request = CreateObject("MSXML2.ServerXMLHTTP.6.0")
  request.setTimeouts 500, 500, 500, 500
  request.Open "GET", "http://127.0.0.1:8501/_stcore/health", False
  request.Send
  If Err.Number = 0 Then
    If request.Status = 200 Then ServerReady = True
  End If
  Err.Clear
  On Error GoTo 0
End Function

Function CloudflaredRunning()
  Dim processes
  CloudflaredRunning = False
  On Error Resume Next
  Set processes = GetObject("winmgmts:").ExecQuery("SELECT ProcessId FROM Win32_Process WHERE Name='cloudflared.exe'")
  If processes.Count > 0 Then CloudflaredRunning = True
  On Error GoTo 0
End Function
