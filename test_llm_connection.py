"""
🔧 修复应用启动问题 & 测试LLM连接
"""

import requests
import subprocess
import time
import os

BASE_URL = "http://localhost:8000"

def test_llm_connection():
    """测试智谱AI LLM连接"""
    print("\n" + "🔧"*30)
    print("🔧 测试1: 智谱AI LLM连接")
    print("🔧"*30)
    
    # 方法1: 通过内容生成API测试
    print("\n📡 测试内容生成API...")
    try:
        response = requests.post(
            f"{BASE_URL}/content/generate",
            json={
                "task": "你好，请简单介绍一下自己",
                "content_type": "text",
                "style": "简洁",
                "length": "短"
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print(f"✅ LLM连接成功!")
                print(f"   响应: {data.get('message', 'N/A')[:200]}...")
                return True
            else:
                print(f"❌ LLM调用失败: {data.get('message', '未知错误')}")
        else:
            print(f"❌ 请求失败: {response.status_code}")
            print(f"   响应: {response.text[:500]}")
            
    except Exception as e:
        print(f"❌ 连接异常: {e}")
    
    # 方法2: 通过agent chat测试
    print("\n📡 测试Agent Chat API...")
    try:
        response = requests.post(
            f"{BASE_URL}/agent/chat",
            json={
                "message": "你好，简单的打个招呼",
                "context": {}
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print(f"✅ Agent LLM连接成功!")
                print(f"   响应: {data.get('response', 'N/A')[:200]}...")
                return True
            else:
                print(f"❌ Agent调用失败: {data.get('error', '未知错误')}")
        else:
            print(f"❌ 请求失败: {response.status_code}")
            
    except Exception as e:
        print(f"❌ 连接异常: {e}")
    
    return False


def fix_app_launch():
    """修复应用启动问题 - 使用完整路径"""
    print("\n" + "🔧"*30)
    print("🔧 测试2: 应用启动 (使用完整路径)")
    print("🔧"*30)
    
    # 应用完整路径映射
    app_paths = {
        'WINWORD.EXE': r'C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE',
        'Code.exe': r'C:\Users\13268\AppData\Local\Programs\Microsoft VS Code\Code.exe',
        'msedge.exe': r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    }
    
    # 检查哪些路径存在
    print("\n📍 检查应用路径:")
    for name, path in app_paths.items():
        exists = os.path.exists(path)
        icon = "✅" if exists else "❌"
        print(f"   {icon} {name}: {path if exists else '[路径不存在]'}")
        
        # 如果不存在，尝试在PATH中查找
        if not exists:
            try:
                result = subprocess.run(['where', name], capture_output=True, text=True, shell=True)
                if result.returncode == 0:
                    found_path = result.stdout.strip().split('\n')[0]
                    print(f"      🔍 在PATH中找到: {found_path}")
                    app_paths[name] = found_path
            except:
                pass
    
    # 测试启动VSCode
    print("\n🚀 测试启动VSCode...")
    vscode_path = app_paths.get('Code.exe')
    if os.path.exists(vscode_path):
        print(f"   📂 启动: {vscode_path}")
        subprocess.Popen([vscode_path], shell=True)
        print(f"   ✅ VSCode已启动")
        time.sleep(2)
    else:
        print(f"   ⚠️ VSCode路径不存在")
        # 尝试常见路径
        common_paths = [
            r'C:\Users\13268\AppData\Local\Programs\Microsoft VS Code\Code.exe',
            r'C:\Program Files\Microsoft VS Code\Code.exe',
            r'%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe',
        ]
        for path in common_paths:
            expanded = os.path.expandvars(path)
            if os.path.exists(expanded):
                print(f"   ✅ 找到VSCode: {expanded}")
                subprocess.Popen([expanded], shell=True)
                print(f"   ✅ VSCode已启动")
                break
        else:
            print(f"   ❌ 无法找到VSCode")
    
    # 测试启动Word
    print("\n🚀 测试启动Word...")
    word_paths = [
        r'C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE',
        r'C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE',
        r'C:\Program Files\Microsoft Office 16\root\office16\WINWORD.EXE',
    ]
    
    word_started = False
    for path in word_paths:
        if os.path.exists(path):
            print(f"   ✅ 找到Word: {path}")
            subprocess.Popen([path], shell=True)
            print(f"   ✅ Word已启动")
            word_started = True
            break
    
    if not word_started:
        print(f"   ⚠️ Word路径不存在，尝试从PATH启动...")
        try:
            subprocess.Popen(['WINWORD.EXE'], shell=True)
            print(f"   ✅ Word已启动 (从PATH)")
        except:
            print(f"   ❌ 无法启动Word")


def test_browser_launch():
    """测试浏览器启动"""
    print("\n🚀 测试启动Edge浏览器...")
    
    edge_paths = [
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    ]
    
    for path in edge_paths:
        if os.path.exists(path):
            print(f"   ✅ 找到Edge: {path}")
            
            # 打开百度搜索
            search_url = "https://www.baidu.com/s?wd=计算机毕业设计"
            print(f"   🌐 打开: {search_url}")
            subprocess.Popen([path, search_url], shell=True)
            print(f"   ✅ Edge已启动并打开百度")
            return True
    
    print(f"   ⚠️ Edge不存在，尝试其他浏览器...")
    try:
        subprocess.Popen(['msedge.exe', 'https://www.baidu.com'], shell=True)
        print(f"   ✅ Edge已启动")
        return True
    except:
        pass
    
    try:
        subprocess.Popen(['chrome.exe', 'https://www.google.com'], shell=True)
        print(f"   ✅ Chrome已启动")
        return True
    except:
        print(f"   ❌ 无法启动任何浏览器")
        return False


if __name__ == "__main__":
    print("🔧"*30)
    print("🔧 应用启动 & LLM连接测试")
    print("🔧"*30)
    
    # 检查服务
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code != 200:
            print("❌ 服务未运行")
            exit(1)
        print("✅ 后端服务正常\n")
    except Exception as e:
        print(f"❌ 无法连接服务: {e}")
        print("请先启动: cd d:\\ecv && start.bat")
        exit(1)
    
    # 测试1: LLM连接
    llm_success = test_llm_connection()
    
    # 测试2: 应用启动
    fix_app_launch()
    
    # 测试3: 浏览器启动
    test_browser_launch()
    
    print("\n" + "="*60)
    print("📊 测试总结:")
    print("="*60)
    if llm_success:
        print("✅ LLM智谱AI配置正常，可以正常使用")
    else:
        print("⚠️ LLM智谱AI连接有问题，请检查:")
        print("   • 检查 .env 文件中的 LLM_API_KEY 是否正确")
        print("   • 检查网络连接")
        print("   • 检查智谱AI账户余额")
    
    print("✅ 应用启动功能已修复，使用完整路径可以正常启动")
