"""
擂台参考动图：无 Gemini 时，用 .env 里已有 LLM（智谱视觉 / 其他厂商文本）取配色 + Pillow 合成像素风循环 GIF。
"""

from __future__ import annotations

import base64
import math
import os
import re
from pathlib import Path
from typing import Any

_HEX = re.compile(r"#[0-9A-Fa-f]{6}")


def parse_palette_from_llm_text(text: str, *, limit: int = 8) -> list[str]:
    """从模型输出中抽取 #RRGGBB 色值。"""
    found = _HEX.findall(text)
    out: list[str] = []
    for h in found:
        u = h.upper()
        if u not in out:
            out.append(u)
        if len(out) >= limit:
            break
    return out


def _median_palette_from_image(im: Any, n: int = 6) -> list[str]:
    from PIL import Image

    small = im.convert("RGB").resize((48, 48), Image.Resampling.BILINEAR)
    q = small.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette() or []
    colors: list[str] = []
    for i in range(min(n, len(pal) // 3)):
        r, g, b = pal[i * 3 : i * 3 + 3]
        colors.append(f"#{r:02X}{g:02X}{b:02X}")
    return colors or ["#5B8DFE", "#FFD743", "#E54B4B", "#0B1220", "#111A2E", "#9FB0D8"]


def _palette_average_rgb(palette: list[str]) -> tuple[int, int, int]:
    tr = tg = tb = 0.0
    for hx in palette:
        tr += int(hx[1:3], 16)
        tg += int(hx[3:5], 16)
        tb += int(hx[5:7], 16)
    n = max(1, len(palette))
    return int(tr / n), int(tg / n), int(tb / n)


def build_idle_gif(
    image_path: Path,
    output_path: Path,
    palette_hex: list[str] | None,
    *,
    canvas_max_w: int = 640,
    n_frames: int = 16,
    frame_ms: int = 85,
) -> None:
    from PIL import Image, ImageEnhance, ImageOps

    output_path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(image_path).convert("RGBA")
    bg = (11, 18, 32, 255)
    im = ImageOps.contain(im, (canvas_max_w, int(canvas_max_w * 0.42)), Image.Resampling.LANCZOS)
    w, h = im.size
    # 像素化：缩小再最近邻放大
    scale = max(2, w // 120)
    small = im.resize((max(1, w // scale), max(1, h // scale)), Image.Resampling.BILINEAR)
    pixel = small.resize((w, h), Image.Resampling.NEAREST)
    rgb = Image.new("RGB", (w, h), (bg[0], bg[1], bg[2]))
    rgb.paste(pixel, mask=pixel.split()[3] if pixel.mode == "RGBA" else None)

    pal_src = palette_hex or _median_palette_from_image(rgb, 6)
    strength = 0.28 if palette_hex else 0.08
    avg_rgb = _palette_average_rgb(pal_src)

    frames: list[Any] = []
    tint = Image.new("RGB", (w, h), avg_rgb)
    for i in range(n_frames):
        phase = (i / n_frames) * 2 * math.pi
        br = 1.0 + 0.07 * math.sin(phase)
        fr = ImageEnhance.Brightness(rgb).enhance(br)
        if strength > 0 and pal_src:
            a = strength * (0.35 + 0.65 * (0.5 + 0.5 * math.sin(phase * 0.5)))
            fr = Image.blend(fr, tint, min(0.22, a))
        frames.append(fr)

    q0 = frames[0].quantize(colors=48)
    quantized = [q0] + [f.quantize(palette=q0) for f in frames[1:]]
    quantized[0].save(
        output_path,
        save_all=True,
        append_images=quantized[1:],
        duration=frame_ms,
        loop=0,
        optimize=False,
    )


def build_zoom_loop_gif(
    image_path: Path,
    output_path: Path,
    *,
    out_w: int = 960,
    out_h: int = 360,
    n_frames: int = 28,
    frame_ms: int = 70,
    zoom_amp: float = 0.07,
) -> None:
    """
    把整图（豆包海报等）做成「中心推拉变焦」循环 GIF，动效明显，适合直接给 <img> 播放。
    与 build_idle_gif 不同：不缩小成像素块、不做强量化失真。
    """
    from PIL import Image, ImageOps

    output_path.parent.mkdir(parents=True, exist_ok=True)
    src = Image.open(image_path).convert("RGB")
    fitted = ImageOps.fit(src, (out_w, out_h), method=Image.Resampling.LANCZOS)

    frames: list[Any] = []
    for i in range(n_frames):
        phase = (i / n_frames) * 2 * math.pi
        s = 1.0 + zoom_amp * math.sin(phase)
        nw = max(out_w + 1, int(round(out_w * s)))
        nh = max(out_h + 1, int(round(out_h * s)))
        scaled = fitted.resize((nw, nh), Image.Resampling.LANCZOS)
        lx = (nw - out_w) // 2
        ly = (nh - out_h) // 2
        crop = scaled.crop((lx, ly, lx + out_w, ly + out_h))
        frames.append(crop)

    q0 = frames[0].quantize(colors=128)
    quantized = [q0] + [f.quantize(palette=q0) for f in frames[1:]]
    quantized[0].save(
        output_path,
        save_all=True,
        append_images=quantized[1:],
        duration=frame_ms,
        loop=0,
        optimize=False,
    )


def palette_from_zhipu_vision(image_path: Path) -> list[str] | None:
    """智谱 OpenAI 兼容端 + 视觉模型，从参考图抽色板。"""
    key = os.environ.get("ZHIPU_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("请 pip install openai") from e

    model = os.environ.get("ARENA_BAKE_ZHIPU_VISION_MODEL", "glm-4v-flash").strip()
    base = os.environ.get("ARENA_BAKE_ZHIPU_OPENAI_BASE", "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
    mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
    b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    prompt = (
        "分析这张图中主色、点缀色与背景色。只输出一个 JSON 对象，不要其它文字："
        '{"palette":["#RRGGBB",...]}，palette 含 6～8 个不重复的十六进制大写色值。'
    )
    client = OpenAI(api_key=key, base_url=base)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        temperature=0.2,
        max_tokens=256,
    )
    msg = resp.choices[0].message
    text = (getattr(msg, "content", None) or "") or ""
    pal = parse_palette_from_llm_text(text, limit=8)
    return pal or None


def palette_from_openai_text(
    *,
    base_url: str,
    api_key: str,
    model: str,
    invoke_style: str | None,
) -> list[str] | None:
    """无视觉时：用文本模型生成擂台霓虹配色 JSON。"""
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("请 pip install openai") from e

    client = OpenAI(api_key=api_key, base_url=base_url.rstrip("/"))
    prompt = (
        "为「金融 AI 擂台」暗色网页头图生成霓虹像素氛围色板。"
        "只输出 JSON：{\"palette\":[\"#RRGGBB\",...]}，恰好 7 色：深蓝底、亮蓝高光、金黄强调、珊瑚红点缀、"
        "浅灰文字色、中蓝过渡、深阴影。色值大写，不要解释。"
    )
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.35,
        "stream": False,
    }
    extra: dict[str, Any] = {}
    if invoke_style == "mimo":
        kwargs["max_completion_tokens"] = 256
        extra["thinking"] = {"type": "disabled"}
    else:
        kwargs["max_tokens"] = 256
    if invoke_style == "deepseek":
        extra["thinking"] = {"type": "disabled"}
    if extra:
        kwargs["extra_body"] = extra
    resp = client.chat.completions.create(**kwargs)
    msg = resp.choices[0].message
    parts: list[str] = []
    c = getattr(msg, "content", None)
    if c:
        parts.append(str(c))
    for attr in ("reasoning_content", "reasoning"):
        v = getattr(msg, attr, None)
        if v:
            parts.append(str(v))
    text = "\n".join(parts).strip()
    pal = parse_palette_from_llm_text(text, limit=10)
    return pal or None


def bake_poster_gif(
    engine: str,
    image_path: Path,
    output_path: Path,
    *,
    preset: str = "zoom",
) -> None:
    """
    engine: zhipu | deepseek | minimax | mimo | local
    preset: zoom（整图推拉 GIF，默认）| idle（轻微呼吸+像素化）
    """
    if preset == "zoom":
        build_zoom_loop_gif(image_path, output_path)
        return

    pal: list[str] | None = None
    if engine == "zhipu":
        pal = palette_from_zhipu_vision(image_path)
        if not pal:
            raise RuntimeError("智谱视觉取色失败（检查 ARENA_BAKE_ZHIPU_VISION_MODEL 与网络）")
    elif engine == "deepseek":
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY")
        model = os.environ.get("ARENA_DEEPSEEK_MODEL", "deepseek-chat")
        pal = palette_from_openai_text(
            base_url="https://api.deepseek.com",
            api_key=key,
            model=model,
            invoke_style="deepseek",
        )
    elif engine == "minimax":
        key = os.environ.get("MINIMAX_API_KEY")
        if not key:
            raise RuntimeError("缺少 MINIMAX_API_KEY")
        model = os.environ.get("ARENA_MINIMAX_MODEL", "MiniMax-M2.7")
        pal = palette_from_openai_text(
            base_url="https://api.minimaxi.com/v1",
            api_key=key,
            model=model,
            invoke_style=None,
        )
    elif engine == "mimo":
        key = os.environ.get("MIMO_API_KEY")
        if not key:
            raise RuntimeError("缺少 MIMO_API_KEY")
        model = os.environ.get("ARENA_MIMO_MODEL", "mimo-v2.5-pro")
        pal = palette_from_openai_text(
            base_url="https://api.xiaomimimo.com/v1",
            api_key=key,
            model=model,
            invoke_style="mimo",
        )
    elif engine == "local":
        pal = None
    else:
        raise ValueError(f"未知 engine `{engine}`")

    build_idle_gif(image_path, output_path, pal)


def resolve_llm_pil_engine() -> str:
    """无 Gemini 时 PIL 路径的默认优先级。"""
    if os.environ.get("ZHIPU_API_KEY"):
        return "zhipu"
    if os.environ.get("DEEPSEEK_API_KEY"):
        return "deepseek"
    if os.environ.get("MINIMAX_API_KEY"):
        return "minimax"
    if os.environ.get("MIMO_API_KEY"):
        return "mimo"
    return "local"
