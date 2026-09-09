"""完整测试：创建登录页面并用VSCode打开，然后用浏览器显示"""
import requests
import os
import subprocess

base = "http://localhost:8000"

# 1. 用Ollama生成登录页面代码
print("=== 1. 生成登录页面HTML ===")
r = requests.post(f'{base}/provider/chat', json={
    'provider_id': 'ollama',
    'messages': [{'role': 'user', 'content': '''生成一个完整的用户登录页面HTML代码。要求：
1. 现代美观的设计，使用渐变背景
2. 包含用户名和密码输入框
3. 包含登录按钮
4. 包含注册和忘记密码链接
5. 响应式设计，适配移动端
直接输出完整的HTML代码，不要任何解释，代码用```html包裹'''}]
})
content = r.json()['choices'][0]['message']['content']
print("生成完成，长度:", len(content))

# 2. 提取HTML代码
if '```html' in content:
    code = content.split('```html')[1].split('```')[0].strip()
elif '```' in content:
    code = content.split('```')[1].strip()
else:
    code = content.strip()

# 3. 创建目录和文件
folder = r"D:\TestFolder"
os.makedirs(folder, exist_ok=True)
filepath = os.path.join(folder, "login.html")
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(code)
print(f"=== 2. 文件已创建: {filepath} ===")

# 4. 打开VSCode
print("=== 3. 打开VSCode ===")
subprocess.Popen(['code', filepath], shell=True)

# 5. 用默认浏览器打开
print("=== 4. 用浏览器打开 ===")
subprocess.Popen(['start', '', filepath], shell=True)

print("\n✅ 完成！VSCode和浏览器应该都已打开登录页面")
