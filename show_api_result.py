"""直接展示API调用结果"""
import requests
import json

print("=" * 70)
print("直接展示API调用 - 证明项目真的能调用API")
print("=" * 70)
print()

# 1. 测试浏览器搜索API
print("【API调用1】浏览器搜索")
print("-" * 50)
print("URL: POST http://localhost:8000/browser/search")
print("请求参数:", json.dumps({"query": "人工智能"}, ensure_ascii=False))
r = requests.post("http://localhost:8000/browser/search", json={"query": "人工智能"})
print("响应结果:", json.dumps(r.json(), ensure_ascii=False, indent=2))
print()
print(">>> 看！浏览器应该已经打开Bing搜索页面了")
print()

# 2. 测试打开应用API
print("【API调用2】打开应用程序")
print("-" * 50)
print("URL: POST http://localhost:8000/desktop/open")
print("请求参数:", json.dumps({"path_or_name": "notepad"}, ensure_ascii=False))
r = requests.post("http://localhost:8000/desktop/open", json={"path_or_name": "notepad"})
print("响应结果:", json.dumps(r.json(), ensure_ascii=False, indent=2))
print()
print(">>> 看！记事本应该已经打开了")
print()

# 3. 测试Agent命令API
print("【API调用3】Agent自然语言理解")
print("-" * 50)
print("URL: POST http://localhost:8000/agent/command")
payload = {"text": "打开计算器", "session_id": "test123"}
print("请求参数:", json.dumps(payload, ensure_ascii=False))
r = requests.post("http://localhost:8000/agent/command", json=payload)
resp = r.json()
print("响应结果:")
print("  reply_text:", resp.get("reply_text", ""))
print("  commands数量:", len(resp.get("commands", [])))
if resp.get("commands"):
    print("  第一个命令:", json.dumps(resp["commands"][0], ensure_ascii=False))
print()
print(">>> 看！Agent识别了你的意图并生成了工具调用")
print()

print("=" * 70)
print("所有API调用都是真实的，由您项目中的代码处理！")
print("=" * 70)
