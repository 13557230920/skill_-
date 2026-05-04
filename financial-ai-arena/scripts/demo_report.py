#!/usr/bin/env python3
"""生成示例 arena_report.html（无需 API），用于预览像素擂台。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from report_html import write_report  # noqa: E402


def main() -> None:
    payload = {
        "mode": "sim",
        "duration_seconds": 60,
        "symbols": ["600519.SH", "000001.SZ"],
        "ais": ["ds_aggressive", "ds_value", "glm_demo"],
        "contestant_meta": {
            "ds_aggressive": {"display": "DeepSeek·激进", "provider": "deepseek"},
            "ds_value": {"display": "DeepSeek·价值", "provider": "deepseek"},
            "glm_demo": {"display": "智谱·均衡", "provider": "zhipu"},
        },
        "rounds": 5,
        "final_prices": {"600519.SH": 1688.0, "000001.SZ": 11.2},
        "final_ranking": [
            {"id": "ds_aggressive", "display": "DeepSeek·激进", "provider": "deepseek", "value": 102_340.12},
            {"id": "glm_demo", "display": "智谱·均衡", "provider": "zhipu", "value": 101_880.5},
            {"id": "ds_value", "display": "DeepSeek·价值", "provider": "deepseek", "value": 100_120.0},
        ],
        "weights": {"ds_aggressive": 0.5, "glm_demo": 0.33, "ds_value": 0.17},
        "snapshots": {
            "ds_aggressive": {
                "display": "DeepSeek·激进",
                "provider": "deepseek",
                "cash": 1200.0,
                "positions": {"600519.SH": 60.0},
                "nav": 102_340.12,
            },
            "glm_demo": {
                "display": "智谱·均衡",
                "provider": "zhipu",
                "cash": 50_000.0,
                "positions": {"000001.SZ": 4600.0},
                "nav": 101_880.5,
            },
            "ds_value": {
                "display": "DeepSeek·价值",
                "provider": "deepseek",
                "cash": 100_120.0,
                "positions": {},
                "nav": 100_120.0,
            },
        },
        "turn_logs": [],
    }
    out = ROOT / "arena_report.html"
    write_report(out, payload)
    state = ROOT / "arena_state.json"
    state.write_text(__import__("json").dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    print(f"Wrote {state}（供 web/ 前端拉取）")
    print("前端: python scripts/serve_web.py → http://127.0.0.1:8765/web/index.html")


if __name__ == "__main__":
    main()
