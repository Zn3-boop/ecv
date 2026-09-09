"""
Office自动化服务 - Word/Excel/PPT控制
使用pywin32实现Windows COM自动化
"""

import pythoncom
import win32com.client
from dataclasses import dataclass
from typing import Any, Optional
import os


@dataclass
class OfficeResult:
    """Office操作结果"""
    success: bool
    message: str
    data: Any = None
    error: str | None = None


def _init_com():
    """初始化COM"""
    try:
        pythoncom.CoInitialize()
        return True
    except:
        return False


def _cleanup_com():
    """清理COM"""
    try:
        pythoncom.CoUninitialize()
    except:
        pass


# ============== Word操作 ==============

def word_create_document(content: str = "", save_path: str = None) -> OfficeResult:
    """
    创建Word文档
    
    Args:
        content: 初始内容
        save_path: 保存路径（可选）
        
    Returns:
        OfficeResult: 操作结果
    """
    try:
        _init_com()
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = True
        
        doc = word.Documents.Add()
        
        if content:
            word.Selection.TypeText(content)
        
        if save_path:
            doc.SaveAs(save_path)
            doc.Close()
            word.Quit()
            _cleanup_com()
            return OfficeResult(
                success=True,
                message=f"文档已保存到 {save_path}",
                data={"path": save_path}
            )
        else:
            _cleanup_com()
            return OfficeResult(
                success=True,
                message="文档已创建（未保存）",
                data={"document": doc, "word": word}
            )
            
    except Exception as e:
        _cleanup_com()
        return OfficeResult(
            success=False,
            message="创建Word文档失败",
            error=str(e)
        )


def word_open_document(file_path: str) -> OfficeResult:
    """
    打开Word文档
    
    Args:
        file_path: 文档路径
        
    Returns:
        OfficeResult: 操作结果
    """
    try:
        if not os.path.exists(file_path):
            return OfficeResult(
                success=False,
                message="文件不存在",
                error=f"{file_path} 不存在"
            )
        
        _init_com()
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = True
        
        doc = word.Documents.Open(file_path)
        
        return OfficeResult(
            success=True,
            message=f"已打开文档 {os.path.basename(file_path)}",
            data={"document": doc, "word": word}
        )
        
    except Exception as e:
        _cleanup_com()
        return OfficeResult(
            success=False,
            message="打开Word文档失败",
            error=str(e)
        )


def word_edit_document(doc, text_to_add: str, position: str = "end") -> OfficeResult:
    """
    编辑Word文档
    
    Args:
        doc: Word文档对象
        text_to_add: 要添加的文本
        position: 位置 ("start", "end", "selection")
        
    Returns:
        OfficeResult: 操作结果
    """
    try:
        if position == "start":
            doc.Range(0, 0).InsertBefore(text_to_add)
        elif position == "end":
            doc.Range(doc.Content.End - 1, doc.Content.End - 1).InsertAfter(text_to_add)
        else:  # selection
            doc.Application.Selection.TypeText(text_to_add)
        
        return OfficeResult(
            success=True,
            message=f"已添加文本: {text_to_add[:50]}...",
            data={"added_text": text_to_add}
        )
        
    except Exception as e:
        return OfficeResult(
            success=False,
            message="编辑文档失败",
            error=str(e)
        )


def word_close_document(doc, save_changes: bool = True) -> OfficeResult:
    """
    关闭Word文档
    
    Args:
        doc: Word文档对象
        save_changes: 是否保存更改
        
    Returns:
        OfficeResult: 操作结果
    """
    try:
        doc.Close(SaveChanges=save_changes)
        return OfficeResult(
            success=True,
            message="文档已关闭"
        )
    except Exception as e:
        return OfficeResult(
            success=False,
            message="关闭文档失败",
            error=str(e)
        )


def word_quit(word) -> OfficeResult:
    """
    退出Word
    
    Args:
        word: Word应用对象
        
    Returns:
        OfficeResult: 操作结果
    """
    try:
        word.Quit()
        _cleanup_com()
        return OfficeResult(
            success=True,
            message="Word已退出"
        )
    except Exception as e:
        return OfficeResult(
            success=False,
            message="退出Word失败",
            error=str(e)
        )


# ============== Excel操作 ==============

def excel_create_workbook(data: list = None, save_path: str = None) -> OfficeResult:
    """
    创建Excel工作簿
    
    Args:
        data: 初始数据（二维数组）
        save_path: 保存路径
        
    Returns:
        OfficeResult: 操作结果
    """
    try:
        _init_com()
        excel = win32com.client.Dispatch("Excel.Application")
        excel.Visible = True
        
        wb = excel.Workbooks.Add()
        ws = wb.ActiveSheet
        
        # 如果提供了数据，写入数据
        if data:
            for row_idx, row in enumerate(data, start=1):
                for col_idx, value in enumerate(row, start=1):
                    ws.Cells(row_idx, col_idx).Value = value
        
        if save_path:
            wb.SaveAs(save_path)
            wb.Close()
            excel.Quit()
            _cleanup_com()
            return OfficeResult(
                success=True,
                message=f"工作簿已保存到 {save_path}",
                data={"path": save_path}
            )
        
        return OfficeResult(
            success=True,
            message="工作簿已创建",
            data={"workbook": wb, "sheet": ws, "excel": excel}
        )
        
    except Exception as e:
        _cleanup_com()
        return OfficeResult(
            success=False,
            message="创建Excel工作簿失败",
            error=str(e)
        )


def excel_open_workbook(file_path: str) -> OfficeResult:
    """
    打开Excel工作簿
    
    Args:
        file_path: 工作簿路径
        
    Returns:
        OfficeResult: 操作结果
    """
    try:
        if not os.path.exists(file_path):
            return OfficeResult(
                success=False,
                message="文件不存在",
                error=f"{file_path} 不存在"
            )
        
        _init_com()
        excel = win32com.client.Dispatch("Excel.Application")
        excel.Visible = True
        
        wb = excel.Workbooks.Open(file_path)
        ws = wb.ActiveSheet
        
        return OfficeResult(
            success=True,
            message=f"已打开工作簿 {os.path.basename(file_path)}",
            data={"workbook": wb, "sheet": ws, "excel": excel}
        )
        
    except Exception as e:
        _cleanup_com()
        return OfficeResult(
            success=False,
            message="打开Excel工作簿失败",
            error=str(e)
        )


def excel_write_cell(ws, row: int, col: int, value: Any) -> OfficeResult:
    """
    写入单元格
    
    Args:
        ws: 工作表对象
        row: 行号
        col: 列号
        value: 值
        
    Returns:
        OfficeResult: 操作结果
    """
    try:
        ws.Cells(row, col).Value = value
        return OfficeResult(
            success=True,
            message=f"已写入 {chr(64+col)}{row}: {value}",
            data={"row": row, "col": col, "value": value}
        )
    except Exception as e:
        return OfficeResult(
            success=False,
            message="写入单元格失败",
            error=str(e)
        )


def excel_read_cell(ws, row: int, col: int) -> OfficeResult:
    """
    读取单元格
    
    Args:
        ws: 工作表对象
        row: 行号
        col: 列号
        
    Returns:
        OfficeResult: 操作结果
    """
    try:
        value = ws.Cells(row, col).Value
        return OfficeResult(
            success=True,
            message=f"单元格 {chr(64+col)}{row} 的值: {value}",
            data={"row": row, "col": col, "value": value}
        )
    except Exception as e:
        return OfficeResult(
            success=False,
            message="读取单元格失败",
            error=str(e)
        )


# ============== PowerPoint操作 ==============

def ppt_create_presentation(title: str = "演示文稿", save_path: str = None) -> OfficeResult:
    """
    创建PowerPoint演示文稿
    
    Args:
        title: 标题
        save_path: 保存路径
        
    Returns:
        OfficeResult: 操作结果
    """
    try:
        _init_com()
        ppt = win32com.client.Dispatch("PowerPoint.Application")
        ppt.Visible = True
        
        presentation = ppt.Presentations.Add()
        slide = presentation.Slides.Add(1, 1)  # 添加第一张幻灯片
        
        # 设置标题
        if slide.Shapes.Title:
            slide.Shapes.Title.TextFrame.TextRange.Text = title
        
        if save_path:
            presentation.SaveAs(save_path)
            presentation.Close()
            ppt.Quit()
            _cleanup_com()
            return OfficeResult(
                success=True,
                message=f"演示文稿已保存到 {save_path}",
                data={"path": save_path}
            )
        
        return OfficeResult(
            success=True,
            message="演示文稿已创建",
            data={"presentation": presentation, "slide": slide, "ppt": ppt}
        )
        
    except Exception as e:
        _cleanup_com()
        return OfficeResult(
            success=False,
            message="创建PowerPoint演示文稿失败",
            error=str(e)
        )


def ppt_add_slide(presentation, title: str = None, content: str = None) -> OfficeResult:
    """
    添加幻灯片
    
    Args:
        presentation: 演示文稿对象
        title: 标题
        content: 内容
        
    Returns:
        OfficeResult: 操作结果
    """
    try:
        slide_count = presentation.Slides.Count
        slide = presentation.Slides.Add(slide_count + 1, 1)
        
        if title and slide.Shapes.Title:
            slide.Shapes.Title.TextFrame.TextRange.Text = title
        
        if content:
            # 添加文本框
            left = 1
            top = 2
            width = 8
            height = 5
            shape = slide.Shapes.AddTextbox(1, left, top, width, height)
            shape.TextFrame.TextRange.Text = content
        
        return OfficeResult(
            success=True,
            message=f"已添加幻灯片 #{slide_count + 1}",
            data={"slide": slide, "slide_number": slide_count + 1}
        )
        
    except Exception as e:
        return OfficeResult(
            success=False,
            message="添加幻灯片失败",
            error=str(e)
        )


def ppt_open_presentation(file_path: str) -> OfficeResult:
    """
    打开PowerPoint演示文稿
    
    Args:
        file_path: 演示文稿路径
        
    Returns:
        OfficeResult: 操作结果
    """
    try:
        if not os.path.exists(file_path):
            return OfficeResult(
                success=False,
                message="文件不存在",
                error=f"{file_path} 不存在"
            )
        
        _init_com()
        ppt = win32com.client.Dispatch("PowerPoint.Application")
        ppt.Visible = True
        
        presentation = ppt.Presentations.Open(file_path)
        
        return OfficeResult(
            success=True,
            message=f"已打开演示文稿 {os.path.basename(file_path)}",
            data={"presentation": presentation, "ppt": ppt}
        )
        
    except Exception as e:
        _cleanup_com()
        return OfficeResult(
            success=False,
            message="打开PowerPoint演示文稿失败",
            error=str(e)
        )
