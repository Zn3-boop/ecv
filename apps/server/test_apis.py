"""测试新增的 API 端点"""
import requests
import json

base_url = 'http://localhost:8000'

# 测试1: 健康检查
print('=== 1. 健康检查 ===')
try:
    r = requests.get(f'{base_url}/health', timeout=3)
    print(f'Status: {r.status_code}')
    print(f'Response: {r.json()}')
except Exception as e:
    print(f'Error: {e}')
    print('后端可能未启动，请先运行: cd apps/server && python -m uvicorn app.main:app --reload')

print()

# 测试2: 打开记事本
print('=== 2. 打开记事本 ===')
try:
    r = requests.post(f'{base_url}/system-app/execute', 
        json={'type': 'app:notepad', 'params': {}, 'description': '打开记事本'},
        timeout=5)
    print(f'Status: {r.status_code}')
    print(f'Response: {json.dumps(r.json(), ensure_ascii=False, indent=2)}')
except Exception as e:
    print(f'Error: {e}')

print()

# 测试3: 自然语言打开计算器
print('=== 3. 自然语言打开计算器 ===')
try:
    r = requests.post(f'{base_url}/system-app/nlp',
        json={'command': '打开计算器'},
        timeout=5)
    print(f'Status: {r.status_code}')
    print(f'Response: {json.dumps(r.json(), ensure_ascii=False, indent=2)}')
except Exception as e:
    print(f'Error: {e}')

print()

# 测试4: 浏览器搜索
print('=== 4. 浏览器搜索 ===')
try:
    r = requests.post(f'{base_url}/browser/nlp',
        json={'command': '搜索Python教程'},
        timeout=5)
    print(f'Status: {r.status_code}')
    print(f'Response: {json.dumps(r.json(), ensure_ascii=False, indent=2)}')
except Exception as e:
    print(f'Error: {e}')

print()

# 测试5: 任务过滤
print('=== 5. 任务过滤 ===')
try:
    r = requests.post(f'{base_url}/task-filter/filter',
        json={'tasks': [{'tool': 'process:kill', 'params': {'pid': 1234}}]},
        timeout=5)
    print(f'Status: {r.status_code}')
    print(f'Response: {json.dumps(r.json(), ensure_ascii=False, indent=2)}')
except Exception as e:
    print(f'Error: {e}')

print()
print('=== 测试完成 ===')
