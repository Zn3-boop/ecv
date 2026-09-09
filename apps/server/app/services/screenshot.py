"""
截图服务

功能：
1. 全屏截图
2. 窗口截图
3. 保存到指定路径
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import mss


@dataclass
class ScreenshotResult:
    """截图结果"""
    success: bool
    file_path: str | None = None
    width: int = 0
    height: int = 0
    error: str | None = None
    message: str = ""


def capture_screen(monitor: int = 1, output_path: str | None = None) -> ScreenshotResult:
    """
    截取屏幕
    
    Args:
        monitor: 显示器编号（1为主屏）
        output_path: 保存路径，默认保存到用户图片目录
        
    Returns:
        ScreenshotResult: 截图结果
    """
    try:
        with mss.mss() as sct:
            # 获取指定显示器
            mon = sct.monitors[monitor]
            
            # 截取屏幕
            screenshot = sct.grab(mon)
            
            # 生成文件名
            if not output_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = os.path.join(
                    os.path.expanduser("~"),
                    "Pictures",
                    f"screenshot_{timestamp}.png"
                )
            
            # 确保目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 保存图片
            mss.tools.to_png(screenshot.rgb, screenshot.size, output=output_path)
            
            return ScreenshotResult(
                success=True,
                file_path=output_path,
                width=screenshot.width,
                height=screenshot.height,
                message=f"截图已保存到: {output_path}"
            )
            
    except Exception as e:
        return ScreenshotResult(
            success=False,
            error=str(e),
            message=f"截图失败: {str(e)}"
        )


def capture_all_monitors(output_dir: str | None = None) -> list[ScreenshotResult]:
    """
    截取所有显示器
    
    Args:
        output_dir: 保存目录
        
    Returns:
        list[ScreenshotResult]: 所有显示器的截图结果
    """
    results = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if not output_dir:
        output_dir = os.path.join(os.path.expanduser("~"), "Pictures")
    
    os.makedirs(output_dir, exist_ok=True)
    
    with mss.mss() as sct:
        for i, mon in enumerate(sct.monitors):
            if i == 0:  # 跳过全屏合成
                continue
                
            try:
                screenshot = sct.grab(mon)
                output_path = os.path.join(output_dir, f"screen_{i}_{timestamp}.png")
                mss.tools.to_png(screenshot.rgb, screenshot.size, output=output_path)
                
                results.append(ScreenshotResult(
                    success=True,
                    file_path=output_path,
                    width=screenshot.width,
                    height=screenshot.height,
                    message=f"显示器{i}截图已保存"
                ))
            except Exception as e:
                results.append(ScreenshotResult(
                    success=False,
                    error=str(e),
                    message=f"显示器{i}截图失败"
                ))
    
    return results


def capture_window(window_title: str) -> ScreenshotResult:
    """
    截取指定窗口
    
    Args:
        window_title: 窗口标题（模糊匹配）
        
    Returns:
        ScreenshotResult: 截图结果
    """
    try:
        import pywinauto
        
        # 查找窗口
        app = pywinauto.Application()
        try:
            window = app.connect(title_re=f".*{window_title}.*")
            hwnd = window.window_.handle
        except Exception:
            return ScreenshotResult(
                success=False,
                error=f"未找到窗口: {window_title}",
                message=f"未找到标题包含'{window_title}'的窗口"
            )
        
        # 获取窗口位置
        rect = pywinauto.win32functions.GetWindowRect(hwnd)
        left, top, right, bottom = rect
        
        # 截图
        with mss.mss() as sct:
            monitor = {
                "left": left,
                "top": top,
                "width": right - left,
                "height": bottom - top,
            }
            screenshot = sct.grab(monitor)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(
                os.path.expanduser("~"),
                "Pictures",
                f"window_{timestamp}.png"
            )
            
            mss.tools.to_png(screenshot.rgb, screenshot.size, output=output_path)
            
            return ScreenshotResult(
                success=True,
                file_path=output_path,
                width=screenshot.width,
                height=screenshot.height,
                message=f"窗口截图已保存到: {output_path}"
            )
            
    except ImportError:
        return ScreenshotResult(
            success=False,
            error="pywinauto未安装",
            message="需要安装pywinauto库才能截取窗口"
        )
    except Exception as e:
        return ScreenshotResult(
            success=False,
            error=str(e),
            message=f"窗口截图失败: {str(e)}"
        )
