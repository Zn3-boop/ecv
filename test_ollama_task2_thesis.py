"""
Ollama测试任务2: 打开浏览器搜索计算机毕设资料，打开Word让LLM生成论文
"""
import requests
import json
import os
import subprocess
import pythoncom
import win32com.client
import time

print("=" * 70)
print("任务2: 搜索毕设资料并生成论文")
print("=" * 70)

# 1. 打开浏览器搜索计算机毕设相关资料
print("\n[1/6] 打开浏览器搜索计算机毕设资料...")

search_query = "计算机科学毕业设计选题推荐 2024"
encoded_query = search_query.replace(" ", "+")
search_url = f"https://www.bing.com/search?q={encoded_query}"

# 用Edge打开搜索
subprocess.Popen(["start", "msedge", "-new-window", search_url], shell=True)
print(f"✅ 已在Edge浏览器打开搜索: {search_query}")

time.sleep(3)  # 等待浏览器打开

# 2. 打开Word
print("\n[2/6] 打开Microsoft Word...")

try:
    pythoncom.CoInitialize()
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = True  # 让Word可见
    doc = word.Documents.Add()
    print("✅ Word已打开并创建新文档")
except Exception as e:
    print(f"❌ Word打开失败: {e}")
    word = None
    doc = None

# 3. 调用Ollama生成论文
print("\n[3/6] 调用Ollama生成计算机毕设论文...")

thesis_prompt = """请帮我撰写一篇计算机科学专业的毕业论文引言部分，要求：
1. 主题：基于人工智能的智能推荐系统研究
2. 字数要求：约1000字
3. 内容包括：
   - 研究背景与意义
   - 国内外研究现状
   - 研究目标与内容
   - 论文结构安排
4. 学术论文格式，专业术语准确
5. 直接输出论文内容，不需要标题或说明"""

r = requests.post("http://localhost:8000/provider/chat", json={
    "provider_id": "ollama",
    "model": "qwen2.5:7b",
    "messages": [
        {"role": "user", "content": thesis_prompt}
    ],
    "temperature": 0.7,
    "max_tokens": 4096
})

print(f"API响应状态: {r.status_code}")

if r.status_code == 200:
    data = r.json()
    thesis_content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
    print(f"LLM生成的论文长度: {len(thesis_content)} 字符")
    
    # 4. 在Word中写入论文标题
    print("\n[4/6] 在Word中写入论文内容...")
    
    if doc:
        # 添加标题
        word.Selection.TypeText("基于人工智能的智能推荐系统研究")
        word.Selection.Font.Size = 16
        word.Selection.Font.Bold = True
        word.Selection.TypeParagraph()
        word.Selection.TypeParagraph()
        
        # 添加摘要标记
        word.Selection.TypeText("【引言】")
        word.Selection.Font.Bold = True
        word.Selection.TypeParagraph()
        
        # 清理论文内容中的markdown格式
        content = thesis_content
        content = content.replace("```", "").replace("**", "")
        
        # 添加论文正文
        word.Selection.TypeText(content)
        word.Selection.TypeParagraph()
        
        print("✅ 论文内容已写入Word")
    
    # 5. 保存Word文档
    print("\n[5/6] 保存Word文档...")
    save_path = "D:/AI_Thesis/thesis_introduction.docx"
    os.makedirs("D:/AI_Thesis", exist_ok=True)
    
    if doc:
        try:
            doc.SaveAs(save_path)
            print(f"✅ 论文已保存到: {save_path}")
        except Exception as e:
            print(f"⚠️ 保存失败: {e}")
            # 尝试保存为RTF格式
            save_path_rtf = "D:/AI_Thesis/thesis_introduction.rtf"
            try:
                doc.SaveAs(save_path_rtf)
                print(f"✅ 论文已保存为RTF格式: {save_path_rtf}")
            except:
                pass
    
    # 6. 格式化输出
    print("\n[6/6] 显示生成的论文内容...")
    print("-" * 70)
    print(thesis_content[:1500])
    if len(thesis_content) > 1500:
        print("...\n(内容已截断)")
    print("-" * 70)
    
    print("\n" + "=" * 70)
    print("✅ 任务2完成!")
    print(f"📄 Word文档已打开，内容已写入")
    print(f"💾 文档路径: {save_path}")
    print("🔍 浏览器已打开毕设搜索页面供您参考")
    print("=" * 70)
    
    # 保持Word打开
    if word:
        word.Activate()
else:
    print(f"❌ 错误: {r.text}")
    if word:
        try:
            word.Quit()
        except:
            pass
