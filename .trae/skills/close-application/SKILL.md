---
name: "close-application"
description: "Closes/kills a running application by process name. Invoke when user says '关闭XX', '关掉XX', '退出XX', '结束XX' or wants to terminate any running program."
---

# Close Application

当用户要求关闭、退出、结束某个应用程序时，使用此skill。

## 触发条件

用户说出以下意图时触发：
- "关闭XX" / "关掉XX" / "退出XX" / "结束XX"
- "把XX关了" / "帮我关掉XX"
- "kill XX" / "close XX" / "quit XX"
- 任何表达想要终止运行中程序的说法

## 执行步骤

1. **识别目标应用** - 从用户输入中提取要关闭的应用名称
2. **查找进程** - 使用PowerShell查找匹配的进程：
   ```powershell
   Get-Process | Where-Object { $_.ProcessName -like "*关键词*" -or $_.MainWindowTitle -like "*关键词*" } | Select-Object Id, ProcessName, MainWindowTitle
   ```
3. **确认并关闭** - 找到进程后执行：
   ```powershell
   Stop-Process -Name "进程名" -Force
   ```
4. **验证** - 再次检查进程是否已关闭

## 常见应用进程名映射

| 用户说法 | 可能的进程名 |
|---------|------------|
| 百度网盘 | BaiduNetdisk, BaiduNetdiskHost |
| 微信 | WeChat |
| QQ | QQ |
| Chrome/谷歌浏览器 | chrome |
| Edge浏览器 | msedge |
| VSCode | Code |
| Word | WINWORD |
| Excel | EXCEL |
| PowerPoint | POWERPNT |
| 记事本 | notepad |
| 计算器 | Calculator |
| 画图 | mspaint |
| 网易云音乐 | cloudmusic |
| 钉钉 | DingTalk |
| 飞书 | Feishu |
| WPS | wps, wpscloudsvr |
| 火狐浏览器 | firefox |
| 360浏览器 | 360chrome |
| 腾讯会议 | wemeetapp |

## 注意事项

- 如果找不到精确匹配，使用模糊搜索并展示给用户确认
- 关闭前确认进程存在，避免报错
- 如果有多个匹配进程，列出所有并让用户选择
- 不要将"关闭XX"误解为搜索意图，这是直接操作系统的关闭命令