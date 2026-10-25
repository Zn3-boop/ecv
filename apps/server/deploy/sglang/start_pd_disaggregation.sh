#!/bin/bash
# SGLang PD分离启动脚本
# 用法: bash start_pd_disaggregation.sh

set -euo pipefail

CONFIG_DIR="$(cd "$(dirname "$0")" && pwd)"
MODEL="Qwen/Qwen2.5-7B-Instruct"

echo "=== SGLang PD Disaggregation Starting ==="

# 启动 Prefill Worker
echo "Starting Prefill Worker on port 8001..."
python -m sglang.launch_server \
    --model-path "$MODEL" \
    --port 8001 \
    --tp 1 \
    --gpu-memory-utilization 0.95 \
    --max-num-seqs 64 \
    --disable-cuda-graph \
    &

PREFILL_PID=$!
echo "Prefill Worker PID: $PREFILL_PID"

sleep 10

# 启动 Decode Worker
echo "Starting Decode Worker on port 8002..."
python -m sglang.launch_server \
    --model-path "$MODEL" \
    --port 8002 \
    --tp 1 \
    --gpu-memory-utilization 0.90 \
    --max-num-seqs 256 \
    --enable-prefix-caching \
    &

DECODE_PID=$!
echo "Decode Worker PID: $DECODE_PID"

sleep 10

# 启动 Router
echo "Starting PD Router on port 8000..."
python -m sglang.launch_router \
    --prefill-urls "http://localhost:8001" \
    --decode-urls "http://localhost:8002" \
    --host 0.0.0.0 \
    --port 8000 \
    --policy kv_aware

echo "=== SGLang PD Disaggregation Stopped ==="