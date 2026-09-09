import os
from huggingface_hub import hf_hub_download, HfApi
import sys

def download_silero_vad():
    """使用 huggingface_hub 下载 Silero VAD 模型"""
    
    output_dir = r"D:\ecv\apps\desktop\models"
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, "silero_vad.onnx")
    
    print("[Download] 开始下载 Silero VAD 模型...")
    print(f"[Download] 目标路径: {output_path}")
    
    try:
        # 尝试从 HuggingFace 下载
        print("[Download] 正在从 HuggingFace 下载...")
        model_path = hf_hub_download(
            repo_id="snakers4/silero-vad",
            filename="files/silero_vad.onnx",
            local_dir=output_dir,
            local_dir_use_symlinks=False,
            resume_download=True
        )
        
        print(f"[Download] ✅ 下载成功!")
        print(f"[Download] 模型路径: {model_path}")
        
        # 检查文件大小
        file_size = os.path.getsize(model_path)
        print(f"[Download] 文件大小: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
        
        if file_size < 1000:
            print("[Download] ⚠️ 警告: 文件大小异常，可能下载失败")
            return False
        
        return True
        
    except Exception as e:
        print(f"[Download] ❌ 下载失败: {e}")
        print("[Download] 尝试使用备用方法...")
        
        try:
            # 备用方法：直接使用 API
            api = HfApi()
            print("[Download] 正在尝试备用下载方法...")
            
            # 直接下载文件
            model_path = hf_hub_download(
                repo_id="snakers4/silero-vad",
                filename="files/silero_vad.onnx",
                local_dir=output_dir,
                local_dir_use_symlinks=False,
                resume_download=True,
                force_download=True
            )
            
            print(f"[Download] ✅ 备用方法下载成功!")
            print(f"[Download] 模型路径: {model_path}")
            
            file_size = os.path.getsize(model_path)
            print(f"[Download] 文件大小: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
            
            return True
            
        except Exception as e2:
            print(f"[Download] ❌ 备用方法也失败: {e2}")
            print(f"[Download] 请手动下载:")
            print(f"[Download] 1. 访问: https://huggingface.co/snakers4/silero-vad/tree/main")
            print(f"[Download] 2. 下载 files/silero_vad.onnx")
            print(f"[Download] 3. 保存到: {output_path}")
            return False

if __name__ == "__main__":
    success = download_silero_vad()
    sys.exit(0 if success else 1)