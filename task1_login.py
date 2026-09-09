import requests
import json

# 任务1: 创建登录页面
r = requests.post('http://localhost:8000/agent/execute', json={
    'provider_id': 'ollama',
    'task': '''请创建一个用户登录页面，保存到 D:\TestFolder\login.html
要求：
1. 美观的登录界面
2. 包含用户名和密码输入框
3. 包含登录按钮
4. 包含注册和忘记密码链接
完成后告诉我文件已创建'''
})
print('Task 1:', r.status_code)
if r.status_code == 200:
    data = r.json()
    print('Result:', data.get('result', '')[:500])
