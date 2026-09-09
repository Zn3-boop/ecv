"""
🎯 测试多步骤任务编排系统
测试用户的需求：打开VSCode + 生成登录页面 + 保存到D盘 + 打开浏览器
"""

import requests
import json
import time
import subprocess
import os

BASE_URL = "http://localhost:8000"

def test_create_workflow():
    """测试创建工作流"""
    print("\n" + "="*60)
    print("🎯 测试1: 创建多步骤任务工作流")
    print("="*60)
    
    # 用户的需求
    user_request = "打开VSCode新建一个页面，让LLM编写一个登录页面，保存到D盘新建的login_project文件夹里，然后打开浏览器预览"
    
    response = requests.post(
        f"{BASE_URL}/task-workflow/create",
        json={
            "user_request": user_request,
            "auto_execute": False  # 先不自动执行，先看看任务列表
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ 工作流创建成功!")
        print(f"📋 工作流ID: {data['workflow_id']}")
        print(f"📝 原始请求: {data['user_request']}")
        print(f"\n📊 任务清单 ({data['completed_tasks']}/{data['total_tasks']}):")
        print("-" * 60)
        
        for i, task in enumerate(data['tasks'], 1):
            status_icon = {
                "pending": "⬜",
                "running": "🔄",
                "success": "✅",
                "failed": "❌",
                "skipped": "⏭️"
            }.get(task['status'], "⬜")
            
            print(f"{i}. {status_icon} {task['title']}")
            print(f"   📝 {task['description']}")
            print(f"   🔧 工具: {task['tool']}")
            print()
        
        print(data['formatted_display'])
        
        return data['workflow_id'], data.get('commands', [])
    else:
        print(f"❌ 工作流创建失败: {response.status_code}")
        print(response.text)
        return None, None


def test_execute_workflow(workflow_id: str):
    """测试执行工作流"""
    print("\n" + "="*60)
    print("🚀 测试2: 执行工作流任务")
    print("="*60)
    
    response = requests.post(f"{BASE_URL}/task-workflow/execute-all?workflow_id={workflow_id}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n📊 执行结果:")
        print(f"   总任务数: {data['total_tasks']}")
        print(f"   完成数: {data['completed_tasks']}")
        print(f"   状态: {data['status']}")
        
        for result in data['results']:
            icon = "✅" if result['success'] else "❌"
            print(f"\n{icon} {result['title']}")
            if result['success']:
                print(f"   结果: {result['result']}")
            else:
                print(f"   错误: {result['result']}")
        
        return True
    else:
        print(f"❌ 执行失败: {response.status_code}")
        print(response.text)
        return False


def test_simple_login_page():
    """测试简单的登录页面生成"""
    print("\n" + "="*60)
    print("🎨 测试3: 简单登录页面生成")
    print("="*60)
    
    # 直接调用内容生成API
    response = requests.post(
        f"{BASE_URL}/content/generate",
        json={
            "task": "登录页面",
            "content_type": "html",
            "style": "现代",
            "length": "中",
            "output_path": "D:/login_project/index.html"
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ 内容生成成功!")
        print(f"   输出文件: {data.get('output_file', 'N/A')}")
        print(f"   内容预览: {data.get('content', '')[:200]}...")
        return True
    else:
        print(f"❌ 内容生成失败: {response.status_code}")
        print(response.text)
        return False


def manual_execute_workflow(commands: list):
    """手动执行工作流命令"""
    print("\n" + "="*60)
    print("⚡ 手动执行任务")
    print("="*60)
    
    for i, cmd in enumerate(commands, 1):
        print(f"\n{i}. 执行命令: {cmd.get('reason', 'N/A')}")
        print(f"   工具: {cmd.get('tool')}")
        print(f"   参数: {cmd.get('params')}")
        
        # 实际执行
        tool = cmd.get('tool')
        params = cmd.get('params', {})
        
        if tool == "app:launch":
            path = params.get("path", "")
            url = params.get("url", "")
            
            if url:
                cmd_str = f'"{path}" {url}'
            else:
                cmd_str = f'"{path}"'
            
            print(f"   🔄 执行: {cmd_str}")
            subprocess.Popen(cmd_str, shell=True)
            print(f"   ✅ 已启动: {path}")
            
        time.sleep(1)


if __name__ == "__main__":
    print("\n" + "🎯"*30)
    print("🎯 多步骤任务编排系统测试")
    print("🎯"*30)
    
    # 检查服务是否运行
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code != 200:
            print("❌ 服务未正常运行")
            exit(1)
        print("✅ 后端服务运行正常")
    except Exception as e:
        print(f"❌ 无法连接到后端服务: {e}")
        print("请先启动后端服务: cd d:\\ecv && start.bat")
        exit(1)
    
    # 测试1: 创建工作流
    workflow_id, commands = test_create_workflow()
    
    if workflow_id and commands:
        # 测试2: 手动执行命令
        print("\n是否手动执行这些命令? (y/n)")
        user_input = input("> ").strip().lower()
        
        if user_input == 'y':
            manual_execute_workflow(commands)
        else:
            # 测试3: 直接测试内容生成
            test_simple_login_page()
    
    print("\n" + "="*60)
    print("✅ 测试完成!")
    print("="*60)
