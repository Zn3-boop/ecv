"""
使用 curl 直接下载 Faster-Whisper 模型
"""
import os
import subprocess
import urllib.request

def download_with_curl():
    """使用 curl 下载模型"""
    local_dir = r"d:\ecv\local-whisper-stt\models\base"
    os.makedirs(local_dir, exist_ok=True)
    
    # 模型文件列表
    files = [
        "config.json",
        "preprocessor_config.json", 
        "tokenizer.json",
        "tokenizer_config.json",
        "model.bin",
        "model.safetensors",  # 备选格式
    ]
    
    base_url = "https://huggingface.co/Systran/faster-whisper-base/resolve/main"
    
    print(f"\n{'='*50}")
    print(f"使用 curl 下载 Faster-Whisper 模型")
    print(f"保存路径: {local_dir}")
    print(f"{'='*50}\n")
    
    # 先测试网络
    print("测试 HuggingFace 连接...")
    try:
        urllib.request.urlopen("https://huggingface.co", timeout=5)
        print("✓ 连接成功！")
    except Exception as e:
        print(f"✗ 连接失败: {e}")
        print("\n建议：")
        print("1. 开启代理软件 (Clash/V2Ray)")
        print("2. 设置环境变量: set HTTP_PROXY=http://127.0.0.1:7890")
        return False
    
    success_count = 0
    for filename in files:
        url = f"{base_url}/{filename}"
        output_path = os.path.join(local_dir, filename)
        
        # 跳过已存在的文件
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"⏭️  跳过 (已存在): {filename}")
            success_count += 1
            continue
        
        print(f"下载: {filename}...")
        try:
            subprocess.run([
                "curl", "-L", "-o", output_path,
                "--connect-timeout", "30",
                "--max-time", "600",  # 10分钟超时
                url
            ], check=True, capture_output=True)
            print(f"✓ 完成: {filename}")
            success_count += 1
        except Exception as e:
            print(f"✗ 失败: {filename} - {e}")
            # 删除不完整的文件
            if os.path.exists(output_path):
                os.remove(output_path)
    
    print(f"\n{'='*50}")
    print(f"下载完成: {success_count}/{len(files)} 个文件")
    print(f"{'='*50}")
    
    if success_count >= 3:  # 至少下载了核心文件
        print("✓ 可以使用模型了！")
        return True
    return False

if __name__ == "__main__":
    download_with_curl()
