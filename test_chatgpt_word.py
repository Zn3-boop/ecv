"""测试删除ChatGPT和用Word打开文件"""
import requests

base_url = 'http://localhost:8000'

print('='*60)
print('测试1: 搜索ChatGPT')
print('='*60)
r = requests.post(f'{base_url}/store/search', json={'query': 'ChatGPT'}, timeout=30)
print(f'Status: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    print(f'成功: {data.get("success")}')
    print(f'消息: {data.get("message")}')
    for app in data.get('apps', [])[:10]:
        print(f'  - {app.get("name")}: {app.get("id")}')

print()
print('='*60)
print('测试2: 查找已安装应用中的ChatGPT')
print('='*60)
r = requests.get(f'{base_url}/store/installed', timeout=30)
if r.status_code == 200:
    data = r.json()
    apps = data.get('apps', [])
    found_chatgpt = [a for a in apps if 'chatgpt' in a.get('name', '').lower() or 'chatgpt' in a.get('id', '').lower()]
    if found_chatgpt:
        print(f'找到 {len(found_chatgpt)} 个ChatGPT相关应用:')
        for app in found_chatgpt[:10]:
            print(f'  - {app.get("name")}: {app.get("id")}')
    else:
        print('未找到已安装的ChatGPT')

print()
print('='*60)
print('测试3: 用Word打开文件测试')
print('='*60)
r = requests.post(f'{base_url}/system-app/nlp',
    json={'command': '打开Word'}, timeout=10)
print(f'Status: {r.status_code}')
if r.status_code == 200:
    data = r.json()
    print(f'识别意图: {data.get("intent")}')
    print(f'执行结果: {data.get("result")}')

print()
print('='*60)
print('测试4: 测试Word路径解析')
print('='*60)
# 测试系统应用控制器的路径解析
from apps.server.app.services.system_app_controller import parse_app_intent

test_commands = [
    '用Word打开 D:\\test.docx',
    '打开Word',
    'word打开 C:\\Users\\test\\文档.docx'
]

for cmd in test_commands:
    action = parse_app_intent(cmd)
    if action:
        print(f'命令: {cmd}')
        print(f'  类型: {action.type}')
        print(f'  参数: {action.params}')
        print(f'  描述: {action.description}')
    else:
        print(f'命令: {cmd} - 无法解析')
    print()
