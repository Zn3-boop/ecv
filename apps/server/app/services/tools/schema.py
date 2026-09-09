from typing import Any

TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "open",
            "description": "打开应用、文件、文件夹或网址。示例：打开微信、打开D盘下载文件夹、打开百度",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "路径或URL，如 'C:\\\\Users\\\\xxx\\\\Desktop\\\\微信.lnk' 或 'https://baidu.com'"
                    }
                },
                "required": ["target"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "app:launch",
            "description": "启动本地应用程序。path可以是应用名（如WeChat.exe、notepad.exe）或绝对路径。url参数用于浏览器打开指定网址。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "应用名或绝对路径，如 'WeChat.exe'、'notepad.exe'、'C:\\\\Program Files\\\\...\\\\app.exe'"},
                    "url": {"type": "string", "description": "可选URL，浏览器启动时打开的网址"},
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选启动参数"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "执行系统命令（危险命令自动拦截）。示例：ping baidu.com, ipconfig, dir C:\\\\",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "命令主体，如 'ping'"},
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "参数列表，如 ['baidu.com']"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "systemControl",
            "description": "系统控制：音量、静音、睡眠、关机等。关机/睡眠需要用户确认",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["volume_up", "volume_down", "mute", "shutdown", "sleep", "brightness_up", "brightness_down"],
                        "description": "操作类型"
                    },
                    "value": {"type": "number", "description": "调整数值（可选）"}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "searchFiles",
            "description": "搜索本地文件。示例：找一下简历.pdf、搜索最近修改的PPT",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词"},
                    "dir": {"type": "string", "description": "搜索目录，默认用户主目录"}
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "getSystemInfo",
            "description": "获取CPU、内存、磁盘等系统监控数据。用户问CPU/内存/磁盘状态时调用",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "diskCleanup",
            "description": "清理C盘临时文件。参数max控制最大清理数量",
            "parameters": {
                "type": "object",
                "properties": {
                    "max": {"type": "number", "default": 50, "description": "最大清理文件数"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tempScan",
            "description": "扫描临时文件，评估可清理项",
            "parameters": {
                "type": "object",
                "properties": {
                    "max": {"type": "number", "default": 50, "description": "最大扫描文件数"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "process:top",
            "description": "获取高内存占用进程列表。用于用户询问内存清理、查看什么程序占用内存时。返回按内存排序的进程列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "max": {"type": "number", "default": 10, "description": "返回进程数量，默认10个"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "process:kill",
            "description": "结束指定进程。可通过name或pid指定。禁止结束系统进程（explorer.exe、dwm.exe、csrss.exe等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pid": {"type": "number", "description": "进程PID"},
                    "name": {"type": "string", "description": "进程名，如 'chrome.exe'"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "process:list",
            "description": "列出所有运行中的进程。",
            "parameters": {
                "type": "object",
                "properties": {
                    "max": {"type": "number", "default": 50, "description": "最大返回数量"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "content:generate",
            "description": "生成文章、代码、文档、网页等内容。task描述任务，content_type指定类型（html/python/word/document/code），auto_open生成后自动打开。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "生成任务描述，如 '登录页面'、'毕业论文'"},
                    "content_type": {"type": "string", "enum": ["html", "python", "word", "document", "code", "article"], "description": "内容类型"},
                    "theme": {"type": "string", "description": "主题或领域"},
                    "style": {"type": "string", "description": "风格，如 '现代'、'简约'"},
                    "length": {"type": "string", "enum": ["短", "中", "长"], "description": "长度"},
                    "output_path": {"type": "string", "description": "输出文件路径（可选）"},
                    "auto_open": {"type": "boolean", "default": True, "description": "生成后自动打开文件"}
                },
                "required": ["task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser:search",
            "description": "在浏览器中搜索关键词。自动选择百度（中文）或Google（英文）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "browser": {"type": "string", "enum": ["edge", "chrome"], "default": "edge", "description": "使用的浏览器"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ide:launch",
            "description": "打开IDE（VSCode/Cursor）创建项目或文件。action=create_project时需提供files和project_name。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ide": {"type": "string", "enum": ["vscode", "cursor"], "description": "IDE类型"},
                    "action": {"type": "string", "enum": ["create_project", "open_file"], "description": "操作类型"},
                    "project_name": {"type": "string", "description": "项目名称"},
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "文件路径"},
                                "template": {"type": "string", "description": "模板名"}
                            }
                        },
                        "description": "要创建的文件列表"
                    },
                    "auto_preview": {"type": "boolean", "default": False, "description": "是否自动预览"}
                },
                "required": ["ide"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard:write",
            "description": "将文本写入系统剪贴板。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要写入剪贴板的文本"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "notify",
            "description": "发送桌面通知。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "通知标题"},
                    "body": {"type": "string", "description": "通知内容"}
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "disk:list",
            "description": "列出所有磁盘驱动器及空间信息。",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "temp:cleanup",
            "description": "清理临时文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "max": {"type": "number", "default": 50, "description": "最大清理文件数"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "system:command",
            "description": "执行系统命令（与shell相同，危险命令自动拦截）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令"},
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "命令参数"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "system:info",
            "description": "获取系统信息（CPU、内存、磁盘等）。与getSystemInfo相同。",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file:list",
            "description": "列出目录下的文件和文件夹。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径"},
                    "pattern": {"type": "string", "description": "文件匹配模式，如 '*.txt'"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file:search",
            "description": "搜索文件。与searchFiles相同。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "搜索起始目录"},
                    "pattern": {"type": "string", "description": "搜索模式，如 '*.pdf'"}
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "network:request",
            "description": "发起HTTP网络请求。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "请求URL"},
                    "method": {"type": "string", "enum": ["GET", "POST"], "default": "GET", "description": "HTTP方法"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "keyboard:type",
            "description": "模拟键盘输入文本。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要输入的文本"}
                },
                "required": ["text"]
            }
        }
    },
]