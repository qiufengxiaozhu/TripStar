"""
AI 行程问答服务
基于 httpx 直接调用 OpenAI 兼容的 Chat Completions API，
将当前旅行计划作为上下文注入,实现针对行程的智能问答
"""

import os
import json
import httpx
from typing import Optional, Any
from dotenv import load_dotenv

# 加载 .env
load_dotenv()

# ============ 从 .env 读取 LLM 配置 ============
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL_ID = os.getenv("LLM_MODEL_ID", "gpt-4")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))

# 确保 base_url 结尾没有多余的斜杠
LLM_BASE_URL = LLM_BASE_URL.rstrip("/")

# ============ System Prompt ============
SYSTEM_PROMPT = """你是一个专业且贴心的私人旅行管家「旅途星辰AI」。

你当前正在为用户提供关于一份 **已生成的旅行计划** 的答疑服务。
用户可能会问你关于行程中的景点、酒店、餐饮、天气、交通、门票、费用等任何细节问题。

请根据下方提供的【当前旅行计划】JSON 上下文来回答用户的问题。
回答规则：
1. 如果行程数据中包含相关信息，请精确引用并给出详细回答。
2. 如果行程数据中没有明确信息，可以基于常识进行合理推断，但需说明"行程中未提供该信息，以下是建议"。
3. 回答要有温度、条理清晰，适当使用 emoji 增加亲切感 🌟。
4. 回答尽量简洁，控制在200字以内，除非用户要求详细展开。
5. 使用中文回答。"""


def _build_context_message(trip_plan_dict: dict[str, Any]) -> str:
    """将旅行计划转化为上下文文本"""
    return f"【当前旅行计划】\n```json\n{json.dumps(trip_plan_dict, ensure_ascii=False, indent=2)}\n```"


async def chat_with_trip_context(
    message: str,
    trip_plan_dict: dict[str, Any],
    history: Optional[list[dict[str, str]]] = None,
) -> str:
    """
    使用 LLM 回答关于当前行程的用户提问

    Args:
        message: 用户的提问
        trip_plan_dict: 当前旅行计划 (dict 格式)
        history: 可选的历史对话 [{"role": "user"/"assistant", "content": "..."}]

    Returns:
        AI 的回复文本
    """
    # 构造消息列表
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_context_message(trip_plan_dict)},
    ]

    # 追加历史对话
    if history:
        for item in history:
            messages.append({
                "role": item.get("role", "user"),
                "content": item.get("content", ""),
            })

    # 追加本次用户提问
    messages.append({"role": "user", "content": message})

    # 调用 LLM
    url = f"{LLM_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}",
    }
    payload = {
        "model": LLM_MODEL_ID,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024,
    }

    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            reply = data["choices"][0]["message"]["content"]
            return reply.strip()

    except httpx.HTTPStatusError as e:
        print(f"❌ LLM API 返回错误: {e.response.status_code} - {e.response.text}")
        return f"抱歉，AI 服务暂时出现问题 (HTTP {e.response.status_code})，请稍后重试 🙏"
    except httpx.TimeoutException:
        print("❌ LLM API 请求超时")
        return "抱歉，AI 回复超时了，请稍后再试 ⏳"
    except Exception as e:
        print(f"❌ LLM 调用异常: {e}")
        return f"抱歉，AI 出现了意外错误，请稍后重试 🙏"
