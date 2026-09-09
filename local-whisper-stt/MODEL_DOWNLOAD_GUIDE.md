# 模型下载指南

## 离线环境模型部署方案

由于当前环境无法连接互联网，您需要在联网环境中下载模型，然后将其传输到当前环境。

## 方案一：在联网电脑上下载模型

1. 在有互联网连接的电脑上克隆或复制此项目
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
3. 下载模型：
   ```bash
   python download_model.py
   ```
4. 将生成的 `models` 目录完整复制到当前环境的项目根目录

## 方案二：手动下载模型

1. 访问模型页面：https://huggingface.co/Systran/faster-whisper-base
2. 下载模型文件
3. 解压到 `d:\ecv\local-whisper-stt\models\base` 目录

## 支持的模型列表

| 模型 | 大小 | 适用场景 |
|------|------|----------|
| tiny | 75MB | 快速测试 |
| base | 142MB | 默认模型 |
| small | 466MB | 平衡精度与速度 |
| medium | 1.5GB | 较高精度 |
| large-v2 | 3.0GB | 最高精度 |

## 验证模型是否就绪

模型下载完成后，可以通过以下命令验证：

```bash
# 设置环境变量后启动服务
WHISPER_MODEL=base python server.py
```

## 注意事项

- 模型文件较大，请确保有足够的磁盘空间
- 离线部署时，模型必须预先下载到本地
- 不同模型对内存的要求不同，选择合适的模型大小