"""
LLM backend router for judge models.

Dispatches based on the model id prefix:
  - "qwen/...", "dashscope/...", "qwen3-...", "qwen-..."  -> DashScope (Aliyun Bailian)
  - "deepseek/...", "deepseek-..."                         -> DeepSeek (api.deepseek.com)
  - everything else                                        -> OpenRouter

Target models (run via OpenClaw) are unaffected — they don't use this module.
"""

from __future__ import annotations

from typing import Any, Dict, List

import lib_dashscope
import lib_deepseek
import lib_openrouter

DASHSCOPE_PREFIXES = ("qwen/", "dashscope/", "qwen3-", "qwen-")
DEEPSEEK_PREFIXES = ("deepseek/", "deepseek-")


def _is_dashscope(model: str) -> bool:
    m = (model or "").lower()
    return any(m.startswith(p) for p in DASHSCOPE_PREFIXES)


def _is_deepseek(model: str) -> bool:
    m = (model or "").lower()
    return any(m.startswith(p) for p in DEEPSEEK_PREFIXES)


def _backend(model: str):
    if _is_deepseek(model):
        return lib_deepseek
    if _is_dashscope(model):
        return lib_dashscope
    return lib_openrouter


def chat_completion(
    *,
    messages: List[Dict[str, str]],
    model: str,
    **kwargs: Any,
) -> str:
    return _backend(model).chat_completion(messages=messages, model=model, **kwargs)


def query_with_system_prompt(
    *,
    system_prompt: str,
    user_message: str,
    model: str,
    **kwargs: Any,
) -> str:
    return _backend(model).query_with_system_prompt(
        system_prompt=system_prompt,
        user_message=user_message,
        model=model,
        **kwargs,
    )


def get_last_usage() -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    merged.update(lib_openrouter.get_last_usage())
    merged.update(lib_dashscope.get_last_usage())
    merged.update(lib_deepseek.get_last_usage())
    return merged


def reset_usage() -> None:
    lib_openrouter.reset_usage()
    lib_dashscope.reset_usage()
    lib_deepseek.reset_usage()
