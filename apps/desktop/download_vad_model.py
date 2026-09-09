import os
import urllib.request
import urllib.error
import time

def download_with_retry(url, output_path, max_retries=3, timeout=30):
    """带重试的下载函数"""
    
    # 设置代理（如果有的话）
    proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    if proxy:
        proxy_handler = urllib.request.ProxyHandler({'http': proxy, 'https': proxy})
        opener = urllib.request.build_opener(proxy_handler)
        urllib.request.install_opener(opener)
        print(f"[Download] 使用代理: {proxy}")
    
    # 尝试多个镜像源
    mirrors = [
        url,  # 原始URL
        "https://hf-mirror.com/snakers4/silero-vad/resolve/main/files/silero_vad.onnx",
        "https://modelscope.cn/models/snakers4/silero-vad/resolve/master/files/silero_vad.onnx"
    ]
    
    for attempt in range(max_retries):
        for mirror_url in mirrors:
            try:
                print(f"[Download] 尝试 {attempt + 1}/{max_retries}: {mirror_url}")
                
                # 创建请求头
                req = urllib.request.Request(
                    mirror_url,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                )
                
                # 下载文件
                with urllib.request.urlopen(req, timeout=timeout) as response:
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
                    
                    print(f"\n[Download] 下载完成: {output_path}")
                    return True
                    
            except urllib.error.HTTPError as e:
                print(f"\n[Download] HTTP 错误: {e.code} - {e.reason}")
                if e.code == 404:
                    print(f"[Download] 镜像源不存在，尝试下一个...")
                    continue
            except urllib.error.URLError as e:
                print(f"\n[Download] 网络错误: {e.reason}")
            except Exception as e:
                print(f"\n[Download] 未知错误: {e}")
            
            # 等待后重试
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"[Download] 等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
    
    return False

if __name__ == "__main__":
    output_dir = r"D:\ecv\apps\desktop\models"
    output_path = os.path.join(output_dir, "silero_vad.onnx")
    
    # 确保目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    print("[Download] 开始下载 Silero VAD 模型...")
    print(f"[Download] 目标路径: {output_path}")
    
    original_url = "https://huggingface.co/snakers4/silero-vad/resolve/main/files/silero_vad.onnx"
    
    if download_with_retry(original_url, output_path):
        print("[Download] ✅ 下载成功!")
        
        # 检查文件大小
        file_size = os.path.getsize(output_path)
        print(f"[Download] 文件大小: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
        
        if file_size < 1000:  # 小于1KB可能是错误页面
            print("[Download] ⚠️ 警告: 文件大小异常，可能下载失败")
    else:
        print("[Download] ❌ 下载失败，请检查网络连接或手动下载")
        print(f"[Download] 手动下载地址: {original_url}")
        print(f"[Download] 保存到: {output_path}")