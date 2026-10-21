Option Explicit

' One-click restart. Use this after installing an update or changing files.
' It stops the app on port 8501, waits briefly, then launches a fresh copy.

Dim shell, fso, projectDir, stopScript, launchScript

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
stopScript = projectDir & "\stop_pr_agent.bat"
launchScript = projectDir & "\launch_pr_agent_hidden.vbs"

If fso.FileExists(stopScript) Then
    shell.Run Chr(34) & stopScript & Chr(34), 0, True
End If

WScript.Sleep 2000

If Not fso.FileExists(launchScript) Then
    MsgBox "Could not find the launcher:" & vbCrLf & launchScript, vbExclamation, "Digital PR Agent"
    WScript.Quit 1
End If

shell.Run "wscript.exe " & Chr(34) & launchScript & Chr(34), 1, False
