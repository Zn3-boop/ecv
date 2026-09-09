"""
应用商店管理服务

功能：
1. 通过winget命令管理Windows应用（winget是微软官方的包管理器）
2. 搜索应用
3. 安装应用
4. 卸载应用
5. 查看已安装应用
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import winreg

_WINGET_SAFE_PATTERN = re.compile(r'^[\w.\- +@()\[\]&,;:=#!~]+$', re.UNICODE)


def _validate_winget_input(value: str, field_name: str, max_len: int = 256) -> str:
    if not value or not isinstance(value, str):
        raise ValueError(f"{field_name} 不能为空")
    cleaned = value.strip()
    if len(cleaned) > max_len:
        raise ValueError(f"{field_name} 过长")
    if not cleaned:
        raise ValueError(f"{field_name} 不能为空")
    if not _WINGET_SAFE_PATTERN.match(cleaned):
        raise ValueError(f"{field_name} 包含非法字符")
    return cleaned


_REGISTRY_UNINSTALL_PATHS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]


def _normalize_for_match(s: str) -> str:
    return re.sub(r'[\s\-_（）()·]', '', s.lower())


def _match_score(query: str, target: str) -> float:
    q = _normalize_for_match(query)
    t = _normalize_for_match(target)
    if not q or not t:
        return 0.0
    if q == t:
        return 1.0
    if q in t:
        return 0.9
    if t in q:
        return 0.7
    q_words = set(re.findall(r'[a-z0-9\u4e00-\u9fff]+', q))
    t_words = set(re.findall(r'[a-z0-9\u4e00-\u9fff]+', t))
    if q_words and t_words:
        overlap = q_words & t_words
        ratio = len(overlap) / len(q_words)
        if ratio >= 0.5:
            return 0.6 * ratio
    qi = 0
    for c in t:
        if qi < len(q) and c == q[qi]:
            qi += 1
    subseq_ratio = qi / len(q)
    if subseq_ratio >= 0.8:
        return 0.3 * subseq_ratio
    return 0.0


def _fuzzy_match(query: str, target: str, threshold: float = 0.5) -> bool:
    return _match_score(query, target) >= threshold


def _find_uninstall_from_registry(package_name: str) -> Optional[dict]:
    candidates = []
    for hive, subkey in _REGISTRY_UNINSTALL_PATHS:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, subkey_name) as app_key:
                            try:
                                display_name, _ = winreg.QueryValueEx(app_key, "DisplayName")
                            except OSError:
                                continue
                            if not display_name:
                                continue
                            score = _match_score(package_name, display_name)
                            if score < 0.5:
                                continue
                            try:
                                uninstall_string, _ = winreg.QueryValueEx(app_key, "UninstallString")
                            except OSError:
                                continue
                            if not uninstall_string:
                                continue
                            try:
                                quiet_uninstall, _ = winreg.QueryValueEx(app_key, "QuietUninstallString")
                            except OSError:
                                quiet_uninstall = None
                            candidates.append({
                                "score": score,
                                "display_name": display_name,
                                "uninstall_string": uninstall_string,
                                "quiet_uninstall_string": quiet_uninstall,
                            })
                    except OSError:
                        continue
        except OSError:
            continue
    if not candidates:
        return None
    candidates.sort(key=lambda c: c["score"], reverse=True)
    best = candidates[0]
    return {
        "display_name": best["display_name"],
        "uninstall_string": best["uninstall_string"],
        "quiet_uninstall_string": best["quiet_uninstall_string"],
    }


def _run_uninstall_command(uninstall_string: str, timeout: float = 120) -> tuple[int, str, str]:
    uninstall_string = uninstall_string.strip()
    
    if uninstall_string.lower().startswith("msiexec"):
        base_cmd = uninstall_string
        if "/quiet" not in base_cmd.lower() and "/qn" not in base_cmd.lower():
            base_cmd += " /qn /norestart"
        commands_to_try = [base_cmd]
    else:
        if uninstall_string.startswith('"'):
            try:
                end_quote = uninstall_string.index('"', 1)
                exe = uninstall_string[1:end_quote]
                args = uninstall_string[end_quote + 1:].strip()
            except ValueError:
                exe = uninstall_string.strip('"')
                args = ""
        else:
            parts = uninstall_string.split(None, 1)
            exe = parts[0]
            args = parts[1] if len(parts) > 1 else ""
        
        silent_params = ['/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '/SILENT', '/S', '/quiet /norestart', '--silent', '--unattended']
        commands_to_try = []
        for sp in silent_params:
            test_args = args
            if not any(p.lower() in test_args.lower() for p in sp.split()):
                test_args = (test_args + ' ' + sp).strip()
            cmd = f'"{exe}" {test_args}'
            if cmd not in commands_to_try:
                commands_to_try.append(cmd)
    
    last_stdout = ""
    last_stderr = ""
    last_rc = -1
    
    for cmd in commands_to_try:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                shell=True,
            )
            stdout = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
            stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
            rc = proc.returncode or 0
            if rc == 0:
                return rc, stdout, stderr
            last_stdout = stdout
            last_stderr = stderr
            last_rc = rc
        except subprocess.TimeoutExpired:
            last_stdout = ""
            last_stderr = "卸载超时"
            last_rc = -1
        except Exception as e:
            last_stdout = ""
            last_stderr = str(e)
            last_rc = -1
    return last_rc, last_stdout, last_stderr


def _run_elevated_uninstall(uninstall_string: str, timeout: float = 180) -> tuple[int, str, str]:
    uninstall_string = uninstall_string.strip()
    safe_cmd = uninstall_string.replace("'", "''").replace('"', '\"')
    ps_script = f"Start-Process -FilePath 'cmd.exe' -ArgumentList '/c {safe_cmd}' -Verb RunAs -Wait -WindowStyle Hidden"
    try:
        proc = subprocess.run(
            ['powershell', '-Command', ps_script],
            capture_output=True,
            timeout=timeout,
            shell=True,
        )
        stdout = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
        stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
        rc = proc.returncode or 0
        return rc, stdout, stderr
    except subprocess.TimeoutExpired:
        return -1, "", "提权卸载超时"
    except Exception as e:
        return -1, "", str(e)


def _run_powershell_uninstall(app_name: str, timeout: float = 120) -> tuple[int, str, str]:
    safe_name = app_name.replace("'", "''").replace('"', '').replace('\\', '').strip()
    ps_script = f"""
$ErrorActionPreference = 'Stop'
try {{
    $pkg = Get-Package -Name '{safe_name}' -ErrorAction SilentlyContinue
    if ($pkg) {{
        Uninstall-Package -Name '{safe_name}' -Force -ErrorAction Stop
        Write-Output 'SUCCESS'
        exit 0
    }}
}} catch {{}}
try {{
    $app = Get-ItemProperty "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*" -ErrorAction SilentlyContinue |
        Where-Object {{ $_.DisplayName -like '*{safe_name}*' }} | Select-Object -First 1
    if (-not $app) {{
        $app = Get-ItemProperty "HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*" -ErrorAction SilentlyContinue |
            Where-Object {{ $_.DisplayName -like '*{safe_name}*' }} | Select-Object -First 1
    }}
    if (-not $app) {{
        $app = Get-ItemProperty "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*" -ErrorAction SilentlyContinue |
            Where-Object {{ $_.DisplayName -like '*{safe_name}*' }} | Select-Object -First 1
    }}
    if ($app -and $app.UninstallString) {{
        $uninst = $app.UninstallString
        Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', $uninst -Verb RunAs -Wait -WindowStyle Hidden
        Write-Output 'SUCCESS_ELEVATED'
        exit 0
    }}
    Write-Output 'NOT_FOUND'
    exit 1
}} catch {{
    Write-Output $_.Exception.Message
    exit 2
}}
"""
    try:
        proc = subprocess.run(
            ['powershell', '-Command', ps_script],
            capture_output=True,
            timeout=timeout,
            shell=True,
        )
        stdout = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
        stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
        rc = proc.returncode or 0
        if "SUCCESS" in stdout or "SUCCESS_ELEVATED" in stdout:
            rc = 0
        return rc, stdout, stderr
    except subprocess.TimeoutExpired:
        return -1, "", "PowerShell 卸载超时"
    except Exception as e:
        return -1, "", str(e)


def _verify_uninstalled(package_name: str) -> bool:
    for hive, subkey in _REGISTRY_UNINSTALL_PATHS:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, subkey_name) as app_key:
                            try:
                                display_name, _ = winreg.QueryValueEx(app_key, "DisplayName")
                            except OSError:
                                continue
                            if display_name and _fuzzy_match(package_name, display_name, threshold=0.7):
                                return False
                    except OSError:
                        continue
        except OSError:
            continue
    return True


def _sanitize_name(name: str) -> str:
    return name.replace('"', '').replace("'", "").replace("\\", "").strip()


from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class StoreResult:
    success: bool
    message: str
    data: Any = None
    error: str | None = None


async def _run_winget(args: list[str], timeout: float) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        'winget', *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ''
    stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ''
    return proc.returncode or 0, stdout, stderr


async def search_app(query: str) -> StoreResult:
    try:
        safe_query = _validate_winget_input(query, "query")
        returncode, stdout, stderr = await _run_winget(
            ['search', safe_query, '--accept-source-agreements'],
            timeout=30,
        )

        if returncode == 0:
            apps = parse_winget_list(stdout)
            return StoreResult(
                success=True,
                message=f"找到 {len(apps)} 个应用",
                data={"apps": apps}
            )
        else:
            return StoreResult(
                success=False,
                message="搜索失败",
                error=stderr or "未知错误"
            )

    except asyncio.TimeoutError:
        return StoreResult(
            success=False,
            message="搜索超时",
            error="搜索操作超时"
        )
    except Exception as e:
        return StoreResult(
            success=False,
            message="搜索失败",
            error=str(e)
        )


async def install_app(package_id: str, app_name: str = None) -> StoreResult:
    try:
        safe_id = _validate_winget_input(package_id, "package_id")
        returncode, stdout, stderr = await _run_winget(
            ['install', '--id', safe_id, '-e', '--silent',
             '--accept-package-agreements', '--accept-source-agreements'],
            timeout=300,
        )

        if returncode == 0:
            return StoreResult(
                success=True,
                message=f"成功安装 {app_name or package_id}",
                data={"package_id": package_id}
            )
        else:
            return StoreResult(
                success=False,
                message="安装失败",
                error=stderr or stdout
            )

    except asyncio.TimeoutError:
        return StoreResult(
            success=False,
            message="安装超时",
            error="安装操作超时，请检查网络连接"
        )
    except Exception as e:
        return StoreResult(
            success=False,
            message="安装失败",
            error=str(e)
        )


async def uninstall_app(package_id: str) -> StoreResult:
    try:
        safe_id = _validate_winget_input(package_id, "package_id")
        winget_error = ""
        methods_tried = []

        try:
            returncode, stdout, stderr = await _run_winget(
                ['uninstall', '--id', safe_id, '-e', '--silent', '--force',
                 '--accept-source-agreements'],
                timeout=90,
            )
            methods_tried.append("winget_id")
            if returncode == 0:
                loop = asyncio.get_running_loop()
                verified = await loop.run_in_executor(None, _verify_uninstalled, package_id)
                if verified:
                    return StoreResult(
                        success=True,
                        message=f"成功卸载 {package_id}（通过 winget ID）",
                        data={"package_id": package_id, "method": "winget_id", "verified": True}
                    )
                winget_error = "winget 返回成功但应用仍存在（可能需要重启或管理员权限）"
            else:
                winget_error = (stderr or stdout or "")[:200]

            returncode2, stdout2, stderr2 = await _run_winget(
                ['uninstall', '--name', safe_id, '--silent', '--force',
                 '--accept-source-agreements'],
                timeout=90,
            )
            methods_tried.append("winget_name")
            if returncode2 == 0:
                loop = asyncio.get_running_loop()
                verified = await loop.run_in_executor(None, _verify_uninstalled, package_id)
                if verified:
                    return StoreResult(
                        success=True,
                        message=f"成功卸载 {package_id}（通过 winget 名称）",
                        data={"package_id": package_id, "method": "winget_name", "verified": True}
                    )
                winget_error = "winget 返回成功但应用仍存在（可能需要重启或管理员权限）"
            else:
                winget_error = winget_error + " | " + (stderr2 or stdout2 or "")[:200]
        except Exception as we:
            winget_error = str(we)

        reg_info = _find_uninstall_from_registry(package_id)
        if reg_info:
            methods_tried.append("registry")
            uninstall_cmd = reg_info.get("quiet_uninstall_string") or reg_info["uninstall_string"]
            display_name = reg_info["display_name"]
            loop = asyncio.get_running_loop()
            rc, out, err = await loop.run_in_executor(
                None, _run_uninstall_command, uninstall_cmd, 180
            )
            if rc == 0:
                verified = await loop.run_in_executor(None, _verify_uninstalled, package_id)
                if verified:
                    return StoreResult(
                        success=True,
                        message=f"成功卸载 {display_name}（通过注册表卸载程序）",
                        data={"package_id": package_id, "method": "registry", "display_name": display_name, "verified": True}
                    )
                reg_error = "注册表卸载返回成功但应用仍存在"
            else:
                reg_error = err or out or f"卸载程序退出码: {rc}"
                if rc == 1603:
                    methods_tried.append("registry_elevated")
                    rc2, out2, err2 = await loop.run_in_executor(
                        None, _run_elevated_uninstall, uninstall_cmd, 180
                    )
                    if rc2 == 0:
                        verified = await loop.run_in_executor(None, _verify_uninstalled, package_id)
                        if verified:
                            return StoreResult(
                                success=True,
                                message=f"成功卸载 {display_name}（通过提权注册表卸载）",
                                data={"package_id": package_id, "method": "registry_elevated", "display_name": display_name, "verified": True}
                            )
                        reg_error = "提权卸载后应用仍存在（可能需要重启）"
                    else:
                        reg_error = f"退出码 {rc}，提权后退出码 {rc2}（可能需要管理员权限）"
        else:
            reg_error = None

        ps_name = display_name if reg_info else package_id
        ps_error = None
        try:
            loop = asyncio.get_running_loop()
            rc, out, err = await loop.run_in_executor(
                None, _run_powershell_uninstall, ps_name, 120
            )
            methods_tried.append("powershell")
            if rc == 0 and ("SUCCESS" in out or "SUCCESS_ELEVATED" in out):
                verified = await loop.run_in_executor(None, _verify_uninstalled, package_id)
                if verified:
                    return StoreResult(
                        success=True,
                        message=f"成功卸载 {ps_name}（通过 PowerShell）",
                        data={"package_id": package_id, "method": "powershell", "verified": True}
                    )
                ps_error = "PowerShell 卸载后应用仍存在（可能需要重启）"
            elif rc == 0:
                verified = await loop.run_in_executor(None, _verify_uninstalled, package_id)
                if verified:
                    return StoreResult(
                        success=True,
                        message=f"成功卸载 {ps_name}（通过 PowerShell，已验证）",
                        data={"package_id": package_id, "method": "powershell", "verified": True}
                    )
                ps_error = (err or out or f"PowerShell 退出码: {rc}")[:200]
            else:
                ps_error = (err or out or f"PowerShell 退出码: {rc}")[:200]
        except Exception as we:
            ps_error = str(we)

        error_parts = []
        if winget_error and winget_error.strip():
            error_parts.append(f"winget: {winget_error.strip()[:200]}")
        if reg_error:
            error_parts.append(f"注册表: {reg_error[:200]}")
        if ps_error:
            error_parts.append(f"PowerShell: {ps_error[:200]}")

        error_detail = " | ".join(error_parts) if error_parts else "所有方法均未找到该应用"
        return StoreResult(
            success=False,
            message=f"卸载 {package_id} 失败",
            error=error_detail,
            data={"methods_tried": methods_tried}
        )

    except ValueError as ve:
        return StoreResult(
            success=False,
            message=f"卸载参数无效",
            error=str(ve)
        )
    except asyncio.TimeoutError:
        return StoreResult(
            success=False,
            message="卸载超时",
            error="卸载操作超时，请手动通过控制面板卸载"
        )
    except Exception as e:
        return StoreResult(
            success=False,
            message="卸载失败",
            error=str(e) or type(e).__name__
        )


async def list_installed() -> StoreResult:
    try:
        returncode, stdout, stderr = await _run_winget(
            ['list'],
            timeout=30,
        )

        if returncode == 0:
            apps = parse_winget_list(stdout)
            return StoreResult(
                success=True,
                message=f"共有 {len(apps)} 个已安装应用",
                data={"apps": apps}
            )
        else:
            return StoreResult(
                success=False,
                message="获取列表失败",
                error=stderr
            )

    except Exception as e:
        return StoreResult(
            success=False,
            message="获取列表失败",
            error=str(e)
        )


def parse_winget_list(output: str) -> list[dict]:
    apps = []
    if not output:
        return apps
    lines = output.split('\n')

    for line in lines[2:]:
        line = line.strip()
        if not line:
            continue

        parts = re.split(r'\s{2,}', line)
        if len(parts) >= 2:
            name = parts[0].strip()
            package_id = parts[1].strip() if len(parts) > 1 else ""
            version = parts[2].strip() if len(parts) > 2 else ""
            source = parts[3].strip() if len(parts) > 3 else ""

            if name and package_id:
                apps.append({
                    "name": name,
                    "id": package_id,
                    "version": version,
                    "source": source,
                })

    return apps


async def get_winget_status() -> StoreResult:
    try:
        returncode, stdout, stderr = await _run_winget(
            ['--version'],
            timeout=10,
        )

        if returncode == 0:
            version = stdout.strip()
            return StoreResult(
                success=True,
                message=f"Winget可用，版本: {version}",
                data={"version": version}
            )
        else:
            return StoreResult(
                success=False,
                message="Winget不可用",
                error="请确保Windows版本支持winget（Windows 10 1809+）"
            )
    except Exception as e:
        return StoreResult(
            success=False,
            message="Winget不可用",
            error=str(e)
        )