"""任务2: 创建毕设论文"""
import os, subprocess, time

print("="*50)
print("任务2: 创建计算机毕设论文")
print("="*50)

# 1. 打开浏览器搜索
print(">>> 步骤1: 打开浏览器搜索毕设相关资源")
subprocess.Popen('start "" "https://www.bing.com/search?q=计算机专业毕业设计+论文模板"', shell=True)
print("[OK] 浏览器已打开搜索")
time.sleep(1)

# 2. 创建论文内容
print(">>> 步骤2: 生成毕业论文内容")
content = """【人工智能在图像识别中的应用研究】

一、摘要

随着深度学习技术的快速发展，人工智能在图像识别领域取得了显著的突破。本文研究了卷积神经网络在图像分类任务中的应用，通过实验验证了残差网络在ImageNet数据集上的优异性能。

二、引言

图像识别是计算机视觉领域的核心任务之一，在医疗诊断、自动驾驶、安防监控等领域有着广泛的应用价值。

三、相关技术

3.1 卷积神经网络

卷积神经网络是一种专门用于处理具有网格结构数据的深度学习模型。

3.2 经典模型

ResNet引入残差连接解决了深层网络的梯度消失问题。

四、实验结果

最终模型达到了良好的准确率。

五、结论

本文验证了深度卷积神经网络的优异性能。
"""

# 3. 保存文件
output_folder = "D:/ecv_test_output/graduation_paper"
os.makedirs(output_folder, exist_ok=True)
txt_file = f"{output_folder}/ai_thesis.txt"
with open(txt_file, "w", encoding="utf-8") as f:
    f.write(content)
print(f"[OK] 已保存: {txt_file}")
print(f"[OK] 论文长度: {len(content)}字符")

# 4. 打开Word
print(">>> 步骤3: 打开Word显示论文")
try:
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = True
    doc = word.Documents.Add()
    word.Selection.TypeText(content)
    print("[OK] Word已打开并显示论文")
except Exception as e:
    print(f"[WARN] 请手动用Word打开文件查看")

print()
print("="*50)
print("[完成] 任务2执行完毕!")
print("="*50)
