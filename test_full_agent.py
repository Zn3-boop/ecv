"""完整Agent功能测试 - 不需要Electron"""
import requests
import os
import subprocess
import time

base = "http://localhost:8000"

print("=" * 60)
print("测试1: 打开VSCode新窗口")
print("=" * 60)
r = requests.post(f'{base}/desktop/open', json={"path_or_name": "code"})
print(f"状态: {r.status_code}")
print(f"结果: {r.json()}")

print()
print("=" * 60)
print("测试2: 创建登录页面文件")
print("=" * 60)

# HTML内容
html_content = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>用户登录</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .login-container {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.2);
            width: 100%;
            max-width: 400px;
        }
        h2 { text-align: center; color: #333; margin-bottom: 30px; }
        .input-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #555; font-weight: 500; }
        input {
            width: 100%; padding: 12px; border: 1px solid #ddd;
            border-radius: 5px; font-size: 14px; transition: border-color 0.3s;
        }
        input:focus { outline: none; border-color: #667eea; }
        .btn-login {
            width: 100%; padding: 12px; background: linear-gradient(135deg, #667eea, #764ba2);
            color: white; border: none; border-radius: 5px; font-size: 16px;
            cursor: pointer; transition: transform 0.2s;
        }
        .btn-login:hover { transform: translateY(-2px); }
        .links { margin-top: 20px; text-align: center; }
        .links a { color: #667eea; text-decoration: none; margin: 0 10px; }
        .links a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="login-container">
        <h2>用户登录</h2>
        <form>
            <div class="input-group">
                <label>用户名</label>
                <input type="text" placeholder="请输入用户名" required>
            </div>
            <div class="input-group">
                <label>密码</label>
                <input type="password" placeholder="请输入密码" required>
            </div>
            <button type="submit" class="btn-login">登 录</button>
        </form>
        <div class="links">
            <a href="#">注册账号</a>
            <a href="#">忘记密码</a>
        </div>
    </div>
</body>
</html>
'''

# 创建目录和文件
folder = r"D:\TestFolder"
os.makedirs(folder, exist_ok=True)
filepath = os.path.join(folder, "login.html")
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(html_content)
print(f"文件已创建: {filepath}")

# 用VSCode打开
print()
print("用VSCode打开文件...")
r = requests.post(f'{base}/desktop/file/open', json={
    "file_path": filepath,
    "app_name": "code"
})
print(f"状态: {r.status_code}, 结果: {r.json()}")

# 用浏览器打开预览
print()
print("用浏览器打开预览...")
r = requests.post(f'{base}/browser/search', json={
    "query": "login page preview",  # 这个会打开默认浏览器
    "browser": "default"
})
print(f"状态: {r.status_code}, 结果: {r.json()}")

print()
print("=" * 60)
print("测试3: 浏览器搜索计算机毕设")
print("=" * 60)
r = requests.post(f'{base}/browser/nlp', json={
    "command": "帮我搜索计算机毕设论文模板"
})
print(f"状态: {r.status_code}")
data = r.json()
print(f"意图: {data.get('intent', {})}")
print(f"执行结果: {data.get('result', {})}")

print()
print("=" * 60)
print("测试4: 创建Word论文文档")
print("=" * 60)
try:
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = True
    
    doc = word.Documents.Add()
    
    # 写入论文标题
    word.Selection.TypeText("计算机科学与技术专业毕业论文\n\n")
    word.Selection.TypeText("题目：基于人工智能的智能问答系统设计与实现\n\n")
    
    # 写入摘要
    word.Selection.TypeText("摘要\n")
    word.Selection.TypeText("随着人工智能技术的快速发展，智能问答系统已成为人机交互的重要方式。本文设计并实现了一个基于深度学习的智能问答系统，采用Transformer架构进行语义理解，实现了高质量的问答服务。实验结果表明，该系统能够准确理解用户问题并给出合理回答。\n\n")
    
    # 写入正文
    word.Selection.TypeText("关键词：人工智能；问答系统；深度学习；自然语言处理\n\n")
    word.Selection.TypeText("1 引言\n")
    word.Selection.TypeText("随着互联网的普及和人工智能技术的发展，人们获取信息的方式发生了巨大变化。传统的搜索引擎需要用户自己筛选信息，而智能问答系统能够直接理解用户问题并给出精准答案，大大提升了用户体验。本研究旨在设计一个基于深度学习的智能问答系统，为用户提供更加智能化的信息服务。\n\n")
    word.Selection.TypeText("2 系统设计\n")
    word.Selection.TypeText("本系统采用B/S架构，主要包括前端交互层、业务逻辑层和数据存储层。前端使用Vue.js框架构建响应式界面，后端采用Python Flask框架，数据存储使用MySQL数据库。问答核心算法采用BERT模型进行语义表示，通过余弦相似度计算问题匹配度。\n\n")
    word.Selection.TypeText("3 系统实现\n")
    word.Selection.TypeText("系统实现了问题解析、答案检索、结果排序等功能模块。用户输入问题后，系统首先进行分词和词性标注，然后通过BERT模型获取问题向量表示，在答案库中进行相似度搜索，最终返回排序后的答案列表。\n\n")
    word.Selection.TypeText("4 实验结果\n")
    word.Selection.TypeText("通过1000组测试数据进行实验，系统的问题理解准确率达到92.5%，答案匹配准确率达到88.3%，平均响应时间为0.3秒。实验表明，该系统能够满足实际应用需求。\n\n")
    word.Selection.TypeText("5 结论\n")
    word.Selection.TypeText("本文设计并实现了一个基于深度学习的智能问答系统，实验结果表明该系统具有良好的性能和实用性。未来工作将探索多轮对话和知识图谱的融合，进一步提升系统的智能化水平。\n\n")
    word.Selection.TypeText("参考文献\n")
    word.Selection.TypeText("[1] 周志华. 机器学习[M]. 清华大学出版社, 2016.\n")
    word.Selection.TypeText("[2] Devlin J, et al. BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding[J]. arXiv, 2018.\n")
    
    # 保存文档
    doc_path = r"D:\TestFolder\计算机毕设论文.docx"
    doc.SaveAs(doc_path)
    print(f"Word文档已创建并保存: {doc_path}")
    print("请查看Word窗口")
    
except Exception as e:
    print(f"Word操作失败: {e}")

print()
print("=" * 60)
print("✅ 所有测试完成！")
print("=" * 60)
