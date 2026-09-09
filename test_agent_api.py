"""测试Agent API的实际能力"""
import requests
import uuid

base = "http://localhost:8000"

# 测试1: 查看系统进程（系统内置能力）
print("=== 测试1: 查看系统进程 ===")
r = requests.post(f'{base}/agent/command', json={
    'text': '查看进程',
    'session_id': str(uuid.uuid4())
})
data = r.json()
print(f"状态: {r.status_code}")
print(f"回复: {data.get('reply_text', '')[:150]}")
print(f"命令数: {len(data.get('commands', []))}")
for cmd in data.get('commands', [])[:3]:
    print(f"  - tool: {cmd.get('tool')}, type: {cmd.get('type')}")

print()
# 测试2: 清理临时文件
print("=== 测试2: 清理临时文件 ===")
r = requests.post(f'{base}/agent/command', json={
    'text': '清理临时文件',
    'session_id': str(uuid.uuid4())
})
data = r.json()
print(f"回复: {data.get('reply_text', '')[:150]}")
print(f"命令数: {len(data.get('commands', []))}")

print()
# 测试3: 打开VSCode（需要Electron运行）
print("=== 测试3: 启动应用 ===")
r = requests.post('http://127.0.0.1:9000/execute', json={
    'tool': 'app:launch',
    'params': {'path': 'code'}
}, timeout=5)
print(f"Electron响应: {r.status_code}")
if r.status_code == 200:
    print(f"结果: {r.json()}")
