"""测试各种软件控制功能"""
import subprocess
import time
import os

def test_open_app(app_name, app_path):
    """测试打开应用"""
    print(f"\n{'='*60}")
    print(f"测试1: 打开 {app_name}")
    print('='*60)
    try:
        result = subprocess.run(
            app_path,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        print(f"✓ {app_name} 已启动 (返回码: {result.returncode})")
        return True
    except Exception as e:
        print(f"✗ 打开 {app_name} 失败: {e}")
        return False

def test_open_file_with_app(app_path, file_path):
    """测试用应用打开文件"""
    print(f"\n{'='*60}")
    print(f"测试: 用 {app_path} 打开文件")
    print('='*60)
    try:
        result = subprocess.run(
            [app_path, file_path],
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        print(f"✓ 文件已用 {app_path} 打开")
        return True
    except Exception as e:
        print(f"✗ 打开文件失败: {e}")
        return False

def test_find_edge_tabs():
    """查找Edge浏览器打开的标签页"""
    print(f"\n{'='*60}")
    print("测试: 查找Edge浏览器打开的标签页")
    print('='*60)
    try:
        # 使用PowerShell获取Edge标签页
        ps_script = '''
        $edge = Get-Process msedge -ErrorAction SilentlyContinue
        if ($edge) {
            Write-Host "Edge正在运行，进程ID: $($edge.Id)"
            # 尝试获取窗口标题
            $windows = Get-Process msedge | Where-Object {$_.MainWindowTitle -ne ""}
            foreach ($win in $windows) {
                Write-Host "标签页: $($win.MainWindowTitle)"
            }
        } else {
            Write-Host "Edge未运行"
        }
        '''
        result = subprocess.run(
            ['powershell', '-Command', ps_script],
            capture_output=True,
            text=True,
            timeout=10
        )
        print(result.stdout if result.stdout else "无输出")
        if result.stderr:
            print(f"错误: {result.stderr[:200]}")
        return True
    except Exception as e:
        print(f"✗ 获取Edge标签页失败: {e}")
        return False

def test_word_create_and_edit():
    """测试Word创建和编辑"""
    print(f"\n{'='*60}")
    print("测试: Word创建新文档并编辑")
    print('='*60)
    
    # 查找Word路径
    word_paths = [
        r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE",
    ]
    
    word_path = None
    for path in word_paths:
        if os.path.exists(path):
            word_path = path
            break
    
    if not word_path:
        print("✗ 未找到Word程序")
        return False
    
    print(f"找到Word: {word_path}")
    
    # 创建临时文档
    temp_doc = r"C:\Users\13268\Desktop\test_doc.docx"
    
    try:
        # 先创建一个简单的docx文件（使用模板）
        # 然后用Word打开
        print(f"创建测试文档: {temp_doc}")
        
        # 使用Word创建空白文档并输入文字
        import pythoncom
        pythoncom.CoInitialize()
        
        import win32com.client
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = True
        
        doc = word.Documents.Add()
        word.Selection.TypeText("你好，这是一段测试文字！")
        word.Selection.TypeParagraph()
        word.Selection.TypeText("自动化编辑测试成功！")
        
        doc.SaveAs(temp_doc)
        print(f"✓ 文档已保存到: {temp_doc}")
        
        # 不关闭Word，让用户看到结果
        # word.Quit()
        # pythoncom.CoUninitialize()
        
        return True
    except ImportError:
        print("⚠ pywin32未安装，跳过Word自动化测试")
        print("  可以手动打开Word测试")
        return False
    except Exception as e:
        print(f"✗ Word自动化测试失败: {e}")
        return False

def test_ppt_open():
    """测试PPT打开"""
    print(f"\n{'='*60}")
    print("测试: 打开PowerPoint")
    print('='*60)
    
    ppt_paths = [
        r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\POWERPNT.EXE",
    ]
    
    for path in ppt_paths:
        if os.path.exists(path):
            try:
                subprocess.Popen([path])
                print(f"✓ PowerPoint已启动: {path}")
                return True
            except Exception as e:
                print(f"✗ 启动失败: {e}")
    
    print("✗ 未找到PowerPoint程序")
    return False

# 主测试流程
if __name__ == "__main__":
    print("="*60)
    print("开始软件控制功能测试")
    print("="*60)
    
    # 1. 打开百度网盘
    test_open_app("百度网盘", "https://pan.baidu.com")
    
    # 2. 打开PowerPoint
    test_ppt_open()
    
    # 3. 测试Word创建和编辑
    test_word_create_and_edit()
    
    # 4. 查找Edge标签页
    test_find_edge_tabs()
    
    print("\n" + "="*60)
    print("测试完成!")
    print("="*60)
