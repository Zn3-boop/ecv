"""
使用Groq API进行测试（完全免费，速度极快）
Groq API配置：
- API URL: https://api.groq.com/openai/v1/chat/completions
- 模型: llama-3.1-8b-instant (免费)
- 需要API Key: https://console.groq.com/keys
"""
import requests
import subprocess
import os

print("=" * 70)
print("使用Groq API测试（免费高速）")
print("=" * 70)

# Groq API配置
API_URL = "https://api.groq.com/openai/v1/chat/completions"
API_KEY = "gsk_xxxxx"  # 用户需要替换为自己的API Key

print("\nGroq API配置信息:")
print("- API URL: https://api.groq.com/openai/v1/chat/completions")
print("- 免费模型: llama-3.1-8b-instant")
print("- 获取Key: https://console.groq.com/keys")

# 检查是否有API Key
if API_KEY == "gsk_xxxxx":
    print("\n⚠️ 请先获取Groq API Key:")
    print("1. 访问 https://console.groq.com/keys")
    print("2. 注册并登录")
    print("3. 创建API Key")
    print("4. 替换脚本中的API_KEY变量")
    
    # 打开网页
    subprocess.Popen(["start", "msedge", "https://console.groq.com/keys"], shell=True)
    print("✅ 已打开Groq注册页面")
    exit()

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# 创建文件夹
os.makedirs("D:/AI_Generated_Pages", exist_ok=True)
os.makedirs("D:/AI_Thesis", exist_ok=True)

# ===== 任务1: 生成登录页面 =====
print("\n" + "=" * 70)
print("[任务1] 使用Groq生成登录页面")
print("=" * 70)

login_prompt = """请用HTML生成一个精美的登录页面代码，要求：
1. 包含用户名、密码输入框和登录按钮
2. 现代渐变风格，科技感
3. 响应式设计，适配移动端
4. 直接给我完整可保存的HTML代码，包含内联CSS和JS
5. 不要任何解释，直接输出HTML代码"""

data1 = {
    "model": "llama-3.1-8b-instant",
    "messages": [{"role": "user", "content": login_prompt}],
    "temperature": 0.7,
    "max_tokens": 4096
}

try:
    print("正在生成登录页面...")
    r1 = requests.post(API_URL, headers=headers, json=data1, timeout=30)
    print(f"状态: {r1.status_code}")
    
    if r1.status_code == 200:
        result1 = r1.json()
        content1 = result1['choices'][0]['message']['content']
        print(f"✅ 生成成功，代码长度: {len(content1)} 字符")
        
        # 保存HTML文件
        with open("D:/AI_Generated_Pages/groq_login.html", "w", encoding="utf-8") as f:
            f.write(content1)
        print("✅ 已保存到 D:/AI_Generated_Pages/groq_login.html")
        
        # 用VSCode打开
        subprocess.Popen(["code", "D:/AI_Generated_Pages/groq_login.html"], shell=True)
        print("✅ VSCode已打开文件")
        
        # 用浏览器打开
        subprocess.Popen(["start", "", "D:/AI_Generated_Pages/groq_login.html"], shell=True)
        print("✅ 浏览器已打开预览")
        
    elif r1.status_code == 401:
        print("❌ API Key无效，请检查是否正确配置")
    else:
        print(f"❌ 错误: {r1.text[:200]}")
        
except Exception as e:
    print(f"❌ 请求失败: {e}")

# ===== 任务2: 生成论文 =====
print("\n" + "=" * 70)
print("[任务2] 使用Groq生成论文 + 浏览器搜索")
print("=" * 70)

thesis_prompt = """请帮我撰写一篇计算机科学专业的毕业论文引言部分，要求：
1. 主题：基于人工智能的智能推荐系统研究
2. 字数要求：约1000字
3. 内容包括：
   - 研究背景与意义
   - 国内外研究现状  
   - 研究目标与内容
   - 论文结构安排
4. 学术论文格式，专业术语准确
5. 直接输出论文内容，不需要标题"""

data2 = {
    "model": "llama-3.1-8b-instant",
    "messages": [{"role": "user", "content": thesis_prompt}],
    "temperature": 0.7,
    "max_tokens": 2048
}

try:
    print("正在生成论文...")
    
    # 打开浏览器搜索毕设资料
    subprocess.Popen(["start", "msedge", "-new-window", 
                     "https://www.bing.com/search?q=计算机科学毕业设计选题推荐+2024"], 
                    shell=True)
    print("✅ 浏览器已打开毕设搜索页面")
    
    r2 = requests.post(API_URL, headers=headers, json=data2, timeout=30)
    print(f"状态: {r2.status_code}")
    
    if r2.status_code == 200:
        result2 = r2.json()
        thesis_content = result2['choices'][0]['message']['content']
        print(f"✅ 生成成功，内容长度: {len(thesis_content)} 字符")
        
        # 打开Word
        import pythoncom
        import win32com.client
        import time
        
        time.sleep(1)
        
        pythoncom.CoInitialize()
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = True
        doc = word.Documents.Add()
        
        # 写入论文标题
        word.Selection.TypeText("基于人工智能的智能推荐系统研究")
        word.Selection.Font.Size = 16
        word.Selection.Font.Bold = True
        word.Selection.TypeParagraph()
        word.Selection.TypeParagraph()
        
        # 写入引言标记
        word.Selection.TypeText("【引言】")
        word.Selection.Font.Bold = True
        word.Selection.Font.Size = 14
        word.Selection.TypeParagraph()
        word.Selection.TypeParagraph()
        
        # 写入论文内容
        word.Selection.TypeText(thesis_content)
        
        print("✅ 论文已写入Word")
        
        # 保存文档
        doc.SaveAs("D:/AI_Thesis/groq_thesis.docx")
        print("✅ 论文已保存到 D:/AI_Thesis/groq_thesis.docx")
        
        # 显示内容预览
        print("\n" + "-" * 50)
        print("论文内容预览:")
        print("-" * 50)
        print(thesis_content[:800])
        if len(thesis_content) > 800:
            print("...\n(内容已截断)")
        
    elif r2.status_code == 401:
        print("❌ API Key无效")
    else:
        print(f"❌ 错误: {r2.text[:200]}")
        
except Exception as e:
    print(f"❌ 请求失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("✅ 测试完成！")
print("=" * 70)
print("\n📋 测试结果汇总:")
print("1. 登录页面: D:/AI_Generated_Pages/groq_login.html")
print("2. 论文文档: D:/AI_Thesis/groq_thesis.docx")
print("3. 浏览器已打开毕设搜索页面")
