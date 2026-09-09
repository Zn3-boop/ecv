@echo off
chcp 65001 >nul
cd /d "d:\ecv"
if exist "d:\ecv\venv\Scripts\python.exe" (
    set "PYTHON=d:\ecv\venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)
cd /d "d:\ecv\apps\server"
%PYTHON% -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
