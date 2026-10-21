Option Explicit

Dim fso, shell, projectDir, pythonExe, checkScript, logPath, command, result
Dim message

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonExe = projectDir & "\.venv\Scripts\python.exe"
checkScript = projectDir & "\storage_self_check.py"
logPath = projectDir & "\backups\latest_storage_check.txt"

If Not fso.FileExists(pythonExe) Then
    MsgBox "I couldn't find the project's Python environment:" & vbCrLf & pythonExe & vbCrLf & vbCrLf & _
           "Make sure this file is inside your vista-pr-agent project folder.", vbCritical, "Vista Social PR Agent"
    WScript.Quit 1
End If

If Not fso.FileExists(checkScript) Then
    MsgBox "I couldn't find storage_self_check.py in:" & vbCrLf & projectDir, vbCritical, "Vista Social PR Agent"
    WScript.Quit 1
End If

shell.CurrentDirectory = projectDir
command = Chr(34) & pythonExe & Chr(34) & " " & Chr(34) & checkScript & Chr(34)
result = shell.Run(command, 0, True)

If result = 0 Then
    message = "All storage checks passed." & vbCrLf & vbCrLf & _
              "Every workflow saves and restores correctly, exports are readable, " & _
              "and a verified database backup was created." & vbCrLf & vbCrLf & _
              "Your real research database was not touched." & vbCrLf & vbCrLf & _
              "Details: " & logPath
    MsgBox message, vbInformation, "Vista Social PR Agent"
Else
    message = "Some storage checks did not pass." & vbCrLf & vbCrLf & _
              "Open this file to see exactly which checks failed:" & vbCrLf & logPath & vbCrLf & vbCrLf & _
              "Your real research database was not touched. Please share the log if you need help."
    MsgBox message, vbExclamation, "Vista Social PR Agent"
End If

WScript.Quit result
