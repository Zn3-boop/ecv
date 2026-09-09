import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# 强制 UTF-8 编码
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
os.environ.setdefault('PYTHONUTF8', '1')

if hasattr(sys.stdout, 'reconfigure') and (sys.stdout.encoding or '').lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure') and (sys.stderr.encoding or '').lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

load_dotenv(Path(__file__).resolve().parents[1] / '.env')

from app.api import agent, automation, browser, chat, desktop, health, provider, storage, system_app, task_filter, tools, voice, screenshot, store, content_generator, generator_settings, task_workflow, desktop_tools, subscription
from app.services.storage import init_storage
from app.utils.response_cleaner import clean_fastapi_response_body


# ========== 使用 lifespan 替代废弃的 on_event("startup") ==========
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    try:
        init_storage()
        print("Storage initialized successfully")
    except Exception as e:
        print(f"Warning: Storage init failed: {e}")
    yield
    # 关闭时执行（如需清理资源）


app = FastAPI(
    title="AI Desktop Agent API",
    version="0.1.0",
    lifespan=lifespan,
)


# ========== CORS 配置：支持 CORS_ALLOW_ALL 开关 ==========
_cors_allow_all = os.getenv("CORS_ALLOW_ALL", "false").strip().lower() in {"1", "true", "yes", "on"}
_allowed_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
_allowed_origins = [o.strip() for o in _allowed_origins_str.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins if not _cors_allow_all else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== 全局中间件：确保 UTF-8 + 异常安全处理 ==========
@app.middleware("http")
async def ensure_utf8(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception as exc:
        # 不暴露内部错误详情给客户端，只返回通用错误
        return JSONResponse(
            status_code=500,
            content={"detail": "服务器内部错误，请稍后再试或联系管理员。"},
            media_type='application/json; charset=utf-8',
        )

    content_type = response.headers.get('Content-Type', '')
    if 'application/json' in content_type:
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
    elif 'charset=' not in content_type and content_type.startswith('text/'):
        response.headers['Content-Type'] = f'{content_type}; charset=utf-8'
    return response


# ========== 全局中间件：清洗响应 ==========
@app.middleware("http")
async def clean_response_middleware(request: Request, call_next):
    response = await call_next(request)
    content_type = response.headers.get('Content-Type', '')

    if 'application/json' not in content_type:
        return response

    body = b''
    async for chunk in response.body_iterator:
        body += chunk

    cleaned_body = clean_fastapi_response_body(body)
    headers = dict(response.headers)
    headers.pop('content-length', None)

    import json
    return JSONResponse(
        content=json.loads(cleaned_body.decode('utf-8')),
        status_code=response.status_code,
        headers=headers,
        media_type='application/json; charset=utf-8',
    )

# 简单路由测试
@app.get("/")
async def root():
    return {"status": "ok", "name": "AI Desktop Agent API"}

@app.get("/health")
async def Health_check():
    return {"status": "healthy"}

# ========== 路由在模块顶层直接注册（替代延迟加载） ==========
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(automation.router)
app.include_router(storage.router)
app.include_router(tools.router)
app.include_router(voice.router)
app.include_router(agent.router)
app.include_router(task_filter.router)
app.include_router(browser.router)
app.include_router(system_app.router)
app.include_router(screenshot.router)
app.include_router(store.router)
app.include_router(desktop.router)
app.include_router(provider.router)
app.include_router(content_generator.router)
app.include_router(generator_settings.router)
app.include_router(task_workflow.router)
app.include_router(desktop_tools.router)
app.include_router(subscription.router)