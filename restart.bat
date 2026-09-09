@echo off
chcp 65001 >nul

echo 关闭旧进程...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM node.exe 2>nul
taskkill /F /IM electron.exe 2>nul
timeout /t 2 /nobreak >nul

echo 启动后端服务...
start "Server" cmd /k "cd /d d:\ecv\apps\server && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

echo 启动前端...
start "Frontend" cmd /k "cd /d d:\ecv\apps\desktop && pnpm dev"

echo 启动桌面端...
start "Desktop" cmd /k "cd /d d:\ecv\apps\desktop && pnpm dev:electron"

echo 完成!
