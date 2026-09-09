import requests
# 先检查WSL IP
import subprocess
result = subprocess.run(['wsl', 'hostname', '-I'], capture_output=True, text=True)
wsl_ip = result.stdout.split()[0] if result.stdout else '127.0.0.1'
print(f"WSL IP: {wsl_ip}")

# 添加Ollama provider
r = requests.post('http://localhost:8000/provider/', json={
    'id': 'ollama',
    'name': 'Ollama (WSL)',
    'api_url': f'http://{wsl_ip}:11434/v1/chat/completions',
    'api_key': 'ollama',
    'model': 'qwen2.5:7b'
})
print('Add:', r.json())

# 测试聊天
r = requests.post('http://localhost:8000/provider/chat', json={
    'provider_id': 'ollama',
    'messages': [{'role': 'user', 'content': 'say hi in 3 words'}]
})
print('Chat:', r.status_code, r.json())
