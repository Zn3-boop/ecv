#!/usr/bin/env python3
"""
Silero VAD 模型下载工具
支持多个下载源，自动重试，SSL证书问题处理
"""

import requests
import os
import sys
import urllib3
import time

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 配置
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(SCRIPT_DIR, 'models')
MODEL_FILE = 'silero_vad.onnx'
OUTPUT_PATH = os.path.join(MODELS_DIR, MODEL_FILE)

# 多个下载源（按优先级排序）
# 注意：标准 silero_vad.onnx 应该在 1.8-2.2MB 左右
DOWNLOAD_SOURCES = [
    {
        'name': 'HuggingFace (snakers4)',
        'url': 'https://huggingface.co/snakers4/silero-vad/resolve/main/files/silero_vad.onnx',
        'expected_size_min': 1_500_000,  # 约 1.5MB
        'expected_size_max': 3_000_000,
    },
    {
        'name': 'GitHub raw (master)',
        'url': 'https://raw.githubusercontent.com/snakers4/silero-vad/master/files/silero_vad.onnx',
        'expected_size_min': 1_500_000,
        'expected_size_max': 3_000_000,
    },
    {
        'name': 'GitHub releases (snakers4)',
        'url': 'https://github.com/snakers4/silero-vad/releases/download/v1.0.0/silero_vad.onnx',
        'expected_size_min': 1_500_000,
        'expected_size_max': 3_000_000,
    },
    {
        'name': 'HuggingFace files API',
        'url': 'https://huggingface.co/api/models/snakers4/silero-vad?blobs=true',
        'expected_size_min': 1_500_000,
        'expected_size_max': 3_000_000,
    },
    {
        'name': 'ModelScope direct',
        'url': 'https://modelscope.cn/models/snakers4/silero-vad/resolve/master/files/silero_vad.onnx',
        'expected_size_min': 1_500_000,
        'expected_size_max': 3_000_000,
    },
    {
        'name': 'ModelScope file list',
        'url': 'https://www.modelscope.cn/api/v1/models/snakers4/silero-vad/repo?Revision=master&FilePath=files/silero_vad.onnx',
        'expected_size_min': 1_500_000,
        'expected_size_max': 3_000_000,
    },
]


def create_session():
    """创建请求会话"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    return session


def download_file(url, expected_size_min=1_500_000):
    """下载文件"""
    session = create_session()
    
    try:
        print(f'  正在连接...')
        response = session.get(url, stream=True, timeout=120, verify=False, allow_redirects=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        if total_size > 0:
            print(f'  文件大小: {total_size / 1024 / 1024:.1f} MB')
        
        downloaded = 0
        with open(OUTPUT_PATH, 'wb') as f:
            for chunk in response.iter_content(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    percent = downloaded * 100 / total_size
                    print(f'\r  进度: {percent:5.1f}%', end='', flush=True)
        
        print()
        return downloaded
        
    except requests.exceptions.Timeout:
        print('  ⏱️ 连接超时')
        return 0
    except requests.exceptions.RequestException as e:
        print(f'  ❌ 网络错误: {e}')
        return 0
    except Exception as e:
        print(f'  ❌ 错误: {e}')
        return 0


def validate_model():
    """验证下载的模型文件"""
    if not os.path.exists(OUTPUT_PATH):
        return False, '文件不存在'
    
    size = os.path.getsize(OUTPUT_PATH)
    
    # 检查是否是 HTML 或错误页面
    try:
        with open(OUTPUT_PATH, 'rb') as f:
            header = f.read(100)
            if b'<!doctype html' in header.lower() or b'<html' in header.lower():
                return False, '下载到的是 HTML 页面而不是模型文件'
    except:
        pass
    
    # 检查文件大小
    if size < 500_000:  # 小于 500KB 肯定不对
        return False, f'文件太小 ({size / 1024:.0f} KB)'
    
    # 检查是否是有效的 ONNX 文件（简单验证）
    try:
        with open(OUTPUT_PATH, 'rb') as f:
            header = f.read(4)
            # ONNX 文件以 "ONNX" 或特定字节开头
            if header[:3] == b'ONX':
                return True, f'有效 ONNX 文件 ({size / 1024 / 1024:.1f} MB)'
    except:
        pass
    
    # 如果文件大于 1MB，也认为是有效的
    if size > 1_000_000:
        return True, f'文件大小正常 ({size / 1024 / 1024:.1f} MB)'
    
    return False, f'无法验证文件有效性 ({size / 1024:.0f} KB)'


def main():
    print('=' * 55)
    print('  Silero VAD 模型下载工具')
    print('=' * 55)
    print(f'目标路径: {OUTPUT_PATH}\n')
    
    # 检查是否已存在
    if os.path.exists(OUTPUT_PATH):
        valid, msg = validate_model()
        if valid:
            print(f'✅ 模型已存在: {msg}')
            return True
        else:
            print(f'⚠️ 已有文件但无效: {msg}')
            print('   重新下载...\n')
            os.remove(OUTPUT_PATH)
    
    # 尝试从各个源下载
    for i, source in enumerate(DOWNLOAD_SOURCES):
        print(f'[{i+1}/{len(DOWNLOAD_SOURCES)}] 尝试: {source["name"]}')
        print(f'    URL: {source["url"][:70]}...')
        
        size = download_file(source['url'])
        
        if size == 0:
            print()
            continue
        
        valid, msg = validate_model()
        if valid:
            print(f'✅ 下载成功！{msg}')
            print(f'   路径: {OUTPUT_PATH}')
            return True
        else:
            print(f'❌ {msg}')
            if os.path.exists(OUTPUT_PATH):
                os.remove(OUTPUT_PATH)
            print()
            # 短暂等待后尝试下一个源
            time.sleep(2)
    
    # 所有源都失败
    print('=' * 55)
    print('❌ 所有下载源均失败！')
    print()
    print('可能的解决方案:')
    print('1. 检查网络连接')
    print('2. 使用 VPN 或代理')
    print('3. 手动下载:')
    print('   - 访问: https://huggingface.co/snakers4/silero-vad/tree/main')
    print('   - 下载 files/silero_vad.onnx')
    print(f'   - 保存到: {OUTPUT_PATH}')
    print()
    print('4. 使用 PyTorch Hub 自动下载:')
    print('   import torch')
    print('   model, utils = torch.hub.load("snakers4/silero-vad", "silero_vad")')
    print('=' * 55)
    return False


if __name__ == '__main__':
    # 创建目录
    os.makedirs(MODELS_DIR, exist_ok=True)
    
    success = main()
    sys.exit(0 if success else 1)
