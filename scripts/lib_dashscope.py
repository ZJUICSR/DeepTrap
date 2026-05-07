"""
DeepTrap DashScope (Aliyun Bailian) API Client.

OpenAI-compatible client for Qwen models served via Aliyun Bailian. Used as an
alternative backend for judge models. Target models still go through OpenClaw, not this client.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from urllib import error, request

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen3-max"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.7
API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}

_last_usage: Dict[str, Any] = {}


def get_last_usage() -> Dict[str, Any]:
    return dict(_last_usage)


def reset_usage() -> None:
    _last_usage.clear()


def get_api_key() -> str:
    key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not key:
        raise RuntimeError(
            "DASHSCOPE_API_KEY environment variable is not set. "
            "Set it to use Qwen via Aliyun Bailian (dashscope.aliyuncs.com)."
        )
    return key


def _strip_prefix(model: str) -> str:
    for p in ("dashscope/", "qwen/"):
        if model.startswith(p):
            return model[len(p):]
    return model


def chat_completion(
    *,
    messages: List[Dict[str, str]],
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout_seconds: float = 120,
) -> str:
    api_key = get_api_key()
    model = _strip_prefix(model)

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = f"{API_BASE}/chat/completions"
    data = json.dumps(payload).encode("utf-8")

    last_exc: Optional[Exception] = None
    result: Dict[str, Any] = {}
    for attempt in range(MAX_RETRIES):
        req = request.Request(url, data=data, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=timeout_seconds) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            break
        except error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            last_exc = RuntimeError(f"DashScope API error {exc.code}: {body}")
            if exc.code in RETRYABLE_HTTP_CODES and attempt < MAX_RETRIES - 1:
                delay = RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning("DashScope %s (attempt %d/%d), retrying in %.0fs...",
                               exc.code, attempt + 1, MAX_RETRIES, delay)
                time.sleep(delay)
                continue
            logger.error("DashScope API error %s: %s", exc.code, body)
            raise last_exc from exc
        except (error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            last_exc = RuntimeError(f"DashScope network error: {exc}")
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning("DashScope network error (attempt %d/%d), retrying in %.0fs: %s",
                               attempt + 1, MAX_RETRIES, delay, exc)
                time.sleep(delay)
                continue
            raise last_exc from exc
    else:
        raise last_exc or RuntimeError("DashScope API failed after retries")

    _last_usage.update(result.get("usage", {}))

    choices = result.get("choices", [])
    if not choices:
        logger.warning("DashScope returned no choices: %s", result)
        return ""

    return choices[0].get("message", {}).get("content", "")


def query_with_system_prompt(
    *,
    system_prompt: str,
    user_message: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout_seconds: float = 120,
) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    return chat_completion(
        messages=messages,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
    )
