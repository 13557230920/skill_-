"""LLM invocation: JSON 决策解析 + 按 ProviderConfig 动态路由（可扩展 driver）。"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI

from config_loader import ProviderConfig


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return t


def parse_decision_json(content: str) -> dict[str, Any]:
    raw = _strip_json_fence(content)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        if start >= 0:
            try:
                obj, _ = json.JSONDecoder().raw_decode(raw, start)
            except json.JSONDecodeError:
                return {"action": "hold", "target": "", "size_pct": 0, "reason": "parse_error"}
        else:
            return {"action": "hold", "target": "", "size_pct": 0, "reason": "parse_error"}
    action = str(obj.get("action", "hold")).lower()
    if action not in ("buy", "sell", "hold"):
        action = "hold"
    try:
        size_pct = float(obj.get("size_pct", 0))
    except (TypeError, ValueError):
        size_pct = 0.0
    size_pct = max(0.0, min(100.0, size_pct))
    return {
        "action": action,
        "target": str(obj.get("target", "")).strip(),
        "size_pct": size_pct,
        "reason": str(obj.get("reason", ""))[:500],
    }


def call_zhipu(
    messages: list[dict[str, str]],
    model: str,
    max_tokens: int = 2048,
    *,
    api_env: str = "ZHIPU_API_KEY",
) -> str:
    key = os.environ.get(api_env)
    if not key:
        raise RuntimeError(f"缺少环境变量 {api_env}（智谱）")

    try:
        from zai import ZhipuAiClient
    except ImportError as e:
        raise RuntimeError("请 pip install zai-sdk") from e

    client = ZhipuAiClient(api_key=key)
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.6,
    }
    thinking = os.environ.get("ARENA_ZHIPU_THINKING", "enabled")
    if thinking and thinking != "disabled":
        kwargs["thinking"] = {"type": thinking}

    resp = client.chat.completions.create(**kwargs)
    msg = resp.choices[0].message
    parts: list[str] = []
    c = getattr(msg, "content", None)
    if c:
        parts.append(str(c))
    for attr in ("reasoning_content", "reasoning"):
        v = getattr(msg, attr, None)
        if v:
            parts.append(str(v))
    return "\n".join(parts).strip() or "{}"


def call_openai_compat(
    *,
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int = 2048,
    extra_body: dict[str, Any] | None = None,
    invoke_style: str | None = None,
) -> str:
    client = OpenAI(api_key=api_key, base_url=base_url.rstrip("/"))
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": 0.6,
    }

    eb: dict[str, Any] = dict(extra_body or {})

    if invoke_style == "mimo":
        kwargs["max_completion_tokens"] = max_tokens
        if "thinking" not in eb:
            eb.setdefault("thinking", {"type": os.environ.get("ARENA_MIMO_THINKING", "disabled")})
    else:
        kwargs["max_tokens"] = max_tokens

    if invoke_style == "deepseek":
        eb.setdefault("thinking", {"type": "enabled"})

    if eb:
        kwargs["extra_body"] = eb

    resp = client.chat.completions.create(**kwargs)
    msg = resp.choices[0].message
    parts: list[str] = []
    c = getattr(msg, "content", None)
    if c:
        parts.append(str(c))
    for attr in ("reasoning_content", "reasoning"):
        v = getattr(msg, attr, None)
        if v:
            parts.append(str(v))
    return "\n".join(parts).strip()


def invoke_provider_dynamic(pc: ProviderConfig, messages: list[dict[str, str]], *, model_override: str | None) -> str:
    """统一入口：由 YAML driver 决定如何调用。"""
    key_env = (pc.env_api_key or "").strip()
    resolved_model = (model_override or "").strip() or (pc.default_model or "").strip()

    if pc.driver == "zhipu":
        if not resolved_model:
            resolved_model = os.environ.get("ARENA_ZHIPU_MODEL", "glm-4-plus")
        return call_zhipu(messages, model=resolved_model, api_env=key_env or "ZHIPU_API_KEY")

    if pc.driver == "openai_compat":
        if not key_env:
            raise RuntimeError(f"provider `{pc.id}` 未配置 env_api_key")
        api_key = os.environ.get(key_env)
        if not api_key:
            raise RuntimeError(f"缺少环境变量 {key_env}（provider `{pc.id}`）")
        if not pc.base_url:
            raise RuntimeError(f"provider `{pc.id}` 为 openai_compat 但未配置 base_url")
        if not resolved_model:
            resolved_model = "gpt-4o-mini"
        return call_openai_compat(
            api_key=api_key,
            base_url=pc.base_url,
            model=resolved_model,
            messages=messages,
            extra_body=pc.openai_extra_body,
            invoke_style=pc.invoke_style,
        )

    raise ValueError(f"未知 driver `{pc.driver}`（provider `{pc.id}`）")
