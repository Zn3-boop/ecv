#!/bin/bash
# AWQ 量化脚本
# 将FP16模型量化为INT4-AWQ，减少显存占用约60%
# 用法: bash quantize_awq.sh [model_name]

set -euo pipefail

MODEL=${1:-"Qwen/Qwen2.5-7B-Instruct"}
MODEL_BASENAME=$(basename "$MODEL" | tr 'A-Z' 'a-z')
OUTPUT_DIR="./models/${MODEL_BASENAME}-awq-int4"

echo "=== AWQ Quantization ==="
echo "Source Model: $MODEL"
echo "Output Dir:   $OUTPUT_DIR"

python -m awq.entrypoint \
    --model_path "$MODEL" \
    --w4a8 \
    --search_scale \
    --run_awq \
    --save_quantized \
    --output_dir "$OUTPUT_DIR"

echo ""
echo "=== Quantization Complete ==="
echo "Quantized model saved to: $OUTPUT_DIR"
echo ""
echo "To serve the quantized model:"
echo "  bash start_vllm.sh $OUTPUT_DIR"
echo ""
echo "Expected savings:"
echo "  FP16 7B:  ~14GB VRAM"
echo "  AWQ INT4: ~5GB VRAM  (65% reduction)"
echo "  FP16 72B: ~144GB VRAM"
echo "  AWQ INT4: ~40GB VRAM (72% reduction)"