"""建议页对话记忆：擂台历练次数、对话条、质量分；供 arena_run 注入与 serve_web API。"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any


def memory_path(root: Path) -> Path:
    return root / "arena_advisor_memory.json"


def default_memory() -> dict[str, Any]:
    return {"version": 1, "challenge_count_by_slot": {}, "episodes": []}


def load_memory(root: Path) -> dict[str, Any]:
    p = memory_path(root)
    if not p.is_file():
        return default_memory()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_memory()
    if not isinstance(raw, dict):
        return default_memory()
    raw.setdefault("version", 1)
    raw.setdefault("challenge_count_by_slot", {})
    raw.setdefault("episodes", [])
    if not isinstance(raw["challenge_count_by_slot"], dict):
        raw["challenge_count_by_slot"] = {}
    if not isinstance(raw["episodes"], list):
        raw["episodes"] = []
    return raw


def save_memory(root: Path, mem: dict[str, Any]) -> None:
    memory_path(root).write_text(json.dumps(mem, ensure_ascii=False, indent=2), encoding="utf-8")


def bump_challenge_counts(root: Path, slot_ids: list[str]) -> None:
    if not slot_ids:
        return
    mem = load_memory(root)
    cc = mem["challenge_count_by_slot"]
    assert isinstance(cc, dict)
    for sid in slot_ids:
        s = str(sid).strip()
        if not s:
            continue
        cc[s] = int(cc.get(s, 0) or 0) + 1
    save_memory(root, mem)


def score_episode(*, user: str, assistant: str) -> dict[str, Any]:
    """轻量启发式：0～1，附可读原因（非学术指标，仅筛明显低质）。"""
    u = (user or "").strip()
    a = (assistant or "").strip()
    score = 0.52
    reasons: list[str] = []

    if len(u) < 6:
        score -= 0.18
        reasons.append("用户过短")
    elif len(u) < 20:
        score -= 0.06
        reasons.append("用户偏短")

    if len(a) < 30:
        score -= 0.28
        reasons.append("回复过短")
    elif len(a) < 120:
        score -= 0.08
        reasons.append("回复偏短")
    elif len(a) > 400:
        score += 0.06
        reasons.append("回复较充实")

    if a:
        uniq_ratio = len(set(a)) / max(len(a), 1)
        if uniq_ratio < 0.08:
            score -= 0.2
            reasons.append("字符重复度高")
        elif uniq_ratio < 0.12:
            score -= 0.08
            reasons.append("重复度略高")

    fin = re.findall(r"[\u4e00-\u9fff]", a)
    if len(fin) < 15 and len(a) > 40:
        score -= 0.05
        reasons.append("中文信息偏少")

    hint = r"(600|000|300|688)\d{3}\.(SH|SZ)|市盈率|市净率|财报|营收|净利润|现金流|估值|仓位|风险"
    if re.search(hint, u + a, re.I):
        score += 0.08
        reasons.append("含金融语义线索")

    score = max(0.0, min(1.0, round(score, 3)))
    if not reasons:
        reasons.append("默认通过")
    return {"quality": score, "quality_reasons": reasons}


def append_episode(
    root: Path,
    *,
    mode: str,
    slot_id: str,
    provider: str,
    display: str,
    user: str,
    assistant: str,
) -> dict[str, Any]:
    mem = load_memory(root)
    sc = score_episode(user=user, assistant=assistant)
    ep = {
        "id": str(uuid.uuid4()),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "mode": mode,
        "slot_id": slot_id,
        "provider": provider,
        "display": display,
        "user": user[:8000],
        "assistant": assistant[:24000],
        "quality": sc["quality"],
        "quality_reasons": sc["quality_reasons"],
    }
    eps: list = mem["episodes"]
    eps.append(ep)
    # 控制体积：保留最近 200 条
    if len(eps) > 200:
        del eps[:-200]
    save_memory(root, mem)
    return ep


def format_training_digest_for_slot(
    root: Path,
    slot_id: str,
    *,
    max_items: int = 2,
    min_quality: float = 0.42,
) -> str:
    """拼进 sim 系统提示的一段摘要（非训练，仅上下文）。"""
    mem = load_memory(root)
    eps = [e for e in mem["episodes"] if isinstance(e, dict) and e.get("slot_id") == slot_id]
    eps.sort(key=lambda x: str(x.get("ts") or ""), reverse=True)
    lines: list[str] = []
    for e in eps:
        try:
            q = float(e.get("quality") or 0)
        except (TypeError, ValueError):
            q = 0
        if q < min_quality:
            continue
        u = str(e.get("user") or "").strip().replace("\n", " ")
        a = str(e.get("assistant") or "").strip().replace("\n", " ")
        if len(u) > 160:
            u = u[:160] + "…"
        if len(a) > 220:
            a = a[:220] + "…"
        lines.append(f"-（质量分 {q:.2f}）问：{u} 答：{a}")
        if len(lines) >= max_items:
            break
    if not lines:
        return ""
    return (
        "【来自真实建议页的近期高质量对话摘要（仅作风格与上下文，非交易指令）】\n"
        + "\n".join(lines)
    )


def pick_veteran_slot(
    root: Path,
    *,
    last_ais: list[str],
    weights: dict[str, float],
    all_slot_ids: list[str],
) -> str | None:
    """历练次数最大；平局时取上一场权重较高且出现在 last_ais 的；再平取 id 序。"""
    mem = load_memory(root)
    cc = mem["challenge_count_by_slot"]
    candidates = all_slot_ids if all_slot_ids else list(cc.keys())
    if not candidates:
        return None

    def score_sid(sid: str) -> tuple[int, float, str]:
        n = int(cc.get(sid, 0) or 0)
        w = float(weights.get(sid, 0) or 0) if sid in (last_ais or []) else 0.0
        return (n, w, sid)

    return max(candidates, key=score_sid)


def build_weight_blend_system(
    *,
    meta: dict[str, dict],
    weights: dict[str, float],
    ais: list[str],
    personas: dict[str, str],
) -> str:
    lines = [
        "你是「上一场金融 AI 擂台」后的综合顾问角色：以下多个槽位曾参与模拟纸交易，并得到采纳权重。",
        "请结合权重在心里衡量各视角的重要性，用**一段**连贯中文回答用户（非投资建议，需提示风险与不确定性）。",
        "权重与槽位：",
    ]
    for sid in sorted(ais, key=lambda x: float(weights.get(x, 0) or 0), reverse=True):
        w = float(weights.get(sid, 0) or 0)
        m = meta.get(sid) or {}
        disp = m.get("display") or sid
        prov = m.get("provider") or ""
        pe = (personas.get(sid) or "").strip()
        pe_short = (pe[:400] + "…") if len(pe) > 400 else pe
        lines.append(f"- [{sid}] {disp}（provider={prov}）采纳权重 {100 * w:.1f}%")
        if pe_short:
            lines.append(f"  人格摘要：{pe_short}")
    lines.append("")
    lines.append("回答时不必逐条扮演，但应体现高权重视角更优先。")
    return "\n".join(lines)
