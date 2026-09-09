"""测试搜索ChatGPT和at1文件"""
import requests
import subprocess
import os

base_url = 'http://localhost:8000'

print('='*60)
print('测试1: 通过API搜索ChatGPT (使用--accept-source-agreements)')
print('='*60)
r = requests.post(f'{base_url}/store/search', json={'query': 'ChatGPT'}, timeout=30)
print(f'Status: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    print(f'成功: {data.get("success")}')
    print(f'消息: {data.get("message")}')
    for app in data.get('apps', [])[:5]:
        print(f'  - {app.get("name")}: {app.get("id")}')

print()
print('='*60)
print('测试2: 查找已安装的ChatGPT')
print('='*60)
r = requests.get(f'{base_url}/store/installed', timeout=30)
if r.status_code == 200:
    data = r.json()
    apps = data.get('apps', [])
    found_chatgpt = [a for a in apps if 'chatgpt' in a.get('name', '').lower() or 'chatgpt' in a.get('id', '').lower()]
    if found_chatgpt:
        print(f'找到 {len(found_chatgpt)} 个ChatGPT:')
        for app in found_chatgpt[:10]:
            print(f'  - {app.get("name")}: {app.get("id")}')
    else:
        print('未找到已安装的ChatGPT')

print()
print('='*60)
print('测试3: 用winget直接搜索ChatGPT')
print('='*60)
result = subprocess.run('winget search ChatGPT --accept-source-agreements', 
                       shell=True, capture_output=True, text=True, timeout=30)
print(result.stdout[:2000] if result.stdout else '无输出')
if result.stderr:
    print(f'错误: {result.stderr[:500]}')

print()
print('='*60)
print('测试4: 搜索包含at1的文件')
print('='*60)
for drive in ['C:', 'D:', 'E:']:
    if os.path.exists(f'{drive}\\'):
        print(f'搜索 {drive}\\ 目录...')
        try:
            for root, dirs, files in os.walk(f'{drive}\\', topdown=True):
                # 限制深度
                depth = root.count(os.sep) - f'{drive}\\'.count(os.sep)
                if depth > 5:
                    dirs.clear()
                    continue
                for f in files:
                    if 'at1' in f.lower():
                        print(f'  找到: {os.path.join(root, f)}')
        except Exception as e:
            print(f'  错误: {e}')
