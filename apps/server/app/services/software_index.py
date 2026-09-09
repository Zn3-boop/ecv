from __future__ import annotations

import json
import os
import re
import winreg
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import fnmatch

# 别名映射：用户口语 -> 注册表/文件名关键词
ALIAS_MAP = {
    # 百度系
    "百度网盘": "baidu", "百度云": "baidu", "百度云盘": "baidu", "baidunetdisk": "baidu",
    # 腾讯系
    "微信": "wechat", "weixin": "wechat", "qq": "qq", "扣扣": "qq", "tim": "tim",
    # 办公
    "记事本": "notepad", "文本编辑器": "notepad", "计算器": "calc",
    "资源管理器": "explorer", "文件管理器": "explorer", "我的电脑": "explorer",
    "任务管理器": "taskmgr", "控制面板": "control", "设置": "ms-settings",
    "终端": "wt", "命令提示符": "cmd", "cmd": "cmd", "powershell": "powershell",
    "画图": "mspaint", "截图工具": "snippingtool",
    # 浏览器
    "edge": "msedge", "edge浏览器": "msedge", "微软浏览器": "msedge",
    "浏览器": "msedge", "chrome": "chrome", "谷歌浏览器": "chrome", "谷歌": "chrome",
    "火狐": "firefox", "firefox": "firefox",
    # 开发工具
    "vscode": "code", "visual studio code": "code", "code": "code",
    "pycharm": "pycharm", "idea": "idea", "webstorm": "webstorm",
    "node": "node", "nodejs": "node", "python": "python",
    # Office 系列（短名 → 注册表关键词）
    "wps": "wps", "office": "winword", "word": "winword", "excel": "excel", "ppt": "powerpnt",
    "winword.exe": "winword", "winword": "winword",
    "excel.exe": "excel", "powerpnt.exe": "powerpnt",
    # 其他常用
    "steam": "steam", "epic": "epic", "钉钉": "dingtalk", "飞书": "feishu", "lark": "lark",
    "网易云音乐": "cloudmusic", "qq音乐": "qqmusic", "酷狗": "kugou",
    "爱奇艺": "iqiyi", "腾讯视频": "tencentvideo", "优酷": "youku",
    "迅雷": "thunder", "bandizip": "bandizip", "7zip": "7z", "everything": "everything",
    "clash": "clash", "v2ray": "v2ray", "telegram": "telegram", "微信开发者工具": "wechatdevtools",
    "腾讯会议": "wemeet", "zoom": "zoom", "teams": "teams", "企业微信": "wxwork",
    "百度翻译": "baidutranslate", "有道翻译": "youdao",
    # .exe 短名兜底（LLM 可能输出这些）
    "msedge.exe": "msedge", "chrome.exe": "chrome", "firefox.exe": "firefox",
    "code.exe": "code", "wechat.exe": "wechat", "dingtalk.exe": "dingtalk",
    "feishu.exe": "feishu", "notepad.exe": "notepad", "calc.exe": "calc",
    "photoshop.exe": "photoshop", "ps": "photoshop",
    "figma": "figma", "剪映": "capcut", "capcut": "capcut",
    "spotify": "spotify", "potplayer": "potplayer",
}

# 系统内置工具（不在注册表卸载列表里，但确定存在）
SYSTEM_APPS = {
    "notepad": {"path": r"C:\Windows\System32\notepad.exe", "display": "记事本"},
    "calc": {"path": r"C:\Windows\System32\calc.exe", "display": "计算器"},
    "mspaint": {"path": r"C:\Windows\System32\mspaint.exe", "display": "画图"},
    "cmd": {"path": r"C:\Windows\System32\cmd.exe", "display": "命令提示符"},
    "taskmgr": {"path": r"C:\Windows\System32\taskmgr.exe", "display": "任务管理器"},
    "control": {"path": r"C:\Windows\System32\control.exe", "display": "控制面板"},
    "explorer": {"path": r"C:\Windows\explorer.exe", "display": "文件资源管理器"},
    "snippingtool": {"path": r"C:\Windows\System32\SnippingTool.exe", "display": "截图工具"},
    "wt": {"path": r"C:\Users\{username}\AppData\Local\Microsoft\WindowsApps\wt.exe", "display": "Windows Terminal"},
}


@dataclass
class SoftwareEntry:
    name: str           # 注册表/快捷方式里的显示名称（如 "百度网盘"）
    exe_path: str       # 可执行文件绝对路径
    publisher: str = ""  # 发布者
    version: str = ""    # 版本
    source: str = ""     # 来源：registry_uninstall / app_paths / start_menu / system / alias
    
    # 用于匹配的搜索关键词（小写）
    keywords: set[str] = field(default_factory=set)


class SoftwareIndex:
    """Windows 已安装软件索引"""
    
    def __init__(self):
        self._entries: list[SoftwareEntry] = []
        self._name_map: dict[str, SoftwareEntry] = {}  # 小写名称 -> entry
        self._keyword_map: dict[str, list[SoftwareEntry]] = {}  # 关键词 -> entries
        self._scanned = False
    
    def scan(self) -> None:
        """扫描所有来源建立索引"""
        if self._scanned:
            return
        
        self._entries.clear()
        self._name_map.clear()
        self._keyword_map.clear()
        
        # 1. 扫描注册表卸载信息（最全面的已安装软件列表）
        self._scan_registry_uninstall(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
        self._scan_registry_uninstall(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")
        self._scan_registry_uninstall(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
        
        # 2. 扫描注册表 App Paths（直接启动路径）
        self._scan_app_paths()
        
        # 3. 扫描开始菜单快捷方式
        self._scan_start_menu()
        
        # 4. 注入系统内置工具
        self._inject_system_apps()
        
        # 5. 构建关键词索引
        self._build_keyword_index()
        
        self._scanned = True
        print(f"[SoftwareIndex] 扫描完成，共 {len(self._entries)} 个软件")
    
    def _scan_registry_uninstall(self, hive: int, subkey: str) -> None:
        """从注册表卸载信息扫描"""
        try:
            with winreg.OpenKey(hive, subkey) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        app_key_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, app_key_name) as app_key:
                            display_name = self._reg_str(app_key, "DisplayName")
                            install_location = self._reg_str(app_key, "InstallLocation")
                            publisher = self._reg_str(app_key, "Publisher")
                            version = self._reg_str(app_key, "DisplayVersion")
                            
                            if not display_name:
                                continue
                            
                            # 尝试在 InstallLocation 下找 .exe
                            exe_path = ""
                            if install_location and os.path.exists(install_location):
                                exe_path = self._find_exe_in_dir(install_location, app_key_name)
                            
                            entry = SoftwareEntry(
                                name=display_name,
                                exe_path=exe_path,
                                publisher=publisher,
                                version=version,
                                source="registry_uninstall"
                            )
                            self._add_entry(entry)
                    except Exception:
                        continue
        except Exception as e:
            print(f"[SoftwareIndex] 注册表扫描失败 {subkey}: {e}")
    
    def _scan_app_paths(self) -> None:
        """扫描 App Paths 注册表（Windows 运行对话框的数据源）"""
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                              r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths") as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        exe_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, exe_name) as app_key:
                            path, _ = winreg.QueryValueEx(app_key, None)
                            if path and os.path.exists(path):
                                # 从 exe 文件名提取名称
                                base_name = os.path.splitext(exe_name)[0]
                                display_name = base_name
                                
                                entry = SoftwareEntry(
                                    name=display_name,
                                    exe_path=path,
                                    source="app_paths"
                                )
                                self._add_entry(entry)
                    except Exception:
                        continue
        except Exception as e:
            print(f"[SoftwareIndex] AppPaths 扫描失败: {e}")
    
    def _scan_start_menu(self) -> None:
        """扫描开始菜单快捷方式"""
        start_menu_paths = [
            os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), 
                        r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.environ.get("APPDATA", r""), 
                        r"Microsoft\Windows\Start Menu\Programs"),
        ]
        
        for root in start_menu_paths:
            if not os.path.exists(root):
                continue
            for dirpath, _, filenames in os.walk(root):
                for fname in filenames:
                    if fname.endswith(".lnk"):
                        full_path = os.path.join(dirpath, fname)
                        # 解析快捷方式目标（需要 comtypes 或 win32com，这里简化）
                        # 简化方案：用快捷方式文件名作为显示名
                        display_name = os.path.splitext(fname)[0]
                        entry = SoftwareEntry(
                            name=display_name,
                            exe_path=full_path,  # 存 .lnk 路径，Electron 端可以解析
                            source="start_menu"
                        )
                        self._add_entry(entry)
    
    def _inject_system_apps(self) -> None:
        """注入系统内置工具"""
        username = os.environ.get("USERNAME", os.environ.get("USER", ""))
        for key, info in SYSTEM_APPS.items():
            path = info["path"].replace("{username}", username)
            # 对于 wt.exe 这种可能在 WindowsApps 的，尝试找实际路径
            if not os.path.exists(path) and key == "wt":
                # 尝试找 Windows Terminal
                wt_alt = os.path.expandvars(r"%LocalAppData%\Microsoft\WindowsApps\wt.exe")
                if os.path.exists(wt_alt):
                    path = wt_alt
            
            entry = SoftwareEntry(
                name=info["display"],
                exe_path=path if os.path.exists(path) else "",
                source="system"
            )
            entry.keywords.add(key)
            self._add_entry(entry)
    
    def _add_entry(self, entry: SoftwareEntry) -> None:
        """添加条目并去重"""
        if not entry.name:
            return
        
        # 如果已存在同名且路径更明确的，保留路径明确的
        lower_name = entry.name.lower()
        if lower_name in self._name_map:
            existing = self._name_map[lower_name]
            if existing.exe_path and not entry.exe_path:
                return  # 保留有路径的
            if not existing.exe_path and entry.exe_path:
                self._name_map[lower_name] = entry
                self._entries = [e for e in self._entries if e.name.lower() != lower_name]
                self._entries.append(entry)
                return
        
        self._name_map[lower_name] = entry
        self._entries.append(entry)
    
    def _build_keyword_index(self) -> None:
        """构建关键词索引用于模糊匹配"""
        for entry in self._entries:
            # 从显示名称提取关键词
            name = entry.name.lower()
            # 去掉版本号、括号内容
            clean = re.sub(r'[\d\.\(\)\[\]]', '', name).strip()
            for word in clean.split():
                if len(word) > 1:
                    entry.keywords.add(word)
                    self._keyword_map.setdefault(word, []).append(entry)
            
            # 加入别名
            for alias, target in ALIAS_MAP.items():
                if target in name or target in entry.exe_path.lower():
                    entry.keywords.add(alias.lower())
                    self._keyword_map.setdefault(alias.lower(), []).append(entry)
            
            # 从路径提取文件名作为关键词
            if entry.exe_path:
                basename = os.path.splitext(os.path.basename(entry.exe_path))[0].lower()
                entry.keywords.add(basename)
                self._keyword_map.setdefault(basename, []).append(entry)
    
    def _reg_str(self, key, value_name: str) -> str:
        """安全读取注册表字符串"""
        try:
            val, _ = winreg.QueryValueEx(key, value_name)
            return str(val) if val else ""
        except Exception:
            return ""
    
    def _find_exe_in_dir(self, directory: str, app_key_name: str) -> str:
        """在目录下寻找最可能的 .exe"""
        if not os.path.exists(directory):
            return ""
        
        # 卸载程序的关键词（这些不是主程序）
        uninstall_keywords = ['uninst', 'uninstall', 'unins', 'setup', 'installer', 'remove']
        # 非主程序关键词（BugReport、crash reporter、update 等）
        non_main_keywords = ['bugreport', 'crashreport', 'crash_handler', 'reporter',
                           'updater', 'update', 'daemon', 'service', 'helper',
                           'watchdog', 'tray', 'agent', 'monitor', 'installer',
                           'uninstall', 'repair', 'configtool', 'setting']
        
        exes = []
        for root, _, files in os.walk(directory):
            # 限制深度，避免遍历太深
            if root.count(os.sep) - directory.count(os.sep) > 2:
                break
            for f in files:
                if f.endswith(".exe"):
                    exes.append(os.path.join(root, f))
        
        if not exes:
            return ""
        
        # 过滤掉卸载程序
        main_exes = []
        for e in exes:
            base = os.path.splitext(os.path.basename(e))[0].lower()
            is_uninstall = any(kw in base for kw in uninstall_keywords)
            if not is_uninstall:
                main_exes.append(e)
        
        # 如果有主程序，优先使用
        if main_exes:
            exes = main_exes
        
        # 进一步过滤：排除非主程序（BugReport 等）
        primary_exes = []
        for e in exes:
            base = os.path.splitext(os.path.basename(e))[0].lower()
            is_non_main = any(kw in base for kw in non_main_keywords)
            if not is_non_main:
                primary_exes.append(e)
        
        # 如果过滤后有结果，使用过滤后的；否则回退
        if primary_exes:
            exes = primary_exes
        
        # 优先匹配和 app_key_name 相似的
        key_lower = app_key_name.lower()
        for e in exes:
            base = os.path.splitext(os.path.basename(e))[0].lower()
            if key_lower in base or base in key_lower:
                return e
        
        # 其次找和目录名相似的（如 BaiduNetdisk 目录下找 BaiduNetdisk.exe）
        dir_basename = os.path.basename(directory).lower()
        for e in exes:
            base = os.path.splitext(os.path.basename(e))[0].lower()
            if dir_basename in base or base in dir_basename:
                return e
        
        # 其次找最短的（通常是主程序）
        return min(exes, key=lambda x: len(os.path.basename(x)))
    
    def find(self, query: str) -> Optional[SoftwareEntry]:
        """
        根据用户输入查找软件。
        支持：精确名称、别名、模糊关键词
        """
        if not self._scanned:
            self.scan()
        
        query_lower = query.lower().strip()
        
        # 1. 精确匹配
        if query_lower in self._name_map:
            return self._name_map[query_lower]
        
        # 2. 别名匹配
        if query_lower in ALIAS_MAP:
            target = ALIAS_MAP[query_lower]
            # 在关键词索引里找
            candidates = self._keyword_map.get(target, [])
            # 优先返回有 exe_path 的
            for c in candidates:
                if c.exe_path and os.path.exists(c.exe_path):
                    return c
            if candidates:
                return candidates[0]
        
        # 3. 包含匹配（名称包含查询词）
        for name_lower, entry in self._name_map.items():
            if query_lower in name_lower:
                if entry.exe_path and os.path.exists(entry.exe_path):
                    return entry
        
        # 4. 关键词包含匹配
        for keyword, entries in self._keyword_map.items():
            if query_lower in keyword or keyword in query_lower:
                for e in entries:
                    if e.exe_path and os.path.exists(e.exe_path):
                        return e
        
        # 5. 尝试直接用 App Paths 查找（兜底）
        # 用户可能说的是文件名，如 "BaiduNetdisk"
        direct_path = self._try_app_paths(query)
        if direct_path:
            return SoftwareEntry(
                name=query,
                exe_path=direct_path,
                source="app_paths_direct"
            )
        
        return None
    
    def _try_app_paths(self, name: str) -> Optional[str]:
        """直接尝试从 App Paths 读取"""
        exe_name = name if name.endswith(".exe") else f"{name}.exe"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                              r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths") as key:
                with winreg.OpenKey(key, exe_name) as app_key:
                    path, _ = winreg.QueryValueEx(app_key, None)
                    if path and os.path.exists(path):
                        return path
        except Exception:
            pass
        return None
    
    def list_all(self) -> list[SoftwareEntry]:
        """返回所有已索引软件"""
        if not self._scanned:
            self.scan()
        return self._entries
    
    def refresh(self) -> None:
        """强制重新扫描"""
        self._scanned = False
        self.scan()


# 全局单例
_software_index = SoftwareIndex()

def get_software_index() -> SoftwareIndex:
    """获取软件索引单例（首次调用时自动扫描）"""
    if not _software_index._scanned:
        _software_index.scan()
    return _software_index


def find_software(query: str) -> Optional[SoftwareEntry]:
    """便捷函数：根据查询查找软件"""
    return get_software_index().find(query)


def get_all_software() -> list[SoftwareEntry]:
    """便捷函数：获取所有软件"""
    return get_software_index().list_all()