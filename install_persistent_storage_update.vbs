Option Explicit

Dim fso, shell, sourceFolder, projectFolder, backupsRoot, backupFolder
Dim stamp, pythonExe, agentPath, appPath, databasePath, command, result
Dim stopCommand, content, fileHandle, errorMessage, launcherPath, stopPath
Dim dbFile, backupDataFolder, sameFolder, smokePath

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

sourceFolder = fso.GetParentFolderName(WScript.ScriptFullName)
projectFolder = fso.GetParentFolderName(WScript.ScriptFullName)
agentPath = fso.BuildPath(projectFolder, "agent.py")
appPath = fso.BuildPath(projectFolder, "app.py")
databasePath = fso.BuildPath(projectFolder, "database.py")
launcherPath = fso.BuildPath(projectFolder, "launch_pr_agent_hidden.vbs")
stopPath = fso.BuildPath(projectFolder, "stop_pr_agent.bat")
pythonExe = fso.BuildPath(projectFolder, ".venv\Scripts\python.exe")
dbFile = fso.BuildPath(projectFolder, "data\pr_agent.sqlite3")

sameFolder = (LCase(fso.GetAbsolutePathName(sourceFolder)) = _
              LCase(fso.GetAbsolutePathName(projectFolder)))

If Not fso.FileExists(fso.BuildPath(sourceFolder, "agent.py")) Or _
   Not fso.FileExists(fso.BuildPath(sourceFolder, "app.py")) Or _
   Not fso.FileExists(fso.BuildPath(sourceFolder, "database.py")) Then
    MsgBox "The update folder must contain agent.py, app.py, and database.py." & vbCrLf & _
           "Extract the complete ZIP package first. Your project was not changed.", vbExclamation, "Digital PR Agent"
    WScript.Quit 1
End If

If Not fso.FolderExists(projectFolder) Then
    MsgBox "I couldn't find the project folder:" & vbCrLf & projectFolder & vbCrLf & _
           "Your files were not changed.", vbCritical, "Digital PR Agent"
    WScript.Quit 1
End If

If Not fso.FileExists(pythonExe) Then
    MsgBox "I couldn't find the project's Python environment:" & vbCrLf & pythonExe & vbCrLf & vbCrLf & _
           "Your files were not changed. Check that the .venv folder is present in the project folder.", vbCritical, "Digital PR Agent"
    WScript.Quit 1
End If

' Stop the hidden local server before updating files.
stopCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command " & _
    Chr(34) & "Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue | " & _
    "Select-Object -ExpandProperty OwningProcess -Unique | " & _
    "ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }" & Chr(34)
On Error Resume Next
shell.Run stopCommand, 0, True
On Error GoTo 0

' Create a timestamped backup of code and the existing local database before changing anything.
backupsRoot = fso.BuildPath(projectFolder, "backups")
If Not fso.FolderExists(backupsRoot) Then fso.CreateFolder backupsRoot
stamp = Year(Now) & Right("0" & Month(Now), 2) & Right("0" & Day(Now), 2) & "-" & _
        Right("0" & Hour(Now), 2) & Right("0" & Minute(Now), 2) & Right("0" & Second(Now), 2)
backupFolder = fso.BuildPath(backupsRoot, "persistent-storage-update-" & stamp)
fso.CreateFolder backupFolder

If fso.FileExists(agentPath) Then fso.CopyFile agentPath, fso.BuildPath(backupFolder, "agent.py"), True
If fso.FileExists(appPath) Then fso.CopyFile appPath, fso.BuildPath(backupFolder, "app.py"), True
If fso.FileExists(databasePath) Then fso.CopyFile databasePath, fso.BuildPath(backupFolder, "database.py"), True

If fso.FileExists(dbFile) Then
    backupDataFolder = fso.BuildPath(backupFolder, "data")
    If Not fso.FolderExists(backupDataFolder) Then fso.CreateFolder backupDataFolder
    fso.CopyFile dbFile, fso.BuildPath(backupDataFolder, "pr_agent.sqlite3"), True
    If fso.FileExists(dbFile & "-wal") Then fso.CopyFile dbFile & "-wal", fso.BuildPath(backupDataFolder, "pr_agent.sqlite3-wal"), True
    If fso.FileExists(dbFile & "-shm") Then fso.CopyFile dbFile & "-shm", fso.BuildPath(backupDataFolder, "pr_agent.sqlite3-shm"), True
End If

' Install application code. When the installer already sits inside the project
' folder there is nothing to copy, so skip the copy instead of failing on it.
If Not sameFolder Then
    On Error Resume Next
    fso.CopyFile fso.BuildPath(sourceFolder, "agent.py"), agentPath, True
    If Err.Number <> 0 Then
        errorMessage = Err.Description
        Err.Clear
        RollBackFiles
        MsgBox "Couldn't install agent.py." & vbCrLf & "Previous code was restored where backups existed." & vbCrLf & _
               "Backup folder: " & backupFolder & vbCrLf & "Error: " & errorMessage, vbCritical, "Digital PR Agent"
        WScript.Quit 1
    End If
    Err.Clear
    fso.CopyFile fso.BuildPath(sourceFolder, "app.py"), appPath, True
    If Err.Number <> 0 Then
        errorMessage = Err.Description
        Err.Clear
        RollBackFiles
        MsgBox "Couldn't install app.py." & vbCrLf & "Previous code was restored where backups existed." & vbCrLf & _
               "Backup folder: " & backupFolder & vbCrLf & "Error: " & errorMessage, vbCritical, "Digital PR Agent"
        WScript.Quit 1
    End If
    Err.Clear
    fso.CopyFile fso.BuildPath(sourceFolder, "database.py"), databasePath, True
    If Err.Number <> 0 Then
        errorMessage = Err.Description
        Err.Clear
        RollBackFiles
        MsgBox "Couldn't install database.py." & vbCrLf & "Previous code was restored where backups existed." & vbCrLf & _
               "Backup folder: " & backupFolder & vbCrLf & "Error: " & errorMessage, vbCritical, "Digital PR Agent"
        WScript.Quit 1
    End If
    Err.Clear
    On Error GoTo 0
End If

' Only add launcher/stop files if absent; preserve the user's existing versions.
If fso.FileExists(fso.BuildPath(sourceFolder, "launch_pr_agent_hidden.vbs")) Then
    If Not fso.FileExists(launcherPath) Then fso.CopyFile fso.BuildPath(sourceFolder, "launch_pr_agent_hidden.vbs"), launcherPath, True
End If
If fso.FileExists(fso.BuildPath(sourceFolder, "stop_pr_agent.bat")) Then
    If Not fso.FileExists(stopPath) Then fso.CopyFile fso.BuildPath(sourceFolder, "stop_pr_agent.bat"), stopPath, True
End If

' Check all syntax with the project's own Python, hidden from the user.
shell.CurrentDirectory = projectFolder
command = Chr(34) & pythonExe & Chr(34) & " -m py_compile " & _
          Chr(34) & agentPath & Chr(34) & " " & Chr(34) & appPath & Chr(34) & " " & Chr(34) & databasePath & Chr(34)
result = shell.Run(command, 0, True)

' Smoke-test existing AI functions and the SQLite functions without making API calls.
smokePath = fso.BuildPath(projectFolder, "_persistent_storage_smoke_check.py")
content = "import agent, database" & vbCrLf & _
          "required_agent = ['analyze_article', 'research_opportunities', 'research_journalists', 'research_listicles', 'research_listicle_contact', 'research_publisher_policy', 'draft_journalist_pitch', 'draft_listicle_inclusion_request']" & vbCrLf & _
          "missing = [name for name in required_agent if not callable(getattr(agent, name, None))]" & vbCrLf & _
          "assert not missing, 'Missing agent functions: ' + ', '.join(missing)" & vbCrLf & _
          "required_db = ['init_db', 'load_app_snapshot', 'save_app_snapshot', 'upsert_listicle_prospect', 'upsert_pr_opportunity', 'upsert_journalist', 'upsert_outreach_draft', 'update_outreach_draft', 'list_outreach_drafts', 'create_database_backup']" & vbCrLf & _
          "missing_db = [name for name in required_db if not callable(getattr(database, name, None))]" & vbCrLf & _
          "assert not missing_db, 'Missing database functions: ' + ', '.join(missing_db)" & vbCrLf & _
          "database.init_db()" & vbCrLf & _
          "assert isinstance(database.load_app_snapshot(), dict), 'Database snapshot could not be read'" & vbCrLf
Set fileHandle = fso.CreateTextFile(smokePath, True, False)
fileHandle.Write content
fileHandle.Close

If result = 0 Then
    command = Chr(34) & pythonExe & Chr(34) & " " & Chr(34) & smokePath & Chr(34)
    result = shell.Run(command, 0, True)
End If

On Error Resume Next
If fso.FileExists(smokePath) Then fso.DeleteFile smokePath, True
On Error GoTo 0

If result <> 0 Then
    RollBackFiles
    MsgBox "The update did not pass its automatic checks. Previous code was restored where backups existed." & vbCrLf & _
           "Your original database was not intentionally overwritten." & vbCrLf & _
           "Backup folder: " & backupFolder & vbCrLf & vbCrLf & _
           "Please share this message if you need help.", vbCritical, "Digital PR Agent"
    WScript.Quit 1
End If

If sameFolder Then
    MsgBox "Checks passed. No files needed copying because this installer is already inside the project folder." & vbCrLf & vbCrLf & _
           "Checks passed: Python syntax, required AI functions, SQLite initialization, and database read check." & vbCrLf & vbCrLf & _
           "Backups saved to:" & vbCrLf & backupFolder & vbCrLf & vbCrLf & _
           "Double-click launch_pr_agent_hidden.vbs in your project folder to open the app.", vbInformation, "Digital PR Agent"
Else
    MsgBox "Persistent storage update installed successfully!" & vbCrLf & vbCrLf & _
           "Checks passed: Python syntax, required AI functions, SQLite initialization, and database read check." & vbCrLf & vbCrLf & _
           "Backups saved to:" & vbCrLf & backupFolder & vbCrLf & vbCrLf & _
           "Research is stored locally at:" & vbCrLf & fso.BuildPath(fso.BuildPath(projectFolder, "data"), "pr_agent.sqlite3") & vbCrLf & vbCrLf & _
           "Double-click launch_pr_agent_hidden.vbs in your project folder to reopen the app.", vbInformation, "Digital PR Agent"
End If
WScript.Quit 0

Sub RollBackFiles()
    On Error Resume Next
    If fso.FileExists(fso.BuildPath(backupFolder, "agent.py")) Then fso.CopyFile fso.BuildPath(backupFolder, "agent.py"), agentPath, True
    If fso.FileExists(fso.BuildPath(backupFolder, "app.py")) Then fso.CopyFile fso.BuildPath(backupFolder, "app.py"), appPath, True
    If fso.FileExists(fso.BuildPath(backupFolder, "database.py")) Then
        fso.CopyFile fso.BuildPath(backupFolder, "database.py"), databasePath, True
    ElseIf fso.FileExists(databasePath) Then
        fso.DeleteFile databasePath, True
    End If
    On Error GoTo 0
End Sub
