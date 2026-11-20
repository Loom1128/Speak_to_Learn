"""呼叫 Claude 並取得結構化（Pydantic）輸出。"""

import logging
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from .config import settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    """API 金鑰從環境變數 ANTHROPIC_API_KEY 讀取。"""
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


class LLMError(Exception):
    """AI 沒有產出可用結果（拒答、輸出被截斷、格式不符）。"""


async def structured_call(system: str, user: str, output_model: type[T]) -> T:
    response = await get_client().beta.messages.parse(
        model=settings.model,
        max_tokens=settings.max_tokens,
        # system prompt 固定不變（Bloom 定義等），加上 cache_control 讓重複呼叫可命中快取、降低成本
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_format=output_model,
        output_config={"effort": settings.effort},
        # 若主模型因安全分類器拒答，由伺服器自動改用合適的備援模型重跑
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )

    log.info(
        "claude call model=%s stop=%s in=%s out=%s cache_read=%s request_id=%s",
        response.model,
        response.stop_reason,
        response.usage.input_tokens,
        response.usage.output_tokens,
        response.usage.cache_read_input_tokens,
        response._request_id,
    )

    if response.stop_reason == "refusal":
        detail = getattr(response.stop_details, "explanation", None) if response.stop_details else None
        raise LLMError(f"AI 拒絕處理此內容：{detail or '未提供原因'}")
    if response.stop_reason == "max_tokens":
        raise LLMError("AI 輸出超過長度上限被截斷，請調高 BLOOM_MAX_TOKENS 或縮短輸入內容。")
    if response.parsed_output is None:
        raise LLMError("AI 輸出無法解析為指定格式。")
    return response.parsed_output
