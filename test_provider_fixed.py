#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试修复后的Provider调用逻辑"""

import asyncio
import sys
import os

# 添加项目路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

async def test_provider():
    """测试Provider调用逻辑"""
    print("="*60)
    print("测试修复后的Provider调用")
    print("="*60)
    
    try:
        # 切换到server目录
        os.chdir(os.path.join(project_root, 'apps', 'server'))
        sys.path.insert(0, '.')
        
        # 导入修复后的Provider
        from app.services.llm.provider import LLMProvider
        
        provider = LLMProvider()
        
        print(f"\n当前Provider配置:")
        print(f"  API URL: {provider.base_url}")
        print(f"  Model: {provider.model}")
        print(f"  Enabled: {provider.enabled}")
        print(f"  Has API Key: {bool(provider.api_key)}")
        
        # 测试对话
        print("\n正在发送测试请求...")
        response = await provider.chat(
            system_prompt="你是一个有帮助的AI助手。",
            user_prompt="请回复测试成功",
            use_cache=False  # 禁用缓存以确保实际请求
        )
        
        print(f"\n✅ AI服务调用成功!")
        print(f"回复: {response}")
        return True
        
    except Exception as e:
        print(f"\n❌ AI服务调用失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_provider())
    sys.exit(0 if result else 1)
