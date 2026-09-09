"""
使用正确的模型ID测试OpenRouter
"""
import requests
import subprocess
import os
import time

print("=" * 70)
print("使用OpenRouter API测试（修正模型ID）")
print("=" * 70)

API_URL = "https://openrouter.ai/api/v1/chat/completions"
API_KEY = os.environ.get("OPENROUTER_API_KEY")

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://github.com",
    "X-Title": "AI-Test"
}

# 使用正确的完整模型ID
MODELS = [
    "meta-llama/llama-3.2-3b-instruct",  # 小型高效
    "google/gemma-2-27b-it",  # Gemma
]

os.makedirs("D:/AI_Generated_Pages", exist_ok=True)
os.makedirs("D:/AI_Thesis", exist_ok=True)

def call_model(model_name, prompt, max_tokens=4096):
    print(f"\n尝试模型: {model_name}")
    
    data = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": max_tokens
    }
    
    try:
        r = requests.post(API_URL, headers=headers, json=data, timeout=120)
        print(f"状态: {r.status_code}")
        
        if r.status_code == 200:
            result = r.json()
            return result['choices'][0]['message']['content']
        else:
            print(f"错误: {r.text[:200]}")
            return None
    except Exception as e:
        print(f"请求失败: {e}")
        return None

# 测试1: 登录页面
print("\n" + "=" * 70)
print("[任务1] 生成登录页面")
print("=" * 70)

login_prompt = """生成一个登录页面的HTML代码，包含用户名密码输入框和登录按钮"""

login_html = None
for model in MODELS:
    login_html = call_model(model, login_prompt, max_tokens=4096)
    if login_html:
        print(f"✅ 成功使用 {model}")
        break

if login_html:
    with open("D:/AI_Generated_Pages/openrouter_login.html", "w", encoding="utf-8") as f:
        f.write(login_html)
    print("✅ 已保存: D:/AI_Generated_Pages/openrouter_login.html")
    
    subprocess.Popen(["code", "D:/AI_Generated_Pages/openrouter_login.html"], shell=True)
    print("✅ VSCode已打开")
    
    subprocess.Popen(["start", "", "D:/AI_Generated_Pages/openrouter_login.html"], shell=True)
    print("✅ 浏览器已打开")

# 测试2: 论文
print("\n" + "=" * 70)
print("[任务2] 生成论文")
print("=" * 70)

subprocess.Popen(["start", "msedge", "-new-window", 
                 "https://www.bing.com/search?q=计算机毕业设计选题"], 
                shell=True)
print("✅ 浏览器已打开搜索页面")

time.sleep(2)

thesis_prompt = "写一篇1000字的计算机论文引言，主题是人工智能推荐系统"

thesis_content = None
for model in MODELS:
    thesis_content = call_model(model, thesis_prompt, max_tokens=2048)
    if thesis_content:
        print(f"✅ 成功使用 {model}")
        break

if thesis_content:
    try:
        import pythoncom
        import win32com.client
        
        pythoncom.CoInitialize()
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = True
        doc = word.Documents.Add()
        
        word.Selection.TypeText("基于人工智能的智能推荐系统研究")
        word.Selection.Font.Size = 16
        word.Selection.Font.Bold = True
        word.Selection.TypeParagraph()
        word.Selection.TypeParagraph()
        word.Selection.TypeText("【引言】")
        word.Selection.Font.Bold = True
        word.Selection.TypeParagraph()
        word.Selection.TypeText(thesis_content)
        
        print("✅ 论文已写入Word")
        doc.SaveAs("D:/AI_Thesis/openrouter_thesis.docx")
        print("✅ 已保存: D:/AI_Thesis/openrouter_thesis.docx")
        
        print("\n预览:")
        print(thesis_content[:600])
        
    except Exception as e:
        print(f"❌ Word失败: {e}")

print("\n✅ 测试完成")