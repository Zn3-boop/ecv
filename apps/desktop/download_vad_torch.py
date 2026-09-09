#!/usr/bin/env python3
"""
使用 PyTorch Hub 下载 Silero VAD 模型
这个脚本需要系统中已安装 torch 和 torchaudio
"""

import os
import sys
import torch

# 模型保存路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(SCRIPT_DIR, 'models')
OUTPUT_PATH = os.path.join(MODEL_DIR, 'silero_vad.onnx')

def download_via_torch_hub():
    """通过 PyTorch Hub 下载模型"""
    print('=' * 55)
    print('  Silero VAD - PyTorch Hub 下载')
    print('=' * 55)
    
    os.makedirs(MODEL_DIR, exist_ok=True)
    
    try:
        print('\n正在从 PyTorch Hub 加载模型...')
        print('这会自动下载 JIT 格式的模型到缓存目录')
        
        # 加载模型（会下载 JIT 格式到 ~/.cache/torch/hub/）
        model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            trust_repo=True
        )
        
        print('✅ JIT 模型加载成功！')
        
        # 获取 JIT 模型路径
        cache_dir = os.path.expanduser('~/.cache/torch/hub/snakers4_silero-vad_master')
        jit_file = os.path.join(cache_dir, 'files', 'silero_vad.jit')
        
        if os.path.exists(jit_file):
            print(f'\nJIT 模型路径: {jit_file}')
            print(f'JIT 模型大小: {os.path.getsize(jit_file) / 1024 / 1024:.1f} MB')
        else:
            # 尝试其他可能的路径
            jit_file = os.path.join(cache_dir, 'silero_vad.jit')
            if os.path.exists(jit_file):
                print(f'\nJIT 模型路径: {jit_file}')
            else:
                print(f'\n⚠️ 未找到 JIT 模型文件')
                print(f'缓存目录: {cache_dir}')
                # 列出缓存目录内容
                if os.path.exists(cache_dir):
                    print('缓存目录内容:')
                    for item in os.listdir(cache_dir):
                        print(f'  - {item}')
        
        print('\n注意: Electron 应用需要 ONNX 格式的模型')
        print('JIT 格式需要手动转换为 ONNX')
        print('\n转换方法（如果需要）:')
        print('1. 使用 onnxruntime 或 torch.onnx.export')
        print('2. 或者使用 silero-vad 包的导出功能')
        
        return True
        
    except Exception as e:
        print(f'\n❌ 下载失败: {e}')
        return False


def check_torch_installation():
    """检查 torch 是否安装"""
    try:
        import torch
        print(f'✅ PyTorch 版本: {torch.__version__}')
        
        try:
            import torchaudio
            print(f'✅ Torchaudio 版本: {torchaudio.__version__}')
        except ImportError:
            print('⚠️ Torchaudio 未安装，模型可能无法加载')
            print('  运行: pip install torchaudio')
        
        return True
    except ImportError:
        print('❌ PyTorch 未安装')
        print('\n安装 PyTorch (CPU 版本):')
        print('  pip install torch torchaudio')
        print('\n或安装 GPU 版本 (需要 CUDA):')
        print('  pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118')
        return False


if __name__ == '__main__':
    print('检查 PyTorch 安装...')
    
    if not check_torch_installation():
        sys.exit(1)
    
    success = download_via_torch_hub()
    sys.exit(0 if success else 1)
