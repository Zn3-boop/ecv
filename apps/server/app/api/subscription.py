# 订阅和支付 API - 商业化基础
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import uuid

router = APIRouter(prefix="/subscription", tags=["订阅"])

# ===== 订阅计划定义 =====

SUBSCRIPTION_PLANS = {
    "free": {
        "id": "free",
        "name": "免费版",
        "price": 0,
        "interval": "lifetime",
        "features": [
            "每日50次AI分析",
            "基础监控功能",
            "语音控制",
        ],
        "limits": {
            "daily_ai_calls": 50,
            "concurrent_agents": 1,
            "history_days": 7,
        }
    },
    "pro": {
        "id": "pro",
        "name": "专业版",
        "price": 29,
        "interval": "monthly",
        "features": [
            "无限AI分析",
            "高级监控功能",
            "语音控制",
            "优先支持",
            "云端同步",
        ],
        "limits": {
            "daily_ai_calls": -1,  # unlimited
            "concurrent_agents": 3,
            "history_days": 90,
        }
    },
    "enterprise": {
        "id": "enterprise",
        "name": "企业版",
        "price": 99,
        "interval": "monthly",
        "features": [
            "无限AI分析",
            "全部监控功能",
            "语音控制",
            "专属支持",
            "云端同步",
            "团队协作",
            "API访问",
        ],
        "limits": {
            "daily_ai_calls": -1,
            "concurrent_agents": -1,
            "history_days": -1,
        }
    }
}

# ===== API 模型 =====

class UserSession(BaseModel):
    user_id: str
    session_token: str
    plan: str
    expires_at: Optional[datetime] = None
    created_at: datetime

class SubscriptionStatus(BaseModel):
    user_id: str
    plan: str
    status: str  # active, expired, cancelled
    expires_at: Optional[datetime] = None
    features: list[str]
    limits: dict

class UsageStats(BaseModel):
    user_id: str
    date: str
    ai_calls_today: int
    daily_limit: int
    remaining: int

# ===== 内存存储（生产环境应使用数据库）=====

# 模拟用户数据
_mock_users = {
    "demo_user": {
        "user_id": "demo_user",
        "plan": "free",
        "status": "active",
        "expires_at": None,
        "created_at": datetime.now(),
        "usage_today": 12,
        "last_reset": datetime.now().date().isoformat(),
    }
}

# ===== API 端点 =====

@router.get("/plans")
async def list_plans():
    """列出所有订阅计划"""
    return {
        "plans": [
            {
                "id": plan_id,
                "name": plan["name"],
                "price": plan["price"],
                "interval": plan["interval"],
                "features": plan["features"],
            }
            for plan_id, plan in SUBSCRIPTION_PLANS.items()
        ]
    }

@router.get("/status/{user_id}", response_model=SubscriptionStatus)
async def get_subscription_status(user_id: str):
    """获取用户订阅状态"""
    user = _mock_users.get(user_id)
    if not user:
        # 返回免费版默认状态
        return SubscriptionStatus(
            user_id=user_id,
            plan="free",
            status="active",
            expires_at=None,
            features=SUBSCRIPTION_PLANS["free"]["features"],
            limits=SUBSCRIPTION_PLANS["free"]["limits"],
        )
    
    return SubscriptionStatus(
        user_id=user["user_id"],
        plan=user["plan"],
        status=user["status"],
        expires_at=user["expires_at"],
        features=SUBSCRIPTION_PLANS.get(user["plan"], SUBSCRIPTION_PLANS["free"])["features"],
        limits=SUBSCRIPTION_PLANS.get(user["plan"], SUBSCRIPTION_PLANS["free"])["limits"],
    )

@router.post("/check-usage/{user_id}")
async def check_usage(user_id: str):
    """检查用户今日使用量"""
    user = _mock_users.get(user_id)
    today = datetime.now().date().isoformat()
    
    if not user or user.get("last_reset") != today:
        # 重置每日计数
        daily_limit = SUBSCRIPTION_PLANS.get(user["plan"] if user else "free", SUBSCRIPTION_PLANS["free"])["limits"]["daily_ai_calls"]
        ai_calls_today = 0
    else:
        daily_limit = SUBSCRIPTION_PLANS.get(user["plan"], SUBSCRIPTION_PLANS["free"])["limits"]["daily_ai_calls"]
        ai_calls_today = user.get("usage_today", 0)
    
    remaining = max(0, daily_limit - ai_calls_today) if daily_limit > 0 else -1  # -1 表示无限
    
    return UsageStats(
        user_id=user_id,
        date=today,
        ai_calls_today=ai_calls_today,
        daily_limit=daily_limit,
        remaining=remaining,
    )

@router.post("/increment-usage/{user_id}")
async def increment_usage(user_id: str):
    """增加使用计数"""
    user = _mock_users.get(user_id)
    today = datetime.now().date().isoformat()
    
    if not user:
        user = {
            "user_id": user_id,
            "plan": "free",
            "status": "active",
            "usage_today": 0,
            "last_reset": today,
        }
        _mock_users[user_id] = user
    
    # 检查是否需要重置
    if user.get("last_reset") != today:
        user["usage_today"] = 0
        user["last_reset"] = today
    
    user["usage_today"] += 1
    
    daily_limit = SUBSCRIPTION_PLANS.get(user["plan"], SUBSCRIPTION_PLANS["free"])["limits"]["daily_ai_calls"]
    remaining = max(0, daily_limit - user["usage_today"]) if daily_limit > 0 else -1
    
    return {
        "success": True,
        "usage_today": user["usage_today"],
        "remaining": remaining,
        "limit_reached": remaining == 0 if daily_limit > 0 else False,
    }

@router.post("/subscribe/{user_id}")
async def subscribe(user_id: str, plan_id: str):
    """订阅指定计划（模拟）"""
    if plan_id not in SUBSCRIPTION_PLANS:
        raise HTTPException(status_code=400, detail=f"无效的计划: {plan_id}")
    
    plan = SUBSCRIPTION_PLANS[plan_id]
    
    # 计算到期时间
    expires_at = None
    if plan["interval"] == "monthly":
        expires_at = datetime.now() + timedelta(days=30)
    
    # 更新用户订阅
    _mock_users[user_id] = {
        "user_id": user_id,
        "plan": plan_id,
        "status": "active",
        "expires_at": expires_at,
        "created_at": datetime.now(),
        "usage_today": 0,
        "last_reset": datetime.now().date().isoformat(),
    }
    
    return {
        "success": True,
        "user_id": user_id,
        "plan": plan_id,
        "status": "active",
        "expires_at": expires_at.isoformat() if expires_at else None,
        "message": f"已成功订阅 {plan['name']}",
    }

@router.post("/cancel/{user_id}")
async def cancel_subscription(user_id: str):
    """取消订阅"""
    if user_id in _mock_users:
        _mock_users[user_id]["status"] = "cancelled"
        return {"success": True, "message": "订阅已取消"}
    return {"success": False, "message": "用户不存在"}

@router.post("/create-checkout-session")
async def create_checkout_session(plan_id: str, user_id: str):
    """创建Stripe结账会话（模拟）"""
    if plan_id not in SUBSCRIPTION_PLANS:
        raise HTTPException(status_code=400, detail=f"无效的计划: {plan_id}")
    
    plan = SUBSCRIPTION_PLANS[plan_id]
    
    # 模拟Stripe会话
    session_id = f"cs_{uuid.uuid4().hex[:24]}"
    
    return {
        "session_id": session_id,
        "url": f"https://checkout.stripe.com/pay/{session_id}",
        "plan_id": plan_id,
        "amount": plan["price"] * 100,  # cents
        "currency": "usd",
    }

@router.post("/webhook")
async def stripe_webhook(payload: dict):
    """Stripe webhook处理器"""
    event_type = payload.get("type")
    
    if event_type == "checkout.session.completed":
        # 处理支付成功
        session = payload.get("data", {}).get("object", {})
        print(f"支付成功: {session}")
        return {"received": True}
    
    elif event_type == "customer.subscription.deleted":
        # 处理订阅取消
        subscription = payload.get("data", {}).get("object", {})
        print(f"订阅取消: {subscription}")
        return {"received": True}
    
    return {"received": True}
