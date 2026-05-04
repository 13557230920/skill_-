#!/usr/bin/env python3
"""金融 AI 擂台：YAML 多人格槽位 + 可扩展 providers + 纸交易 + HTML（含本地像素榜）。"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from pathlib import Path

from arena_dotenv import load_arena_dotenv

from config_loader import Contestant, load_arena_config, legacy_builtin_contestants, parse_contestants, parse_providers
from providers import invoke_provider_dynamic, parse_decision_json
from report_html import write_report
from simulator import (
    Portfolio,
    apply_decision,
    drift_prices,
    initial_prices,
    rank_players,
    weights_from_rank,
)

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = SKILL_ROOT / "configs" / "arena_config.yaml"


def sibling_skill_paths() -> list[str]:
    """并列 skills 目录下 SKILL.md；新接 provider 仍走同一套 prompt，无需逐模型改代码。"""
    skills_dir = SKILL_ROOT.parent
    names = [
        "financial-analysis",
        "jrj-quote-skill",
        "tushare-finance",
        "multi-search-engine",
        "self-improving",
        "moltpixel",
        "financial-ai-arena",
    ]
    out: list[str] = []
    for n in names:
        p = skills_dir / n / "SKILL.md"
        if p.exists():
            out.append(str(p))
    extra_dirs = (os.environ.get("ARENA_EXTRA_SKILL_SUBDIRS") or "").strip()
    if extra_dirs:
        for raw in extra_dirs.split(","):
            sub = raw.strip()
            if not sub:
                continue
            p = skills_dir / sub / "SKILL.md"
            if p.exists():
                sp = str(p)
                if sp not in out:
                    out.append(sp)
    return out


def _inject_previous_sim_memory(output_dir: Path, base_system: str) -> str:
    """把上一场 post_game_feedback 摘要拼进系统提示（伪记忆；真进化仍靠外部存储或训练）。"""
    v = (os.environ.get("ARENA_INJECT_PREV_FEEDBACK") or "1").strip().lower()
    if v in ("0", "false", "no", "off"):
        return base_system
    p = output_dir / "arena_state.json"
    if not p.is_file():
        return base_system
    try:
        prev = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return base_system
    rows = prev.get("post_game_feedback") or []
    if not isinstance(rows, list) or not rows:
        return base_system
    lines: list[str] = []
    for row in rows[:8]:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("slot_id") or "")
        rk = row.get("rank")
        tx = (str(row.get("text") or "")).strip().replace("\n", " ")
        if len(tx) > 220:
            tx = tx[:220] + "…"
        if sid and sid != "_all" and tx:
            lines.append(f"- [{sid}] 第{rk}名: {tx}")
    if not lines:
        return base_system
    return (
        base_system
        + "\n\n【上一场赛后各槽位自陈摘要（仅作风格/心理参考，非本场交易指令）】\n"
        + "\n".join(lines)
    )


def build_base_system_prompt() -> str:
    skills_block = "\n".join(f"- {p}" for p in sibling_skill_paths()) or "- （未找到并列 SKILL.md，请确认 skills 目录）"
    extra = (os.environ.get("ARENA_EXTRA_SKILL_PATHS") or "").strip()
    if extra:
        for raw in extra.split(","):
            p = raw.strip()
            if not p:
                continue
            skills_block += f"\n- {p}"
    return (
        "你是金融模拟擂台赛中的一名交易员智能体。结合风控与分散化，只输出一个 JSON 对象，"
        "不要 Markdown、不要代码围栏、不要前后说明文字。\n"
        '格式：{"action":"buy|sell|hold","target":"<标的代码>","size_pct":0-100,"reason":"<一句话>"}\n'
        "规则：target 必须来自本轮给出的 universe；buy 时 size_pct 为愿意使用现金的比例；"
        "sell 为减仓比例；hold 时可将 size_pct 设为 0。\n"
        "下列路径仅为**文档说明**（能力边界参考）。本 runner 可在 sim 内做**预检索摘要**或 **Tushare 收盘价初始化**（见环境变量）；"
        "其余 MCP 仍由宿主按需调用。\n"
        "宿主工作区技能文档路径：\n"
        f"{skills_block}\n"
    )


def _normalize_scenario_pack(raw: dict | None) -> dict[str, object]:
    """Web/API 传入的 scenario 对象：赛题 md、可选初始价、标的、是否冻结漂移价。"""
    if not raw or not isinstance(raw, dict):
        return {"scenario_md": "", "initial_prices": {}, "symbols": None, "freeze_prices": False}
    md = str(raw.get("scenario_md") or raw.get("md") or "").strip()
    if len(md) > 100_000:
        md = md[:100_000] + "\n…（已截断）"
    ip = raw.get("initial_prices") or raw.get("prices")
    prices_out: dict[str, float] = {}
    if isinstance(ip, dict):
        for k, v in ip.items():
            sk = str(k).strip()
            if not sk:
                continue
            try:
                prices_out[sk] = float(v)
            except (TypeError, ValueError):
                continue
    sym_list = None
    syms = raw.get("symbols")
    if isinstance(syms, list):
        sym_list = [str(x).strip() for x in syms if str(x).strip()]
    elif isinstance(syms, str) and syms.strip():
        sym_list = [s.strip() for s in syms.split(",") if s.strip()]
    freeze = bool(raw.get("freeze_prices")) or str(raw.get("no_drift") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    return {"scenario_md": md, "initial_prices": prices_out, "symbols": sym_list, "freeze_prices": freeze}


def build_messages(
    *,
    contestant: Contestant,
    base_system: str,
    round_idx: int,
    symbols: list[str],
    prices: dict,
    pf: Portfolio,
    context_snip: str = "",
    arena_training_digest: str = "",
    scenario_md: str = "",
) -> list[dict[str, str]]:
    persona = (contestant.persona or "").strip()
    extra = (contestant.system_extra or "").strip()
    parts = [base_system.strip()]
    if persona:
        parts.append("【人格与策略】\n" + persona)
    if extra:
        parts.append("【额外系统约束】\n" + extra)
    atd = (arena_training_digest or "").strip()
    if atd:
        parts.append(atd)
    system = "\n\n".join(parts)

    user_lines = [
        f"选手显示名：{contestant.display}",
        f"内部槽位 id：{contestant.id}",
        f"第 {round_idx} 回合。",
        f"universe: {symbols}",
        f"当前价格 JSON: {json.dumps(prices, ensure_ascii=False)}",
        f"现金: {pf.cash:.2f}",
        f"持仓股数 JSON: {json.dumps(pf.positions, ensure_ascii=False)}",
        "请给出下一步交易 JSON。",
    ]
    sn = (context_snip or "").strip()
    if sn:
        user_lines.append("【回合前预检索摘要（非报价校验；策略辅助）】\n" + sn[:2000])
    sm = (scenario_md or "").strip()
    if sm:
        user_lines.append("【本场赛题与背景材料（用户上传，非实盘指令；结合 JSON 决策输出）】\n" + sm[:12000])
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(user_lines)},
    ]


def _invoke_slot(contestant: Contestant, providers: dict, messages: list[dict[str, str]]) -> str:
    pc = providers.get(contestant.provider)
    if not pc:
        raise RuntimeError(f"槽位 `{contestant.id}` 引用未知 provider `{contestant.provider}`，请检查 arena_config.yaml")
    return invoke_provider_dynamic(pc, messages, model_override=contestant.model)


def _post_game_feedback_enabled() -> bool:
    v = (os.environ.get("ARENA_POST_GAME_FEEDBACK") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _build_rank_block_for_feedback(display_rank: list[dict]) -> str:
    lines = []
    for i, row in enumerate(display_rank, start=1):
        rid = str(row.get("id") or "")
        disp = str(row.get("display") or rid)
        val = float(row.get("value") or 0)
        lines.append(f"第{i}名 · {rid}（{disp}）NAV={val:.2f}")
    return "\n".join(lines) if lines else "（无排名数据）"


def _build_feedback_messages(
    contestant: Contestant,
    *,
    rank_block: str,
    my_rank: int,
    n_players: int,
    my_nav: float,
    leader_nav: float,
) -> list[dict[str, str]]:
    gap = float(leader_nav) - float(my_nav)
    user = (
        "本场纸交易模拟已结束。以下是所有人最终排名（按 NAV 从高到低）：\n"
        f"{rank_block}\n\n"
        f"你的槽位 id：{contestant.id}\n"
        f"你的显示名：{contestant.display}\n"
        f"你的最终 NAV：{my_nav:.2f}\n"
        f"你在上述名次中的位置：第 {my_rank} 名 / 共 {n_players} 人\n"
        f"与当前第一名 NAV 的差距：{gap:.2f}（数值越大表示你相对第一名越低）\n\n"
        "请用 2～5 句中文简要复盘：①承认排名事实；②相对其他选手的表现；③若落后，指出一个可改进方向。"
        "不要输出 JSON、不要给出新的交易指令；非投资建议，仅为赛后口吻。"
    )
    system = (
        "你是刚结束一场金融模拟擂台赛的交易员智能体。"
        "当前任务是阅读最终排名并做简短自我复盘，帮助你在下一场调整策略认知。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _run_post_game_feedback_round(
    *,
    contestants: list[Contestant],
    providers: dict,
    display_rank: list[dict],
    totals: dict[str, float],
) -> list[dict]:
    """每场结束后：并行询问各模型，使其收到名次与相对差距（文本反馈，非训练）。"""
    if not display_rank:
        return []
    rank_block = _build_rank_block_for_feedback(display_rank)
    leader_nav = float(display_rank[0].get("value") or 0)
    rank_by_id = {str(r.get("id") or ""): i + 1 for i, r in enumerate(display_rank)}
    n_players = len(display_rank)

    out: list[dict] = []
    future_to_c: dict = {}
    with ThreadPoolExecutor(max_workers=max(1, len(contestants))) as pool:
        for c in contestants:
            sid = c.id
            my_rank = rank_by_id.get(sid, n_players)
            my_nav = float(totals.get(sid) or 0)
            msgs = _build_feedback_messages(
                c,
                rank_block=rank_block,
                my_rank=my_rank,
                n_players=n_players,
                my_nav=my_nav,
                leader_nav=leader_nav,
            )
            fut = pool.submit(_invoke_slot, c, providers, msgs)
            future_to_c[fut] = c

        batch_deadline = min(300.0, 60.0 + 40.0 * len(contestants))
        seen_ids: set[str] = set()
        try:
            for fut in as_completed(future_to_c, timeout=batch_deadline):
                c = future_to_c[fut]
                sid = c.id
                seen_ids.add(sid)
                raw = ""
                err = None
                try:
                    raw = fut.result(timeout=75)
                except Exception as e:  # noqa: BLE001
                    err = repr(e)
                out.append(
                    {
                        "slot_id": sid,
                        "display": c.display,
                        "provider": c.provider,
                        "rank": rank_by_id.get(sid, n_players),
                        "text": (raw or "").strip()[:4000],
                        "raw_tail": (raw or "")[-1200:],
                        "error": err,
                    }
                )
        except FuturesTimeoutError:
            pass
        for fut, c in future_to_c.items():
            if c.id in seen_ids:
                continue
            raw = ""
            err = "post_game_feedback_timeout"
            if fut.done():
                try:
                    raw = fut.result(timeout=2)
                    err = None
                except Exception as e:  # noqa: BLE001
                    err = repr(e)
            out.append(
                {
                    "slot_id": c.id,
                    "display": c.display,
                    "provider": c.provider,
                    "rank": rank_by_id.get(c.id, n_players),
                    "text": (raw or "").strip()[:4000],
                    "raw_tail": (raw or "")[-1200:],
                    "error": err,
                }
            )
    out.sort(key=lambda x: (x.get("rank") is None, x.get("rank") or 99))
    return out


def _write_arena_live(path: Path, obj: dict) -> None:
    try:
        path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _clear_arena_live(path: Path | None) -> None:
    if not path:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _arena_live_file_path(output_dir: Path | None) -> Path | None:
    if not output_dir:
        return None
    v = (os.environ.get("ARENA_LIVE_PROGRESS") or "1").strip().lower()
    if v in ("0", "false", "no", "off"):
        return None
    return output_dir / "arena_live.json"


def _live_payload(
    *,
    round_idx: int,
    duration_seconds: int,
    symbols: list[str],
    slot_ids: list[str],
    contestants: list[Contestant],
    portfolios: dict[str, Portfolio],
    prices: dict[str, float],
    price_source: str,
) -> dict:
    by_id = {c.id: c for c in contestants}
    totals = {c.id: portfolios[c.id].total_value(prices) for c in contestants}
    ranking = rank_players(totals)
    display_rank: list[dict] = []
    for sid, val in ranking:
        c = by_id[sid]
        display_rank.append(
            {
                "id": sid,
                "display": c.display,
                "provider": c.provider,
                "value": float(val),
            }
        )
    contestant_meta = {c.id: {"display": c.display, "provider": c.provider} for c in contestants}
    snapshots: dict[str, dict] = {}
    for c in contestants:
        pf = portfolios[c.id]
        snapshots[c.id] = {
            "display": c.display,
            "provider": c.provider,
            "cash": round(pf.cash, 2),
            "positions": {k: round(v, 4) for k, v in pf.positions.items()},
            "nav": round(totals[c.id], 2),
        }
    return {
        "active": True,
        "mode": "sim",
        "round": round_idx,
        "duration_seconds": duration_seconds,
        "symbols": symbols,
        "ais": slot_ids,
        "contestant_meta": contestant_meta,
        "final_ranking": display_rank,
        "snapshots": snapshots,
        "price_source": price_source,
    }


def run_simulation(
    *,
    contestants: list[Contestant],
    providers: dict,
    duration_seconds: int,
    symbols: list[str],
    seed: int | None,
    output_dir: Path | None = None,
    scenario_pack: dict | None = None,
    max_rounds: int | None = None,
    seconds_per_round: float | None = None,
) -> dict:
    live_path = _arena_live_file_path(output_dir)
    rng = random.Random(seed)
    pack = _normalize_scenario_pack(scenario_pack)
    user_md = str(pack["scenario_md"] or "")
    user_px: dict[str, float] = pack["initial_prices"]  # type: ignore[assignment]
    pack_syms = pack["symbols"]
    freeze_prices = bool(pack["freeze_prices"])
    sym_list = list(symbols)
    if isinstance(pack_syms, list) and len(pack_syms) > 0:
        sym_list = list(pack_syms)

    price_source = "drift_synthetic"
    use_ts = (os.environ.get("ARENA_USE_TUSHARE_PRICES") or "").strip().lower() in ("1", "true", "yes", "on")
    if user_px:
        prices: dict[str, float] = {}
        for s in sym_list:
            if s in user_px:
                prices[s] = round(float(user_px[s]), 4)
            else:
                prices[s] = round(initial_prices([s], rng)[s], 4)
        price_source = "user_json"
    elif use_ts:
        from arena_market_data import fetch_initial_prices_tushare

        got, _err = fetch_initial_prices_tushare(sym_list)
        if got:
            prices = got
            price_source = "tushare_daily"
        else:
            prices = initial_prices(sym_list, rng)
    else:
        prices = initial_prices(sym_list, rng)

    symbols = sym_list
    slot_ids = [c.id for c in contestants]
    portfolios = {sid: Portfolio() for sid in slot_ids}
    base_system = build_base_system_prompt()
    if output_dir:
        base_system = _inject_previous_sim_memory(output_dir, base_system)
    logs: list[dict] = []

    deadline = time.monotonic() + max(15, duration_seconds)
    round_idx = 0
    mr_cap = int(max_rounds) if max_rounds is not None and int(max_rounds) > 0 else None
    spr_budget = float(seconds_per_round) if seconds_per_round is not None and float(seconds_per_round) > 0 else None

    def flush_live(r: int) -> None:
        if not live_path:
            return
        _write_arena_live(
            live_path,
            _live_payload(
                round_idx=r,
                duration_seconds=duration_seconds,
                symbols=symbols,
                slot_ids=slot_ids,
                contestants=contestants,
                portfolios=portfolios,
                prices=prices,
                price_source=price_source,
            ),
        )

    try:
        flush_live(0)

        while True:
            if mr_cap is not None and round_idx >= mr_cap:
                break
            if time.monotonic() >= deadline:
                break
            round_idx += 1
            if not freeze_prices:
                prices = drift_prices(prices, rng)

            if spr_budget is not None:
                per_timeout = max(5.0, min(120.0, spr_budget / max(1, len(slot_ids)) - 0.5))
                batch_timeout = spr_budget + 20.0
            else:
                per_timeout = max(8.0, min(45.0, (deadline - time.monotonic()) / max(1, len(slot_ids)) - 0.5))
                if per_timeout < 5:
                    break
                batch_timeout = per_timeout * max(1, len(slot_ids)) + 10.0

            context_snip = ""
            if (os.environ.get("ARENA_DDG_SEARCH") or "").strip().lower() in ("1", "true", "yes", "on"):
                from arena_market_data import ddg_instant_summary

                q = " ".join(symbols[:2]) + " A-share stock"
                context_snip = ddg_instant_summary(q)

            future_to_slot: dict = {}
            with ThreadPoolExecutor(max_workers=len(slot_ids)) as pool:
                for c in contestants:
                    digest = ""
                    if output_dir:
                        from advisor_memory import format_training_digest_for_slot

                        try:
                            min_q = float((os.environ.get("ARENA_TRAINING_DIGEST_MIN_Q") or "0.42").strip())
                        except ValueError:
                            min_q = 0.42
                        digest = format_training_digest_for_slot(
                            output_dir, c.id, max_items=2, min_quality=min_q
                        )
                    messages = build_messages(
                        contestant=c,
                        base_system=base_system,
                        round_idx=round_idx,
                        symbols=symbols,
                        prices=prices,
                        pf=portfolios[c.id],
                        context_snip=context_snip,
                        arena_training_digest=digest,
                        scenario_md=user_md,
                    )
                    fut = pool.submit(_invoke_slot, c, providers, messages)
                    future_to_slot[fut] = c.id

                def _consume_slot_future(fut, sid: str, *, after_batch_timeout: bool) -> None:
                    raw = ""
                    err = None
                    if after_batch_timeout:
                        if fut.done():
                            try:
                                raw = fut.result(timeout=min(per_timeout, 45.0))
                            except Exception as e:  # noqa: BLE001
                                err = repr(e)
                                raw = "{}"
                        else:
                            try:
                                fut.cancel()
                            except Exception:
                                pass
                            err = (
                                "TimeoutError: 本回合批次等待超时（as_completed）；"
                                "部分槽位模型未在墙时内返回。请提高「总时长 / 每回合预算」或检查网络与 API。"
                            )
                            raw = "{}"
                    else:
                        try:
                            raw = fut.result(timeout=per_timeout)
                        except Exception as e:  # noqa: BLE001
                            err = repr(e)
                            raw = "{}"
                    decision = (
                        parse_decision_json(raw)
                        if not err
                        else {"action": "hold", "target": "", "size_pct": 0, "reason": err or "error"}
                    )
                    apply_decision(portfolios[sid], decision, prices, universe=symbols)
                    c = next(x for x in contestants if x.id == sid)
                    logs.append(
                        {
                            "round": round_idx,
                            "slot_id": sid,
                            "provider": c.provider,
                            "raw_tail": raw[-800:],
                            "decision": decision,
                            "prices": dict(prices),
                        }
                    )

                pending = set(future_to_slot.keys())
                try:
                    for fut in as_completed(future_to_slot, timeout=batch_timeout):
                        pending.discard(fut)
                        _consume_slot_future(fut, future_to_slot[fut], after_batch_timeout=False)
                except FuturesTimeoutError:
                    for fut in list(pending):
                        sid = future_to_slot[fut]
                        pending.discard(fut)
                        _consume_slot_future(fut, sid, after_batch_timeout=True)

            flush_live(round_idx)

        totals: dict[str, float] = {c.id: portfolios[c.id].total_value(prices) for c in contestants}
        ranking = rank_players(totals)
        order = [sid for sid, _ in ranking]
        weights = weights_from_rank(order)

        by_id = {c.id: c for c in contestants}
        display_rank = []
        for sid, val in ranking:
            c = by_id[sid]
            display_rank.append(
                {
                    "id": sid,
                    "display": c.display,
                    "provider": c.provider,
                    "value": float(val),
                }
            )

        snapshots: dict[str, dict] = {}
        for c in contestants:
            pf = portfolios[c.id]
            snapshots[c.id] = {
                "display": c.display,
                "provider": c.provider,
                "cash": round(pf.cash, 2),
                "positions": {k: round(v, 4) for k, v in pf.positions.items()},
                "nav": round(totals[c.id], 2),
            }

        contestant_meta = {c.id: {"display": c.display, "provider": c.provider} for c in contestants}

        post_fb: list[dict] = []
        if _post_game_feedback_enabled():
            try:
                post_fb = _run_post_game_feedback_round(
                    contestants=contestants,
                    providers=providers,
                    display_rank=display_rank,
                    totals=totals,
                )
            except Exception as e:  # noqa: BLE001
                post_fb = [
                    {
                        "slot_id": "_all",
                        "display": "",
                        "provider": "",
                        "rank": None,
                        "text": "",
                        "raw_tail": "",
                        "error": f"post_game_feedback_failed: {e!r}",
                    }
                ]

        scen_prev = (user_md[:240] + "…") if len(user_md) > 240 else user_md
        return {
            "mode": "sim",
            "duration_seconds": duration_seconds,
            "symbols": symbols,
            "ais": slot_ids,
            "contestant_meta": contestant_meta,
            "rounds": round_idx,
            "final_prices": prices,
            "final_ranking": display_rank,
            "weights": weights,
            "snapshots": snapshots,
            "turn_logs": logs,
            "post_game_feedback": post_fb,
            "price_source": price_source,
            "match_max_rounds": mr_cap,
            "match_seconds_per_round": spr_budget,
            "freeze_prices": freeze_prices,
            "scenario_md_preview": scen_prev,
            "scenario_md_chars": len(user_md),
        }
    finally:
        _clear_arena_live(live_path)


def append_learning_log(output_dir: Path, summary: str) -> None:
    p = output_dir / "data" / "learning_log.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    line = f"\n\n## {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n{summary}\n"
    with p.open("a", encoding="utf-8") as f:
        f.write(line)


def real_mode_payload(last: dict, user_query: str) -> dict:
    weights = last.get("weights") or {}
    ranking = last.get("final_ranking") or []
    meta = last.get("contestant_meta") or {}
    lines = [
        "【实盘/对话模式 · 多模型加权协作】",
        "以下为上一场擂台结束后的采纳权重（数值越大，综合结论中该槽位意见占比越高）：",
    ]
    for sid, w in sorted(weights.items(), key=lambda x: x[1], reverse=True):
        m = meta.get(sid) or {}
        disp = m.get("display") or sid
        prov = m.get("provider") or ""
        tail = f"（provider={prov}）" if prov else ""
        lines.append(f"- {disp} [{sid}]{tail}: {100*w:.1f}%")
    lines.append("")
    lines.append("用户问题：")
    lines.append(user_query)
    lines.append("")
    lines.append("请各模型先独立给出要点，再由宿主按权重做合成答复（非投资建议）。")
    return {
        "mode": "real",
        "weights": weights,
        "last_ranking": ranking,
        "prompt_for_host": "\n".join(lines),
    }


def resolve_contestants(
    *,
    config_path: Path,
    contestants_arg: str | None,
    ais_arg: list[str] | None,
) -> tuple[list[Contestant], dict]:
    cfg = load_arena_config(config_path)
    providers = parse_providers(cfg)
    cmap = parse_contestants(cfg)

    if contestants_arg and ais_arg:
        raise SystemExit("请只使用其一：--contestants 或 --ais")

    if contestants_arg:
        ids = [x.strip() for x in contestants_arg.split(",") if x.strip()]
        if not (2 <= len(ids) <= 4):
            raise SystemExit("--contestants 需要 2~4 个槽位 id，逗号分隔")
        out: list[Contestant] = []
        for cid in ids:
            if cid not in cmap:
                raise SystemExit(f"未知槽位 id `{cid}`，请在 {config_path} 的 contestants 中定义")
            c = cmap[cid]
            if c.provider not in providers:
                raise SystemExit(f"槽位 `{cid}` 的 provider `{c.provider}` 未在配置中声明")
            out.append(c)
        return out, providers

    if ais_arg:
        if not (2 <= len(ais_arg) <= 4):
            raise SystemExit("--ais 需要 2~4 个 provider slug")
        for slug in ais_arg:
            if slug not in providers:
                raise SystemExit(
                    f"未知 provider `{slug}`。请在 arena_config.yaml 的 providers 中添加，或使用 --contestants 指定自定义槽位。"
                )
        return legacy_builtin_contestants(list(dict.fromkeys(ais_arg))), providers

    raise SystemExit("必须提供 --contestants id1,id2 或 --ais zhipu deepseek ...")


def main() -> None:
    load_arena_dotenv()

    parser = argparse.ArgumentParser(description="金融 AI 擂台赛 runner")
    parser.add_argument(
        "--mode",
        choices=["sim", "real"],
        default="sim",
        help="sim=纸交易模拟；real=根据上一场 weights 生成对话编排提示",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="arena_config.yaml 路径",
    )
    parser.add_argument(
        "--contestants",
        type=str,
        default=None,
        help="sim：2~4 个槽位 id，逗号分隔（见 configs/arena_config.yaml），支持同一厂商多人格",
    )
    parser.add_argument(
        "--ais",
        nargs="*",
        default=None,
        metavar="PROVIDER",
        help="sim：兼容旧用法，2~4 个 provider id（须在 yaml providers 中存在）",
    )
    parser.add_argument("--duration", type=int, default=60, help="总墙时上限（秒）；与 --max-rounds 先到先停")
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=0,
        help="最多跑几回合（0=不按回合上限，仅受 --duration 约束）",
    )
    parser.add_argument(
        "--seconds-per-round",
        type=float,
        default=0,
        help="每回合模型侧总墙时预算（秒）；0=按剩余总时长在当回合均分",
    )
    parser.add_argument(
        "--scenario-file",
        type=Path,
        default=None,
        help="JSON：scenario_md、initial_prices、symbols（可选）、freeze_prices（可选，冻结回合间漂移）",
    )
    parser.add_argument("--symbols", default="600519.SH,000001.SZ", help="逗号分隔标的池（可被 scenario 内 symbols 覆盖）")
    parser.add_argument("--output-dir", type=Path, default=SKILL_ROOT, help="报告与状态输出目录")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--user-query", default="", help="real 模式用户问题摘要")
    args = parser.parse_args()

    if not args.config.is_file():
        raise SystemExit(f"找不到配置文件: {args.config}")

    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = out_dir / "arena_state.json"

    if args.mode == "real":
        if not state_path.exists():
            raise SystemExit(f"缺少 {state_path}，请先运行一次 sim 模式")
        last = json.loads(state_path.read_text(encoding="utf-8"))
        payload = real_mode_payload(last, args.user_query or "（无额外说明）")
        state_path.write_text(json.dumps({"last_sim": last, "real": payload}, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "arena_real_prompt.md").write_text(payload["prompt_for_host"], encoding="utf-8")
        print(payload["prompt_for_host"])
        return

    has_c = bool(args.contestants and args.contestants.strip())
    has_ais = bool(args.ais)
    if has_c == has_ais:
        raise SystemExit("sim 模式必须二选一：提供 --contestants id1,id2 或 --ais zhipu deepseek ...（不能都空或都填）")
    if has_c and has_ais:
        raise SystemExit("sim 模式请勿同时使用 --contestants 与 --ais")

    contestants, providers = resolve_contestants(
        config_path=args.config,
        contestants_arg=args.contestants.strip() if args.contestants else None,
        ais_arg=args.ais if has_ais else None,
    )

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if len(symbols) < 1:
        raise SystemExit("至少一个标的")

    scenario_pack: dict | None = None
    if args.scenario_file:
        if not args.scenario_file.is_file():
            raise SystemExit(f"找不到 scenario 文件: {args.scenario_file}")
        raw_sc = json.loads(args.scenario_file.read_text(encoding="utf-8"))
        if not isinstance(raw_sc, dict):
            raise SystemExit("scenario 文件须为 JSON 对象")
        scenario_pack = raw_sc

    mr = int(args.max_rounds) if args.max_rounds > 0 else None
    spr = float(args.seconds_per_round) if args.seconds_per_round > 0 else None

    payload = run_simulation(
        contestants=contestants,
        providers=providers,
        duration_seconds=args.duration,
        symbols=symbols,
        seed=args.seed,
        output_dir=out_dir,
        scenario_pack=scenario_pack,
        max_rounds=mr,
        seconds_per_round=spr,
    )
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        from advisor_memory import bump_challenge_counts

        bump_challenge_counts(out_dir, list(payload.get("ais") or []))
    except Exception:
        pass
    write_report(out_dir / "arena_report.html", payload)

    summary_lines = [
        f"回合数 {payload['rounds']}，标的 {symbols}，槽位 {payload['ais']}，价格来源 {payload.get('price_source', '')}",
        "排名: " + ", ".join(f"{r['id']}={r['value']:.2f}" for r in payload["final_ranking"]),
        "权重: " + json.dumps(payload["weights"], ensure_ascii=False),
    ]
    append_learning_log(out_dir, "\n".join(summary_lines))

    print(json.dumps(payload["final_ranking"], ensure_ascii=False, indent=2))
    print("weights:", json.dumps(payload["weights"], ensure_ascii=False))
    print(f"Wrote {state_path} and {out_dir / 'arena_report.html'}")


if __name__ == "__main__":
    main()
