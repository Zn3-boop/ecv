"""快速测试Ollama"""
import requests

print("快速测试Ollama...")
r = requests.post("http://localhost:8000/provider/chat", json={
    "provider_id": "ollama",
    "model": "qwen2.5:7b",
    "messages": [{"role": "user", "content": "Hi"}],
    "max_tokens": 20
})
print(f"状态: {r.status_code}")
print(r.text[:500])
