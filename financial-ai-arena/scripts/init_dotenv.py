#!/usr/bin/env python3
"""若尚无 .env，则从 .env.example 复制一份模板（不覆盖已有 .env）。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    dst = ROOT / ".env"
    src = ROOT / ".env.example"
    if dst.exists():
        print(f"已存在 {dst}，未修改。请编辑并填入 DEEPSEEK_API_KEY 等。")
        return
    if not src.is_file():
        print(f"缺少模板 {src}", file=sys.stderr)
        sys.exit(1)
    shutil.copy(src, dst)
    print(f"已创建 {dst}")
    print("请编辑该文件，取消注释并填写 DEEPSEEK_API_KEY=（不要引号），保存后重启 serve_web / 终端任务。")


if __name__ == "__main__":
    main()
