"""
使用SiliconFlow API进行测试
SiliconFlow API配置：
- API URL: https://api.siliconflow.cn/v1/chat/completions
- 需要API Key（可以免费注册获取）
"""
import requests

print("=" * 70)
print("使用SiliconFlow API测试")
print("=" * 70)

# SiliconFlow API配置
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
API_KEY = input("请输入您的SiliconFlow API Key: ").strip()

if not API_KEY:
    print("未提供API Key，跳过测试")
    exit()

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# 测试1: 生成登录页面
print("\n[测试1] 使用SiliconFlow生成登录页面...")

login_page_prompt = """请用HTML生成一个精美的登录页面代码，要求：
1. 包含用户名、密码输入框和登录按钮
2. 现代渐变风格，科技感
3. 响应式设计，适配移动端
4. 直接给我完整可保存的HTML代码，包含内联CSS和JS"""

data = {
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [{"role": "user", "content": login_page_prompt}],
    "temperature": 0.7,
    "max_tokens": 4096
}

try:
    r = requests.post(API_URL, headers=headers, json=data, timeout=60)
    print(f"状态: {r.status_code}")
    
    if r.status_code == 200:
        result = r.json()
        content = result['choices'][0]['message']['content']
        print(f"生成成功，代码长度: {len(content)} 字符")
        
        # 保存到文件
        with open("D:/AI_Generated_Pages/siliconflow_login.html", "w", encoding="utf-8") as f:
            f.write(content)
        print("✅ 登录页面已保存到 D:/AI_Generated_Pages/siliconflow_login.html")
        
        # 用浏览器打开
        import subprocess
        subprocess.Popen(["start", "", "D:/AI_Generated_Pages/siliconflow_login.html"], shell=True)
        print("✅ 浏览器已打开预览")
    else:
        print(f"错误: {r.text}")
except Exception as e:
    print(f"请求失败: {e}")

# 测试2: 生成论文
print("\n[测试2] 使用SiliconFlow生成论文...")

thesis_prompt = """请帮我撰写一篇计算机科学专业的毕业论文引言部分，要求：
1. 主题：基于人工智能的智能推荐系统研究
2. 字数要求：约1000字
3. 内容包括：研究背景与意义、国内外研究现状、研究目标与内容、论文结构安排
4. 学术论文格式，专业术语准确"""

data2 = {
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [{"role": "user", "content": thesis_prompt}],
    "temperature": 0.7,
    "max_tokens": 2048
}

try:
    r2 = requests.post(API_URL, headers=headers, json=data2, timeout=60)
    print(f"状态: {r2.status_code}")
    
    if r2.status_code == 200:
        result2 = r2.json()
        thesis_content = result2['choices'][0]['message']['content']
        print(f"生成成功，内容长度: {len(thesis_content)} 字符")
        
        # 打开Word
        import pythoncom
        import win32com.client
        import time
        
        # 先打开浏览器搜索毕设资料
        import subprocess
        subprocess.Popen(["start", "msedge", "-new-window", 
                         "https://www.bing.com/search?q=计算机科学毕业设计选题推荐"], 
                        shell=True)
        print("✅ 浏览器已打开毕设搜索页面")
        time.sleep(2)
        
        # 打开Word
        pythoncom.CoInitialize()
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = True
        doc = word.Documents.Add()
        
        # 写入标题和内容
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
        
        # 保存文档
        import os
        os.makedirs("D:/AI_Thesis", exist_ok=True)
        doc.SaveAs("D:/AI_Thesis/siliconflow_thesis.docx")
        print("✅ 论文已保存到 D:/AI_Thesis/siliconflow_thesis.docx")
    else:
        print(f"错误: {r2.text}")
except Exception as e:
    print(f"请求失败: {e}")

print("\n" + "=" * 70)
print("测试完成！")
print("=" * 70)
