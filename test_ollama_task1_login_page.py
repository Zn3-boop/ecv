"""
Ollama测试任务1: 使用LLM生成登录页面，保存到D盘新文件夹，并打开浏览器查看
"""
import requests
import json
import os
import subprocess

print("=" * 70)
print("任务1: 使用Ollama LLM生成登录页面")
print("=" * 70)

# 1. 确保Ollama Provider已配置
print("\n[1/5] 检查Ollama Provider配置...")

# 先添加或更新ollama provider
provider_config = {
    "id": "ollama",
    "name": "Ollama (本地)",
    "api_url": "http://localhost:11434/v1/chat/completions",
    "api_key": "",
    "model": "qwen2.5:3b",
    "extra": {"temperature": 0.7, "max_tokens": 4096}
}

r = requests.post("http://localhost:8000/provider/", json=provider_config)
print(f"Provider配置响应: {r.json()}")

# 2. 创建D盘新文件夹
print("\n[2/5] 创建D盘新文件夹...")
folder_path = "D:/AI_Generated_Pages"
os.makedirs(folder_path, exist_ok=True)
print(f"✅ 文件夹已创建: {folder_path}")

# 3. 调用Ollama生成登录页面
print("\n[3/5] 调用Ollama生成登录页面HTML...")

prompt = """请用HTML生成一个精美的登录页面代码，要求：
1. 包含用户名、密码输入框和登录按钮
2. 现代渐变风格，科技感
3. 响应式设计，适配移动端
4. 包含表单验证效果
5. 直接给我完整可保存的HTML代码，包含内联CSS和JS
6. 不要解释，直接输出HTML代码"""

r = requests.post("http://localhost:8000/provider/chat", json={
    "provider_id": "ollama",
    "model": "qwen2.5:7b",
    "messages": [
        {"role": "user", "content": prompt}
    ],
    "temperature": 0.7,
    "max_tokens": 4096
})

print(f"API响应状态: {r.status_code}")

if r.status_code == 200:
    data = r.json()
    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
    print(f"LLM生成的代码长度: {len(content)} 字符")
    
    # 4. 保存到文件
    print("\n[4/5] 保存HTML到文件...")
    file_path = f"{folder_path}/login_page.html"
    
    # 清理代码，提取HTML部分
    if "```html" in content:
        start = content.find("```html") + 7
        end = content.rfind("```")
        content = content[start:end].strip()
    elif "```" in content:
        start = content.find("```") + 3
        end = content.rfind("```")
        content = content[start:end].strip()
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"✅ 登录页面已保存到: {file_path}")
    
    # 5. 用VSCode打开文件
    print("\n[5/5] 用VSCode打开文件...")
    subprocess.Popen(["code", file_path], shell=True)
    print("✅ VSCode已打开登录页面")
    
    # 用浏览器打开预览
    print("\n正在用浏览器打开预览...")
    subprocess.Popen(["start", "", file_path], shell=True)
    print("✅ 浏览器已打开登录页面预览")
    
    print("\n" + "=" * 70)
    print("✅ 任务1完成!")
    print(f"📁 文件位置: {file_path}")
    print("=" * 70)
else:
    print(f"❌ 错误: {r.text}")
