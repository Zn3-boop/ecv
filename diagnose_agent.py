"""Agent 项目诊断脚本 - 收集所有代码逻辑发给开发者"""
import os
import sys
import json
import re
import requests
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path("D:/ecv")
OUTPUT_FILE = PROJECT_ROOT / "agent_diagnosis_report.md"

def scan_python_files():
    """扫描所有Python文件"""
    files = []
    exclude = {'venv', '__pycache__', '.git', 'node_modules', 'dist', 'build'}
    for path in PROJECT_ROOT.rglob("*.py"):
        if any(part in exclude for part in path.parts):
            continue
        rel = path.relative_to(PROJECT_ROOT)
        size = path.stat().st_size
        files.append({"path": str(rel), "size": size})
    return sorted(files, key=lambda x: x["size"], reverse=True)

def extract_routers():
    """提取FastAPI路由"""
    routers = []
    router_pattern = re.compile(r'APIRouter\s*\(\s*prefix\s*=\s*["\']([^"\']+)["\']')
    route_pattern = re.compile(r'@router\.(get|post|put|delete)\s*\(\s*["\']([^"\']+)["\']')
    
    for path in PROJECT_ROOT.rglob("*.py"):
        if 'venv' in str(path):
            continue
        try:
            text = path.read_text(encoding='utf-8')
            prefix_match = router_pattern.search(text)
            if prefix_match or '@router.' in text:
                routes = route_pattern.findall(text)
                if routes or prefix_match:
                    routers.append({
                        "file": str(path.relative_to(PROJECT_ROOT)),
                        "prefix": prefix_match.group(1) if prefix_match else "未知",
                        "routes": [f"{m[0].upper()} {m[1]}" for m in routes]
                    })
        except:
            pass
    return routers

def extract_tools():
    """提取工具定义"""
    tools = []
    tool_pattern = re.compile(r'["\']([a-z_]+:[a-z_]+)["\']')
    
    for path in PROJECT_ROOT.rglob("*.py"):
        if 'venv' in str(path):
            continue
        try:
            text = path.read_text(encoding='utf-8')
            if 'tool' in text.lower() and ('registry' in text.lower() or 'executor' in text.lower() or 'dispatch' in text.lower()):
                found = set(tool_pattern.findall(text))
                if found:
                    tools.append({
                        "file": str(path.relative_to(PROJECT_ROOT)),
                        "tools": sorted(found)
                    })
        except:
            pass
    return tools

def extract_prompts():
    """提取System Prompt"""
    prompts = []
    prompt_pattern = re.compile(r'(SYSTEM_PROMPT|GENERATOR_SYSTEM_PROMPT|STRUCTURED_SYSTEM_PROMPT)\s*=\s*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', re.DOTALL)
    
    for path in PROJECT_ROOT.rglob("*.py"):
        if 'venv' in str(path):
            continue
        try:
            text = path.read_text(encoding='utf-8')
            matches = prompt_pattern.findall(text)
            for name, content in matches:
                prompts.append({
                    "file": str(path.relative_to(PROJECT_ROOT)),
                    "name": name,
                    "length": len(content),
                    "preview": content[:500].replace('\n', ' ')
                })
        except:
            pass
    return prompts

def test_api():
    """测试关键API"""
    results = []
    base = "http://localhost:8000"
    
    # 测试健康检查
    try:
        r = requests.get(f"{base}/health", timeout=3)
        results.append({"api": "GET /health", "status": r.status_code, "response": r.text[:200]})
    except Exception as e:
        results.append({"api": "GET /health", "status": "ERROR", "response": str(e)})
    
    # 测试内容生成
    try:
        r = requests.post(f"{base}/content/generate", json={
            "task": "测试登录页面",
            "content_type": "html",
            "output_path": "D:/TestFolder/test_diag.html"
        }, timeout=15)
        data = r.json()
        results.append({
            "api": "POST /content/generate",
            "status": r.status_code,
            "success": data.get("success"),
            "message": data.get("message", ""),
            "error_detail": data.get("error_detail", "无"),
            "has_content": bool(data.get("content")),
            "content_preview": (data.get("content") or "")[:100]
        })
    except Exception as e:
        results.append({"api": "POST /content/generate", "status": "ERROR", "response": str(e)})
    
    # 测试agent/command意图识别
    try:
        r = requests.post(f"{base}/agent/command", json={
            "text": "打开记事本写这是测试",
            "session_id": "test-123"
        }, timeout=15)
        data = r.json()
        results.append({
            "api": "POST /agent/command",
            "status": r.status_code,
            "reply": (data.get("reply_text") or "")[:200],
            "solutions_count": len(data.get("solutions", [])),
            "commands": [c.get("tool") for c in data.get("solutions", [{}])[0].get("commands", [])] if data.get("solutions") else []
        })
    except Exception as e:
        results.append({"api": "POST /agent/command", "status": "ERROR", "response": str(e)})
    
    return results

def read_config():
    """读取配置文件"""
    configs = {}
    
    # 尝试读取 providers.json
    providers_path = PROJECT_ROOT / "providers.json"
    if providers_path.exists():
        try:
            configs["providers.json"] = json.loads(providers_path.read_text(encoding='utf-8'))
        except Exception as e:
            configs["providers.json"] = f"读取失败: {e}"
    
    # 尝试读取 generator_config
    for path in PROJECT_ROOT.rglob("generator_config.py"):
        if 'venv' not in str(path):
            try:
                text = path.read_text(encoding='utf-8')
                # 提取关键变量
                lines = []
                for line in text.split('\n'):
                    if any(k in line for k in ['provider', 'model', 'enabled', 'ollama', 'openai']):
                        lines.append(line.strip())
                configs["generator_config.py"] = "\n".join(lines[:30])
            except Exception as e:
                configs["generator_config.py"] = f"读取失败: {e}"
            break
    
    return configs

def generate_report():
    """生成诊断报告"""
    report = []
    report.append(f"# Agent 项目诊断报告\n生成时间: {datetime.now()}\n")
    
    # 1. 项目结构
    report.append("## 1. 项目文件结构 (Top 20)\n")
    files = scan_python_files()[:20]
    for f in files:
        report.append(f"- `{f['path']}` ({f['size']} bytes)")
    report.append(f"\n总计 Python 文件: {len(scan_python_files())} 个\n")
    
    # 2. API路由
    report.append("## 2. API 路由表\n")
    routers = extract_routers()
    for r in routers:
        report.append(f"\n### {r['file']} (prefix: {r['prefix']})")
        for route in r['routes']:
            report.append(f"- `{route}`")
    
    # 3. 工具列表
    report.append("\n## 3. 工具定义\n")
    tools = extract_tools()
    for t in tools:
        report.append(f"\n### {t['file']}")
        for tool in t['tools']:
            report.append(f"- `{tool}`")
    
    # 4. Prompt摘要
    report.append("\n## 4. System Prompt 摘要\n")
    prompts = extract_prompts()
    for p in prompts:
        report.append(f"\n### {p['name']} (文件: {p['file']}, 长度: {p['length']})")
        report.append(f"```\n{p['preview']}...\n```")
    
    # 5. 配置
    report.append("\n## 5. 配置文件\n")
    configs = read_config()
    for name, content in configs.items():
        report.append(f"\n### {name}")
        if isinstance(content, dict):
            report.append(f"```json\n{json.dumps(content, indent=2, ensure_ascii=False)}\n```")
        else:
            report.append(f"```\n{content}\n```")
    
    # 6. API测试结果
    report.append("\n## 6. API 实时测试结果\n")
    tests = test_api()
    for t in tests:
        report.append(f"\n### {t['api']}")
        report.append(f"```json\n{json.dumps(t, indent=2, ensure_ascii=False)}\n```")
    
    return "\n".join(report)

if __name__ == "__main__":
    print("正在诊断 Agent 项目...")
    print(f"项目路径: {PROJECT_ROOT}")
    print("扫描文件中...")
    
    report = generate_report()
    OUTPUT_FILE.write_text(report, encoding='utf-8')
    
    print(f"\n诊断报告已生成: {OUTPUT_FILE}")
    print(f"报告大小: {len(report)} 字符")
    print("\n请把这份文件的内容复制发给我")
