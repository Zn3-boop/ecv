"""测试应用商店和360卸载"""
import requests

base_url = 'http://localhost:8000'

# 1. 搜索360
print('搜索360:')
r = requests.post(f'{base_url}/store/search', json={'query': '360'}, timeout=30)
if r.status_code == 200:
    data = r.json()
    apps = data.get('apps', [])
    print(f'找到 {len(apps)} 个结果')
    for app in apps[:5]:
        print(f'  - {app.get("name")}: {app.get("id")}')

# 2. 查看已安装的应用
print()
print('已安装应用（找360）:')
r = requests.get(f'{base_url}/store/installed', timeout=30)
if r.status_code == 200:
    data = r.json()
    apps = data.get('apps', [])
    found_360 = [a for a in apps if '360' in a.get('name', '').lower() or '360' in a.get('id', '').lower()]
    if found_360:
        print(f'找到 {len(found_360)} 个360相关应用:')
        for app in found_360[:5]:
            print(f'  - {app.get("name")}: {app.get("id")}')
    else:
        print('未找到已安装的360')
