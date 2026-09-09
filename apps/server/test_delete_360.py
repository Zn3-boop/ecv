"""测试卸载360和打开Word文件"""
import requests

base_url = 'http://localhost:8000'

# 测试1: 搜索360
print('='*60)
print('测试1: 搜索360')
print('='*60)
r = requests.post(f'{base_url}/store/search', json={'query': '360'}, timeout=30)
print(f'Status: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    print(f'消息: {data.get("message")}')
    for app in data.get('apps', [])[:10]:
        print(f'  - {app.get("name")}: {app.get("id")}')

# 测试2: 获取已安装应用，找360
print()
print('='*60)
print('测试2: 查找已安装的360')
print('='*60)
r = requests.get(f'{base_url}/store/installed', timeout=30)
if r.status_code == 200:
    data = r.json()
    apps = data.get('apps', [])
    found_360 = [a for a in apps if '360' in a.get('name', '').lower() or '360' in a.get('id', '').lower()]
    if found_360:
        print(f'找到 {len(found_360)} 个360相关应用:')
        for app in found_360[:10]:
            print(f'  - {app.get("name")}: {app.get("id")}')
    else:
        print('未找到已安装的360')

# 测试3: 用Word打开文件
print()
print('='*60)
print('测试3: 用Word打开文件')
print('='*60)
r = requests.post(f'{base_url}/system-app/nlp',
    json={'command': '用Word打开 D:\\test.docx'}, timeout=10)
print(f'Status: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    print(f'识别意图: {data.get("intent")}')
    print(f'执行结果: {data.get("result")}')

# 测试4: 直接打开Word
print()
print('='*60)
print('测试4: 打开Word')
print('='*60)
r = requests.post(f'{base_url}/system-app/nlp',
    json={'command': '打开Word'}, timeout=10)
print(f'Status: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    print(f'执行结果: {data.get("result")}')
