"""测试所有新实现的功能"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_api(endpoint, method="get", data=None):
    """测试API"""
    url = f"{BASE_URL}{endpoint}"
    try:
        if method == "get":
            resp = requests.get(url, timeout=10)
        else:
            resp = requests.post(url, json=data, timeout=10)
        print(f"\n{'='*60}")
        print(f"API: {method.upper()} {endpoint}")
        print(f"状态码: {resp.status_code}")
        try:
            print(f"响应: {json.dumps(resp.json(), ensure_ascii=False, indent=2)}")
        except:
            print(f"响应: {resp.text[:500]}")
        return resp.status_code == 200
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"API: {method.upper()} {endpoint}")
        print(f"❌ 请求失败: {e}")
        return False

def test_browser_tabs():
    """测试获取浏览器标签页"""
    print(f"\n{'='*60}")
    print("测试: 获取Edge浏览器标签页")
    try:
        # 直接用PowerShell测试
        import subprocess
        script = '''
        $tabs = @()
        $procs = Get-Process msedge -ErrorAction SilentlyContinue
        if ($procs) {
            foreach ($proc in $procs) {
                if ($proc.MainWindowTitle -ne "") {
                    $title = $proc.MainWindowTitle
                    $tabs += @{ "title" = $title; "pid" = $proc.Id }
                }
            }
        }
        $tabs | ConvertTo-Json -Compress
        '''
        result = subprocess.run(['powershell', '-Command', script], capture_output=True, text=True, timeout=10)
        if result.stdout.strip():
            print(f"✓ Edge正在运行，找到标签页:")
            try:
                tabs = json.loads(result.stdout.strip())
                if isinstance(tabs, dict):
                    tabs = [tabs]
                for tab in tabs[:5]:
                    print(f"  - {tab.get('title', 'N/A')[:60]}")
            except:
                print(f"  {result.stdout[:200]}")
            return True
        else:
            print("⚠ Edge未运行或无标签页")
            return True
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_desktop_apps():
    """测试桌面应用"""
    print(f"\n{'='*60}")
    print("测试: 桌面应用控制")
    tests = [
        ("/desktop/find", "post", {"name": "notepad"}),
        ("/desktop/running", "get", None),
    ]
    for endpoint, method, data in tests:
        test_api(endpoint, method, data)

def test_browser_apis():
    """测试浏览器API"""
    print(f"\n{'='*60}")
    print("测试: 浏览器API")
    tests = [
        ("/browser/prompt", "get", None),
        ("/browser/intent", "post", {"command": "用Edge搜索Python教程"}),
        ("/browser/search", "post", {"query": "测试搜索", "browser": "edge"}),
    ]
    for endpoint, method, data in tests:
        test_api(endpoint, method, data)

def test_office():
    """测试Office自动化（只测试路径查找）"""
    print(f"\n{'='*60}")
    print("测试: Office应用查找")
    import os
    
    word_path = r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE"
    excel_path = r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE"
    ppt_path = r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE"
    
    for name, path in [("Word", word_path), ("Excel", excel_path), ("PowerPoint", ppt_path)]:
        if os.path.exists(path):
            print(f"✓ {name}: {path}")
        else:
            print(f"✗ {name}: 未找到")

if __name__ == "__main__":
    print("="*60)
    print("开始测试所有新功能")
    print("="*60)
    
    # 1. 健康检查
    test_api("/health")
    
    # 2. Office自动化测试
    test_office()
    
    # 3. 浏览器标签页测试
    test_browser_tabs()
    
    # 4. 浏览器API测试
    test_browser_apis()
    
    # 5. 桌面应用测试
    test_desktop_apps()
    
    print("\n" + "="*60)
    print("测试完成!")
    print("="*60)
