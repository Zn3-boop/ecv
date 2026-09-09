"""调试解析问题"""
import subprocess
import re

cmd = 'winget search "ChatGPT" --accept-source-agreements'
result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
output = result.stdout

print(f"Return code: {result.returncode}")
print(f"Output length: {len(output)}")
print("=" * 50)
print("原始输出前500字符:")
print(output[:500])
print("=" * 50)

# 尝试解析
apps = []
lines = output.split('\n')
print(f"总行数: {len(lines)}")
print("前10行:")
for i, line in enumerate(lines[:10]):
    print(f"{i}: '{line}'")
