"""测试ChatGPT搜索"""
import requests

r = requests.post('http://localhost:8000/store/search', json={'query': 'ChatGPT'}, timeout=60)
print(f'Status: {r.status_code}')
data = r.json()
print(f"成功: {data.get('success')}")
print(f"消息: {data.get('message')}")
apps = data.get('apps', [])
print(f"应用数量: {len(apps)}")
for a in apps[:5]:
    print(f"  - {a.get('name')}: {a.get('id')}")
