"""Load arena_config.yaml: providers + contestants, with ${ENV} expansion."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_ENV_BRACE = re.compile(r"\$\{([^}]+)\}")


def _expand_env(obj: Any) -> Any:
    if isinstance(obj, str):
        def repl(m: re.Match[str]) -> str:
            return os.environ.get(m.group(1).strip(), "")

        return _ENV_BRACE.sub(repl, obj)
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(v) for v in obj]
    return obj


@dataclass
class ProviderConfig:
    id: str
    driver: str
    env_api_key: str
    default_model: str = ""
    base_url: str | None = None
    openai_extra_body: dict[str, Any] | None = None
    invoke_style: str | None = None


@dataclass
class Contestant:
    """一场擂台里的一个「槽位」：可映射任意 provider，多人格靠 persona 区分。"""

    id: str
    provider: str
    display: str
    persona: str = ""
    system_extra: str = ""
    model: str | None = None


def load_arena_config(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _expand_env(raw)


def parse_providers(cfg: dict[str, Any]) -> dict[str, ProviderConfig]:
    out: dict[str, ProviderConfig] = {}
    for pid, v in (cfg.get("providers") or {}).items():
        if not isinstance(v, dict):
            continue
        driver = str(v.get("driver") or "").strip()
        if not driver:
            continue
        oeb = v.get("openai_extra_body")
        if isinstance(oeb, dict):
            oeb = dict(oeb)
        else:
            oeb = None
        out[str(pid)] = ProviderConfig(
            id=str(pid),
            driver=driver,
            env_api_key=str(v.get("env_api_key") or "").strip(),
            default_model=str(v.get("default_model") or "").strip(),
            base_url=(str(v.get("base_url")).strip() if v.get("base_url") else None),
            openai_extra_body=oeb,
            invoke_style=(str(v["invoke_style"]).strip() if v.get("invoke_style") else None),
        )
    return out


def parse_contestants(cfg: dict[str, Any]) -> dict[str, Contestant]:
    out: dict[str, Contestant] = {}
    for row in cfg.get("contestants") or []:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("id") or "").strip()
        if not cid:
            continue
        out[cid] = Contestant(
            id=cid,
            provider=str(row.get("provider") or "").strip(),
            display=str(row.get("display") or cid).strip(),
            persona=str(row.get("persona") or "").strip(),
            system_extra=str(row.get("system_extra") or "").strip(),
            model=(str(row.get("model")).strip() if row.get("model") else None),
        )
    return out


def legacy_builtin_contestants(provider_slugs: list[str]) -> list[Contestant]:
    """兼容 --ais：每个 slug 一个槽位，人格为空。"""
    labels = {
        "zhipu": "智谱 GLM",
        "deepseek": "DeepSeek",
        "minimax": "MiniMax",
        "mimo": "小米 MiMo",
    }
    out: list[Contestant] = []
    for s in provider_slugs:
        out.append(
            Contestant(
                id=s,
                provider=s,
                display=labels.get(s, s),
                persona="",
                system_extra="",
                model=None,
            )
        )
    return out
