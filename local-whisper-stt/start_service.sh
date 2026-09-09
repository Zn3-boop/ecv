#!/bin/bash
# 本地 Whisper STT 服务启动脚本 (Linux/Mac 版本)

echo "正在启动本地 Whisper STT 服务..."
echo "服务地址: http://localhost:5051"

# 检查模型是否存在
if [ ! -d "models/base" ]; then
    echo ""
    echo "错误: 未找到模型文件！"
    echo "请先在联网环境中下载模型，详情见 MODEL_DOWNLOAD_GUIDE.md"
    echo ""
    exit 1
fi

echo ""
echo "检测到本地模型，正在启动服务..."
echo ""

# 启动服务
python server.py