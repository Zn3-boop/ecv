import requests
# Update model first
r = requests.put('http://localhost:8000/provider/openrouter', json={'model': 'nousresearch/hermes-3-llama-3.1-405b:free'})
print('Update:', r.json())

# Test chat
r = requests.post('http://localhost:8000/provider/chat', json={
    'provider_id': 'openrouter',
    'messages': [{'role': 'user', 'content': 'say hi in 3 words'}]
})
print('Chat:', r.status_code, r.json())
