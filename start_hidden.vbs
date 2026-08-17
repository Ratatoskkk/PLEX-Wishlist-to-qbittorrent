' Start ras with no console window at all.
' Put a shortcut to this in shell:startup to have it run at login.
' The tray icon is your way back in.

Dim shell, fso, here
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

here = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = here

' 0 = hidden window, False = do not wait for it to finish.
shell.Run "pythonw.exe """ & here & "\start.py"" run --tray", 0, False
