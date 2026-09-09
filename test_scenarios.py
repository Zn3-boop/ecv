"""
🎯 测试两个完整场景
场景1: 打开VSCode → LLM生成登录页面 → 保存到D盘 → 浏览器打开
场景2: 打开浏览器搜索 → 打开Word → LLM生成论文
"""

import requests
import time
import os

BASE_URL = "http://localhost:8000"

def test_scenario_1():
    """场景1: 登录页面工作流"""
    print("\n" + "🎯"*30)
    print("🎯 场景1: 创建登录页面")
    print("🎯"*30)
    
    request = "打开VSCode新窗口，让AI帮我创建一个登录页面，保存到D盘的login_page文件夹，然后在Edge浏览器中打开预览"
    
    print(f"\n📝 用户请求: {request}")
    
    try:
        # 创建工作流
        print("\n🔄 正在分解任务...")
        resp = requests.post(
            f"{BASE_URL}/task-workflow/create",
            json={"user_request": request, "auto_execute": False},
            timeout=30
        )
        
        if resp.status_code != 200:
            print(f"❌ 创建工作流失败: {resp.status_code}")
            print(f"   响应: {resp.text[:200]}")
            return False
        
        data = resp.json()
        workflow_id = data.get('workflow_id')
        
        print(f"\n✅ 工作流创建成功!")
        print(f"   🆔 ID: {workflow_id}")
        print(f"   📊 任务数: {data.get('total_tasks', 0)}")
        
        # 显示任务列表
        print("\n📋 任务清单:")
        for i, task in enumerate(data.get('tasks', []), 1):
            status = "☐" if task.get('status') == 'pending' else "✅" if task.get('status') == 'success' else "❌"
            print(f"   {status} {i}. {task.get('title', 'N/A')}")
            print(f"       工具: {task.get('tool', 'N/A')}")
        
        # 执行工作流
        print("\n🚀 开始执行...")
        exec_resp = requests.post(
            f"{BASE_URL}/task-workflow/execute-all",
            params={"workflow_id": workflow_id},
            timeout=120
        )
        
        if exec_resp.status_code == 200:
            exec_data = exec_resp.json()
            completed = exec_data.get('completed_tasks', 0)
            total = exec_data.get('total_tasks', 0)
            
            print(f"\n📊 执行结果: {completed}/{total} 任务完成")
            
            # 显示详细结果
            print("\n📌 任务执行详情:")
            for result in exec_data.get('results', []):
                status_icon = "✅" if result.get('success') else "❌"
                print(f"   {status_icon} {result.get('title', '任务')}")
                if not result.get('success'):
                    error = result.get('result', {}).get('error', 'N/A')
                    print(f"       ❌ 错误: {error}")
                else:
                    msg = result.get('result', {}).get('message', '')
                    if msg:
                        print(f"       📝 {msg[:100]}")
            
            # 检查文件是否创建
            file_path = "D:/login_page/index.html"
            if os.path.exists(file_path):
                print(f"\n✅ 文件已创建: {file_path}")
                file_size = os.path.getsize(file_path)
                print(f"   📊 文件大小: {file_size} 字节")
            else:
                print(f"\n⚠️ 文件未创建: {file_path}")
            
            return completed == total
        else:
            print(f"❌ 执行失败: {exec_resp.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        return False


def test_scenario_2():
    """场景2: 论文工作流"""
    print("\n" + "🎯"*30)
    print("🎯 场景2: 搜索并生成论文")
    print("🎯"*30)
    
    request = "打开Edge浏览器搜索计算机毕设相关资料，打开Word编辑器，然后让AI生成一篇1000字的毕业论文，主题是人工智能在教育领域的应用"
    
    print(f"\n📝 用户请求: {request}")
    
    try:
        # 创建工作流
        print("\n🔄 正在分解任务...")
        resp = requests.post(
            f"{BASE_URL}/task-workflow/create",
            json={"user_request": request, "auto_execute": False},
            timeout=30
        )
        
        if resp.status_code != 200:
            print(f"❌ 创建工作流失败: {resp.status_code}")
            print(f"   响应: {resp.text[:200]}")
            return False
        
        data = resp.json()
        workflow_id = data.get('workflow_id')
        
        print(f"\n✅ 工作流创建成功!")
        print(f"   🆔 ID: {workflow_id}")
        print(f"   📊 任务数: {data.get('total_tasks', 0)}")
        
        # 显示任务列表
        print("\n📋 任务清单:")
        for i, task in enumerate(data.get('tasks', []), 1):
            status = "☐" if task.get('status') == 'pending' else "✅" if task.get('status') == 'success' else "❌"
            print(f"   {status} {i}. {task.get('title', 'N/A')}")
            print(f"       工具: {task.get('tool', 'N/A')}")
        
        # 执行工作流
        print("\n🚀 开始执行...")
        exec_resp = requests.post(
            f"{BASE_URL}/task-workflow/execute-all",
            params={"workflow_id": workflow_id},
            timeout=180  # 论文生成需要更长时间
        )
        
        if exec_resp.status_code == 200:
            exec_data = exec_resp.json()
            completed = exec_data.get('completed_tasks', 0)
            total = exec_data.get('total_tasks', 0)
            
            print(f"\n📊 执行结果: {completed}/{total} 任务完成")
            
            # 显示详细结果
            print("\n📌 任务执行详情:")
            for result in exec_data.get('results', []):
                status_icon = "✅" if result.get('success') else "❌"
                print(f"   {status_icon} {result.get('title', '任务')}")
                if not result.get('success'):
                    error = result.get('result', {}).get('error', 'N/A')
                    print(f"       ❌ 错误: {error}")
                else:
                    msg = result.get('result', {}).get('message', '')
                    if msg:
                        print(f"       📝 {msg[:100]}")
                    # 显示生成的内容
                    content = result.get('result', {}).get('content', '')
                    if content and len(content) > 50:
                        print(f"       📄 内容预览: {content[:100]}...")
            
            return completed == total
        else:
            print(f"❌ 执行失败: {exec_resp.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        return False


def main():
    print("🎯"*30)
    print("🎯 双场景测试")
    print("🎯"*30)
    
    # 检查服务
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=2)
        if r.status_code != 200:
            print("❌ 服务未运行")
            return
        print("✅ 服务正常\n")
    except:
        print("❌ 无法连接服务，请先运行 start.bat")
        return
    
    # 测试场景1
    success1 = test_scenario_1()
    
    # 测试场景2
    success2 = test_scenario_2()
    
    # 总结
    print("\n" + "="*60)
    print("📊 测试总结")
    print("="*60)
    print(f"   场景1 (登录页面): {'✅ 全部成功' if success1 else '❌ 部分失败'}")
    print(f"   场景2 (论文生成): {'✅ 全部成功' if success2 else '❌ 部分失败'}")
    
    print("\n💡 说明:")
    print("   • 如果任务失败，请检查错误信息")
    print("   • LLM连接问题需要重启服务")
    print("   • 应用启动问题已使用完整路径修复")


if __name__ == "__main__":
    main()
