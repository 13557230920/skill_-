#!/usr/bin/env python3
"""
生成擂台用 GIF（默认 `web/generated/arena-poster.gif`）：

1) **Gemini**（可选）：`uv run --with sprite-animator`，需 GEMINI_API_KEY/GOOGLE_API_KEY + uv。
2) **Pillow（默认 `--preset zoom`）**：把豆包整图做成**中心推拉变焦**循环 GIF，供前端 `<img>` 原生播放动画。
3) **`--preset idle`**：智谱/其它 LLM 取色板 + 轻微呼吸（旧效果）；`local` 不调 API。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / "assets" / "arena-reference.png"
DEFAULT_OUT = ROOT / "web" / "generated" / "arena-poster.gif"


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _resolve_uv_prefix() -> list[str] | None:
    if shutil.which("uv"):
        return ["uv"]
    probe = subprocess.run(
        [sys.executable, "-m", "uv", "--version"],
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        return [sys.executable, "-m", "uv"]
    return None


def _run_gemini_sprite(inp: Path, out: Path, animation: str) -> int:
    uv_prefix = _resolve_uv_prefix()
    if not uv_prefix:
        print("uv not found. Install: pip install uv", file=sys.stderr)
        return 3
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        print("Set GEMINI_API_KEY or GOOGLE_API_KEY for sprite-animator.", file=sys.stderr)
        return 4
    cmd = [
        *uv_prefix,
        "run",
        "--with",
        "sprite-animator",
        "sprite-animator",
        "-i",
        str(inp),
        "-o",
        str(out),
        "-a",
        animation,
    ]
    print("+", " ".join(cmd))
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Bake arena poster-idle.gif: Gemini sprite-animator OR arena LLM keys + Pillow."
    )
    ap.add_argument("-i", "--input", type=Path, default=None, help=f"default: {DEFAULT_IN}")
    ap.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT, help=f"default: {DEFAULT_OUT}")
    ap.add_argument(
        "-a",
        "--animation",
        default="idle",
        choices=("idle", "wave", "bounce", "dance"),
        help="仅 engine=gemini（sprite-animator）时生效",
    )
    ap.add_argument(
        "--engine",
        choices=("auto", "gemini", "zhipu", "deepseek", "minimax", "mimo", "local"),
        default="auto",
        help="auto：有 Gemini+uv 则用 sprite-animator，否则按 ZHIPU→DEEPSEEK→MINIMAX→MIMO→local",
    )
    ap.add_argument(
        "--preset",
        choices=("zoom", "idle"),
        default="zoom",
        help="仅 Pillow 路径：zoom=整图推拉 GIF（默认）；idle=轻微呼吸+像素化",
    )
    args = ap.parse_args()
    _load_env_file(ROOT / ".env")
    inp = (args.input or DEFAULT_IN).resolve()
    out = args.output.resolve()
    if not inp.is_file():
        print(f"Input image not found: {inp}", file=sys.stderr)
        print("  Copy your reference PNG to that path, or pass -i path/to.png", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)

    from arena_gif_bake import bake_poster_gif, resolve_llm_pil_engine

    engine = args.engine
    if engine == "auto":
        has_gem = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
        uv_ok = _resolve_uv_prefix() is not None
        if has_gem and uv_ok:
            engine = "gemini"
        elif has_gem and not uv_ok:
            print("Note: GEMINI/GOOGLE key set but uv missing; using LLM+Pillow instead.", file=sys.stderr)
            engine = resolve_llm_pil_engine()
        else:
            engine = resolve_llm_pil_engine()

    if engine == "gemini":
        rc = _run_gemini_sprite(inp, out, args.animation)
        if rc == 0:
            print(f"OK: {out}")
        return rc

    try:
        bake_poster_gif(engine, inp, out, preset=args.preset)
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 5
    print(f"OK: {out} (engine={engine}, Pillow, preset={args.preset})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
