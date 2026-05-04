/**
 * 数据加载与演示；像素绘制见 arena-draw.js（纯 Canvas，无贴图）。
 */

/**
 * 内置演示数据：**不是**真实行情、**不是**金融 skill / MCP 的产出；为本地写死的 JSON 片段，用于无 `arena_state.json` 时预览 Canvas。
 * 与 `arena_run.py` 完整 sim 产物的字段形状一致；四角像素人数 = 下面 `ais` / `final_ranking` 人数。
 */
export const DEMO_STATE = {
  mode: "sim",
  price_source: "drift_synthetic",
  duration_seconds: 30,
  symbols: ["600519.SH", "000001.SZ"],
  ais: ["ds_aggressive", "ds_value", "glm_demo", "mimo_quant"],
  contestant_meta: {
    ds_aggressive: { display: "DeepSeek·激进", provider: "deepseek" },
    ds_value: { display: "DeepSeek·价值", provider: "deepseek" },
    glm_demo: { display: "智谱·均衡", provider: "zhipu" },
    mimo_quant: { display: "MiMo·量化", provider: "mimo" },
  },
  rounds: 6,
  final_prices: { "600519.SH": 1688.0, "000001.SZ": 11.2 },
  final_ranking: [
    { id: "ds_aggressive", display: "DeepSeek·激进", provider: "deepseek", value: 102340.12 },
    { id: "mimo_quant", display: "MiMo·量化", provider: "mimo", value: 101550.0 },
    { id: "glm_demo", display: "智谱·均衡", provider: "zhipu", value: 101880.5 },
    { id: "ds_value", display: "DeepSeek·价值", provider: "deepseek", value: 100120.0 },
  ],
  weights: { ds_aggressive: 0.34, mimo_quant: 0.28, glm_demo: 0.22, ds_value: 0.16 },
  snapshots: {},
  turn_logs: [
    {
      round: 1,
      slot_id: "ds_aggressive",
      provider: "deepseek",
      raw_tail: '{"action":"hold","target":"","size_pct":0,"reason":"演示：内置数据，非真实行情"}',
      decision: { action: "hold", target: "", size_pct: 0, reason: "演示" },
    },
    {
      round: 1,
      slot_id: "mimo_quant",
      provider: "mimo",
      raw_tail: '{"action":"hold","target":"","size_pct":0,"reason":"演示占位"}',
      decision: { action: "hold", target: "", size_pct: 0 },
    },
  ],
  post_game_feedback: [
    {
      slot_id: "ds_aggressive",
      display: "DeepSeek·激进",
      provider: "deepseek",
      rank: 1,
      text: "（演示）已知全场名次：接受当前排名第一，复盘占位。",
    },
    {
      slot_id: "mimo_quant",
      display: "MiMo·量化",
      provider: "mimo",
      rank: 2,
      text: "（演示）名次反馈占位：相对他人与改进方向略。",
    },
  ],
};

/**
 * `arena_run --mode real` 会把根对象写成 `{ last_sim, real }`，擂台/建议页需要继续读上一场 sim 的扁平字段。
 */
export function normalizeArenaState(raw) {
  if (!raw || typeof raw !== "object") return raw;
  if (raw.last_sim && typeof raw.last_sim === "object") {
    const s = raw.last_sim;
    if (s.mode === "sim" || Array.isArray(s.ais) || Array.isArray(s.final_ranking)) return s;
  }
  return raw;
}

export async function loadArenaState() {
  const url = new URL("../arena_state.json", import.meta.url);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const raw = await res.json();
  return normalizeArenaState(raw);
}

export async function loadRealPrompt() {
  try {
    if (typeof window !== "undefined" && /^https?:$/i.test(window.location.protocol || "")) {
      const r = await fetch(`${window.location.origin}/api/arena-real-prompt`, { cache: "no-store" });
      if (!r.ok) return "";
      const j = await r.json();
      if (!j || !j.ok) return "";
      return String(j.text || "");
    }
    const url = new URL("../arena_real_prompt.md", import.meta.url);
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return "";
    return await res.text();
  } catch {
    return "";
  }
}

export function renderMetaLine(data) {
  const meta = data.contestant_meta || {};
  return (data.ais || [])
    .map((id) => {
      const m = meta[id] || {};
      return m.display ? `${id}（${m.display}）` : id;
    })
    .join(" · ");
}
