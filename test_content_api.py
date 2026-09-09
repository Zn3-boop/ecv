"""测试扩展后的内容生成API"""
import requests
import json

print("=" * 70)
print("测试扩展后的内容生成API")
print("=" * 70)
print()

# 测试用例1: 生成HTML登录页面
print("【测试1】生成HTML登录页面")
print("-" * 50)
r = requests.post("http://localhost:8000/content/generate", json={
    "task": "用户登录页面",
    "content_type": "html",
    "style": "现代渐变风格",
    "output_path": "D:/TestFolder/ai_login.html"
})
data = r.json()
print(f"状态: {r.status_code}, 成功: {data.get('success')}")
print(f"输出文件: {data.get('output_file')}")
print(f"内容预览: {data.get('content', '')[:200]}...")
print()

# 测试用例2: 生成Word论文
print("【测试2】生成Word论文")
print("-" * 50)
r = requests.post("http://localhost:8000/content/generate", json={
    "task": "毕业论文",
    "content_type": "word",
    "theme": "人工智能",
    "length": "长",
    "output_path": "D:/TestFolder/ai_thesis.txt"
})
data = r.json()
print(f"状态: {r.status_code}, 成功: {data.get('success')}")
print(f"输出文件: {data.get('output_file')}")
print(f"内容预览: {data.get('content', '')[:300]}...")
print()

# 测试用例3: 生成PPT大纲
print("【测试3】生成PPT大纲")
print("-" * 50)
r = requests.post("http://localhost:8000/content/generate", json={
    "task": "项目汇报PPT",
    "content_type": "ppt",
    "theme": "电商系统",
    "output_path": "D:/TestFolder/ai_ppt_outline.txt"
})
data = r.json()
print(f"状态: {r.status_code}, 成功: {data.get('success')}")
print(f"内容: {data.get('content', '')[:500]}")
print()

# 测试用例4: 打开浏览器并生成内容
print("【测试4】打开浏览器搜索并生成内容")
print("-" * 50)
r = requests.post("http://localhost:8000/content/browser/generate", json={
    "browser_url": "https://www.bing.com/search?q=人工智能发展趋势",
    "task": "总结搜索结果",
    "content_type": "document",
    "theme": "AI发展趋势"
})
data = r.json()
print(f"状态: {r.status_code}")
print(f"浏览器已打开: {data.get('browser_opened', False)}")
print(f"消息: {data.get('message', '')}")
print()

print("=" * 70)
print("✅ 所有API测试完成！")
print("=" * 70)
