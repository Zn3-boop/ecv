"""
自动化测试脚本 - 测试LLM生成内容功能
测试1: 打开VSCode新建页面让LLM写登录页面并保存到D盘新文件夹，在浏览器打开
测试2: 打开浏览器搜索计算机毕设相关文件，打开Word，让LLM创建1000字论文
"""

import requests
import json
import time
import os
import subprocess

# API基础URL
BASE_URL = "http://localhost:8000"

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def test_task1_login_page():
    """测试1: LLM生成登录页面并保存到D盘"""
    print_section("测试1: LLM生成登录页面")
    
    # 步骤1: 在浏览器中打开D盘新建的文件夹路径
    # 先创建目标文件夹
    folder_path = r"D:\LLM_Generated_Pages"
    os.makedirs(folder_path, exist_ok=True)
    print(f"✓ 已创建目标文件夹: {folder_path}")
    
    # 步骤2: 调用内容生成API让LLM生成登录页面
    print("\n正在调用LLM生成登录页面...")
    
    payload = {
        "task": "登录页面",
        "content_type": "html",
        "theme": "现代化",
        "length": "短",
        "style": "现代简洁",
        "output_path": os.path.join(folder_path, "login_page.html"),
    }
    
    try:
        response = requests.post(f"{BASE_URL}/content/generate", json=payload, timeout=180)
        result = response.json()
        
        print(f"\nAPI响应成功: {result.get('success')}")
        
        if result.get('output_file'):
            file_path = result.get('output_file')
            print(f"✓ 文件已保存: {file_path}")
            
            # 步骤3: 在浏览器中打开生成的HTML文件
            print("\n正在浏览器中打开生成的登录页面...")
            browser_url = f"file:///{file_path.replace('\\', '/')}"
            subprocess.Popen(f'start "" "{file_path}"', shell=True)
            print(f"✓ 已在浏览器中打开: {browser_url}")
            
            return True, file_path
        else:
            print(f"✗ 文件保存失败: {result.get('message')}")
            return False, None
            
    except Exception as e:
        print(f"✗ 测试1执行失败: {str(e)}")
        return False, str(e)


def test_task2_graduation_paper():
    """测试2: 搜索毕设内容，创建Word论文"""
    print_section("测试2: 搜索毕设并创建论文")
    
    # 步骤1: 在浏览器中搜索计算机毕设相关内容
    print("\n步骤1: 打开浏览器搜索计算机毕设相关文件...")
    
    browser_payload = {
        "command": "搜索计算机毕业设计论文模板"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/browser/nlp", json=browser_payload, timeout=30)
        result = response.json()
        
        print(f"浏览器操作结果: {result.get('result', {}).get('message')}")
        print(f"搜索URL: {result.get('result', {}).get('url')}")
        
    except Exception as e:
        print(f"浏览器搜索失败(继续测试): {str(e)}")
    
    time.sleep(2)  # 等待浏览器打开
    
    # 步骤2: 打开Word
    print("\n步骤2: 打开Microsoft Word...")
    
    try:
        # 使用默认方式打开Word
        word_path = r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE"
        if os.path.exists(word_path):
            subprocess.Popen(word_path)
            print("✓ Word已启动")
        else:
            # 尝试用start命令打开
            subprocess.Popen('start winword', shell=True)
            print("✓ Word已启动(通过start命令)")
    except Exception as e:
        print(f"打开Word失败: {str(e)}")
    
    time.sleep(3)  # 等待Word启动
    
    # 步骤3: 调用LLM生成1000字的计算机毕设论文
    print("\n步骤3: 调用LLM生成计算机毕设论文(约1000字)...")
    
    paper_payload = {
        "task": "计算机科学专业毕业论文",
        "content_type": "word",
        "theme": "人工智能在图像识别中的应用",
        "length": "中",
        "style": "学术",
        "output_path": r"D:\LLM_Generated_Pages\graduation_paper.txt"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/content/generate", json=paper_payload, timeout=180)
        result = response.json()
        
        print(f"\nAPI响应成功: {result.get('success')}")
        
        if result.get('success'):
            content = result.get('content', '')
            word_count = len(content.replace(' ', '').replace('\n', ''))
            print(f"✓ 论文生成成功，字数约: {word_count} 字")
            print(f"\n论文预览(前500字):\n{content[:500]}...")
            
            # 保存论文内容
            if result.get('output_file'):
                print(f"\n✓ 论文已保存到: {result.get('output_file')}")
            
            # 将内容复制到剪贴板
            try:
                import pyperclip
                pyperclip.copy(content)
                print("✓ 论文内容已复制到剪贴板，可以在Word中粘贴")
            except:
                print("注意: 请手动将生成的论文内容复制到Word中")
            
            return True, content
        else:
            print(f"✗ 论文生成失败: {result.get('message')}")
            return False, result.get('message')
            
    except Exception as e:
        print(f"✗ 测试2执行失败: {str(e)}")
        return False, str(e)


def main():
    print("\n" + "="*60)
    print("  自动化任务测试")
    print("  测试1: LLM生成登录页面并保存")
    print("  测试2: 搜索毕设+创建Word论文")
    print("="*60)
    
    # 检查API服务是否运行
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print("⚠ API服务可能未正常运行")
    except:
        print("⚠ 无法连接到API服务，请确保服务已启动 (uvicorn app.main:app)")
        print("  启动命令: cd apps/server && uvicorn app.main:app --reload --port 8000")
        return
    
    # 执行测试1
    success1, result1 = test_task1_login_page()
    
    # 等待用户确认
    input("\n按Enter键继续测试2...")
    
    # 执行测试2
    success2, result2 = test_task2_graduation_paper()
    
    # 总结
    print_section("测试总结")
    print(f"测试1 (登录页面生成): {'✓ 成功' if success1 else '✗ 失败'}")
    print(f"测试2 (毕设论文生成): {'✓ 成功' if success2 else '✗ 失败'}")
    
    if success1 and success2:
        print("\n🎉 所有测试通过!")
    else:
        print("\n⚠ 部分测试失败，请检查日志")


if __name__ == "__main__":
    main()
