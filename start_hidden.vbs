Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Games\Agents\plex_aither_automation"
WshShell.Run "python app.py", 0, False
