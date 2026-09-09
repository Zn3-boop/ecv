"""
使用 ModelScope 镜像下载 Faster-Whisper 模型
国内下载速度更快
"""
import os
from modelscope.hub.snapshot_download import snapshot_download

def download_with_modelscope(model_id="ZhanwuLyu/faster-whisper-base"):
    """使用 ModelScope 下载模型"""
    local_dir = os.path.join(os.path.dirname(__file__), "models")
    os.makedirs(local_dir, exist_ok=True)
    
    print(f"\n{'='*50}")
    print(f"使用 ModelScope 下载 Faster-Whisper 模型")
    print(f"模型: {model_id}")
    print(f"保存路径: {local_dir}")
    print(f"{'='*50}\n")
    
    try:
        cache_dir = os.path.join(local_dir, "modelscope_cache")
        os.makedirs(cache_dir, exist_ok=True)
        
        model_dir = snapshot_download(
            model_id,
            cache_dir=cache_dir,
            revision='master'
        )
        print(f"\n✓ 模型下载完成！")
        print(f"模型路径: {model_dir}")
        
        # 复制到目标位置
        import shutil
        target_dir = os.path.join(local_dir, "base")
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        shutil.copytree(model_dir, target_dir)
        print(f"已复制到: {target_dir}")
        
        return True
    except Exception as e:
        print(f"\n✗ 下载失败: {e}")
        return False

if __name__ == "__main__":
    download_with_modelscope()
