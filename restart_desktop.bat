@echo off
chcp 65001 >nul
echo 重新构建并启动桌面端...
cd /d d:\ecv\apps\desktop
call pnpm build
call pnpm dev:electron
