# 本地 Whisper STT 服务部署指南

## 环境要求

- Python 3.8+
- FFmpeg (用于音频格式转换)

## 安装步骤

### 1. 在有网络的环境中准备依赖

在有互联网连接的机器上执行以下操作：

```bash
# 克隆或复制项目到联网机器
git clone <repository-url>

# 创建虚拟环境并安装依赖
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖包
pip install -r requirements.txt

# 下载模型到本地缓存
python download_model.py

# 或者下载特定模型
WHISPER_MODEL=base python download_model.py
WHISPER_MODEL=small python download_model.py
WHISPER_MODEL=medium python download_model.py
WHISPER_MODEL=large-v2 python download_model.py
```

可用的模型大小：
- tiny (75MB) - 适合快速测试
- base (142MB) - 默认模型
- small (466MB) - 平衡精度与速度
- medium (1.5GB) - 较高精度
- large-v2 (3.0GB) - 最高精度

### 2. 将完整项目复制到离线环境

将整个项目文件夹（包括 venv 和 models 目录）复制到离线环境。

### 3. 在离线环境中启动服务

```bash
# 进入项目目录
cd local-whisper-stt

# 激活虚拟环境
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 启动服务
python server.py

# 或指定模型和计算类型
WHISPER_MODEL=base WHISPER_COMPUTE=float32 python server.py
```

服务将在 `http://0.0.0.0:5051` 上运行

## API 接口

服务兼容 OpenAI `/v1/audio/transcriptions` API 格式

### 健康检查
- GET `/health`

### 语音转文字
- POST `/v1/audio/transcriptions`

参数：
- `file`: 音频文件
- `model`: 模型名称 (默认: whisper-1)
- `language`: 语言代码 (默认: zh)
- `response_format`: 返回格式 (json/text, 默认: json)

## 环境变量

- `WHISPER_MODEL`: 模型大小 (默认: base)
- `WHISPER_COMPUTE`: 计算类型 (默认: float32)

## 批量表格确认功能

项目还包含了批量处理表格的功能：

```bash
# 处理Excel表格
python batch_confirm_tables.py input.xlsx [output.xlsx]
```

## 故障排除

1. **模型加载失败**: 确保已下载模型到本地的 `models` 目录
2. **FFmpeg 未找到**: 安装 FFmpeg 并添加到系统 PATH
3. **内存不足**: 使用较小的模型 (tiny/base/small)
4. **网络错误**: 确认在离线模式下运行，模型已预先下载

## 注意事项

- 必须在联网环境中预先下载模型
- 大型模型需要更多内存和时间
- 推荐使用 GPU 加速进行生产环境部署
- 所有依赖包也需在联网环境中预先安装