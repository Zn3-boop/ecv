import requests
r = requests.put('http://localhost:8000/provider/openrouter', json={'model': 'qwen/qwen3-coder:free'})
print(r.json())
