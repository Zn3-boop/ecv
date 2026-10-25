#!/bin/bash
# vLLM 启动脚本 - Qwen2.5-7B-Instruct
# 用法: bash start_vllm.sh [model_name] [gpu_count]

set -euo pipefail

MODEL=${1:-"Qwen/Qwen2.5-7B-Instruct"}
GPU_COUNT=${2:-1}
CONFIG_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== vLLM Starting ==="
echo "Model: $MODEL"
echo "GPU Count: $GPU_COUNT"
echo "Config: $CONFIG_DIR/vllm_config.yaml"

python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" \
    --served-model-name "$(basename $MODEL | tr 'A-Z' 'a-z')" \
    --tensor-parallel-size "$GPU_COUNT" \
    --gpu-memory-utilization 0.90 \
    --max-num-seqs 256 \
    --max-model-len 8192 \
    --enable-prefix-caching \
    --enable-chunked-prefill \
    --cuda-graph-max-bs 16 \
    --kv-cache-dtype fp8_e5m2 \
    --guided-decoding-backend xgrammar \
    --host 0.0.0.0 \
    --port 8001 \
    --disable-log-stats false

echo "=== vLLM Stopped ==="