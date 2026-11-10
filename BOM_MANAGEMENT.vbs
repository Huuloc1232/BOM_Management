' BOM Management - chay server an (khong hien cua so console) va mo trinh duyet.
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Run "cmd /c ""run_bom_management_web.bat""", 0, False
