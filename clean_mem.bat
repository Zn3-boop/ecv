@echo off
echo 正在清理内存...
taskkill /f /im baidunetdisk.exe >nul 2>nul
taskkill /f /im python.exe >nul 2>nul
rundll32.exe advapi32.dll,ProcessIdleTasks
echo 清理完成