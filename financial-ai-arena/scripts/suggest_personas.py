#!/usr/bin/env python3
"""调用指定 writer（providers 之一）生成 contestants_gen（JSON，兼容 YAML），便于粘贴进 arena_config.yaml。"""

from __future__ import annotations

import argparse
from pathlib import Path

from arena_dotenv import load_arena_dotenv

from persona_api import DEFAULT_CONFIG, suggest_personas_text

SKILL_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    load_arena_dotenv()

    p = argparse.ArgumentParser(description="生成人格 JSON/YAML 草稿（contestants_gen）")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--writer", required=True, help="providers 中的 id，例如 deepseek / zhipu")
    p.add_argument("--slots", type=int, default=4, help="生成多少个互不重叠人格（默认 4）")
    p.add_argument("--topic", default="A股纸交易模拟擂台：多回合买卖 hold，控制回撤")
    args = p.parse_args()

    if not args.config.is_file():
        raise SystemExit(f"找不到 {args.config}")

    if not (2 <= args.slots <= 4):
        raise SystemExit("--slots 须在 2~4")

    text = suggest_personas_text(
        args.config,
        args.writer,
        args.slots,
        args.topic,
    )
    print(text)


if __name__ == "__main__":
    main()
