@echo off
chcp 65001 >nul
echo ========================================
echo   模型下载进度检查
echo ========================================
echo.

set "model_dir=d:\ecv\local-whisper-stt\models\base"

if not exist "%model_dir%" (
    echo 模型目录不存在
    exit /b 1
)

echo [已下载的文件]
echo.

set "total_size=0"
set "file_count=0"

for %%F in ("%model_dir%\*") do (
    set /a file_count+=1
    set "size=%%~zF"
    set /a total_size+=size
    echo   %%~nxF - %%~zF bytes
)

echo.
echo [统计]
echo   文件数量: %file_count%
echo   总大小: %total_size% bytes (%total_size:~0,-3% KB)

REM 检查 model.bin 是否完成
if exist "%model_dir%\model.bin" (
    for %%F in ("%model_dir%\model.bin") do (
        set "bin_size=%%~zF"
        if !bin_size! geq 145000000 (
            echo.
            echo ✓ model.bin 已完成（约 138MB）
        ) else (
            echo.
            echo model.bin 下载中... (!bin_size! bytes)
        )
    )
)

echo.
echo 模型完整大小应为约 140MB
echo 如果 model.bin 达到 140MB+，说明下载完成
echo.

pause
