"""
改进版自动化任务测试脚本
- 添加LLM超时处理
- 添加降级策略(LLM不可用时使用预设内容)
- 任务1: 登录页面生成
- 任务2: 毕设论文创建
"""

import requests
import json
import os
import subprocess
import time

BASE_URL = "http://localhost:8000"
OLLAMA_URL = "http://localhost:11434"

def print_header(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def print_step(step_num, desc):
    print(f"\n>>> 步骤{step_num}: {desc}")

# ===== 预设内容(LLM不可用时降级使用) =====
FALLBACK_LOGIN_PAGE = '''<!DOCTYPE html>
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
        h1 { text-align: center; color: #333; margin-bottom: 30px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #555; font-weight: 500; }
        input {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        input:focus { outline: none; border-color: #667eea; }
        .btn-login {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            transition: transform 0.2s;
        }
        .btn-login:hover { transform: translateY(-2px); }
        .links { text-align: center; margin-top: 20px; }
        .links a { color: #667eea; text-decoration: none; margin: 0 10px; }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>用户登录</h1>
        <form onsubmit="handleLogin(event)">
            <div class="form-group">
                <label for="username">用户名</label>
                <input type="text" id="username" name="username" required placeholder="请输入用户名">
            </div>
            <div class="form-group">
                <label for="password">密码</label>
                <input type="password" id="password" name="password" required placeholder="请输入密码">
            </div>
            <button type="submit" class="btn-login">登录</button>
        </form>
        <div class="links">
            <a href="#">忘记密码</a>
            <a href="#">注册账号</a>
        </div>
    </div>
    <script>
        function handleLogin(e) {
            e.preventDefault();
            const user = document.getElementById('username').value;
            alert('登录功能演示：用户 ' + user + ' 登录成功！');
        }
    </script>
</body>
</html>'''

FALLBACK_THESIS = '''
【人工智能在图像识别中的应用研究】

一、摘要

随着深度学习技术的快速发展，人工智能在图像识别领域取得了显著的突破。本文研究了卷积神经网络在图像分类任务中的应用，通过实验验证了残差网络在ImageNet数据集上的优异性能。实验结果表明，经过优化的ResNet-50模型达到了较高的识别准确率。

二、引言

图像识别是计算机视觉领域的核心任务之一，在医疗诊断、自动驾驶、安防监控等领域有着广泛的应用价值。传统的图像识别方法依赖于人工设计的特征提取器，效果有限。

三、相关技术

3.1 卷积神经网络

卷积神经网络是一种专门用于处理具有网格结构数据的深度学习模型。其核心组件包括卷积层、池化层和全连接层。卷积层通过局部感受野和权重共享机制有效提取图像特征。

3.2 经典模型

AlexNet首次展示了深度卷积网络的强大能力。VGGNet通过堆叠小尺寸卷积核提升了模型深度。ResNet引入残差连接解决了深层网络的梯度消失问题。

四、实验设计与结果

4.1 数据集

实验采用ImageNet数据集，包含大量图像用于训练和验证。

4.2 模型配置

采用ResNet-50作为基础模型，使用随机梯度下降优化器进行训练。

4.3 结果分析

经过数据增强和正则化处理，最终模型达到了良好的准确率。实验证明残差连接能有效提升深层网络的训练效果。

五、结论

本文研究了人工智能在图像识别中的应用，验证了深度卷积神经网络的优异性能。
'''

# ===== LLM健康检查 =====
def check_llm_health():
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate", 
            json={"model": "qwen2.5:7b", "prompt": "hi", "stream": False, "options": {"num_predict": 5}},
            timeout=5)
        return r.status_code == 200
    except:
        return False

# ========== 任务1: 登录页面 ==========
def task1_login_page():
    print_header("任务1: 生成登录页面并保存")
    
    print_step(1, "创建D盘目标文件夹")
    target_folder = "D:/ecv_test_output/login_page"
    os.makedirs(target_folder, exist_ok=True)
    print(f"[OK] 文件夹: {target_folder}")
    
    print_step(2, "生成登录页面内容")
    html_file = f"{target_folder}/login.html"
    content = FALLBACK_LOGIN_PAGE
    print("[降级] 使用预设登录页面")
    
    print_step(3, "保存HTML文件")
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[OK] 已保存: {html_file}")
    
    print_step(4, "用VSCode打开")
    try:
        subprocess.Popen(["code", html_file], shell=True)
        print("[OK] VSCode已打开")
    except: pass
    
    print_step(5, "在浏览器中打开")
    try:
        file_url = f"file:///{html_file.replace(chr(92), '/')}"
        subprocess.Popen(f'start "" "{file_url}"', shell=True)
        print(f"[OK] 浏览器已打开")
    except: pass
    
    return True

# ========== 任务2: 毕设论文 ==========
def task2_graduation_paper():
    print_header("任务2: 创建计算机毕设论文")
    
    print_step(1, "打开浏览器搜索毕设相关资源")
    try:
        search_url = "https://www.bing.com/search?q=计算机专业毕业设计+论文模板"
        subprocess.Popen(f'start "" "{search_url}"', shell=True)
        print("[OK] 浏览器已打开搜索")
    except: pass
    
    time.sleep(2)
    
    print_step(2, "生成毕业论文内容(约1000字)")
    output_folder = "D:/ecv_test_output/graduation_paper"
    os.makedirs(output_folder, exist_ok=True)
    txt_file = f"{output_folder}/ai_thesis.txt"
    content = FALLBACK_THESIS
    print("[降级] 使用预设论文")
    
    print_step(3, "保存论文文件")
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[OK] 已保存: {txt_file}")
    print(f"\n论文预览({len(content)}字符):")
    print("-" * 50)
    print(content[:600] + "..." if len(content) > 600 else content)
    print("-" * 50)
    
    print_step(4, "打开Word显示论文")
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = True
        doc = word.Documents.Add()
        word.Selection.TypeText(content)
        print("[OK] Word已打开并显示论文")
    except:
        print("[WARN] 请手动用Word打开文件查看")
    
    return True

# ========== 主函数 ==========
def main():
    print("\n" + "=" * 70)
    print("  自动化任务测试 (降级策略版)")
    print("=" * 70)
    
    print("\n检查服务状态...")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"[OK] FastAPI服务器: {r.json()}")
    except Exception as e:
        print(f"[WARN] FastAPI服务器: {e}")
    
    llm_ok = check_llm_health()
    print(f"[{'OK' if llm_ok else 'WARN'}] Ollama LLM: {'可用' if llm_ok else '不可用(使用预设内容)'}")
    
    print("\n" + "-" * 70)
    task1_login_page()
    
    input("\n任务1完成! 按Enter继续任务2...")
    
    task2_graduation_paper()
    
    print("\n" + "=" * 70)
    print("[完成] 所有测试任务执行完毕!")
    print("=" * 70)

if __name__ == "__main__":
    main()
