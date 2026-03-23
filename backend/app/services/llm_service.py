"""LLM服务模块"""

import os
from hello_agents import HelloAgentsLLM
from ..config import get_settings

_llm_instance = None


def get_llm() -> HelloAgentsLLM:
    """获取LLM实例(单例模式)"""
    global _llm_instance

    if _llm_instance is None:
        settings = get_settings()

        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_BASE_URL")
        model_id = os.getenv("LLM_MODEL_ID")
        timeout = int(os.getenv("LLM_TIMEOUT", "120"))

        print(f"[LLM] 正在初始化...", flush=True)
        print(f"[LLM]   model    = {model_id}", flush=True)
        print(f"[LLM]   base_url = {base_url}", flush=True)
        print(f"[LLM]   api_key  = {api_key[:20] + '...' if api_key else 'None'}", flush=True)
        print(f"[LLM]   timeout  = {timeout}s", flush=True)

        if not api_key or not base_url or not model_id:
            print(f"[LLM] 警告: 缺少必要配置! api_key={bool(api_key)}, base_url={bool(base_url)}, model={bool(model_id)}", flush=True)

        _llm_instance = HelloAgentsLLM(
            provider="custom",
            api_key=api_key,
            base_url=base_url,
            model=model_id,
            timeout=timeout,
            max_tokens=8192,
        )

        from openai import OpenAI
        _llm_instance._client = OpenAI(
            api_key=_llm_instance.api_key,
            base_url=_llm_instance.base_url,
            timeout=_llm_instance.timeout,
            default_headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

        print(f"[LLM] 初始化成功! provider={_llm_instance.provider}, model={_llm_instance.model}, base_url={_llm_instance.base_url}", flush=True)

    return _llm_instance


def reset_llm():
    """重置LLM实例(用于测试或重新配置)"""
    global _llm_instance
    _llm_instance = None

