"""直接测试LLM生成内容"""
import requests
import json

print("=" * 70)
print("直接测试LLM生成代码能力")
print("=" * 70)

# 调用 provider 的 chat 功能直接生成内容
r = requests.post("http://localhost:8000/provider/chat", json={
    "provider_id": "ollama",
    "model": "qwen2.5:7b",
    "messages": [
        {"role": "user", "content": "请用HTML生成一个精美的登录页面代码，包含用户名、密码输入框和登录按钮，现代渐变风格，直接给我完整可保存的HTML代码，不需要解释"}
    ]
})

data = r.json()
print(f"状态: {r.status_code}")

if r.status_code == 200:
    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
    print(f"LLM生成的代码长度: {len(content)} 字符")
    print("=" * 70)
    print("LLM生成的HTML代码:")
    print("=" * 70)
    print(content[:2000])  # 显示前2000字符
    print("...")
    
    # 保存到文件
    if "<html" in content.lower() or "<!doctype" in content.lower():
        with open("D:/TestFolder/ai_login_page.html", "w", encoding="utf-8") as f:
            f.write(content)
        print()
        print("=" * 70)
        print("✅ AI生成的内容已保存到 D:/TestFolder/ai_login_page.html")
        print("=" * 70)
else:
    print(f"错误: {data}")
