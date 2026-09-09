@echo off
chcp 65001 >nul
echo ================================================
echo   Silero VAD 模型下载脚本
echo ================================================
echo.

:: 创建 models 目录
if not exist "models" mkdir "models"

:: 检查是否已存在
if exist "models\silero_vad.onnx" (
    for %%A in ("models\silero_vad.onnx") do set SIZE=%%~zA
    if %SIZE% GTR 1000000 (
        echo ✅ 模型已存在！
        echo    路径: %~dp0models\silero_vad.onnx
        echo    大小: %SIZE% bytes
        echo.
        echo 可以直接启动 Electron 应用了！
        echo.
        pause
        exit /b 0
    )
)

echo 正在下载 Silero VAD 模型...
echo.

:: 尝试多个源（按顺序尝试）
set DOWNLOAD_SUCCESS=0

echo [1/3] 尝试从 k2-fsa/sherpa-onnx 下载（国内访问较快）...
powershell -Command "try { Invoke-WebRequest -Uri 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx' -OutFile 'models\silero_vad.onnx' -TimeoutSec 300 -UseBasicParsing; exit 0 } catch { exit 1 }"
if %ERRORLEVEL% EQU 0 (
    for %%A in ("models\silero_vad.onnx") do set SIZE=%%~zA
    if %SIZE% GTR 1000000 (
        set DOWNLOAD_SUCCESS=1
        goto :download_success
    )
)

echo [2/3] 尝试从 HuggingFace 下载...
powershell -Command "try { Invoke-WebRequest -Uri 'https://huggingface.co/snakers4/silero-vad/resolve/main/files/silero_vad.onnx' -OutFile 'models\silero_vad.onnx' -TimeoutSec 300 -UseBasicParsing; exit 0 } catch { exit 1 }"
if %ERRORLEVEL% EQU 0 (
    for %%A in ("models\silero_vad.onnx") do set SIZE=%%~zA
    if %SIZE% GTR 1000000 (
        set DOWNLOAD_SUCCESS=1
        goto :download_success
    )
)

echo [3/3] 尝试从 GitHub raw 下载...
powershell -Command "try { Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/snakers4/silero-vad/master/files/silero_vad.onnx' -OutFile 'models\silero_vad.onnx' -TimeoutSec 300 -UseBasicParsing; exit 0 } catch { exit 1 }"
if %ERRORLEVEL% EQU 0 (
    for %%A in ("models\silero_vad.onnx") do set SIZE=%%~zA
    if %SIZE% GTR 1000000 (
        set DOWNLOAD_SUCCESS=1
    )
)

:download_success
echo.
if %DOWNLOAD_SUCCESS% EQU 1 (
    echo ================================================
    echo   ✅ 下载完成！
    echo ================================================
    echo    路径: %~dp0models\silero_vad.onnx
    echo    大小: %SIZE% bytes
    echo.
    echo 现在可以启动 Electron 应用了！
) else (
    echo ================================================
    echo   ❌ 下载失败！
    echo ================================================
    echo.
    echo 手动下载方案：
    echo 1. 访问以下任一网站:
    echo    - https://huggingface.co/snakers4/silero-vad/tree/main
    echo    - https://github.com/k2-fsa/sherpa-onnx/releases
    echo 2. 下载 silero_vad.onnx 文件
    echo 3. 保存到: %~dp0models\silero_vad.onnx
    echo.
    echo 或使用 Python 脚本（更可靠）:
    echo    python download_vad.py
)

echo.
pause
