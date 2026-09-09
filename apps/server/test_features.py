"""综合功能测试"""
import requests
import json

base_url = 'http://localhost:8000'

def test(name, func):
    print(f'\n{"="*60}')
    print(f'测试: {name}')
    print('='*60)
    try:
        result = func()
        if result:
            print('✅ 通过')
        else:
            print('❌ 失败')
        return result
    except Exception as e:
        print(f'❌ 异常: {e}')
        return False

# 测试1: 截图功能
def test_screenshot():
    print('发送: POST /screenshot/capture')
    r = requests.post(f'{base_url}/screenshot/capture',
        json={'monitor': 1}, timeout=10)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        print(f'文件路径: {data.get("file_path")}')
        print(f'尺寸: {data.get("width")}x{data.get("height")}')
        print(f'消息: {data.get("message")}')
        return True
    return False

# 测试2: Winget状态检查
def test_store_status():
    print('发送: GET /store/status')
    r = requests.get(f'{base_url}/store/status', timeout=10)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        print(f'消息: {data.get("message")}')
        print(f'版本: {data.get("version")}')
        return True
    return False

# 测试3: 搜索应用
def test_store_search():
    print('发送: POST /store/search')
    r = requests.post(f'{base_url}/store/search',
        json={'query': 'vscode'}, timeout=30)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        print(f'消息: {data.get("message")}')
        apps = data.get('apps', [])[:3]  # 只显示前3个
        for app in apps:
            print(f'  - {app.get("name")}: {app.get("id")}')
        return True
    return False

# 测试4: 获取已安装应用
def test_store_list():
    print('发送: GET /store/installed')
    r = requests.get(f'{base_url}/store/installed', timeout=30)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        print(f'消息: {data.get("message")}')
        apps = data.get('apps', [])[:5]  # 只显示前5个
        for app in apps:
            print(f'  - {app.get("name")}')
        return True
    return False

# 测试5: 打开PowerPoint
def test_open_powerpoint():
    print('发送: "打开PowerPoint"')
    r = requests.post(f'{base_url}/system-app/nlp',
        json={'command': '打开PowerPoint'}, timeout=10)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        print(f'识别意图: {data.get("intent")}')
        print(f'执行结果: {data.get("result")}')
        return True
    return False

# 测试6: 打开Word
def test_open_word():
    print('发送: "打开Word"')
    r = requests.post(f'{base_url}/system-app/nlp',
        json={'command': '打开Word'}, timeout=10)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        print(f'识别意图: {data.get("intent")}')
        print(f'执行结果: {data.get("result")}')
        return True
    return False

# 测试7: 打开联想应用商店
def test_lenovo_store():
    print('发送: "打开联想应用商店"')
    r = requests.post(f'{base_url}/system-app/nlp',
        json={'command': '打开联想应用商店'}, timeout=10)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        print(f'识别意图: {data.get("intent")}')
        print(f'执行结果: {data.get("result")}')
        return True
    return False

# 测试8: 打开Microsoft Store
def test_microsoft_store():
    print('发送: "打开微软应用商店"')
    r = requests.post(f'{base_url}/system-app/nlp',
        json={'command': '打开微软应用商店'}, timeout=10)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        print(f'识别意图: {data.get("intent")}')
        print(f'执行结果: {data.get("result")}')
        return True
    return False

# 运行所有测试
print('🚀 开始综合功能测试')
print(f'后端地址: {base_url}')

# 先检查健康状态
r = requests.get(f'{base_url}/health', timeout=3)
if r.status_code != 200:
    print('❌ 后端未启动，请先运行: cd apps/server && python -m uvicorn app.main:app --reload')
    exit(1)
print('✅ 后端运行正常')

results = []
results.append(('截图功能', test_screenshot()))
results.append(('Winget状态检查', test_store_status()))
results.append(('搜索应用(vscode)', test_store_search()))
results.append(('获取已安装应用', test_store_list()))
results.append(('打开PowerPoint', test_open_powerpoint()))
results.append(('打开Word', test_open_word()))
results.append(('打开联想应用商店', test_lenovo_store()))
results.append(('打开Microsoft Store', test_microsoft_store()))

print('\n' + '='*60)
print('📊 测试结果汇总')
print('='*60)
for name, passed in results:
    status = '✅' if passed else '❌'
    print(f'{status} {name}')

passed_count = sum(1 for _, p in results if p)
print(f'\n通过: {passed_count}/{len(results)}')
print('\n💡 注意：部分功能需要在实际Windows环境中验证效果')
