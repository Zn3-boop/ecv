"""
使用智谱AI API测试
API: https://open.bigmodel.cn/api/paas/v4
Key: 从环境变量 ZHIPU_API_KEY 读取
"""
import requests
import subprocess
import os
import time

print("=" * 70)
print("使用智谱AI API测试")
print("=" * 70)

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
API_KEY = os.environ.get("ZHIPU_API_KEY")

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

os.makedirs("D:/AI_Generated_Pages", exist_ok=True)
os.makedirs("D:/AI_Thesis", exist_ok=True)

# 任务1: 登录页面
print("\n[任务1] 生成登录页面")

login_prompt = """用HTML生成登录页面代码，包含用户名、密码输入框和登录按钮，渐变风格，响应式设计。直接输出HTML代码，不要解释。"""

data1 = {
    "model": "glm-4-flash",
    "messages": [{"role": "user", "content": login_prompt}],
    "temperature": 0.7,
    "max_tokens": 2048
}

try:
    print("正在生成登录页面...")
    r1 = requests.post(API_URL, headers=headers, json=data1, timeout=120)
    print(f"状态: {r1.status_code}")
    
    if r1.status_code == 200:
        result1 = r1.json()
        content1 = result1['choices'][0]['message']['content']
        print(f"✅ 生成成功，长度: {len(content1)} 字符")
        
        with open("D:/AI_Generated_Pages/zhipu_login.html", "w", encoding="utf-8") as f:
            f.write(content1)
        print("✅ 已保存: D:/AI_Generated_Pages/zhipu_login.html")
        
        subprocess.Popen(["code", "--new-window", "D:/AI_Generated_Pages/zhipu_login.html"], shell=True)
        print("✅ VSCode已打开")
        
        subprocess.Popen(["start", "", "D:/AI_Generated_Pages/zhipu_login.html"], shell=True)
        print("✅ 浏览器已打开")
    else:
        print(f"❌ 错误: {r1.text[:300]}")
except Exception as e:
    print(f"❌ 失败: {e}")

# 任务2: 论文
print("\n[任务2] 生成论文 + 搜索毕设")

subprocess.Popen(["start", "msedge", "-new-window", 
                 "https://www.bing.com/search?q=计算机科学毕业设计选题"], shell=True)
print("✅ 浏览器已打开毕设搜索页面")

time.sleep(2)

thesis_prompt = """撰写计算机论文引言，约1000字，主题：基于人工智能的智能推荐系统研究。包含：1)研究背景与意义 2)国内外研究现状 3)研究目标与内容 4)论文结构安排。学术格式，直接输出内容。"""

data2 = {
    "model": "glm-4-flash",
    "messages": [{"role": "user", "content": thesis_prompt}],
    "temperature": 0.7,
    "max_tokens": 1024
}

try:
    print("正在生成论文...")
    r2 = requests.post(API_URL, headers=headers, json=data2, timeout=120)
    print(f"状态: {r2.status_code}")
    
    if r2.status_code == 200:
        result2 = r2.json()
        thesis = result2['choices'][0]['message']['content']
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
            doc.SaveAs("D:/AI_Thesis/zhipu_thesis.docx")
            print("✅ 已保存: D:/AI_Thesis/zhipu_thesis.docx")
            
            print("\n预览:", thesis[:400])
        except Exception as e:
            print(f"Word失败: {e}")
    else:
        print(f"❌ 错误: {r2.text[:300]}")
except Exception as e:
    print(f"❌ 失败: {e}")

print("\n" + "=" * 70)
print("✅ 测试完成！")
print("=" * 70)