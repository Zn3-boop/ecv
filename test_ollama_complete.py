"""
使用本地Ollama完成测试
"""
import requests
import subprocess
import os
import time

print("=" * 70)
print("使用本地Ollama完成测试")
print("=" * 70)

API_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b"

os.makedirs("D:/AI_Generated_Pages", exist_ok=True)
os.makedirs("D:/AI_Thesis", exist_ok=True)

# 任务1: 登录页面
print("\n[任务1] 生成登录页面")

login_prompt = """用HTML生成登录页面代码，包含用户名、密码输入框和登录按钮，渐变风格，响应式设计。直接输出HTML代码，不要解释。"""

print(f"使用模型: {MODEL}")
print("正在生成登录页面...")

try:
    r = requests.post(API_URL, json={
        "model": MODEL,
        "prompt": login_prompt,
        "stream": False
    }, timeout=120)
    
    if r.status_code == 200:
        content = r.json()['response']
        print(f"✅ 生成成功，长度: {len(content)} 字符")
        
        with open("D:/AI_Generated_Pages/ollama_login.html", "w", encoding="utf-8") as f:
            f.write(content)
        print("✅ 已保存: D:/AI_Generated_Pages/ollama_login.html")
        
        subprocess.Popen(["code", "--new-window", "D:/AI_Generated_Pages/ollama_login.html"], shell=True)
        print("✅ VSCode已打开")
        
        subprocess.Popen(["start", "", "D:/AI_Generated_Pages/ollama_login.html"], shell=True)
        print("✅ 浏览器已打开")
    else:
        print(f"❌ 错误: {r.status_code}")
except Exception as e:
    print(f"❌ 失败: {e}")

# 任务2: 论文
print("\n[任务2] 生成论文 + 搜索毕设")

subprocess.Popen(["start", "msedge", "-new-window", 
                 "https://www.bing.com/search?q=计算机科学毕业设计选题"], shell=True)
print("✅ 浏览器已打开毕设搜索页面")

time.sleep(2)

thesis_prompt = "撰写计算机论文引言，约1000字，主题：基于人工智能的智能推荐系统研究。包含研究背景、国内外现状、研究目标。学术格式，直接输出内容。"

try:
    print("正在生成论文...")
    r = requests.post(API_URL, json={
        "model": MODEL,
        "prompt": thesis_prompt,
        "stream": False
    }, timeout=120)
    
    if r.status_code == 200:
        thesis = r.json()['response']
        print(f"✅ 生成成功，长度: {len(thesis)} 字符")
        
        try:
            import pythoncom, win32com.client
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
            word.Selection.TypeParagraph()
            word.Selection.TypeText(thesis)
            
            print("✅ 论文已写入Word")
            doc.SaveAs("D:/AI_Thesis/ollama_thesis.docx")
            print("✅ 已保存: D:/AI_Thesis/ollama_thesis.docx")
            
            print("\n预览:", thesis[:400])
        except Exception as e:
            print(f"Word失败: {e}")
    else:
        print(f"❌ 错误: {r.status_code}")
except Exception as e:
    print(f"❌ 失败: {e}")

print("\n" + "=" * 70)
print("✅ 测试完成！")
print("=" * 70)
