"""单页 HTML 报告：纯 Canvas 像素擂台（与 web/arena-draw.js 同源逻辑通过模块加载）。"""

from __future__ import annotations

import json
from pathlib import Path


def write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data_json = json.dumps(payload, ensure_ascii=False, indent=2)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>金融 AI 擂台赛 · 战报</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=M+PLUS+Rounded+1c:wght@500;800&family=Noto+Sans+SC:wght@400;600;700&family=ZCOOL+KuaiLe&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --bg-deep: #030711;
      --bg-mid: #0a1628;
      --gold: #f6c744;
      --text: #eef4ff;
      --muted: #8ca6c8;
      --border: rgba(34, 211, 238, 0.22);
      --crimson: #e11d48;
    }}
    body {{
      font-family: "Noto Sans SC", system-ui, sans-serif;
      margin: 0;
      background: radial-gradient(ellipse 100% 70% at 50% -15%, #1e3a5f 0%, transparent 52%),
        linear-gradient(165deg, var(--bg-mid) 0%, var(--bg-deep) 45%, #020308 100%);
      color: var(--text);
      min-height: 100vh;
    }}
    .wrap {{ max-width: 1000px; margin: 0 auto; padding: 20px 16px 40px; }}
    h1 {{
      font-family: "ZCOOL KuaiLe", "M PLUS Rounded 1c", fantasy, sans-serif;
      font-size: 1.25rem;
      font-weight: 400;
      margin: 10px 0 14px;
      color: var(--gold);
      letter-spacing: 0.06em;
      text-shadow: 0 0 20px rgba(246, 199, 68, 0.35), 2px 2px 0 #2a1810;
      border-left: 4px solid var(--crimson);
      padding-left: 12px;
    }}
    .panel {{
      background: rgba(10, 22, 42, 0.88);
      border: 2px solid var(--border);
      border-radius: 16px;
      padding: 14px 16px;
      margin-top: 14px;
      box-shadow: 0 0 0 1px rgba(244, 192, 37, 0.12), 0 14px 40px rgba(0, 0, 0, 0.5),
        inset 0 1px 0 rgba(255, 255, 255, 0.06);
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
    th, td {{ border-bottom: 1px solid var(--border); padding: 9px 8px; text-align: left; }}
    th {{ color: var(--gold); font-family: "M PLUS Rounded 1c", "Noto Sans SC", sans-serif; font-size: 0.82rem; }}
    .tag {{
      display: inline-block;
      padding: 3px 10px;
      border-radius: 6px;
      background: linear-gradient(135deg, rgba(225, 29, 72, 0.35), rgba(34, 211, 238, 0.2));
      border: 1px solid rgba(255, 255, 255, 0.12);
      margin-right: 6px;
      margin-bottom: 4px;
      font-size: 0.78rem;
      font-weight: 700;
    }}
    .warn {{ color: #fb923c; font-size: 0.88rem; margin-top: 8px; font-weight: 600; }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      background: rgba(4, 10, 22, 0.9);
      padding: 12px;
      border-radius: 10px;
      border: 1px solid var(--border);
      font-size: 0.82rem;
    }}
    .sub {{ color: var(--muted); font-size: 0.86rem; margin-top: 6px; }}
    .arena-stage {{ position: relative; display: block; width: 100%; max-width: 960px; aspect-ratio: 960 / 360; }}
    canvas.pixel {{
      width: 100%;
      max-width: 960px;
      height: auto;
      image-rendering: pixelated;
      image-rendering: crisp-edges;
      background: radial-gradient(circle at 50% 30%, #152238 0%, #070d18 70%);
      border-radius: 12px;
      border: 2px solid rgba(244, 192, 37, 0.28);
      display: block;
      margin-top: 8px;
      box-shadow: 0 0 20px rgba(34, 211, 238, 0.08);
    }}
    .arena-stage canvas.pixel {{ position: relative; margin-top: 0; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="panel">
      <h1>像素擂台 · 战报</h1>
      <p class="sub">与 <code>web/arena.html</code> 同源：全程序像素擂台 + JSON 排名，rAF 动效。请用 HTTP 打开。</p>
      <div class="arena-stage">
        <canvas class="pixel arena-canvas" id="arenaHero" width="960" height="360"></canvas>
      </div>
    </div>
    <div class="panel">
      <h1>NAV 像素条形榜</h1>
      <canvas class="pixel" id="pixelRank" width="640" height="220"></canvas>
    </div>
    <div class="panel">
      <h1>模拟设置与结果</h1>
      <p>
        <span class="tag">模式</span> {payload.get("mode", "")}
        <span class="tag">时长(秒)</span> {payload.get("duration_seconds", "")}
        <span class="tag">标的</span> {", ".join(payload.get("symbols", []))}
      </p>
      <p><span class="tag">参赛槽位</span> <span id="slotLine"></span></p>
      <div class="warn">仅供学习与研究演示，不构成投资建议。</div>
    </div>
    <div class="panel">
      <h1>数据明细</h1>
      <table>
        <thead><tr><th>#</th><th>擂台昵称</th><th>槽位 / 显示名</th><th>provider</th><th>终值 NAV</th></tr></thead>
        <tbody id="rank"></tbody>
      </table>
    </div>
    <div class="panel">
      <h1>各 AI 终局持仓与现金</h1>
      <table>
        <thead><tr><th>槽位</th><th>显示名</th><th>NAV</th><th>现金</th><th>持仓</th></tr></thead>
        <tbody id="snap"></tbody>
      </table>
    </div>
    <div class="panel">
      <h1>实盘/决策权重</h1>
      <table>
        <thead><tr><th>槽位</th><th>权重</th></tr></thead>
        <tbody id="weights"></tbody>
      </table>
    </div>
    <div class="panel">
      <h1>原始 JSON</h1>
      <pre id="raw"></pre>
    </div>
  </div>
  <script type="application/json" id="arena-payload">{data_json}</script>
  <script type="module">
    import {{ drawPixelArenaScene, drawPixelRank, rankedSlotsForArena }} from "./web/arena-draw.js";
    const data = JSON.parse(document.getElementById("arena-payload").textContent);
    const meta = data.contestant_meta || {{}};
    const slotLine = (data.ais || []).map((id) => {{
      const m = meta[id] || {{}};
      return id + (m.display ? "（" + m.display + "）" : "");
    }}).join(" · ");
    document.getElementById("slotLine").textContent = slotLine || "（无）";

    const rankBody = document.getElementById("rank");
    rankedSlotsForArena(data).forEach((row, i) => {{
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${{i+1}}</td><td>${{row.stageName}}</td><td>${{row.id}} · ${{row.display}}</td><td>${{row.provider || ""}}</td><td>${{Number(row.value).toFixed(2)}}</td>`;
      rankBody.appendChild(tr);
    }});

    const snapBody = document.getElementById("snap");
    Object.entries(data.snapshots || {{}}).forEach(([k,s]) => {{
      const tr = document.createElement("tr");
      const pos = JSON.stringify(s.positions || {{}});
      tr.innerHTML = `<td>${{k}}</td><td>${{s.display}}</td><td>${{s.nav}}</td><td>${{s.cash}}</td><td>${{pos}}</td>`;
      snapBody.appendChild(tr);
    }});

    const wBody = document.getElementById("weights");
    Object.entries(data.weights || {{}}).forEach(([k,v]) => {{
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${{k}}</td><td>${{(100*v).toFixed(1)}}%</td>`;
      wBody.appendChild(tr);
    }});

    const arenaCanvas = document.getElementById("arenaHero");
    let arenaSceneData = data;
    function arenaTick(nowMs) {{
      drawPixelArenaScene(arenaCanvas, arenaSceneData, nowMs * 0.001);
      requestAnimationFrame(arenaTick);
    }}
    requestAnimationFrame(arenaTick);
    drawPixelRank(document.getElementById("pixelRank"), data);
    document.getElementById("raw").textContent = JSON.stringify(data, null, 2);
  </script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")
