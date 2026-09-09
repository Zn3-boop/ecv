"""测试LLM生成内容 + 系统API保存打开"""
import requests
import json
import os
import subprocess

print("=" * 70)
print("测试完整流程：LLM生成内容 → 保存文件 → 打开查看")
print("=" * 70)
print()

# 1. 直接调用Ollama生成登录页面HTML
print("【步骤1】让Ollama(LLM)生成登录页面HTML代码")
print("-" * 50)

try:
    # 直接调用Ollama API
    r = requests.post("http://localhost:11434/api/generate", json={
        "model": "qwen2.5:7b",
        "prompt": "请用HTML生成一个精美的用户登录页面代码，包含用户名、密码输入框和登录按钮，使用现代渐变背景风格，直接给我完整可保存的HTML代码，只返回代码不要解释",
        "stream": False
    }, timeout=60)
    
    if r.status_code == 200:
        result = r.json()
        html_content = result.get("response", "")
        print(f"LLM生成的内容长度: {len(html_content)} 字符")
        print()
        print("LLM生成的内容预览:")
        print(html_content[:500])
        print("...")
    else:
        print(f"LLM调用失败: {r.status_code}")
        html_content = None
except Exception as e:
    print(f"LLM调用异常: {e}")
    html_content = None

print()

# 2. 保存到文件
if html_content:
    print("【步骤2】保存LLM生成的内容到文件")
    print("-" * 50)
    
    os.makedirs("D:/TestFolder", exist_ok=True)
    file_path = "D:/TestFolder/llm_generated_login.html"
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"文件已保存: {file_path}")
    print(f"文件大小: {os.path.getsize(file_path)} bytes")
    print()

# 3. 用VSCode打开
print("【步骤3】用VSCode打开文件")
print("-" * 50)
r = requests.post("http://localhost:8000/desktop/file/open", json={
    "file_path": file_path,
    "app": "code"
})
print(f"API响应: {r.json()}")
print()

# 4. 用浏览器打开预览
print("【步骤4】用浏览器打开预览")
print("-" * 50)
r = requests.post("http://localhost:8000/browser/search", json={
    "query": "file:///D:/TestFolder/llm_generated_login.html"
})
print(f"API响应: {r.json()}")
print()

print("=" * 70)
print("✅ 完成！请检查：")
print("   1. VSCode应该打开了 D:/TestFolder/llm_generated_login.html")
print("   2. 浏览器应该打开了该文件的预览")
print("=" * 70)
