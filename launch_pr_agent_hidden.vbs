Option Explicit

Dim shell, fso, projectDir, pythonExe, appPath, command
Dim ready, startTime, url

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonExe = projectDir & "\.venv\Scripts\python.exe"
appPath = projectDir & "\app.py"
url = "http://localhost:8501"

If Not fso.FileExists(pythonExe) Then
    MsgBox "Could not find the project's Python environment:" & vbCrLf & pythonExe, vbExclamation, "Digital PR Agent"
    WScript.Quit 1
End If

If Not fso.FileExists(appPath) Then
    MsgBox "Could not find app.py in:" & vbCrLf & projectDir, vbExclamation, "Digital PR Agent"
    WScript.Quit 1
End If

shell.CurrentDirectory = projectDir

' If Streamlit is already running, reuse it and open the browser.
If IsServerReady() Then
    shell.Run url, 1, False
    WScript.Quit 0
End If

' Launch Streamlit in a hidden process using this project's Python.
command = Chr(34) & pythonExe & Chr(34) & " -m streamlit run " & Chr(34) & appPath & Chr(34) & " --server.headless true --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false"
shell.Run command, 0, False

' Wait up to 45 seconds for the app to be ready.
ready = False
startTime = Timer
Do
    WScript.Sleep 500
    If IsServerReady() Then
        ready = True
        Exit Do
    End If
    If Timer - startTime >= 45 Then Exit Do
Loop

If ready Then
    shell.Run url, 1, False
Else
    MsgBox "The PR Agent did not start within 45 seconds." & vbCrLf & _
           "Check that app.py works and OPENAI_API_KEY is set in Windows.", _
           vbExclamation, "Digital PR Agent"
End If

Function IsServerReady()
    Dim request, success
    success = False
    On Error Resume Next
    Set request = CreateObject("WinHttp.WinHttpRequest.5.1")
    request.Open "GET", "http://127.0.0.1:8501/_stcore/health", False
    request.SetTimeouts 500, 500, 500, 500
    request.Send
    If Err.Number = 0 Then
        If request.Status = 200 Then success = True
    End If
    Err.Clear
    On Error GoTo 0
    IsServerReady = success
End Function
