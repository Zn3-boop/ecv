import requests
r = requests.post('http://127.0.0.1:8000/content/generate', json={
    'task': '测试Word生成',
    'content_type': 'word',
    'auto_open': False
})
import json
print(json.dumps(r.json(), indent=2, ensure_ascii=False))
