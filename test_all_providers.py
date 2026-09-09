"""
🔬 测试所有AI Provider连接
验证多步骤任务编排系统的完整功能
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_health():
    """检查服务状态"""
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=2)
        print(f"✅ 服务正常: {resp.status_code}")
        return True
    except Exception as e:
        print(f"❌ 服务未运行: {e}")
        return False

def test_providers():
    """测试所有provider"""
    print("\n" + "🔬"*20)
    print("🔬 测试1: 所有Provider状态")
    print("🔬"*20)
    
    try:
        resp = requests.get(f"{BASE_URL}/provider/list", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print(f"\n📋 Provider列表:")
            for p in data.get('providers', []):
                enabled = "✅" if p.get('enabled') else "❌"
                print(f"   {enabled} {p.get('name')}: {p.get('model')}")
            return True
    except Exception as e:
        print(f"❌ 获取Provider失败: {e}")
    return False

def test_content_generation():
    """测试内容生成（使用LLM）"""
    print("\n" + "🔬"*20)
    print("🔬 测试2: 内容生成（LLM）")
    print("🔬"*20)
    
    test_cases = [
        {
            "name": "登录页面",
            "task": "创建一个漂亮的登录页面HTML，包含用户名、密码输入框和登录按钮",
            "content_type": "html",
            "output_path": "D:/login_page/index.html"
        },
        {
            "name": "毕业论文",
            "task": "写一篇1000字的毕业论文，主题是人工智能在教育领域的应用",
            "content_type": "text",
            "output_path": "D:/thesis/paper.txt"
        }
    ]
    
    for case in test_cases:
        print(f"\n📝 测试: {case['name']}")
        try:
            resp = requests.post(
                f"{BASE_URL}/content/generate",
                json=case,
                timeout=60
            )
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    print(f"   ✅ 生成成功!")
                    print(f"   📄 输出: {data.get('output_file', 'N/A')}")
                    if 'content' in data and data['content']:
                        print(f"   📊 内容长度: {len(data['content'])} 字符")
                else:
                    print(f"   ❌ 生成失败: {data.get('message', '未知错误')}")
            else:
                print(f"   ❌ HTTP错误: {resp.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"   ⏰ 请求超时")
        except Exception as e:
            print(f"   ❌ 异常: {e}")

def test_workflow():
    """测试完整工作流"""
    print("\n" + "🔬"*20)
    print("🔬 测试3: 多步骤任务编排")
    print("🔬"*20)
    
    test_requests = [
        {
            "name": "登录页面工作流",
            "request": "创建一个登录页面，保存到D盘login_page文件夹，然后在Edge浏览器中打开"
        },
        {
            "name": "论文工作流",
            "request": "打开浏览器搜索计算机毕设相关资料，打开Word编辑器，生成一篇1000字的毕业论文，主题是人工智能在教育领域的应用"
        }
    ]
    
    for case in test_requests:
        print(f"\n📋 工作流: {case['name']}")
        print(f"   用户请求: {case['request']}")
        
        try:
            # 创建工作流
            resp = requests.post(
                f"{BASE_URL}/task-workflow/create",
                json={
                    "user_request": case['request'],
                    "auto_execute": False  # 先不自动执行
                },
                timeout=30
            )
            
            if resp.status_code == 200:
                data = resp.json()
                workflow_id = data.get('workflow_id')
                
                print(f"\n   ✅ 工作流创建成功!")
                print(f"   🆔 工作流ID: {workflow_id}")
                print(f"   📊 任务数量: {data.get('total_tasks', 0)}")
                
                # 显示任务列表
                tasks = data.get('tasks', [])
                for i, task in enumerate(tasks, 1):
                    tool = task.get('tool', 'unknown')
                    title = task.get('title', '无标题')
                    print(f"\n   📌 任务 {i}: {title}")
                    print(f"      🔧 工具: {tool}")
                    print(f"      📝 描述: {task.get('description', 'N/A')[:80]}...")
                
                # 执行工作流
                print(f"\n   🚀 开始执行工作流...")
                exec_resp = requests.post(
                    f"{BASE_URL}/task-workflow/execute-all",
                    params={"workflow_id": workflow_id},
                    timeout=120
                )
                
                if exec_resp.status_code == 200:
                    exec_data = exec_resp.json()
                    completed = exec_data.get('completed_tasks', 0)
                    total = exec_data.get('total_tasks', 0)
                    
                    print(f"\n   📊 执行结果: {completed}/{total} 任务成功")
                    
                    # 显示结果
                    results = exec_data.get('results', [])
                    for result in results:
                        status = "✅" if result.get('success') else "❌"
                        print(f"   {status} {result.get('title', '任务')}")
                        if not result.get('success'):
                            print(f"      错误: {result.get('result', {}).get('error', 'N/A')}")
                else:
                    print(f"   ❌ 执行失败: {exec_resp.status_code}")
            else:
                print(f"   ❌ 创建失败: {resp.status_code}")
                print(f"   响应: {resp.text[:200]}")
                
        except requests.exceptions.Timeout:
            print(f"   ⏰ 请求超时")
        except Exception as e:
            print(f"   ❌ 异常: {e}")
        
        print()

def main():
    print("🔬"*30)
    print("🔬 全功能测试 - 多步骤任务编排系统")
    print("🔬"*30)
    
    # 检查服务
    if not test_health():
        print("\n❌ 请先启动服务: cd d:\\ecv && start.bat")
        return
    
    # 测试Provider
    test_providers()
    
    # 测试内容生成
    test_content_generation()
    
    # 测试工作流
    test_workflow()
    
    print("\n" + "="*60)
    print("📊 测试完成!")
    print("="*60)
    print("\n💡 说明:")
    print("   • 如果所有测试都通过，说明系统完全可用")
    print("   • 如果LLM测试失败，检查API Key和网络连接")
    print("   • 应用启动应该能正常工作（使用完整路径）")

if __name__ == "__main__":
    main()
