"""检查已安装的ChatGPT"""
import requests

r = requests.get('http://localhost:8000/store/installed', timeout=60)
data = r.json()
apps = [a for a in data.get('apps', []) if 'chatgpt' in a.get('name', '').lower() or 'chatgpt' in a.get('id', '').lower()]
print(f'找到 {len(apps)} 个已安装ChatGPT:')
for a in apps:
    print(f"  - {a.get('name')}: {a.get('id')}")
