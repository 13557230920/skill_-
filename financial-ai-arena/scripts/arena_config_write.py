"""将「导出区」的 contestants YAML 片段合并进 arena_config.yaml（供 serve_web POST）。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml


def apply_contestants_snippet(config_path: Path, snippet_yaml: str) -> tuple[bool, str]:
    """
    用片段中的 contestants 列表替换配置文件中的同名键。
    写入前复制一份 config_path -> config_path.bak（覆盖旧 .bak）。
    注意：整文件会以 PyYAML 重新序列化，原文件中的注释与键顺序可能变化。
    """
    text = (snippet_yaml or "").strip()
    if not text:
        return False, "YAML 片段为空"

    try:
        frag = yaml.safe_load(text)
    except Exception as e:
        return False, f"片段 YAML 解析失败: {e}"

    if not isinstance(frag, dict):
        return False, "片段须为 YAML 映射（以 contestants: 开头）"
    new_list = frag.get("contestants")
    if not isinstance(new_list, list) or len(new_list) == 0:
        return False, "片段中须包含非空 contestants 列表"

    if not config_path.is_file():
        return False, f"找不到配置文件: {config_path}"

    try:
        full: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        return False, f"读取 arena_config 失败: {e}"

    if not isinstance(full, dict):
        return False, "arena_config 根须为 YAML 映射"

    providers = full.get("providers") or {}
    if not isinstance(providers, dict):
        return False, "arena_config.providers 无效"

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for i, row in enumerate(new_list):
        if not isinstance(row, dict):
            return False, f"contestants[{i}] 须为对象"
        cid = str(row.get("id") or "").strip()
        if not cid:
            return False, f"第 {i + 1} 条缺少 id"
        if cid in seen:
            return False, f"contestants 中存在重复 id: {cid}"
        seen.add(cid)
        pid = str(row.get("provider") or "").strip()
        if not pid:
            return False, f"槽位 `{cid}` 缺少 provider"
        if pid not in providers:
            return False, f"槽位 `{cid}` 引用未知 provider `{pid}`，请先在 providers 中配置"

        norm: dict[str, Any] = {
            "id": cid,
            "provider": pid,
            "display": str(row.get("display") or cid).strip(),
            "persona": str(row.get("persona") or "").strip(),
            "system_extra": str(row.get("system_extra") or "").strip(),
        }
        m = row.get("model")
        if m is not None and str(m).strip():
            norm["model"] = str(m).strip()
        normalized.append(norm)

    bak = config_path.with_suffix(config_path.suffix + ".bak")
    shutil.copy2(config_path, bak)

    full["contestants"] = normalized
    out = yaml.dump(
        full,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    )
    config_path.write_text(out, encoding="utf-8")
    return True, f"已写入 {config_path.name}；已备份为 {bak.name}（整文件已重排，注释可能丢失，建议用 git diff 确认）"
