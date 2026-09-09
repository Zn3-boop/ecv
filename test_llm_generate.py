"""测试LLM生成内容"""
import requests
import json
import uuid

print("=" * 70)
print("测试LLM生成登录页面HTML代码")
print("=" * 70)

# 直接调用LLM生成内容
r = requests.post("http://localhost:8000/agent/solve-problems", json={
    "text": "生成一个精美的用户登录页面HTML代码",
    "session_id": str(uuid.uuid4())
})

data = r.json()
print(f"状态: {r.status_code}")
print(f"回复: {data.get('reply_text', '')}")
print(f"分析: {data.get('analysis', '')}")
print()

# 看看解决方案
solutions = data.get('solutions', [])
if solutions:
    print("解决方案数量:", len(solutions))
    for sol in solutions:
        print(f"  - {sol.get('title', '未命名')}")
        print(f"    描述: {sol.get('description', '')}")
        print(f"    步骤: {sol.get('steps', [])}")
        print(f"    命令: {[c.get('tool') for c in sol.get('commands', [])]}")
else:
    print("没有解决方案")

print()
print("=" * 70)
print("直接用 /agent/command 看LLM解析")
print("=" * 70)
r2 = requests.post("http://localhost:8000/agent/command", json={
    "text": "生成HTML代码",
    "session_id": str(uuid.uuid4())
})
print(f"回复: {r2.json().get('reply_text', '')}")
