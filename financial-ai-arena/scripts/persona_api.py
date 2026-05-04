"""人格生成与解析：模型输出优先 JSON（contestants_gen），兼容旧 YAML；供 CLI 与 serve_web API 复用。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

from config_loader import load_arena_config, parse_providers
from providers import invoke_provider_dynamic

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = SKILL_ROOT / "configs" / "arena_config.yaml"


def strip_code_fence(text: str) -> str:
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def extract_contestants_gen_block(text: str) -> str:
    """从模型夹杂说明的正文中切出以 contestants_gen: 开头的 YAML 片段。"""
    raw = strip_code_fence(text)
    lines = raw.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^\s*contestants_gen\s*:\s*", line):
            return "\n".join(lines[i:]).strip()
    m = re.search(r"(?m)^\s*contestants_gen\s*:\s*.*$", raw)
    if m:
        return raw[m.start() :].strip()
    return raw.strip()


def _normalize_gen_list(gen: Any) -> tuple[list[dict[str, Any]], str | None]:
    if not isinstance(gen, list):
        return [], "contestants_gen 不是列表"
    out: list[dict[str, Any]] = []
    for i, row in enumerate(gen):
        if not isinstance(row, dict):
            return [], f"contestants_gen[{i}] 不是对象"
        out.append(dict(row))
    return out, None


def try_parse_contestants_gen_json(text: str) -> tuple[list[dict[str, Any]] | None, str | None]:
    """从首字符 { 起 raw_decode 第一个 JSON 对象，读取 contestants_gen。"""
    t = strip_code_fence(text).strip()
    i = t.find("{")
    if i < 0:
        return None, None
    try:
        obj, _end = json.JSONDecoder().raw_decode(t[i:])
    except json.JSONDecodeError as e:
        return None, str(e)
    if not isinstance(obj, dict):
        return None, "JSON 根须为对象"
    gen = obj.get("contestants_gen")
    rows, err = _normalize_gen_list(gen)
    if err:
        return None, err
    return rows, None


def parse_contestants_gen(text: str) -> tuple[list[dict[str, Any]], str | None]:
    """从模型输出解析 contestants_gen：优先 JSON，其次 YAML。"""
    cleaned = strip_code_fence(text).strip()
    json_rows, json_err = try_parse_contestants_gen_json(cleaned)
    if json_rows is not None:
        return json_rows, None

    raw = extract_contestants_gen_block(cleaned)
    yaml_err: str | None = None
    try:
        data = yaml.safe_load(raw)
    except Exception as e:
        yaml_err = str(e)
        data = None

    if data is not None and isinstance(data, dict):
        gen = data.get("contestants_gen")
        rows, err = _normalize_gen_list(gen)
        if err is None:
            return rows, None
        yaml_err = yaml_err or err

    parts = []
    if json_err is not None:
        parts.append(f"JSON: {json_err}")
    if yaml_err is not None:
        parts.append(f"YAML: {yaml_err}")
    return [], "解析失败: " + ("; ".join(parts) if parts else "未知格式")


def public_config_snapshot(config_path: Path) -> dict[str, Any]:
    """供前端展示：providers 摘要 + 全部 contestants（无密钥）。"""
    cfg = load_arena_config(config_path)
    prov_out: dict[str, Any] = {}
    for pid, v in (cfg.get("providers") or {}).items():
        if not isinstance(v, dict):
            continue
        prov_out[str(pid)] = {
            "driver": str(v.get("driver") or ""),
            "default_model": str(v.get("default_model") or ""),
            "env_api_key": str(v.get("env_api_key") or ""),
        }
    contestants: list[dict[str, Any]] = []
    for row in cfg.get("contestants") or []:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("id") or "").strip()
        if not cid:
            continue
        contestants.append(
            {
                "id": cid,
                "provider": str(row.get("provider") or "").strip(),
                "display": str(row.get("display") or cid).strip(),
                "model": (str(row.get("model")).strip() if row.get("model") else None),
                "persona": str(row.get("persona") or "").strip(),
                "system_extra": str(row.get("system_extra") or "").strip(),
            }
        )
    return {
        "version": cfg.get("version", 1),
        "providers": prov_out,
        "contestants": contestants,
        "config_path": str(config_path.resolve()),
    }


def suggest_personas_text(
    config_path: Path,
    writer: str,
    slots: int,
    topic: str,
    *,
    providers_per_slot: list[str] | None = None,
) -> str:
    """调用 writer 对应 provider，返回模型原始文本（应为含 contestants_gen 的 JSON 或 YAML）。"""
    if not (2 <= slots <= 4):
        raise ValueError("slots 须在 2~4")
    cfg = load_arena_config(config_path)
    pmap = parse_providers(cfg)
    pc = pmap.get(writer)
    if not pc:
        raise ValueError(f"未知 writer `{writer}`，请检查 arena_config.yaml 的 providers")

    if providers_per_slot is None:
        providers_per_slot = [writer] * slots
    if len(providers_per_slot) != slots:
        raise ValueError("providers_per_slot 长度须等于 slots")
    for p in providers_per_slot:
        if p not in pmap:
            raise ValueError(f"未知 provider `{p}`")

    req = ", ".join(f"{i + 1}:{p}" for i, p in enumerate(providers_per_slot))
    system = (
        "你是严格 JSON 生成器。输出必须且只能是一段合法 UTF-8 JSON：从全文第一个字符 `{` 开始，到与之匹配的最后一个 `}` 结束；"
        "此前不得有任何字符（禁止前言、禁止中文说明、禁止 Markdown、禁止 ``` 围栏）。\n"
        "JSON 结构固定为：{\"contestants_gen\": [ {...}, ... ]}。"
        f"数组 contestants_gen 恰好 {slots} 个对象；第 n 个对象的 provider 必须严格等于：{req}。\n"
        "每个对象必须包含字符串键：id（英文蛇形小写）、provider、display（中文短名）、persona、system_extra。"
        "persona 中的换行必须写成 JSON 字符串里的 \\n，禁止 YAML 多行块、禁止在 JSON 外写「id:」「display:」等说明。\n"
        "人格彼此明显不同，覆盖激进/价值/宏观/量化纪律等之一，避免重复措辞。"
    )
    user = (
        f"主题：{topic}\n"
        f"只输出上述 JSON 对象，contestants_gen 含 {slots} 项，顺序与 provider 一致。"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    model_ov = os.environ.get("ARENA_PERSONA_WRITER_MODEL") or None
    return invoke_provider_dynamic(pc, messages, model_override=model_ov)


def suggest_one_contestant_text(
    config_path: Path,
    writer: str,
    topic: str,
    target_provider: str,
    *,
    id_hint: str = "",
    display_hint: str = "",
    avoid_one_liners: str = "",
) -> str:
    """生成单条槽位，contestants_gen 仅含 1 项；该项 provider 须为 target_provider。"""
    cfg = load_arena_config(config_path)
    pmap = parse_providers(cfg)
    pc = pmap.get(writer)
    if not pc:
        raise ValueError(f"未知 writer `{writer}`")
    if target_provider not in pmap:
        raise ValueError(f"未知 target_provider `{target_provider}`")

    hints = []
    if id_hint.strip():
        hints.append(f"优先使用 id（可微调）：{id_hint.strip()}")
    if display_hint.strip():
        hints.append(f"显示名参考：{display_hint.strip()}")
    if avoid_one_liners.strip():
        hints.append("避免与下列人格雷同（换角度写）：\n" + avoid_one_liners.strip()[:1200])
    hint_block = "\n".join(hints) if hints else "（无额外约束）"

    system = (
        "你是严格 JSON 生成器。输出必须且只能是一段合法 UTF-8 JSON：从第一个 `{` 到最后一个匹配的 `}`；"
        "此前不得有任何字符；禁止 Markdown、禁止 ``` 围栏、禁止在 JSON 外写说明句。\n"
        "结构：{\"contestants_gen\": [ { ... } ]}，数组恰好 1 个对象，该对象 provider 必须严格等于 "
        f'"{target_provider}"；键：id、provider、display、persona、system_extra（均为字符串，无则用 ""）。'
        "persona 内换行用 \\n 写在字符串里。"
    )
    user = f"主题：{topic}\n{hint_block}\n只输出该 JSON 对象，contestants_gen 仅 1 项。"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    model_ov = os.environ.get("ARENA_PERSONA_WRITER_MODEL") or None
    return invoke_provider_dynamic(pc, messages, model_override=model_ov)


def _yaml_scalar(s: str) -> str:
    if not s:
        return '""'
    if re.search(r'[:#\[\]{}@`|&*!]', s) or "\n" in s or s.strip() != s:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def contestant_yaml_block(c: dict[str, Any]) -> str:
    """单条 contestant 格式化为 yaml 片段（缩进列表项）。"""
    lines: list[str] = []
    pid = str(c.get("provider") or "").strip()
    cid = str(c.get("id") or "").strip()
    disp = str(c.get("display") or cid).strip()
    persona = str(c.get("persona") or "").strip()
    sysx = str(c.get("system_extra") or "").strip()
    model = c.get("model")
    lines.append(f"  - id: {cid}")
    lines.append(f"    provider: {pid}")
    lines.append(f"    display: {_yaml_scalar(disp)}")
    if model and str(model).strip():
        lines.append(f"    model: {str(model).strip()}")
    if "\n" in persona or len(persona) > 72:
        lines.append("    persona: |")
        for pl in persona.split("\n") or [""]:
            lines.append(f"      {pl}")
    else:
        lines.append(f"    persona: {_yaml_scalar(persona)}")
    lines.append(f"    system_extra: {_yaml_scalar(sysx)}")
    return "\n".join(lines)


def slots_to_export_yaml(slots: list[dict[str, Any]]) -> str:
    """多块 contestants 列表导出。"""
    parts = ["contestants:"]
    for s in slots:
        parts.append(contestant_yaml_block(s))
    return "\n".join(parts) + "\n"
