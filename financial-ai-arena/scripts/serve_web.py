#!/usr/bin/env python3
"""在 skill 根目录启动静态服务 + 擂台配置/人格生成 API（供 web/arena-setup.html）。"""

from __future__ import annotations

import http.server
import json
import os
import socketserver
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
PORT = 8765


def _is_loopback_host(host: str) -> bool:
    if host in ("127.0.0.1", "::1", "localhost"):
        return True
    # Windows / 双栈下常见
    if host.startswith("::ffff:127.0.0.1"):
        return True
    return False


class ArenaDevHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """开发用：禁止强缓存；处理 /api/* 与 /web/api/* 后回退为根目录静态文件。支持 GET 与 POST（人格接口）。"""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("directory", str(ROOT))
        super().__init__(*args, **kwargs)

    def _parsed_url(self):
        """部分客户端会把 path 写成 //api/...，导致匹配不到 /api/。"""
        raw = self.path or ""
        if not isinstance(raw, str):
            raw = str(raw)
        if raw.startswith("//"):
            raw = "/" + raw[2:].lstrip("/")
        return urlparse(raw)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def _loopback_only(self) -> bool:
        return _is_loopback_host(self.client_address[0])

    def _send_json(self, status: int, obj: object) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self) -> dict:
        n = int(self.headers.get("Content-Length", "0") or 0)
        if n <= 0:
            return {}
        raw = self.rfile.read(n)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    @staticmethod
    def _normalize_api_path(parsed) -> str | None:
        """把 /web/api/foo 与 /api/foo 统一成 /api/foo。"""
        p = unquote((parsed.path or "").strip())
        if not p or p == "/":
            return None
        while p.startswith("//"):
            p = "/" + p[2:].lstrip("/")
        p = p.rstrip("/") or "/"
        if p.startswith("/web/api/"):
            p = "/api/" + p[len("/web/api/") :]
        elif p == "/web/api":
            p = "/api"
        if p.startswith("/api/") or p == "/api":
            return p
        return None

    @staticmethod
    def _first(qs: dict[str, list[str]], key: str, default: str = "") -> str:
        vals = qs.get(key)
        if not vals:
            return default
        v = vals[0]
        return v.strip() if isinstance(v, str) else default

    def _body_suggest_personas_from_query(self, parsed) -> dict:
        qs = parse_qs(parsed.query, keep_blank_values=True)
        providers_raw = self._first(qs, "providers", "")
        ppl = [x.strip() for x in providers_raw.split(",") if x.strip()] if providers_raw else []
        slots_s = self._first(qs, "slots", "2")
        try:
            slots_n = int(slots_s)
        except ValueError:
            slots_n = 2
        return {
            "writer": self._first(qs, "writer", ""),
            "topic": self._first(qs, "topic", "") or "A股纸交易模拟擂台",
            "slots": slots_n,
            "providers": ppl if ppl else None,
        }

    def _body_suggest_one_from_query(self, parsed) -> dict:
        qs = parse_qs(parsed.query, keep_blank_values=True)
        return {
            "writer": self._first(qs, "writer", ""),
            "topic": self._first(qs, "topic", "") or "A股纸交易模拟擂台",
            "provider": self._first(qs, "provider", ""),
            "id_hint": self._first(qs, "id_hint", ""),
            "display_hint": self._first(qs, "display_hint", ""),
            "avoid_brief": self._first(qs, "avoid_brief", ""),
        }

    def _run_suggest_personas(self, body: dict) -> None:
        from persona_api import (
            DEFAULT_CONFIG,
            parse_contestants_gen,
            suggest_personas_text,
        )

        writer = str(body.get("writer") or "").strip()
        topic = str(body.get("topic") or "").strip() or "A股纸交易模拟擂台"
        slots = int(body.get("slots") or 2)
        pps = body.get("providers")
        providers_per_slot = None
        if isinstance(pps, list) and pps:
            providers_per_slot = [str(x).strip() for x in pps]
        text = suggest_personas_text(
            DEFAULT_CONFIG,
            writer,
            slots,
            topic,
            providers_per_slot=providers_per_slot,
        )
        items, err = parse_contestants_gen(text)
        self._send_json(
            200,
            {
                "ok": True,
                "raw": text,
                "items": items,
                "parse_error": err,
            },
        )

    def _run_suggest_one(self, body: dict) -> None:
        from persona_api import (
            DEFAULT_CONFIG,
            parse_contestants_gen,
            suggest_one_contestant_text,
        )

        writer = str(body.get("writer") or "").strip()
        topic = str(body.get("topic") or "").strip() or "A股纸交易模拟擂台"
        target_provider = str(body.get("provider") or "").strip()
        id_hint = str(body.get("id_hint") or "")
        display_hint = str(body.get("display_hint") or "")
        avoid = str(body.get("avoid_brief") or "")
        text = suggest_one_contestant_text(
            DEFAULT_CONFIG,
            writer,
            topic,
            target_provider,
            id_hint=id_hint,
            display_hint=display_hint,
            avoid_one_liners=avoid,
        )
        items, err = parse_contestants_gen(text)
        one = items[0] if len(items) == 1 else None
        self._send_json(
            200,
            {
                "ok": True,
                "raw": text,
                "item": one,
                "items": items,
                "parse_error": err,
            },
        )

    def _handle_suggest_api(self, path: str, body: dict) -> None:
        if not self._loopback_only():
            self._send_json(403, {"ok": False, "error": "API 仅允许本机回环访问"})
            return
        try:
            if path == "/api/suggest-personas":
                self._run_suggest_personas(body)
            else:
                self._run_suggest_one(body)
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})

    def do_GET(self) -> None:
        parsed = self._parsed_url()
        api_p = self._normalize_api_path(parsed)
        if api_p == "/api/ping":
            self._send_json(
                200,
                {
                    "ok": True,
                    "handler": "arena-serve-web",
                    "features": {"advisor_api": True},
                },
            )
            return
        if api_p == "/api/run-sim-status":
            self._handle_run_sim_status()
            return
        if api_p == "/api/arena-config":
            try:
                from persona_api import DEFAULT_CONFIG, public_config_snapshot

                snap = public_config_snapshot(DEFAULT_CONFIG)
                self._send_json(200, {"ok": True, "config": snap})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return
        if api_p == "/api/advisor-context":
            self._handle_advisor_context()
            return
        if api_p == "/api/arena-real-prompt":
            self._handle_arena_real_prompt()
            return
        if api_p == "/api/suggest-personas":
            self._handle_suggest_api("/api/suggest-personas", self._body_suggest_personas_from_query(parsed))
            return
        if api_p == "/api/suggest-one":
            self._handle_suggest_api("/api/suggest-one", self._body_suggest_one_from_query(parsed))
            return
        raw_api = unquote((parsed.path or "").strip())
        while raw_api.startswith("//"):
            raw_api = "/" + raw_api[2:].lstrip("/")
        if raw_api.startswith("/api/") or raw_api == "/api":
            self._send_json(
                404,
                {
                    "ok": False,
                    "error": "未识别的 /api 路径（本进程路由表不含此端点）。请确认运行的是本仓库最新 scripts/serve_web.py；若 8765 已被旧版或其它程序占用，请先结束该进程再启动。",
                    "path": raw_api,
                },
            )
            return
        super().do_GET()

    def _check_config_write_token(self, body: dict) -> tuple[bool, str]:
        token = os.environ.get("ARENA_CONFIG_WRITE_TOKEN", "").strip()
        if not token:
            return True, ""
        got = (self.headers.get("X-Arena-Write-Token") or "").strip()
        if not got:
            got = str(body.get("write_token") or "").strip()
        if got != token:
            return (
                False,
                "已在环境变量中设置 ARENA_CONFIG_WRITE_TOKEN：请在请求体 write_token 或请求头 X-Arena-Write-Token 中携带相同值。",
            )
        return True, ""

    def _handle_run_sim_status(self) -> None:
        if not self._loopback_only():
            self._send_json(403, {"ok": False, "error": "API 仅允许本机回环访问"})
            return
        from arena_sim_job import get_status

        st = get_status()
        live = None
        live_path = ROOT / "arena_live.json"
        if live_path.is_file():
            try:
                live = json.loads(live_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                live = None
        self._send_json(200, {"ok": True, **st, "live": live})

    def _handle_run_sim_start(self, body: dict) -> None:
        if not self._loopback_only():
            self._send_json(403, {"ok": False, "error": "API 仅允许本机回环访问"})
            return
        from arena_sim_job import request_start

        c = body.get("contestants")
        if isinstance(c, list):
            c = ",".join(str(x).strip() for x in c if str(x).strip())
        if not isinstance(c, str):
            c = ""
        c = c.strip()
        try:
            dur = int(body.get("duration", 60))
        except (TypeError, ValueError):
            dur = 60
        sym = body.get("symbols")
        if sym is not None and not isinstance(sym, str):
            sym = str(sym)

        max_rounds = None
        raw_mr = body.get("max_rounds")
        if raw_mr not in (None, ""):
            try:
                max_rounds = int(raw_mr)
            except (TypeError, ValueError):
                self._send_json(400, {"ok": False, "error": "max_rounds 须为整数或留空"})
                return
            if max_rounds < 1:
                max_rounds = None

        seconds_per_round = None
        raw_spr = body.get("seconds_per_round")
        if raw_spr not in (None, ""):
            try:
                seconds_per_round = float(raw_spr)
            except (TypeError, ValueError):
                self._send_json(400, {"ok": False, "error": "seconds_per_round 须为数字或留空"})
                return
            if seconds_per_round <= 0:
                seconds_per_round = None

        scenario_pack: dict = {}
        nested = body.get("scenario")
        if isinstance(nested, dict):
            scenario_pack.update(nested)
        sm = body.get("scenario_md")
        if isinstance(sm, str) and sm.strip():
            scenario_pack["scenario_md"] = sm.strip()[:120_000]
        ip = body.get("initial_prices")
        if isinstance(ip, dict):
            scenario_pack["initial_prices"] = ip
        sy = body.get("scenario_symbols") or body.get("override_symbols")
        if isinstance(sy, str) and sy.strip():
            scenario_pack["symbols"] = sy.strip()
        if body.get("freeze_prices") is True or body.get("freeze_prices") == 1:
            scenario_pack["freeze_prices"] = True

        pack_out = scenario_pack if scenario_pack else None

        ok, msg = request_start(
            root=ROOT,
            contestants=c,
            duration=dur,
            symbols=sym if isinstance(sym, str) else None,
            max_rounds=max_rounds,
            seconds_per_round=seconds_per_round,
            scenario_pack=pack_out,
        )
        if ok:
            self._send_json(202, {"ok": True, "message": msg})
        elif "已有比赛" in msg:
            self._send_json(409, {"ok": False, "error": msg})
        else:
            self._send_json(400, {"ok": False, "error": msg})

    def _handle_arena_real_prompt(self) -> None:
        """避免前端直接 GET /arena_real_prompt.md 在文件不存在时产生 404 控制台噪声。"""
        if not self._loopback_only():
            self._send_json(403, {"ok": False, "error": "API 仅允许本机回环访问"})
            return
        p = ROOT / "arena_real_prompt.md"
        if not p.is_file():
            self._send_json(
                200,
                {
                    "ok": True,
                    "text": "",
                    "hint": "尚未生成。在 skill 根目录执行：python scripts/arena_run.py --mode real --user-query \"…\"",
                },
            )
            return
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as e:
            self._send_json(200, {"ok": True, "text": "", "hint": str(e)})
            return
        self._send_json(200, {"ok": True, "text": text})

    def _handle_advisor_context(self) -> None:
        if not self._loopback_only():
            self._send_json(403, {"ok": False, "error": "API 仅允许本机回环访问"})
            return
        try:
            from advisor_memory import load_memory
            from config_loader import load_arena_config, parse_contestants
            from persona_api import DEFAULT_CONFIG
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})
            return

        state_path = ROOT / "arena_state.json"
        arena: dict = {}
        if state_path.is_file():
            try:
                raw = json.loads(state_path.read_text(encoding="utf-8"))
                ls = raw.get("last_sim")
                arena = ls if isinstance(ls, dict) else raw
            except (OSError, json.JSONDecodeError):
                arena = {}

        mem = load_memory(ROOT)
        cfg = load_arena_config(DEFAULT_CONFIG)
        cmap = parse_contestants(cfg)
        last_ais = list(arena.get("ais") or [])
        rows = []
        for cid, c in sorted(cmap.items(), key=lambda x: x[0]):
            ccn = int(mem.get("challenge_count_by_slot", {}).get(cid, 0) or 0)
            rows.append(
                {
                    "id": cid,
                    "display": c.display,
                    "provider": c.provider,
                    "challenge_count": ccn,
                    "in_last_arena": cid in last_ais,
                }
            )

        turn_logs = arena.get("turn_logs") or []
        if not isinstance(turn_logs, list):
            turn_logs = []
        transparency = {
            "symbols": arena.get("symbols"),
            "rounds": arena.get("rounds"),
            "price_source": arena.get("price_source"),
            "final_prices": arena.get("final_prices"),
            "ais_last": last_ais,
            "turn_logs_preview": turn_logs[-16:],
            "turn_logs_total": len(turn_logs),
            "final_ranking": arena.get("final_ranking"),
        }
        eps = mem.get("episodes") or []
        recent = list(reversed(eps[-40:])) if isinstance(eps, list) else []

        self._send_json(
            200,
            {
                "ok": True,
                "arena": {
                    "weights": arena.get("weights") or {},
                    "contestant_meta": arena.get("contestant_meta") or {},
                    "ais": last_ais,
                },
                "contestants": rows,
                "transparency": transparency,
                "recent_episodes": recent,
                "quality_note": "质量分 0～1：综合用户/回复长度、字符重复度、中文信息量、金融关键词等启发式，用于筛掉明显敷衍内容；非学术指标。",
            },
        )

    def _handle_advisor_chat(self, body: dict) -> None:
        if not self._loopback_only():
            self._send_json(403, {"ok": False, "error": "API 仅允许本机回环访问"})
            return
        try:
            from advisor_memory import append_episode, build_weight_blend_system, pick_veteran_slot
            from config_loader import load_arena_config, parse_contestants, parse_providers
            from persona_api import DEFAULT_CONFIG
            from providers import invoke_provider_dynamic
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})
            return

        mode = str(body.get("chat_mode") or body.get("mode") or "slot").strip().lower()
        msgs = body.get("messages")
        if not isinstance(msgs, list) or not msgs:
            self._send_json(400, {"ok": False, "error": "messages 须为非空数组，元素含 role、content"})
            return

        cfg = load_arena_config(DEFAULT_CONFIG)
        providers = parse_providers(cfg)
        cmap = parse_contestants(cfg)
        if not cmap:
            self._send_json(400, {"ok": False, "error": "arena_config.yaml 无 contestants"})
            return

        state_path = ROOT / "arena_state.json"
        arena: dict = {}
        if state_path.is_file():
            try:
                raw = json.loads(state_path.read_text(encoding="utf-8"))
                ls = raw.get("last_sim")
                arena = ls if isinstance(ls, dict) else raw
            except (OSError, json.JSONDecodeError):
                pass

        weights: dict[str, float] = {}
        for k, v in (arena.get("weights") or {}).items():
            try:
                weights[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        meta = dict(arena.get("contestant_meta") or {})
        ais = [str(x).strip() for x in (arena.get("ais") or []) if str(x).strip()]
        ais_f = [a for a in ais if a in cmap]

        api_msgs: list[dict[str, str]] = []
        for m in msgs[-24:]:
            if not isinstance(m, dict):
                continue
            role = str(m.get("role") or "").strip()
            content = str(m.get("content") or "")
            if role not in ("user", "assistant", "system"):
                continue
            api_msgs.append({"role": role, "content": content})

        if not api_msgs or api_msgs[-1]["role"] != "user":
            self._send_json(400, {"ok": False, "error": "对话最后一条须为 user"})
            return

        system_prefix = (
            "你是真实金融场景下的分析助手。须声明不构成投资建议，提示数据滞后、模型幻觉与监管边界。\n"
        )
        chosen_id: str | None = None

        if mode in ("veteran", "历练", "experience", "max_challenge"):
            chosen_id = pick_veteran_slot(
                ROOT, last_ais=ais, weights=weights, all_slot_ids=list(cmap.keys())
            )
            if not chosen_id:
                self._send_json(400, {"ok": False, "error": "无法选择历练槽位"})
                return
        elif mode in ("weight", "权重", "blend", "committee"):
            if not ais_f:
                self._send_json(
                    400,
                    {"ok": False, "error": "权重合成需要上一场擂台 ais；请先跑 sim 或改用「自选槽位」"},
                )
                return
            chosen_id = max(ais_f, key=lambda s: float(weights.get(s, 0) or 0))
            personas = {cid: cmap[cid].persona for cid in ais_f}
            system_prefix += (
                build_weight_blend_system(meta=meta, weights=weights, ais=ais_f, personas=personas) + "\n\n"
            )
        else:
            chosen_id = str(body.get("slot_id") or "").strip()
            if chosen_id not in cmap:
                self._send_json(400, {"ok": False, "error": f"未知 slot_id：`{chosen_id}`"})
                return

        c = cmap[chosen_id]
        pc = providers.get(c.provider)
        if not pc:
            self._send_json(400, {"ok": False, "error": f"provider `{c.provider}` 未在 yaml 中配置"})
            return

        digest_parts = [system_prefix]
        if mode not in ("weight", "权重", "blend", "committee"):
            persona = (c.persona or "").strip()
            if persona:
                digest_parts.append("【人格】\n" + persona)
        se = (c.system_extra or "").strip()
        if se:
            digest_parts.append("【额外约束】\n" + se)
        full_system = "\n\n".join(digest_parts)
        full_messages = [{"role": "system", "content": full_system}] + api_msgs

        try:
            reply = invoke_provider_dynamic(pc, full_messages, model_override=c.model)
        except Exception as e:
            self._send_json(500, {"ok": False, "error": repr(e)})
            return

        last_user = api_msgs[-1]["content"]
        ep = append_episode(
            ROOT,
            mode=mode,
            slot_id=chosen_id,
            provider=c.provider,
            display=c.display,
            user=last_user,
            assistant=str(reply or ""),
        )

        self._send_json(
            200,
            {
                "ok": True,
                "reply": str(reply or ""),
                "resolved_slot": chosen_id,
                "episode": {
                    "id": ep.get("id"),
                    "quality": ep.get("quality"),
                    "quality_reasons": ep.get("quality_reasons"),
                },
            },
        )

    def _handle_write_contestants(self, body: dict) -> None:
        if not self._loopback_only():
            self._send_json(403, {"ok": False, "error": "API 仅允许本机回环访问"})
            return
        ok_t, err_t = self._check_config_write_token(body)
        if not ok_t:
            self._send_json(403, {"ok": False, "error": err_t})
            return
        cy = body.get("contestants_yaml")
        if not isinstance(cy, str) or not cy.strip():
            self._send_json(400, {"ok": False, "error": "缺少字符串字段 contestants_yaml"})
            return
        try:
            from arena_config_write import apply_contestants_snippet
            from persona_api import DEFAULT_CONFIG

            ok, msg = apply_contestants_snippet(DEFAULT_CONFIG, cy)
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})
            return
        if ok:
            self._send_json(200, {"ok": True, "message": msg})
        else:
            self._send_json(400, {"ok": False, "error": msg})

    def _handle_add_provider(self, body: dict) -> None:
        if not self._loopback_only():
            self._send_json(403, {"ok": False, "error": "API 仅允许本机回环访问"})
            return
        ok_t, err_t = self._check_config_write_token(body)
        if not ok_t:
            self._send_json(403, {"ok": False, "error": err_t})
            return
        from arena_provider_write import apply_provider_to_config
        from persona_api import DEFAULT_CONFIG

        ow = body.get("overwrite")
        overwrite = ow is True or str(ow).lower() in ("1", "true", "yes")
        try:
            ok, msg = apply_provider_to_config(
                DEFAULT_CONFIG,
                provider_id=str(body.get("id") or ""),
                driver=str(body.get("driver") or ""),
                env_api_key=str(body.get("env_api_key") or ""),
                default_model=str(body.get("default_model") or ""),
                base_url=str(body.get("base_url") or ""),
                invoke_style=str(body.get("invoke_style") or ""),
                openai_extra_body_json=str(
                    body.get("openai_extra_body_json") or body.get("openai_extra_body") or ""
                ),
                overwrite=overwrite,
            )
        except Exception as e:
            self._send_json(500, {"ok": False, "error": str(e)})
            return
        if ok:
            self._send_json(200, {"ok": True, "message": msg})
        else:
            self._send_json(400, {"ok": False, "error": msg})

    def do_POST(self) -> None:
        parsed = self._parsed_url()
        api_p = self._normalize_api_path(parsed)
        if api_p == "/api/write-contestants":
            if not self._loopback_only():
                self._send_json(403, {"ok": False, "error": "API 仅允许本机回环访问"})
                return
            try:
                body = self._read_json_body()
            except json.JSONDecodeError as e:
                self._send_json(400, {"ok": False, "error": f"JSON 无效: {e}"})
                return
            self._handle_write_contestants(body)
            return
        if api_p == "/api/add-provider":
            if not self._loopback_only():
                self._send_json(403, {"ok": False, "error": "API 仅允许本机回环访问"})
                return
            try:
                body = self._read_json_body()
            except json.JSONDecodeError as e:
                self._send_json(400, {"ok": False, "error": f"JSON 无效: {e}"})
                return
            self._handle_add_provider(body)
            return
        if api_p == "/api/run-sim":
            if not self._loopback_only():
                self._send_json(403, {"ok": False, "error": "API 仅允许本机回环访问"})
                return
            try:
                body = self._read_json_body()
            except json.JSONDecodeError as e:
                self._send_json(400, {"ok": False, "error": f"JSON 无效: {e}"})
                return
            self._handle_run_sim_start(body)
            return
        if api_p == "/api/advisor-chat":
            if not self._loopback_only():
                self._send_json(403, {"ok": False, "error": "API 仅允许本机回环访问"})
                return
            try:
                body = self._read_json_body()
            except json.JSONDecodeError as e:
                self._send_json(400, {"ok": False, "error": f"JSON 无效: {e}"})
                return
            self._handle_advisor_chat(body)
            return
        if api_p not in ("/api/suggest-personas", "/api/suggest-one"):
            self.send_error(404)
            return
        try:
            body = self._read_json_body()
        except json.JSONDecodeError as e:
            self._send_json(400, {"ok": False, "error": f"JSON 无效: {e}"})
            return
        self._handle_suggest_api(api_p, body)


class ReuseTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def main() -> None:
    from arena_dotenv import load_arena_dotenv

    load_arena_dotenv()
    os.chdir(ROOT)
    print("=" * 60)
    print("  Financial AI Arena — serve_web")
    print("  处理器:", ArenaDevHTTPRequestHandler.__name__)
    print("  GET/POST /api/suggest-personas  ·  GET/POST /api/suggest-one")
    print("  POST   /api/write-contestants  （本机回环：写 configs/arena_config.yaml 的 contestants）")
    print("  POST   /api/add-provider       （本机回环：合并自定义 providers，与 write 同口令策略）")
    print("  POST   /api/run-sim  ·  GET /api/run-sim-status  （本机：后台跑 arena_run sim）")
    print("  GET    /api/advisor-context  ·  POST /api/advisor-chat  （真实建议页：上下文 + 对话）")
    print("  GET    /api/arena-real-prompt  （arena_real_prompt.md，无文件时 200 空文本）")
    print("  GET    /api/arena-config  ·  GET /api/ping  （/web/api/* 镜像同效）")
    print("  若人格接口返回 501，说明 8765 端口上不是本脚本，请关掉旧进程后重启。")
    print("=" * 60)
    with ReuseTCPServer(("", PORT), ArenaDevHTTPRequestHandler) as httpd:
        print(f"Serving from:\n  {ROOT}\n")
        print(f"首页:       http://127.0.0.1:{PORT}/web/index.html")
        print(f"擂台配置:   http://127.0.0.1:{PORT}/web/arena-setup.html")
        print(f"擂台竞技:   http://127.0.0.1:{PORT}/web/arena.html")
        print(f"金融建议:   http://127.0.0.1:{PORT}/web/advisor.html")
        print("按 Ctrl+C 停止\n")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
