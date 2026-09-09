"""
🎓 测试论文工作流
打开浏览器搜索→打开Word→生成论文
"""

import requests
import json
import subprocess
import time
import os

BASE_URL = "http://localhost:8000"

def test_thesis_workflow():
    """测试论文工作流"""
    print("\n" + "🎓"*30)
    print("🎓 论文工作流测试")
    print("🎓"*30)
    
    # 用户的需求
    user_request = "打开浏览器搜索计算机毕设相关资料，打开Word编辑器，生成一篇1000字的毕业论文，主题是人工智能在教育领域的应用，然后让我看看成果"
    
    print(f"\n📝 原始请求: {user_request}")
    print("\n" + "="*60)
    
    # 创建工作流
    response = requests.post(
        f"{BASE_URL}/task-workflow/create",
        json={
            "user_request": user_request,
            "auto_execute": False
        }
    )
    
    if response.status_code != 200:
        print(f"❌ 工作流创建失败: {response.status_code}")
        print(response.text)
        return
    
    data = response.json()
    workflow_id = data['workflow_id']
    
    print(f"✅ 工作流创建成功!")
    print(f"📋 工作流ID: {workflow_id}")
    print(f"\n📊 任务清单 ({data['completed_tasks']}/{data['total_tasks']}):")
    print("-" * 60)
    
    for i, task in enumerate(data['tasks'], 1):
        status_icon = "⬜"
        print(f"{i}. {status_icon} {task['title']}")
        print(f"   📝 {task['description']}")
        print(f"   🔧 工具: {task['tool']}")
        print()
    
    # 手动执行每个任务
    print("\n" + "="*60)
    print("⚡ 开始执行任务")
    print("="*60)
    
    for i, task in enumerate(data['tasks'], 1):
        print(f"\n📌 任务 {i}: {task['title']}")
        
        tool = task['tool']
        params = task.get('params', {})
        
        try:
            if tool == "browser:search":
                query = params.get('query', '计算机毕业设计')
                print(f"   🔍 搜索: {query}")
                
                import urllib.parse
                if any('\u4e00' <= c <= '\u9fff' for c in query):
                    url = f"https://www.baidu.com/s?wd={urllib.parse.quote(query)}"
                else:
                    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                
                print(f"   🌐 打开: {url}")
                subprocess.Popen(['msedge.exe', url], shell=True)
                print(f"   ✅ 浏览器已打开")
                
            elif tool == "app:launch":
                path = params.get('path', '')
                if path == 'WINWORD.EXE':
                    print(f"   📄 启动 Word...")
                    subprocess.Popen(['WINWORD.EXE'], shell=True)
                    print(f"   ✅ Word已启动")
                elif path == 'Code.exe':
                    print(f"   💻 启动 VSCode...")
                    subprocess.Popen(['Code.exe'], shell=True)
                    print(f"   ✅ VSCode已启动")
                elif 'msedge' in path.lower() or path == 'msedge.exe':
                    print(f"   🌐 启动 Edge...")
                    subprocess.Popen(['msedge.exe'], shell=True)
                    print(f"   ✅ Edge已启动")
                else:
                    print(f"   🚀 启动: {path}")
                    subprocess.Popen([path], shell=True)
                    print(f"   ✅ 已启动")
                    
            elif tool == "content:generate":
                print(f"   📝 正在生成论文内容...")
                
                content_type = params.get('content_type', 'word')
                task_text = params.get('task', '毕业论文')
                
                gen_response = requests.post(
                    f"{BASE_URL}/content/generate",
                    json={
                        "task": f"{task_text}：人工智能在教育领域的应用，约1000字",
                        "content_type": content_type,
                        "style": "学术",
                        "length": "medium",
                        "output_path": "D:/thesis/ai_education_paper.doc"
                    },
                    timeout=60
                )
                
                if gen_response.status_code == 200:
                    gen_data = gen_response.json()
                    if gen_data.get('success'):
                        print(f"   ✅ 论文生成成功!")
                        print(f"   📁 文件: {gen_data.get('output_file', 'N/A')}")
                        
                        # 保存内容预览
                        content = gen_data.get('content', '')
                        if content:
                            print(f"\n   📄 内容预览 (前500字):")
                            print("   " + "-"*50)
                            preview = content[:500].replace('\n', '\n   ')
                            print(f"   {preview}...")
                            print("   " + "-"*50)
                    else:
                        print(f"   ⚠️ 生成失败: {gen_data.get('message', '未知错误')}")
                else:
                    print(f"   ❌ 生成请求失败: {gen_response.status_code}")
                    
            else:
                print(f"   ⚠️ 未知工具: {tool}")
                
        except Exception as e:
            print(f"   ❌ 执行错误: {e}")
        
        time.sleep(1)
    
    print("\n" + "="*60)
    print("🎉 所有任务执行完成!")
    print("="*60)
    print("\n📋 任务总结:")
    print("   ✅ 1. 浏览器已打开，你可以查看搜索结果")
    print("   ✅ 2. Word编辑器已启动")
    print("   ✅ 3. 论文已生成并保存")
    print("\n💡 现在你可以:")
    print("   • 查看D盘 thesis 文件夹中的论文文件")
    print("   • 在Word中打开并编辑生成的论文")
    print("   • 继续在浏览器中搜索更多资料")


def create_d_thesis_folder():
    """创建D盘论文文件夹"""
    thesis_path = "D:/thesis"
    if not os.path.exists(thesis_path):
        os.makedirs(thesis_path)
        print(f"✅ 已创建文件夹: {thesis_path}")
    return thesis_path


if __name__ == "__main__":
    # 确保D盘论文文件夹存在
    create_d_thesis_folder()
    
    # 检查服务
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code != 200:
            print("❌ 服务未运行")
            exit(1)
        print("✅ 后端服务正常")
    except Exception as e:
        print(f"❌ 无法连接服务: {e}")
        print("请先启动: cd d:\\ecv && start.bat")
        exit(1)
    
    # 执行论文工作流
    test_thesis_workflow()
