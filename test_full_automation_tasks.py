"""
综合自动化任务测试脚本
任务1: LLM编写登录页面，保存到D盘新文件夹，用VSCode打开，浏览器打开
任务2: 浏览器搜索计算机毕设相关文件，打开Word，创建一篇约1000字的论文
"""

import requests
import json
import os
import subprocess
import time

BASE_URL = "http://localhost:8000"

def print_header(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def print_step(step_num, desc):
    print(f"\n>>> 步骤{step_num}: {desc}")

# ========== 任务1: 登录页面生成 ==========
def task1_login_page():
    print_header("任务1: LLM编写登录页面并保存到D盘")
    
    # 步骤1: 创建D盘目标文件夹
    print_step(1, "创建D盘目标文件夹")
    target_folder = "D:/ecv_test_output/login_page"
    try:
        os.makedirs(target_folder, exist_ok=True)
        print(f"[OK] 文件夹已创建: {target_folder}")
    except Exception as e:
        print(f"[FAIL] 创建文件夹失败: {e}")
        return False
    
    # 步骤2: 调用LLM生成登录页面
    print_step(2, "调用LLM生成登录页面")
    try:
        response = requests.post(f"{BASE_URL}/content/generate", json={
            "task": "用户登录页面",
            "content_type": "html",
            "style": "现代渐变风格",
            "output_path": f"{target_folder}/login.html"
        }, timeout=180)
        
        result = response.json()
        print(f"API响应状态: {response.status_code}")
        print(f"成功: {result.get('success')}")
        print(f"输出文件: {result.get('output_file')}")
        
        if result.get('success') and result.get('output_file'):
            print(f"[OK] 登录页面已保存: {result.get('output_file')}")
            
            # 显示内容预览
            content = result.get('content', '')
            print(f"内容预览 ({len(content)}字符):")
            print("-" * 50)
            print(content[:500] + "..." if len(content) > 500 else content)
            print("-" * 50)
        else:
            print(f"[FAIL] 生成失败: {result.get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"[FAIL] 调用API失败: {e}")
        return False
    
    # 步骤3: 用VSCode打开生成的HTML文件
    print_step(3, "用VSCode打开生成的HTML文件")
    try:
        html_file = f"{target_folder}/login.html"
        if os.path.exists(html_file):
            subprocess.Popen(["code", html_file], shell=True)
            print(f"[OK] 已用VSCode打开: {html_file}")
        else:
            print(f"[WARN] 文件不存在，跳过VSCode打开")
    except Exception as e:
        print(f"[WARN] VSCode打开失败: {e}")
    
    # 步骤4: 在浏览器中打开HTML文件
    print_step(4, "在浏览器中打开HTML文件")
    try:
        html_file = f"{target_folder}/login.html"
        if os.path.exists(html_file):
            # 使用file://协议打开本地HTML文件
            file_url = f"file:///{html_file.replace(':', ':').replace('\\\\', '/')}"
            subprocess.Popen(f'start "" "{file_url}"', shell=True)
            print(f"[OK] 已在浏览器中打开: {file_url}")
        else:
            print(f"[WARN] 文件不存在，跳过浏览器打开")
    except Exception as e:
        print(f"[WARN] 浏览器打开失败: {e}")
    
    return True

# ========== 任务2: 计算机毕设论文 ==========
def task2_graduation_paper():
    print_header("任务2: 计算机毕设论文创建")
    
    # 步骤1: 打开浏览器搜索计算机毕设相关文件
    print_step(1, "打开浏览器搜索计算机毕设相关文件")
    try:
        # 使用Bing搜索计算机毕设相关资源
        search_url = "https://www.bing.com/search?q=计算机专业毕业设计+论文+模板+范例"
        subprocess.Popen(f'start "" "{search_url}"', shell=True)
        print(f"[OK] 已在浏览器中打开搜索: {search_url}")
        time.sleep(2)  # 等待浏览器启动
    except Exception as e:
        print(f"[FAIL] 浏览器打开失败: {e}")
    
    # 步骤2: 调用LLM生成计算机毕设论文
    print_step(2, "调用LLM生成计算机毕设论文(约1000字)")
    try:
        response = requests.post(f"{BASE_URL}/content/generate", json={
            "task": "计算机专业毕业论文",
            "content_type": "word",
            "theme": "人工智能在图像识别中的应用",
            "length": "中",  # 约1000字
            "style": "学术风格",
            "output_path": "D:/ecv_test_output/graduation_paper/ai_thesis.txt"
        }, timeout=180)
        
        result = response.json()
        print(f"API响应状态: {response.status_code}")
        print(f"成功: {result.get('success')}")
        print(f"输出文件: {result.get('output_file')}")
        
        if result.get('success') and result.get('output_file'):
            paper_content = result.get('content', '')
            print(f"[OK] 论文内容已生成 ({len(paper_content)}字符)")
            
            # 显示论文内容预览
            print("\n论文内容预览:")
            print("-" * 50)
            print(paper_content[:1000] + "..." if len(paper_content) > 1000 else paper_content)
            print("-" * 50)
            
            # 同时保存为纯文本版本（方便查看）
            txt_file = result.get('output_file')
            print(f"\n[OK] 论文已保存到: {txt_file}")
        else:
            print(f"[FAIL] 生成失败: {result.get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"[FAIL] 调用API失败: {e}")
        return False
    
    # 步骤3: 使用Win32 COM打开Word（如果论文内容已生成）
    print_step(3, "打开Word并显示论文内容")
    try:
        # 尝试使用win32com打开Word并创建文档
        import pythoncom
        import win32com.client
        
        # 初始化COM
        pythoncom.CoInitialize()
        
        # 创建Word应用
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = True
        
        # 创建新文档
        doc = word.Documents.Add()
        
        # 写入论文内容
        paper_content = result.get('content', '')
        if paper_content:
            word.Selection.TypeText(paper_content)
        
        print(f"[OK] Word已打开，论文内容已写入新文档")
        print("[WARN] 注意: 如果需要保存为.docx格式，请手动在Word中另存为")
        
    except ImportError:
        print("[WARN] win32com模块不可用，跳过Word自动打开")
        print("   论文内容已保存到文件，请手动用Word打开查看")
    except Exception as e:
        print(f"[WARN] Word打开失败: {e}")
        print("   论文内容已保存到文件，请手动用Word打开查看")
    
    return True

# ========== 主函数 ==========
def main():
    print("\n" + "=" * 70)
    print("  [TEST] 综合自动化任务测试")
    print("  测试系统LLM自动化任务执行能力")
    print("=" * 70)
    
    # 检查服务器连接
    print("\n检查服务器连接...")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        if r.status_code == 200:
            print(f"[OK] 服务器正常: {r.json()}")
        else:
            print(f"[FAIL] 服务器异常: {r.status_code}")
            return
    except Exception as e:
        print(f"[FAIL] 无法连接服务器: {e}")
        return
    
    # 执行任务1
    success1 = task1_login_page()
    
    print("\n" + "-" * 70)
    print("任务1完成，请查看VSCode和浏览器窗口。")
    print("按Enter继续执行任务2...")
    input()
    
    # 执行任务2
    success2 = task2_graduation_paper()
    
    # 总结
    print("\n" + "=" * 70)
    print("  [RESULT] 测试结果总结")
    print("=" * 70)
    print(f"任务1 (登录页面生成): {'[OK]' if success1 else '[FAIL]'}")
    print(f"任务2 (毕设论文创建): {'[OK]' if success2 else '[FAIL]'}")
    
    if success1 and success2:
        print("\n[SUCCESS] 所有自动化任务测试完成!")
    else:
        print("\n[WARN] 部分任务失败，请检查上述错误信息")
    
    print("=" * 70)

if __name__ == "__main__":
    main()
