# 模型文件手动下载指南

由于网络限制，无法直接下载模型。请按以下步骤手动获取模型文件：

## 方法一：使用浏览器下载

1. 打开浏览器访问：https://huggingface.co/Systran/faster-whisper-base
2. 点击 "Files and versions" 标签页
3. 下载以下文件到本地：
   - config.json
   - model.bin
   - tokenizer.json
   - preprocessor_config.json
   - generation_config.json
   - vocab.json
   - merges.txt
   - feature_extractor_config.json
   - normalizer.json (如果存在)

4. 将下载的文件放入 `d:\ecv\local-whisper-stt\models\base` 目录

## 方法二：使用 Hugging Face CLI (在其他联网设备)

如果有条件使用其他联网设备，可以：

```bash
# 安装 huggingface_hub
pip install huggingface_hub

# 下载模型
huggingface-cli download Systran/faster-whisper-base --local-dir ./faster-whisper-base
```

然后将下载的文件复制到 `d:\ecv\local-whisper-stt\models\base` 目录

## 方法三：使用 Git LFS (在其他联网设备)

```bash
git lfs install
git clone https://huggingface.co/Systran/faster-whisper-base
```

## 验证模型文件完整性

下载完成后，base模型应该包含以下核心文件：

```
models/base/
├── config.json
├── model.bin
├── tokenizer.json
├── preprocessor_config.json
├── generation_config.json
├── vocab.json
├── merges.txt
└── feature_extractor_config.json
```

## 启动服务

模型文件放置到位后，即可启动服务：

```bash
python server.py
```

## 其他模型大小

如需其他模型，替换 URL 中的 "base" 为：
- tiny (约 75MB)
- base (约 142MB) 
- small (约 466MB)
- medium (约 1.5GB)
- large-v2 (约 3.0GB)

例如：https://huggingface.co/Systran/faster-whisper-small