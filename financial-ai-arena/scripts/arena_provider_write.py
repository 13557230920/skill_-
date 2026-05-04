"""将用户自定义 provider 合并进 arena_config.yaml（供首页模型接入 + serve_web）。"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


def apply_provider_to_config(
    config_path: Path,
    *,
    provider_id: str,
    driver: str,
    env_api_key: str,
    default_model: str,
    base_url: str = "",
    invoke_style: str = "",
    openai_extra_body_json: str = "",
    overwrite: bool = False,
) -> tuple[bool, str]:
    pid = (provider_id or "").strip()
    if not _ID_RE.match(pid):
        return False, "provider id 须为小写字母开头，仅小写字母、数字、下划线，最长 64"

    drv = (driver or "").strip()
    if drv not in ("zhipu", "openai_compat"):
        return False, "driver 当前仅支持：zhipu、openai_compat（与 scripts/providers.py 一致）"

    envk = (env_api_key or "").strip()
    if not _ENV_RE.match(envk):
        return False, "env_api_key 须为环境变量名（大写字母开头，如 MY_OPENAI_KEY），密钥请写在 .env 中，勿提交仓库"

    dm = (default_model or "").strip()
    if not dm:
        return False, "请填写 default_model（如 gpt-4o-mini、glm-4-plus）"

    if not config_path.is_file():
        return False, f"找不到配置文件: {config_path}"

    try:
        full: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        return False, f"读取 arena_config 失败: {e}"

    prov = full.setdefault("providers", {})
    if not isinstance(prov, dict):
        return False, "arena_config.providers 无效"

    if pid in prov and not overwrite:
        return False, f"已存在 provider `{pid}`：可换 id，或在请求里设 overwrite=true 覆盖"

    entry: dict[str, Any] = {"driver": drv, "env_api_key": envk, "default_model": dm}

    if drv == "openai_compat":
        bu = (base_url or "").strip().rstrip("/")
        if not bu:
            return False, "openai_compat 必须填写 base_url（OpenAI 兼容网关根地址，如 https://api.xxx.com/v1）"
        entry["base_url"] = bu
        inv = (invoke_style or "").strip()
        if inv in ("deepseek", "mimo"):
            entry["invoke_style"] = inv
        extra = (openai_extra_body_json or "").strip()
        if extra:
            try:
                entry["openai_extra_body"] = json.loads(extra)
            except json.JSONDecodeError as e:
                return False, f"openai_extra_body JSON 无效: {e}"

    bak = config_path.with_suffix(config_path.suffix + ".bak")
    shutil.copy2(config_path, bak)
    prov[pid] = entry
    out = yaml.dump(
        full,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    )
    config_path.write_text(out, encoding="utf-8")
    return (
        True,
        f"已写入 provider `{pid}`；备份 {bak.name}。请在 .env 中设置 {envk}=你的密钥 后重启 serve_web / 再拉配置。",
    )
