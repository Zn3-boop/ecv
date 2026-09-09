"""
使用OpenRouter API完整测试（多个免费模型）
API Key: 从环境变量 OPENROUTER_API_KEY 读取
"""
import requests
import subprocess
import os
import time

print("=" * 70)
print("使用OpenRouter API完整测试")
print("=" * 70)

# OpenRouter API配置
API_URL = "https://openrouter.ai/api/v1/chat/completions"
API_KEY = os.environ.get("OPENROUTER_API_KEY")

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://github.com",
    "X-Title": "AI-Test"
}

# 尝试的免费模型列表（按推荐顺序）
MODELS = [
    "moonshotai/kimi-k2.6",
    "meta-llama/llama-3.3-70b-instruct",
    "google/gemma-4-31b-it",
    "nvidia/nemotron-3-nano-9b-v2",
    "liquid/lfm-2.5-1.2b-thinking",
]

# 创建文件夹
os.makedirs("D:/AI_Generated_Pages", exist_ok=True)
os.makedirs("D:/AI_Thesis", exist_ok=True)

def call_model(model_name, prompt, max_tokens=4096):
    """调用模型"""
    print(f"\n正在使用模型: {model_name}")
    
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
        elif r.status_code == 403:
            print(f"❌ 模型 {model_name} 不可用或额度用完")
            return None
        else:
            print(f"❌ 错误: {r.text[:200]}")
            return None
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return None

# ===== 任务1: 生成登录页面 =====
print("\n" + "=" * 70)
print("[任务1] 生成登录页面")
print("=" * 70)

login_prompt = """请用HTML生成一个精美的登录页面代码，要求：
1. 包含用户名、密码输入框和登录按钮
2. 现代渐变风格，科技感
3. 响应式设计，适配移动端
4. 直接给我完整可保存的HTML代码，包含内联CSS和JS
5. 不要任何解释，直接输出HTML代码"""

login_html = None
for model in MODELS:
    print(f"\n尝试模型: {model}")
    login_html = call_model(model, login_prompt, max_tokens=4096)
    if login_html:
        print(f"✅ 成功使用 {model} 生成登录页面")
        break
    print("尝试下一个模型...")

if login_html:
    # 保存HTML文件
    with open("D:/AI_Generated_Pages/openrouter_login.html", "w", encoding="utf-8") as f:
        f.write(login_html)
    print("✅ 已保存到 D:/AI_Generated_Pages/openrouter_login.html")
    
    # 用VSCode打开
    subprocess.Popen(["code", "D:/AI_Generated_Pages/openrouter_login.html"], shell=True)
    print("✅ VSCode已打开文件")
    
    # 用浏览器打开
    subprocess.Popen(["start", "", "D:/AI_Generated_Pages/openrouter_login.html"], shell=True)
    print("✅ 浏览器已打开预览")
else:
    print("❌ 所有模型都失败")

# ===== 任务2: 生成论文 =====
print("\n" + "=" * 70)
print("[任务2] 生成论文 + 搜索毕设资料")
print("=" * 70)

# 先打开浏览器搜索毕设资料
subprocess.Popen(["start", "msedge", "-new-window", 
                 "https://www.bing.com/search?q=计算机科学毕业设计选题推荐+2024"], 
                shell=True)
print("✅ 浏览器已打开毕设搜索页面")

time.sleep(2)

thesis_prompt = """请帮我撰写一篇计算机科学专业的毕业论文引言部分，要求：
1. 主题：基于人工智能的智能推荐系统研究
2. 字数要求：约1000字
3. 内容包括：
   - 研究背景与意义
   - 国内外研究现状  
   - 研究目标与内容
   - 论文结构安排
4. 学术论文格式，专业术语准确
5. 直接输出论文内容"""

thesis_content = None
for model in MODELS:
    print(f"\n尝试模型: {model}")
    thesis_content = call_model(model, thesis_prompt, max_tokens=2048)
    if thesis_content:
        print(f"✅ 成功使用 {model} 生成论文")
        break
    print("尝试下一个模型...")

if thesis_content:
    # 打开Word
    try:
        import pythoncom
        import win32com.client
        
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
        doc.SaveAs("D:/AI_Thesis/openrouter_thesis.docx")
        print("✅ 论文已保存到 D:/AI_Thesis/openrouter_thesis.docx")
        
        # 显示内容预览
        print("\n" + "-" * 50)
        print("论文内容预览:")
        print("-" * 50)
        print(thesis_content[:800])
        if len(thesis_content) > 800:
            print("...\n(内容已截断)")
            
    except Exception as e:
        print(f"❌ Word操作失败: {e}")
        # 保存为txt
        with open("D:/AI_Thesis/openrouter_thesis.txt", "w", encoding="utf-8") as f:
            f.write(thesis_content)
        print("✅ 已保存为txt文件")
else:
    print("❌ 所有模型都失败")

print("\n" + "=" * 70)
print("✅ 测试完成！")
print("=" * 70)
print("\n📋 测试结果汇总:")
print("1. 登录页面: D:/AI_Generated_Pages/openrouter_login.html")
print("2. 论文文档: D:/AI_Thesis/openrouter_thesis.docx")
print("3. 浏览器已打开毕设搜索页面")