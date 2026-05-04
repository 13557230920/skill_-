"""从 serve_web 非阻塞拉起 arena_run.py sim（子进程 + 线程），供擂台页「开始比赛」。"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

_lock = threading.Lock()
_state: dict = {
    "running": False,
    "exit_code": None,
    "stderr_tail": "",
    "stdout_tail": "",
    "started_monotonic": 0.0,
    "finished_monotonic": 0.0,
}


def _worker(cmd: list[str], cwd: str) -> None:
    out, err = "", ""
    ec: int | None = None
    try:
        kw: dict = {
            "cwd": cwd,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        p = subprocess.Popen(cmd, **kw)
        out, err = p.communicate()
        ec = int(p.returncode) if p.returncode is not None else -1
    except Exception as e:
        ec = -1
        err = (err or "") + "\n" + repr(e)
    with _lock:
        _state["exit_code"] = ec
        _state["stdout_tail"] = (out or "")[-3000:]
        _state["stderr_tail"] = (err or "")[-8000:]
        _state["finished_monotonic"] = time.monotonic()
        _state["running"] = False


def request_start(
    *,
    root: Path,
    contestants: str,
    duration: int,
    symbols: str | None,
    max_rounds: int | None = None,
    seconds_per_round: float | None = None,
    scenario_pack: dict | None = None,
) -> tuple[bool, str]:
    raw = (contestants or "").replace(" ", "").strip()
    ids = [x for x in raw.split(",") if x]
    if not 2 <= len(ids) <= 4:
        return False, "contestants 须为 2～4 个 id，逗号分隔（须与 configs/arena_config.yaml 中一致）"
    if duration < 15 or duration > 7200:
        return False, "duration 须在 15～7200 秒之间"
    if max_rounds is not None:
        if max_rounds < 1 or max_rounds > 500:
            return False, "max_rounds 须在 1～500 之间或留空"
    if seconds_per_round is not None:
        if seconds_per_round < 5 or seconds_per_round > 600:
            return False, "seconds_per_round 须在 5～600 之间或留空"

    scenario_path: Path | None = None
    if scenario_pack and isinstance(scenario_pack, dict):
        sp = scenario_pack
        has_content = False
        if str(sp.get("scenario_md") or sp.get("md") or "").strip():
            has_content = True
        ip = sp.get("initial_prices") or sp.get("prices")
        if isinstance(ip, dict) and ip:
            has_content = True
        syms = sp.get("symbols")
        if isinstance(syms, list) and syms:
            has_content = True
        elif isinstance(syms, str) and syms.strip():
            has_content = True
        if bool(sp.get("freeze_prices")) or str(sp.get("no_drift") or "").strip().lower() in ("1", "true", "yes", "on"):
            has_content = True
        if has_content:
            data_dir = root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            scenario_path = data_dir / "last_scenario_pack.json"
            scenario_path.write_text(json.dumps(scenario_pack, ensure_ascii=False), encoding="utf-8")

    with _lock:
        if _state["running"]:
            return False, "已有比赛在进行中，请等待结束后再试"
        _state["running"] = True
        _state["exit_code"] = None
        _state["stderr_tail"] = ""
        _state["stdout_tail"] = ""
        _state["started_monotonic"] = time.monotonic()
        _state["finished_monotonic"] = 0.0

    sym = (symbols or "").strip() or "600519.SH,000001.SZ"
    cmd = [
        sys.executable,
        str(root / "scripts" / "arena_run.py"),
        "--mode",
        "sim",
        "--contestants",
        ",".join(ids),
        "--duration",
        str(int(duration)),
        "--symbols",
        sym,
        "--output-dir",
        str(root),
    ]
    if max_rounds is not None and max_rounds > 0:
        cmd += ["--max-rounds", str(int(max_rounds))]
    if seconds_per_round is not None and float(seconds_per_round) > 0:
        cmd += ["--seconds-per-round", str(float(seconds_per_round))]
    if scenario_path is not None:
        cmd += ["--scenario-file", str(scenario_path)]

    threading.Thread(target=_worker, args=(cmd, str(root)), daemon=True).start()
    return True, "已在后台启动 arena_run.py"


def get_status() -> dict:
    with _lock:
        return {
            "running": bool(_state["running"]),
            "exit_code": _state["exit_code"],
            "stderr_tail": _state["stderr_tail"] or "",
            "stdout_tail": _state["stdout_tail"] or "",
            "started_monotonic": float(_state["started_monotonic"] or 0),
            "finished_monotonic": float(_state["finished_monotonic"] or 0),
        }
