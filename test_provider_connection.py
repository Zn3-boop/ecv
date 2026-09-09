"""
测试 Provider 连接
"""
import asyncio
import sys
sys.path.insert(0, 'apps/server')

from app.services.provider_manager import get_provider_manager


async def test_all_providers():
    """测试所有启用的Provider"""
    manager = get_provider_manager()
    providers = manager.list_providers()
    
    print("=" * 60)
    print("Provider 连接测试")
    print("=" * 60)
    
    for p in providers:
        print(f"\n测试: {p.name} (ID: {p.id})")
        print(f"  URL: {p.api_url}")
        print(f"  Model: {p.model}")
        print(f"  Enabled: {p.enabled}")
        
        if not p.enabled:
            print("  ⏭️  跳过（已禁用）")
            continue
        
        # 本地Ollama不需要API Key
        if not p.api_key and not ("localhost" in p.api_url or "127.0.0.1" in p.api_url):
            print("  ⚠️  跳过（无API Key）")
            continue
        
        # 获取完整URL
        full_url = p.get_full_url()
        print(f"  完整URL: {full_url}")
        
        # 测试连接
        result = await manager.chat_completion(
            p.id,
            messages=[{"role": "user", "content": "Hi, reply with 'OK'"}],
            max_tokens=10
        )
        
        if "error" in result:
            print(f"  ❌ 错误: {result['error']}")
        else:
            print(f"  ✅ 连接成功!")
            try:
                content = result["choices"][0]["message"]["content"]
                print(f"  回复: {content}")
            except:
                print(f"  响应: {result}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_all_providers())
