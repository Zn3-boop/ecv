@echo off
chcp 65001 >nul
echo ========================================
echo AI Desktop Agent - 重启所有服务
echo ========================================
echo.

:: 设置 Python 路径（优先使用 venv）
if exist "d:\ecv\venv\Scripts\python.exe" (
    set "PYTHON=d:\ecv\venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)
echo [0/6] Python: %PYTHON%

:: 1. 关闭旧进程
echo [1/6] 关闭旧进程...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM node.exe 2>nul
taskkill /F /IM electron.exe 2>nul
timeout /t 3 /nobreak >nul

:: 2. 启动后端服务
echo [2/6] 启动后端服务 (端口 8000)...
start "Server" cmd /k "cd /d d:\ecv\apps\server && %PYTHON% -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

timeout /t 2 /nobreak >nul

:: 3. 启动Edge TTS API
echo [3/6] 启动TTS服务 (端口 8080)...
start "TTS" cmd /k "cd /d d:\ecv\edge-tts-api && %PYTHON% -m uvicorn main:app --host 127.0.0.1 --port 8080"

:: 4. 启动Whisper STT
echo [4/6] 启动Whisper STT (端口 5051)...
start "Whisper" cmd /k "cd /d d:\ecv\local-whisper-stt && %PYTHON% server.py"

:: 5. 启动前端开发服务器
echo [5/6] 启动前端开发服务器 (端口 5173)...
start "Frontend" cmd /k "cd /d d:\ecv\apps\desktop && pnpm dev"

:: 6. 启动Electron桌面端
echo [6/6] 启动Electron桌面端...
timeout /t 5 /nobreak >nul
start "Desktop" cmd /k "cd /d d:\ecv\apps\desktop && pnpm dev:electron"

echo.
echo ========================================
echo 所有服务已重启！
echo - 后端:   http://127.0.0.1:8000
echo - TTS:    http://127.0.0.1:8080
echo - Whisper: http://127.0.0.1:5051
echo - 前端:   http://127.0.0.1:5173
echo - 桌面端: Electron应用窗口
echo ========================================