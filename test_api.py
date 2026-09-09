import requests
r = requests.post('http://127.0.0.1:8000/agent/solve-problems', json={'text': 'CPU占用高', 'session_id': 'test'})
print('Status:', r.status_code)
data = r.json()
print('Solutions:', len(data.get('solutions', [])))
print('Reply:', data.get('reply_text', '')[:100])
