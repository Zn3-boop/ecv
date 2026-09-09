"""
模型预下载脚本
用于将 faster-whisper 模型下载到本地，以便在离线环境中使用

支持代理配置和国内镜像自动切换
"""
import os
import urllib.request
import urllib.error
from typing import Optional
from faster_whisper import WhisperModel

def _setup_download_proxy() -> Optional[str]:
    """
    自动配置 HuggingFace 下载代理
    优先级：环境变量 > 自动检测常见代理 > 国内镜像
    返回: 使用的代理地址，如果使用镜像则返回 None
    """
    # 1. 检查环境变量
    proxy = (
        os.getenv("HTTP_PROXY") or 
        os.getenv("HTTPS_PROXY") or 
        os.getenv("http_proxy") or 
        os.getenv("https_proxy")
    )
    
    if proxy:
        print(f"[下载器] 使用环境变量代理: {proxy}")
        _apply_proxy(proxy)
        return proxy
    
    # 2. 尝试常见代理端口
    common_proxies = [
        "http://127.0.0.1:7890",   # Clash 默认
        "http://127.0.0.1:7897",   # Clash 备用
        "http://127.0.0.1:1080",   # V2Ray 默认
        "http://127.0.0.1:8080",  # 通用代理
        "http://192.168.1.1:7890", # 路由器代理
    ]
    
    print("[下载器] 正在自动检测可用代理...")
    for candidate in common_proxies:
        try:
            handler = urllib.request.ProxyHandler({
                "http": candidate,
                "https": candidate,
            })
            opener = urllib.request.build_opener(handler)
            # 测试代理是否可用
            opener.open("https://huggingface.co", timeout=3)
            print(f"[下载器] ✓ 自动检测到可用代理: {candidate}")
            _apply_proxy(candidate)
            return candidate
        except (urllib.error.URLError, OSError, TimeoutError):
            continue
    
    # 3. 无可用代理 → 使用国内镜像
    print("[下载器] ✗ 无可用代理，切换到 HuggingFace 国内镜像")
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    print("[下载器] 使用镜像地址: https://hf-mirror.com")
    return None

def _apply_proxy(proxy: str):
    """应用代理配置"""
    os.environ["HTTP_PROXY"] = proxy
    os.environ["HTTPS_PROXY"] = proxy
    os.environ["http_proxy"] = proxy
    os.environ["https_proxy"] = proxy
    
    handler = urllib.request.ProxyHandler({
        "http": proxy,
        "https": proxy,
    })
    urllib.request.install_opener(urllib.request.build_opener(handler))

def _setup_cache_dir():
    """配置模型缓存目录"""
    # 默认缓存到 D 盘，避免 WSL 磁盘空间不足
    cache_dir = os.getenv("HF_HOME", "/mnt/d/hf_cache")
    
    # 如果是 Windows 路径，转换为 WSL 路径
    if cache_dir.startswith("D:"):
        cache_dir = "/mnt/d" + cache_dir[2:].replace("\\", "/")
    
    os.makedirs(cache_dir, exist_ok=True)
    os.environ["HF_HOME"] = cache_dir
    os.environ["TRANSFORMERS_CACHE"] = f"{cache_dir}/transformers"
    os.environ["HUGGINGFACE_HUB_CACHE"] = f"{cache_dir}/hub"
    print(f"[下载器] 模型缓存目录: {cache_dir}")

def download_model_locally(model_size="base"):
    """下载指定大小的模型到本地"""
    # 配置代理和缓存
    # 强制使用官方源（禁用自动镜像切换）
    os.environ["HF_ENDPOINT"] = "https://huggingface.co"
    _setup_download_proxy()
    _setup_cache_dir()
    
    local_dir = os.path.join(os.path.dirname(__file__), "models")
    os.makedirs(local_dir, exist_ok=True)
    
    print(f"\n{'='*50}")
    print(f"开始下载 Faster-Whisper 模型: {model_size}")
    print(f"保存路径: {local_dir}")
    print(f"{'='*50}\n")
    
    try:
        model = WhisperModel(model_size, download_root=local_dir)
        print(f"\n✓ 模型 {model_size} 下载完成！")
        return True
    except Exception as e:
        print(f"\n✗ 下载失败: {e}")
        print("\n如果网络超时，建议尝试:")
        print("1. 确保代理软件正在运行")
        print("2. 或者手动下载模型到: https://huggingface.co/Systran/faster-whisper-{model_size}")
        return False

if __name__ == "__main__":
    model_size = os.getenv("WHISPER_MODEL", "base")
    download_model_locally(model_size)
