import os
import ssl
import urllib.request
from huggingface_hub import hf_hub_download
import sys

# 禁用SSL验证（仅用于测试）
ssl._create_default_https_context = ssl._create_unverified_context

def download_with_huggingface_hub():
    """使用 huggingface_hub 下载，禁用SSL验证"""
    
    output_dir = r"D:\ecv\apps\desktop\models"
    os.makedirs(output_dir, exist_ok=True)
    
    print("[Download] 开始下载 Silero VAD 模型...")
    print(f"[Download] 目标路径: {output_dir}")
    
    try:
        print("[Download] 正在从 HuggingFace 下载...")
        model_path = hf_hub_download(
            repo_id="snakers4/silero-vad",
            filename="files/silero_vad.onnx",
            local_dir=output_dir,
            force_download=True
        )
        
        print(f"[Download] ✅ 下载成功!")
        print(f"[Download] 模型路径: {model_path}")
        
        file_size = os.path.getsize(model_path)
        print(f"[Download] 文件大小: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
        
        if file_size > 1000:
            return True
        else:
            print("[Download] ⚠️ 警告: 文件大小异常")
            return False
            
    except Exception as e:
        print(f"[Download] ❌ 下载失败: {e}")
        return False

def download_direct_url():
    """直接使用 urllib 下载"""
    
    output_dir = r"D:\ecv\apps\desktop\models"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "silero_vad.onnx")
    
    url = "https://huggingface.co/snakers4/silero-vad/resolve/main/files/silero_vad.onnx"
    
    print(f"[Download] 尝试直接下载: {url}")
    
    try:
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )
        
        with urllib.request.urlopen(req, timeout=60) as response:
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(output_path, 'wb') as f:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if total_size > 0:
                        progress = (downloaded / total_size) * 100
                        print(f"\r[Download] 进度: {progress:.1f}% ({downloaded}/{total_size} bytes)", end='')
            
            print(f"\n[Download] ✅ 下载完成!")
            
            file_size = os.path.getsize(output_path)
            print(f"[Download] 文件大小: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
            
            return file_size > 1000
            
    except Exception as e:
        print(f"\n[Download] ❌ 直接下载失败: {e}")
        return False

if __name__ == "__main__":
    print("[Download] 尝试方法1: HuggingFace Hub")
    if download_with_huggingface_hub():
        print("[Download] ✅ 成功!")
        sys.exit(0)
    
    print("\n[Download] 尝试方法2: 直接URL下载")
    if download_direct_url():
        print("[Download] ✅ 成功!")
        sys.exit(0)
    
    print("\n[Download] ❌ 所有方法都失败了")
    print("[Download] 请手动下载:")
    print("[Download] 1. 访问: https://huggingface.co/snakers4/silero-vad/tree/main")
    print("[Download] 2. 找到并下载 files/silero_vad.onnx")
    print(f"[Download] 3. 保存到: D:\\ecv\\apps\\desktop\\models\\silero_vad.onnx")
    sys.exit(1)