"""统一加载环境变量：先 monorepo 根目录 .env，再 skill 根目录 .env（后者覆盖同名键）。"""

from __future__ import annotations

from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent


def load_arena_dotenv() -> None:
    """与 arena_run / serve_web / suggest_personas 共用。"""
    from dotenv import load_dotenv

    # 典型布局：…/jingrong_skill/skills/financial-ai-arena → 仓库根为 parent.parent
    mono_repo_root = SKILL_ROOT.parent.parent
    repo_env = mono_repo_root / ".env"
    if repo_env.is_file():
        load_dotenv(repo_env, override=False)
    skill_env = SKILL_ROOT / ".env"
    if skill_env.is_file():
        load_dotenv(skill_env, override=True)
    load_dotenv(override=False)
