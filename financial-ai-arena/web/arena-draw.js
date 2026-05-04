/**
 * 纯 Canvas 像素擂台 — 程序绘制；`t` 为秒级时间轴（rAF 驱动：天幕闪星、灯柱、绳高光、
 * 彩纸、围绳、四角 Q 版、标题与榜等）。
 */

export const ARENA_PET_NAMES = ["小财猫", "金鼠宝", "银狐妹", "铜犬弟", "小青蛇", "玉兔儿"];

export function stageNameForRank(indexZeroBased) {
  if (indexZeroBased < ARENA_PET_NAMES.length) return ARENA_PET_NAMES[indexZeroBased];
  return `选手${indexZeroBased + 1}`;
}

/** 按槽位 id 稳定分配外观，换名次时颜色不跟人错绑 */
export function variantForSlotId(id) {
  const s = String(id || "");
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h) % 4;
}

/** 与 Q 版配色同一哈希：每名选手固定「擂台艺名」，换位时名字跟人走 */
export function arenaPetNameForSlot(id) {
  return ARENA_PET_NAMES[variantForSlotId(id)] || `选手`;
}

/**
 * 用 snapshots.nav（赛间每回合必更新）与 final_ranking 合并出当前 NAV，避免只信榜上陈旧 value。
 */
function effectiveNavForSlot(id, snaps, byId) {
  const sn = snaps[id] || {};
  const navSnap = sn.nav != null ? Number(sn.nav) : NaN;
  const row = byId.get(id);
  const navRow = row && row.value != null && row.value !== "" ? Number(row.value) : NaN;
  if (Number.isFinite(navSnap)) return navSnap;
  if (Number.isFinite(navRow)) return navRow;
  return 0;
}

export function rankedSlotsForArena(data) {
  const meta = data.contestant_meta || {};
  const snaps = data.snapshots || {};
  const rankRows = Array.isArray(data.final_ranking) ? data.final_ranking : [];
  const byId = new Map();
  for (const r of rankRows) {
    const id = String(r.id || "").trim();
    if (id) byId.set(id, r);
  }

  let order = [...new Set((Array.isArray(data.ais) ? data.ais : []).map(String).filter(Boolean))];
  if (order.length) {
    // ais 偶发少于 final_ranking（旧 JSON / 合并异常）时，仍把榜上的人画全
    const seen = new Set(order);
    for (const r of rankRows) {
      const id = String(r.id || "").trim();
      if (id && !seen.has(id)) {
        seen.add(id);
        order.push(id);
      }
    }
  }
  if (!order.length) {
    const seen = new Set();
    for (const r of rankRows.slice().sort((a, b) => Number(b.value) - Number(a.value))) {
      const id = String(r.id || "").trim();
      if (id && !seen.has(id)) {
        seen.add(id);
        order.push(id);
      }
    }
  }
  if (order.length > 4) order = order.slice(0, 4);

  const merged = [];
  for (const id of order) {
    const r = byId.get(id);
    const sn = snaps[id] || {};
    const mm = meta[id] || {};
    const value = effectiveNavForSlot(id, snaps, byId);
    const display = String((r && r.display) || sn.display || mm.display || id).trim() || id;
    const provider = String((r && r.provider) || sn.provider || mm.provider || "").trim();
    merged.push({ id, display, provider, value });
  }
  merged.sort((a, b) => b.value - a.value);
  return merged.slice(0, 4).map((r) => ({
    ...r,
    stageName: arenaPetNameForSlot(r.id),
    sub: subtitleForSlot(r),
  }));
}

/** 赛间用 snapshots.nav 重建 final_ranking，保证与像素条、排序一致 */
export function rebuildFinalRankingFromSnapshots(data) {
  const snaps = data.snapshots;
  const meta = data.contestant_meta || {};
  const rankFb = Array.isArray(data.final_ranking) ? data.final_ranking : [];
  const aisRaw = Array.isArray(data.ais) && data.ais.length ? data.ais : rankFb.map((r) => String(r.id || "").trim()).filter(Boolean);
  const ais = [...new Set(aisRaw.map(String))].filter(Boolean);
  if (!snaps || typeof snaps !== "object" || !ais.length) return null;

  const rows = [];
  for (const sid of ais) {
    const sn = snaps[sid] || {};
    const m = meta[sid] || {};
    let nav = Number(sn.nav);
    if (!Number.isFinite(nav)) {
      const fb = rankFb.find((x) => String(x.id || "").trim() === sid);
      nav = fb != null ? Number(fb.value) : NaN;
    }
    if (!Number.isFinite(nav)) return null;
    rows.push({
      id: sid,
      display: String(sn.display || m.display || sid).trim() || sid,
      provider: String(sn.provider || m.provider || "").trim(),
      value: nav,
    });
  }
  rows.sort((a, b) => b.value - a.value);
  return rows.length ? rows : null;
}

function subtitleForSlot(r) {
  const d = (r.display || "").trim();
  const id = (r.id || "").trim();
  if (d && d !== id) return `${d} · ${id}`;
  return id || d || "";
}

function easeOutCubic(u) {
  const x = Math.min(1, Math.max(0, u));
  return 1 - (1 - x) ** 3;
}

/**
 * 赛后在 Q 版脸上叠小像素：joy / sad / shake / relax（shake 主位移由调用方处理）
 */
function drawMoodOverlay(ctx, ox, oy, g, mood, t) {
  const P = (dx, dy, w, h, c) => b(ctx, ox + dx * g, oy + dy * g, w * g, h * g, c);
  if (mood === "joy") {
    P(5, 3, 2, 1, "#fbbf24");
    P(4, 8, 6, 1, "#0f172a");
    P(5, 8, 4, 1, "#fda4af");
  } else if (mood === "sad") {
    P(4, 5, 2, 2, "#93c5fd");
    P(7, 5, 2, 2, "#93c5fd");
    P(5, 6, 3, 1, "#0f172a");
    P(5, 8, 1, 2, "#38bdf8");
  } else if (mood === "relax") {
    P(4, 5, 6, 1, "#0f172a");
    P(4, 6, 6, 1, "#0f172a");
    const wv = 0.35 + 0.15 * Math.sin(t * 2.2);
    b(ctx, ox + 2 * g, oy + 9 * g, 10 * g, 2 * g, `rgba(15,23,42,${0.35 + wv})`);
  } else if (mood === "shake") {
    P(4, 5, 2, 2, "#0f172a");
    P(7, 5, 2, 2, "#0f172a");
    P(5, 8, 2, 1, "#be123c");
  }
}

/* —— 参考色板 —— */
const C = {
  skyTop: "#070f1c",
  skyBot: "#152a45",
  blueUI: "#5b8dfe",
  blueDark: "#2d4a8f",
  yellow: "#ffd743",
  red: "#e54b4b",
  cream: "#f7f4ec",
  white: "#ffffff",
  orange: "#ff9f45",
  pink: "#ffb6c1",
};

function px(ctx, x, y, w, h, color) {
  ctx.fillStyle = color;
  ctx.fillRect(Math.floor(x), Math.floor(y), Math.ceil(w), Math.ceil(h));
}

function b(ctx, x, y, w, h, color) {
  if (w > 0 && h > 0) px(ctx, x, y, w, h, color);
}

/** 像素圆角条（阶梯近似） */
function pillBar(ctx, x, y, w, h, fill, border) {
  const r = 6;
  b(ctx, x + r, y, w - 2 * r, h, fill);
  b(ctx, x, y + r, w, h - 2 * r, fill);
  b(ctx, x + 3, y, w - 6, r, fill);
  b(ctx, x + 3, y + h - r, w - 6, r, fill);
  if (border) {
    b(ctx, x + r, y - 1, w - 2 * r, 2, border);
    b(ctx, x + r, y + h - 1, w - 2 * r, 2, border);
    b(ctx, x - 1, y + r, 2, h - 2 * r, border);
    b(ctx, x + w - 1, y + r, 2, h - 2 * r, border);
  }
}

function drawSky(ctx, W, H) {
  const step = 4;
  for (let y = 0; y < H; y += step) {
    const t = y / (H * 0.55);
    const r = Math.floor(7 + t * 30);
    const g = Math.floor(18 + t * 40);
    const bl = Math.floor(35 + t * 55);
    b(ctx, 0, y, W * 0.72, step, `rgb(${r},${g},${bl})`);
  }
  b(ctx, W * 0.72, 0, W * 0.28, H, C.skyBot);
}

function drawBunting(ctx, x0, x1, y) {
  const cols = [C.red, C.blueUI, C.yellow];
  let x = x0;
  let i = 0;
  while (x < x1 - 8) {
    ctx.fillStyle = cols[i % 3];
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + 9, y);
    ctx.lineTo(x + 4, y + 14);
    ctx.closePath();
    ctx.fill();
    x += 11;
    i++;
  }
}

function drawFloodlight(ctx, poleX, topY, t = 0) {
  const pulse = 0.78 + 0.22 * Math.sin(t * 3.2 + poleX * 0.02);
  b(ctx, poleX, topY, 6, 70, "#2a3f5f");
  b(ctx, poleX - 2, topY - 2, 10, 10, "#4a5568");
  b(ctx, poleX - 14, topY + 8, 34, 22, `rgba(255,250,220,${0.9 * pulse})`);
  b(ctx, poleX - 10, topY + 12, 26, 14, `rgba(255,255,255,${0.52 * pulse})`);
  const gr = ctx.createRadialGradient(poleX + 3, topY + 18, 2, poleX + 3, topY + 18, 80);
  gr.addColorStop(0, `rgba(255, 248, 200, ${0.32 * pulse})`);
  gr.addColorStop(1, "rgba(255, 248, 200, 0)");
  ctx.fillStyle = gr;
  ctx.fillRect(poleX - 80, topY - 10, 160, 140);
}

function drawCrowdBleachers(ctx, x0, y0, w, h, seed, t = 0) {
  let s = seed;
  const rnd = () => {
    s = (s * 1103515245 + 12345) >>> 0;
    return s / 4294967296;
  };
  b(ctx, x0, y0, w, h, "#0a1628");
  const dots = ["#e54b4b", "#5b8dfe", "#ffd743", "#7dd3fc", "#f472b6"];
  const n = Math.floor((w * h) / 58);
  for (let i = 0; i < n; i++) {
    const baseX = x0 + rnd() * w;
    const baseY = y0 + rnd() * h;
    let x = baseX;
    let y = baseY;
    if (t) {
      const u = (baseX - x0 + t * 36 + i * 23) % w;
      const v = (baseY - y0 + t * 24 + i * 17) % h;
      x = x0 + (u < 0 ? u + w : u);
      y = y0 + (v < 0 ? v + h : v);
    }
    b(ctx, x, y, 3 + (rnd() > 0.5 ? 2 : 0), 3, dots[(i + seed) % dots.length]);
  }
}

/** 角柱：黄顶 + 红身（参考图） */
function drawCornerPost(ctx, x, y) {
  b(ctx, x, y, 14, 8, C.yellow);
  b(ctx, x + 1, y + 8, 12, 14, C.red);
  b(ctx, x + 4, y + 20, 6, 3, "#8b0000");
}

function drawRopeH(ctx, x0, y, len, cols, thick) {
  const seg = 12;
  for (let i = 0; i < len; i += seg) {
    const c = cols[Math.floor(i / seg) % cols.length];
    b(ctx, x0 + i, y, Math.min(seg, len - i), thick, c);
  }
}

function drawRopeV(ctx, x, y0, len, cols, thick) {
  const seg = 12;
  for (let j = 0; j < len; j += seg) {
    const c = cols[Math.floor(j / seg) % cols.length];
    b(ctx, x, y0 + j, thick, Math.min(seg, len - j), c);
  }
}

/** 侧边绳：深蓝条 + 黄白小点（第二参考图） */
function drawRopeVDecor(ctx, x, y0, len) {
  b(ctx, x, y0, 8, len, "#1e3a5f");
  for (let j = 8; j < len - 4; j += 10) {
    b(ctx, x + 2, y0 + j, 3, 3, C.yellow);
    if (j + 5 < len) b(ctx, x + 5, y0 + j + 5, 2, 2, C.white);
  }
}

/**
 * rankVariant 0..3 决定外观：蓝猫AI / 金鼠 / 白狐 / 橘虎
 * (ox,oy) 左上角像素，g 单像素格放大
 * mood: idle | joy | sad | shake | relax — 赛后决算用
 */
function drawChibiCorner(ctx, ox, oy, g, rankVariant, mood = "idle", t = 0) {
  const shakeX = mood === "shake" ? Math.sin(t * 22) * 2.2 * g : 0;
  const joyY = mood === "joy" ? Math.sin(t * 5.5) * 2 * g : 0;
  const ox0 = ox + shakeX;
  const oy0 = oy + joyY;
  const P = (dx, dy, w, h, c) => b(ctx, ox0 + dx * g, oy0 + dy * g, w * g, h * g, c);

  const eye = () => {
    P(4, 5, 2, 2, "#0f172a");
    P(7, 5, 2, 2, "#0f172a");
    P(5, 5, 1, 1, C.white);
    P(8, 5, 1, 1, C.white);
    P(4, 7, 1, 1, C.pink);
    P(8, 7, 1, 1, C.pink);
  };

  if (rankVariant === 0) {
    // 浅蓝猫 + 蓝背心 + 黄 AI
    for (let yy = 3; yy <= 8; yy++) for (let xx = 2; xx <= 9; xx++) P(xx, yy, 1, 1, "#93d9ff");
    P(3, 2, 2, 2, "#38bdf8");
    P(8, 2, 2, 2, "#38bdf8");
    P(4, 9, 4, 2, "#1e40af");
    P(5, 7, 2, 2, C.yellow);
    P(7, 7, 2, 2, C.yellow);
    eye();
  } else if (rankVariant === 1) {
    // 金黄鼠感 + 红腮红
    for (let yy = 3; yy <= 8; yy++) for (let xx = 2; xx <= 9; xx++) P(xx, yy, 1, 1, "#fcd34d");
    P(3, 2, 2, 2, "#f59e0b");
    P(8, 2, 2, 2, "#f59e0b");
    P(3, 6, 1, 1, "#ef4444");
    P(9, 6, 1, 1, "#ef4444");
    P(5, 9, 4, 1, C.red);
    P(6, 8, 2, 1, C.yellow);
    eye();
  } else if (rankVariant === 2) {
    // 白狐 + 蓝耳饰
    for (let yy = 3; yy <= 8; yy++) for (let xx = 2; xx <= 9; xx++) P(xx, yy, 1, 1, "#f8fafc");
    P(2, 1, 2, 3, C.blueUI);
    P(9, 1, 2, 3, C.blueUI);
    P(5, 9, 2, 1, C.blueUI);
    eye();
  } else {
    // 橘条纹 + 红项圈 + 黄铃
    for (let yy = 3; yy <= 8; yy++) for (let xx = 2; xx <= 9; xx++) {
      const stripe = (xx + yy) % 3 === 0 ? "#ea580c" : "#fdba74";
      P(xx, yy, 1, 1, stripe);
    }
    P(3, 2, 2, 2, "#c2410c");
    P(8, 2, 2, 2, "#c2410c");
    P(4, 9, 4, 1, C.red);
    P(6, 8, 2, 1, C.yellow);
    eye();
  }

  if (mood && mood !== "idle") drawMoodOverlay(ctx, ox0, oy0, g, mood, t);
}

function drawLeaderboard(ctx, px0, py0, pw, ph, list, headlineExtra = "") {
  pillBar(ctx, px0, py0, pw, ph, C.blueDark, "#7dd3fc");
  const headH = headlineExtra ? 40 : 28;
  b(ctx, px0 + 8, py0 + 8, pw - 16, headH, "#1e40af");
  ctx.fillStyle = C.white;
  ctx.font = "bold 13px ui-monospace, monospace";
  ctx.textAlign = "center";
  if (headlineExtra) {
    ctx.fillText("当前排名", px0 + pw / 2, py0 + 22);
    ctx.font = "10px ui-monospace, monospace";
    ctx.fillStyle = "rgba(255,255,255,0.9)";
    ctx.fillText(headlineExtra + " · NAV 排序", px0 + pw / 2, py0 + 38);
  } else {
    ctx.fillText("当前排名", px0 + pw / 2, py0 + 27);
  }
  ctx.textAlign = "left";

  let ly = py0 + 8 + headH + 6;
  const rowH = 38;
  const innerW = pw - 20;
  const ix = px0 + 10;

  list.forEach((r, i) => {
    let fill = "#2d4a8f";
    let border = "#7dd3fc";
    let fg = C.white;
    let sub = "rgba(255,255,255,0.75)";
    if (i === 0) {
      fill = "#ffd743";
      border = "#f59e0b";
      fg = "#1a1003";
      sub = "rgba(0,0,0,0.55)";
    } else if (i === 1) {
      fill = "#ff9f45";
      border = "#ea580c";
      fg = "#1c0d04";
      sub = "rgba(0,0,0,0.5)";
    }
    pillBar(ctx, ix, ly, innerW, rowH, fill, border);
    ctx.fillStyle = fg;
    ctx.font = "bold 12px ui-monospace, monospace";
    ctx.fillText(`${i + 1}. ${r.stageName}`, ix + 12, ly + 22);
    ctx.fillStyle = sub;
    ctx.font = "10px ui-monospace, monospace";
    ctx.fillText((r.sub || r.id).slice(0, 16), ix + 12, ly + 34);
    ly += rowH + 6;
  });
}

function drawSkyTwinkles(ctx, W, H, t) {
  const mx = W * 0.7;
  const my = H * 0.52;
  for (let n = 0; n < 56; n++) {
    const x = (n * 131 + 19) % mx;
    const y = (n * 83 + 29) % my;
    const tw = 0.3 + 0.7 * Math.sin(t * 5.2 + n * 0.85);
    if (tw < 0.28) continue;
    b(ctx, Math.floor(x), Math.floor(y), 2, 2, `rgba(220,235,255,${0.12 + 0.38 * tw})`);
  }
}

function drawRightColumnSweep(ctx, W, H, t) {
  const x0 = W * 0.72;
  const wCol = W - x0;
  const sweep = ((t * 38) % (wCol + 80)) - 40;
  b(ctx, x0 + sweep, 0, 22, H, "rgba(255,255,255,0.045)");
}

function drawRingFloorDetail(ctx, rx, ry, rw, rh, t) {
  const ix = rx + 6;
  const iy = ry + 6;
  const iw = rw - 12;
  const ih = rh - 12;
  for (let yy = iy; yy < iy + ih; yy += 12) {
    const a = 0.05 + 0.025 * Math.sin(t * 2.1 + yy * 0.07);
    b(ctx, ix, yy, iw, 1, `rgba(30,55,90,${a})`);
  }
  for (let xx = ix + 10; xx < ix + iw - 6; xx += 28) {
    for (let yy = iy + 10; yy < iy + ih - 8; yy += 26) {
      const k = 0.5 + 0.5 * Math.sin(t * 3.4 + xx * 0.04 + yy * 0.03);
      b(ctx, xx, yy, 2, 2, `rgba(255,210,80,${0.06 * k})`);
    }
  }
}

function drawRopeSparkle(ctx, x0, y, len, thick, t) {
  for (let i = 0; i < len; i += 20) {
    const gl = 0.35 + 0.65 * Math.sin(t * 7 + i * 0.15);
    b(ctx, x0 + i + 3, y - 1, 2, thick + 1, `rgba(255,255,255,${0.18 * gl})`);
  }
}

function drawCornerVignette(ctx, W, H) {
  b(ctx, 0, 0, 44, 36, "rgba(0,0,0,0.14)");
  b(ctx, W - 44, 0, 44, 36, "rgba(0,0,0,0.14)");
  b(ctx, 0, H - 36, 48, 36, "rgba(0,0,0,0.18)");
}

/**
 * @param {object} [paintOpts]
 * @param {number} [paintOpts.wallMs] performance.now 毫秒，用于插值与决算窗口
 * @param {{ fromIds: string[], t0: number, durationMs: number } | null} [paintOpts.rankSwapAnim] 排名变化时四角位移动画
 * @param {number | null} [paintOpts.settlementUntilMs] 结束后决算表情截止时间（仅 !_live 时生效）
 */
function paintArenaProcedural(ctx, W, H, data, t, paintOpts = null) {
  drawSky(ctx, W, H);
  drawSkyTwinkles(ctx, W, H, t);
  drawRightColumnSweep(ctx, W, H, t);
  drawBunting(ctx, 10, W * 0.68, 6);
  drawBunting(ctx, 18, W * 0.66, 22);
  drawCrowdBleachers(ctx, 8, 24, Math.floor(W * 0.62), 36, 77, t);
  drawCrowdBleachers(ctx, 8, H - 46, Math.floor(W * 0.62), 40, 99, t);
  drawFloodlight(ctx, 72, 28, t);
  drawFloodlight(ctx, Math.floor(W * 0.52), 32, t);

  const rx = 44;
  const ry = 58;
  const rw = 520;
  const rh = 248;

  b(ctx, rx - 20, ry - 24, rw + 40, rh + 48, "#0c1828");
  b(ctx, rx - 12, ry - 16, rw + 24, rh + 32, "#152a45");
  b(ctx, rx - 6, ry - 8, rw + 12, rh + 16, "#1e3a5f");

  b(ctx, rx, ry, rw, rh, C.cream);
  b(ctx, rx + 4, ry + 4, rw - 8, rh - 8, "#faf8f3");
  drawRingFloorDetail(ctx, rx, ry, rw, rh, t);
  b(ctx, rx, ry, rw, 3, "#e2ddd4");
  b(ctx, rx, ry + rh - 3, rw, 3, "#d5d0c6");

  const rwT = 10;
  const ropeYOff = Math.sin(t * 2.1) * 2.2;
  drawRopeH(ctx, rx, ry - 14 + ropeYOff, rw, [C.red, C.white], rwT);
  drawRopeH(ctx, rx, ry + rh + 4 - ropeYOff, rw, ["#1565c0", C.yellow], rwT);
  drawRopeSparkle(ctx, rx, ry - 14 + ropeYOff, rw, rwT, t);
  drawRopeSparkle(ctx, rx, ry + rh + 4 - ropeYOff, rw, rwT, t + 1.2);
  drawRopeV(ctx, rx - 14, ry, rh, [C.red, C.white], rwT);
  drawRopeVDecor(ctx, rx + rw + 4, ry, rh);

  drawCornerPost(ctx, rx - 18, ry - 22);
  drawCornerPost(ctx, rx + rw - 4, ry - 22);
  drawCornerPost(ctx, rx - 18, ry + rh - 6);
  drawCornerPost(ctx, rx + rw - 4, ry + rh - 6);

  const title = "金融AI擂台赛";
  ctx.font = "bold 26px ui-monospace, monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const tx = rx + rw / 2;
  const ty = ry + rh / 2 + Math.sin(t * 1.7) * 1.4;
  const rim = 0.35 + 0.15 * Math.sin(t * 2.4);
  ctx.lineWidth = 10;
  ctx.strokeStyle = `rgba(30,58,138,${0.55 + rim * 0.2})`;
  ctx.strokeText(title, tx, ty + 2);
  ctx.lineWidth = 8;
  ctx.strokeStyle = "#1e3a8f";
  ctx.strokeText(title, tx, ty + 1);
  ctx.lineWidth = 5;
  ctx.strokeStyle = C.blueUI;
  ctx.strokeText(title, tx, ty);
  ctx.fillStyle = C.yellow;
  ctx.fillText(title, tx, ty);
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";

  const ranked = rankedSlotsForArena(data);
  const nShow = Math.min(4, Math.max(0, ranked.length));
  const g = 3;
  /** 物理四角最多 4 个槽位；上场 N 人则只在前 N 角画小人（2～4 常见） */
  const corners = [
    [rx + 22, ry + 20],
    [rx + rw - 52, ry + 20],
    [rx + 22, ry + rh - 52],
    [rx + rw - 52, ry + rh - 52],
  ].slice(0, nShow);

  const wallMs =
    paintOpts && typeof paintOpts.wallMs === "number"
      ? paintOpts.wallMs
      : typeof performance !== "undefined"
        ? performance.now()
        : 0;

  let swapAlpha = 1;
  /** @type {string[] | null} */
  let fromIds = null;
  const ra = paintOpts && paintOpts.rankSwapAnim;
  if (ra && Array.isArray(ra.fromIds) && ra.fromIds.length && typeof ra.t0 === "number" && ra.durationMs > 0) {
    const elapsed = wallMs - ra.t0;
    if (elapsed < ra.durationMs) {
      swapAlpha = easeOutCubic(elapsed / ra.durationMs);
      fromIds = ra.fromIds;
    }
  }

  const inSettlement =
    Boolean(paintOpts && paintOpts.settlementUntilMs != null && wallMs < paintOpts.settlementUntilMs) &&
    !data._live;

  let headlineExtra = "";
  if (data._live && data.rounds != null && Number(data.rounds) > 0) {
    headlineExtra = `第 ${data.rounds} 回合`;
  } else if (inSettlement) {
    headlineExtra = "已结束 · 决算";
  }

  for (let idx = 0; idx < nShow; idx++) {
    if (idx >= ranked.length) break;
    const slot = ranked[idx];
    const id = String(slot.id || "").trim();
    let cx = corners[idx][0];
    let cy = corners[idx][1];
    if (fromIds && fromIds.length === ranked.length && ranked.length === corners.length) {
      const oldI = fromIds.indexOf(id);
      if (oldI >= 0 && oldI < corners.length) {
        cx = corners[oldI][0] + (corners[idx][0] - corners[oldI][0]) * swapAlpha;
        cy = corners[oldI][1] + (corners[idx][1] - corners[oldI][1]) * swapAlpha;
      }
    }
    const bob = Math.sin(t * 3.3 + idx * 1.5) * 3.2;
    const py = cy + bob;
    const variant = variantForSlotId(id);
    let mood = "idle";
    if (inSettlement) {
      if (idx === 0) mood = "joy";
      else if (idx === 1) mood = "relax";
      else if (idx === 2) mood = "sad";
      else mood = "shake";
    }
    b(ctx, cx + 2, py + 11 * g + 1, 32, 5, "rgba(15,23,42,0.28)");
    drawChibiCorner(ctx, cx, py, g, variant, mood, t);
    ctx.fillStyle = "#0f172a";
    ctx.font = "bold 11px ui-monospace, monospace";
    ctx.fillText(slot.stageName, cx, py + 11 * g + 2);
    ctx.fillStyle = "#475569";
    ctx.font = "9px ui-monospace, monospace";
    ctx.fillText((slot.sub || slot.id).slice(0, 16), cx, py + 11 * g + 14);
  }

  const px0 = 588;
  const py0 = 42;
  const pw = 352;
  const ph = 280;
  const glow = 0.18 + 0.1 * Math.sin(t * 2.9);
  pillBar(ctx, px0 - 5, py0 - 5, pw + 10, ph + 10, `rgba(45,74,143,${glow * 0.45})`, null);
  drawLeaderboard(ctx, px0, py0, pw, ph, ranked.slice(0, 6), headlineExtra);
  drawCornerVignette(ctx, W, H);
}

/**
 * @param {HTMLCanvasElement} canvas
 * @param {object} data arena JSON
 * @param {number} [t] 秒，环境动效
 * @param {null | { wallMs?: number; rankSwapAnim?: { fromIds: string[]; t0: number; durationMs: number } | null; settlementUntilMs?: number | null }} [sceneOpts] 排名换位插值与赛后决算
 */
export function drawPixelArenaScene(canvas, data, t = 0, sceneOpts = null) {
  const ctx = canvas.getContext("2d");
  const W = canvas.width;
  const H = canvas.height;
  ctx.imageSmoothingEnabled = false;
  ctx.clearRect(0, 0, W, H);
  paintArenaProcedural(ctx, W, H, data, t, sceneOpts || {});
}

/**
 * 条形宽度：NAV 接近时若仍用 value/max 会全员顶满。
 * 先用 (v - vmin) / spread 拉开；spread 相对过小时按名次给递减比例，保证肉眼可辨。
 */
export function navBarWidthsForCanvas(ranked) {
  const vals = ranked.map((r) => Number(r.value) || 0);
  const maxv = Math.max(...vals, 1e-9);
  const minv = Math.min(...vals);
  const spread = maxv - minv;
  const relSpread = spread / maxv;
  const n = ranked.length;
  const out = [];
  if (n <= 0) return out;
  if (spread <= 1e-6 || relSpread < 0.0008) {
    const step = n > 1 ? 0.72 / (n - 1) : 0;
    for (let i = 0; i < n; i++) {
      const frac = 1.0 - i * step;
      out.push(Math.max(0.18, frac));
    }
    return out;
  }
  for (let i = 0; i < n; i++) {
    const t = (vals[i] - minv) / spread;
    const floor = 0.22;
    out.push(floor + (1 - floor) * t);
  }
  return out;
}

export function drawPixelRank(canvas, data) {
  const ctx = canvas.getContext("2d");
  const W = canvas.width;
  const H = canvas.height;
  ctx.imageSmoothingEnabled = false;
  b(ctx, 0, 0, W, H, "#0a0f1a");
  const ranked = rankedSlotsForArena(data);
  if (!ranked.length) return;
  const innerW = W - 130;
  const fracs = navBarWidthsForCanvas(ranked);
  const palette = ["#ffd743", "#ff9f45", "#5b8dfe", "#4ade80", "#c084fc", "#f472b6"];
  const barH = Math.floor((H - 32) / ranked.length);
  let y = 16;
  ranked.forEach((r, idx) => {
    const color = palette[idx % palette.length];
    const bw = Math.max(12, Math.floor((fracs[idx] || 0.5) * innerW));
    pillBar(ctx, 108, y + 2, bw, barH - 4, color, "#334155");
    ctx.fillStyle = "#fef08a";
    ctx.font = "bold 12px ui-monospace, monospace";
    ctx.fillText(`${idx + 1}. ${r.stageName}`, 10, y + barH / 2 + 2);
    ctx.fillStyle = "#94a3b8";
    ctx.font = "10px monospace";
    ctx.fillText((r.sub || r.id).slice(0, 24), 10, y + barH / 2 + 14);
    y += barH;
  });
}
