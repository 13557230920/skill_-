/**
 * 擂台配置页：默认加载同目录下 `api/arena-config.json`（无 /api 请求，避免 Cursor 纯静态预览控制台 404）。
 * 人格生成仍用 `../api/suggest-*`（需 serve_web）；「从 serve_web 拉取」才请求 `/api/arena-config`。
 */

const $ = (id) => document.getElementById(id);

/** 导出区专用提示（复制 / 写回 / 下载），避免用户只看页面底部却找不到顶栏 apiHint） */
function setExportHint(msg, kind) {
  const el = $("exportHint");
  if (!el) return;
  el.textContent = msg || "";
  if (kind === "err") el.style.color = "#f85149";
  else if (kind === "ok") el.style.color = "#3fb950";
  else el.style.color = "";
}

/** 解析为与 `web/arena-setup.js` 同级的上一级目录下的 `api/`（通常为站点根 `/api/`） */
const API_ROOT = new URL("../api/", import.meta.url);

function arenaApi(endpoint) {
  const name = String(endpoint || "").replace(/^\//, "");
  return new URL(name, API_ROOT);
}

/** 与 arena-setup.js 同目录下的 api/arena-config.json（纯静态服务可读，供 Cursor 内置预览等） */
function staticArenaConfigJsonUrl() {
  return new URL("api/arena-config.json", import.meta.url).href;
}

/** true：未连上 Python serve_web，仅有静态 JSON / 内置占位（无法一键生成人格） */
let staticApiOnly = false;

/** 复制到剪贴板：说明为何网页不能自启 Python + 在 Cursor 里怎么一键跑任务 */
const SERVE_WEB_CLIPBOARD = `【为什么点了「一键生成」仍不行】
浏览器安全策略禁止网页在点击时启动你电脑上的 Python，所以没有任何网站按钮能替你执行 python scripts/serve_web.py。

【在 Cursor 里最省事的做法】
1. Ctrl+Shift+P → 输入并选择：Tasks: Run Task
2. 选与你的工作区匹配的一项：Arena: serve web (8765) [工作区=jingrong_skill 根] 或 [工作区=financial-ai-arena]
3. 保持该终端不关，用 Chrome/Edge 打开：http://127.0.0.1:8765/web/arena-setup.html
4. 点「从 serve_web 拉取最新配置」，再点「一键生成上场槽人格」

【终端手动】先 cd 到本 skill 根目录（含 configs、scripts 的 financial-ai-arena 文件夹），再执行：
python scripts/serve_web.py
`;

/** API 不可用时用于填满下拉与 4 槽占位（与 configs/arena_config.yaml 常见 id 对齐） */
const CONFIG_FALLBACK = {
  version: 1,
  providers: {
    zhipu: { driver: "zhipu", default_model: "glm-4-plus" },
    deepseek: { driver: "openai_compat", default_model: "deepseek-chat" },
    minimax: { driver: "openai_compat", default_model: "MiniMax-M2.7" },
    mimo: { driver: "openai_compat", default_model: "mimo-v2.5-pro" },
  },
  contestants: [],
};

/** @type {{ version: number, providers: Record<string, {driver: string, default_model: string}>, contestants: Array<{id: string, provider: string, display: string, model?: string|null, persona: string}> }} */
let serverConfig = { ...CONFIG_FALLBACK, contestants: [] };

/** @type {Array<{ id: string, provider: string, model: string, display: string, persona: string }>} */
let slots = [];

let activeCount = 3;

function providerIds() {
  return Object.keys(serverConfig.providers || {}).sort();
}

function defaultModel(pid) {
  const p = serverConfig.providers[pid];
  return (p && p.default_model) || "";
}

function escapeYamlScalar(s) {
  const t = String(s ?? "");
  if (!t) return '""';
  if (/[\n:#\[\]{}@`|&*!]/.test(t) || t !== t.trim()) {
    return '"' + t.replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"';
  }
  return t;
}

function slotToYamlBlock(s) {
  const lines = [];
  lines.push(`  - id: ${s.id.trim() || "unnamed"}`);
  lines.push(`    provider: ${s.provider}`);
  lines.push(`    display: ${escapeYamlScalar(s.display)}`);
  if (s.model && String(s.model).trim()) {
    lines.push(`    model: ${String(s.model).trim()}`);
  }
  const persona = String(s.persona || "");
  if (persona.includes("\n") || persona.length > 72) {
    lines.push("    persona: |");
    for (const pl of persona.split("\n")) {
      lines.push(`      ${pl}`);
    }
  } else {
    lines.push(`    persona: ${escapeYamlScalar(persona)}`);
  }
  lines.push(`    system_extra: ""`);
  return lines.join("\n");
}

function buildExportYaml() {
  ensureFourSlots();
  const parts = ["contestants:"];
  for (let i = 0; i < activeCount; i++) {
    parts.push(slotToYamlBlock(slots[i]));
  }
  return parts.join("\n") + "\n";
}

function buildCliCommand() {
  ensureFourSlots();
  const ids = [];
  for (let i = 0; i < activeCount; i++) {
    const id = slots[i].id.trim();
    if (!id) {
      return { ok: false, msg: `第 ${i + 1} 槽 id 为空，请填写英文槽位 id（如 ds_aggressive）` };
    }
    ids.push(id);
  }
  const line = `python scripts/arena_run.py --mode sim --contestants ${ids.join(",")} --duration 60`;
  return { ok: true, line };
}

/** 保证 slots 恒为 4 项，避免在 loadConfig 完成前切换上场人数导致崩溃 */
function ensureFourSlots() {
  if (Array.isArray(slots) && slots.length === 4 && slots.every(Boolean)) {
    return;
  }
  initSlotsFromConfig();
}

function initSlotsFromConfig() {
  const ids = providerIds();
  const firstP = ids[0] || "deepseek";
  slots = [0, 1, 2, 3].map((i) => {
    const tmpl = serverConfig.contestants[i];
    if (tmpl) {
      return {
        id: tmpl.id,
        provider: tmpl.provider || firstP,
        model: tmpl.model || "",
        display: tmpl.display || tmpl.id,
        persona: tmpl.persona || "",
      };
    }
    return {
      id: `fighter_${i + 1}`,
      provider: firstP,
      model: "",
      display: `选手 ${i + 1}`,
      persona: "",
    };
  });
}

function renderSlots() {
  ensureFourSlots();
  const host = $("slotsHost");
  host.innerHTML = "";
  for (let i = 0; i < 4; i++) {
    const disabled = i >= activeCount;
    const s = slots[i];
    const card = document.createElement("div");
    card.className = "setup-slot" + (disabled ? " setup-slot--off" : "");
    card.dataset.slot = String(i);

    const pidOpts = providerIds()
      .map(
        (pid) =>
          `<option value="${escapeAttr(pid)}" ${s.provider === pid ? "selected" : ""}>${escapeAttr(pid)} (${escapeAttr(
            defaultModel(pid)
          )})</option>`
      )
      .join("");

    const tmplOpts = [
      '<option value="">— 从现有配置复制 —</option>',
      ...(serverConfig.contestants || []).map(
        (c) => `<option value="${escapeAttr(c.id)}">${escapeAttr(c.id)} · ${escapeAttr(c.display)}</option>`
      ),
    ].join("");

    card.innerHTML = `
      <div class="setup-slot-head">
        <span class="tag">槽位 ${i + 1}</span>
        ${disabled ? '<span class="sub" style="margin:0">未上场</span>' : ""}
      </div>
      <div class="field-row">
        <label>provider</label>
        <select class="inp setup-prov" data-k="provider" ${disabled ? "disabled" : ""}>${pidOpts}</select>
      </div>
      <div class="field-row">
        <label>模型覆盖</label>
        <input type="text" class="inp setup-model" data-k="model" placeholder="留空则用 provider 默认" value="${escapeAttr(
          s.model || ""
        )}" ${disabled ? "disabled" : ""} />
      </div>
      <div class="field-row">
        <label>槽位 id</label>
        <input type="text" class="inp setup-id" data-k="id" value="${escapeAttr(s.id)}" ${disabled ? "disabled" : ""} />
      </div>
      <div class="field-row">
        <label>显示名</label>
        <input type="text" class="inp setup-display" data-k="display" value="${escapeAttr(s.display)}" ${
      disabled ? "disabled" : ""
    } />
      </div>
      <div class="field-row field-row--grow">
        <label>人格 persona</label>
        <textarea class="inp setup-persona" data-k="persona" rows="5" ${disabled ? "disabled" : ""}></textarea>
      </div>
      <div class="field-row setup-actions">
        <select class="inp setup-tmpl" ${disabled ? "disabled" : ""}>${tmplOpts}</select>
        <button type="button" class="btn setup-apply-tmpl" data-slot="${i}" ${disabled ? "disabled" : ""}>复制到本槽</button>
        <button type="button" class="btn btn-primary setup-gen-one" data-slot="${i}" ${disabled ? "disabled" : ""}>仅生成此槽</button>
      </div>
    `;
    host.appendChild(card);
    card.querySelector(".setup-persona").value = s.persona;
  }

  host.querySelectorAll(".setup-prov").forEach((sel) => {
    sel.addEventListener("change", (ev) => {
      const idx = slotIndexFromEl(/** @type {HTMLElement} */ (ev.target));
      if (idx < 0) return;
      slots[idx].provider = /** @type {HTMLSelectElement} */ (ev.target).value;
    });
  });
  ["model", "id", "display", "persona"].forEach((k) => {
    host.querySelectorAll(`[data-k="${k}"]`).forEach((inp) => {
      inp.addEventListener("input", (ev) => {
        const idx = slotIndexFromEl(/** @type {HTMLElement} */ (ev.target));
        if (idx < 0) return;
        slots[idx][k] = /** @type {HTMLInputElement | HTMLTextAreaElement} */ (ev.target).value;
        refreshPreview();
      });
    });
  });
  host.querySelectorAll(".setup-apply-tmpl").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      const slot = Number(/** @type {HTMLElement} */ (ev.target).closest("[data-slot]")?.getAttribute("data-slot"));
      const sel = /** @type {HTMLSelectElement} */ (
        /** @type {HTMLElement} */ (ev.target).closest(".setup-slot")?.querySelector(".setup-tmpl")
      );
      const tid = sel && sel.value;
      if (!tid) return;
      const c = serverConfig.contestants.find((x) => x.id === tid);
      if (!c) return;
      slots[slot] = {
        id: c.id,
        provider: c.provider,
        model: c.model || "",
        display: c.display,
        persona: c.persona || "",
      };
      renderSlots();
      refreshPreview();
    });
  });
  host.querySelectorAll(".setup-gen-one").forEach((btn) => {
    btn.addEventListener("click", () => genOneSlot(Number(btn.getAttribute("data-slot"))));
  });
}

function slotIndexFromEl(el) {
  const card = el.closest(".setup-slot");
  if (!card) return -1;
  return Number(card.getAttribute("data-slot"));
}

function escapeAttr(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}

function refreshPreview() {
  $("yamlOut").value = buildExportYaml();
  const cmd = buildCliCommand();
  $("cliOut").value = cmd.ok ? cmd.line : cmd.msg;
}

async function fetchConfigJson(url) {
  const res = await fetch(url, { cache: "no-store" });
  const text = await res.text();
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    parsed = { ok: false };
  }
  return { res, parsed };
}

function applyLoadedConfig(j, opts) {
  const { staticSnapshot, fromLive } = opts || {};
  serverConfig = j.config;
  const nProv = Object.keys(serverConfig.providers || {}).length;
  const nCon = (serverConfig.contestants || []).length;
  if (fromLive) {
    $("cfgStatus").textContent = `已从动态接口加载（${nProv} 个 providers，${nCon} 条 contestants 模板）。可「一键生成」人格。`;
  } else if (staticSnapshot) {
    $("cfgStatus").textContent =
      `已加载静态 **api/arena-config.json**（${nProv} 个 providers，${nCon} 条模板）。默认**不请求** \`/api/arena-config\`，避免 Cursor 等纯静态预览在控制台报 404。` +
      "一键生成需 Python：请运行 **`python scripts/serve_web.py`** 后点下方 **「从 serve_web 拉取最新配置」**（或系统浏览器打开同一页）。";
  } else {
    $("cfgStatus").textContent = `已加载配置（${nProv} 个 providers，${nCon} 条模板）。`;
  }
  initSlotsFromConfig();
  renderWriterSelect();
  renderSlots();
  refreshPreview();
}

/** 默认先读静态 JSON，不向 /api/arena-config 发请求，避免 Simple Browser 控制台 404。 */
async function loadConfig() {
  staticApiOnly = true;
  const liveUrl = arenaApi("arena-config").href;
  const snapUrl = staticArenaConfigJsonUrl();
  $("cfgStatus").textContent = "正在加载配置…";

  let j;
  try {
    const r = await fetchConfigJson(snapUrl);
    if (r.res.ok && r.parsed.ok) {
      j = r.parsed;
      staticApiOnly = true;
    } else {
      throw new Error("no static");
    }
  } catch {
    try {
      const r = await fetchConfigJson(liveUrl);
      if (r.res.ok && r.parsed.ok) {
        j = r.parsed;
        staticApiOnly = false;
      } else {
        throw new Error("no live");
      }
    } catch {
      $("cfgStatus").textContent =
        "缺少 **web/api/arena-config.json** 且无法访问动态接口。已使用内置占位。请运行 **`python scripts/serve_web.py`** 或补全静态 JSON。";
      serverConfig = { ...CONFIG_FALLBACK, contestants: [] };
      staticApiOnly = true;
      initSlotsFromConfig();
      renderWriterSelect();
      renderSlots();
      refreshPreview();
      return;
    }
  }

  applyLoadedConfig(j, { staticSnapshot: staticApiOnly, fromLive: !staticApiOnly });
}

/** 用户主动连接 serve_web 时再请求 /api/arena-config（此时控制台若 404 说明未启动 serve_web）。 */
async function pullLiveConfigFromServeWeb() {
  const btn = $("btnLiveCfg");
  if (btn) btn.disabled = true;
  $("apiHint").textContent = "正在请求动态接口…";
  try {
    const r = await fetchConfigJson(arenaApi("arena-config").href);
    if (!r.res.ok || !r.parsed.ok) {
      $("apiHint").textContent =
        "动态接口不可用（HTTP " +
        r.res.status +
        "）。请确认已在 skill 根目录运行 **`python scripts/serve_web.py`**，且控制台出现 ArenaDevHTTPRequestHandler。";
      return;
    }
    staticApiOnly = false;
    applyLoadedConfig(r.parsed, { fromLive: true });
    $("apiHint").textContent = "已切换到动态配置，可一键生成人格。";
  } catch (e) {
    $("apiHint").textContent = String(e.message || e);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function renderWriterSelect() {
  const sel = $("writerSel");
  const ids = providerIds();
  if (!ids.length) {
    sel.innerHTML = '<option value="">（无 provider，请检查配置）</option>';
    return;
  }
  sel.innerHTML = ids.map((id) => `<option value="${escapeAttr(id)}">${escapeAttr(id)}</option>`).join("");
  if (ids.includes("deepseek")) sel.value = "deepseek";
  else sel.value = ids[0];
}

function activeWriter() {
  const v = ($("writerSel").value || "").trim();
  if (v) return v;
  const ids = providerIds();
  return ids[0] || "deepseek";
}

function activeTopic() {
  return $("topicInp").value.trim() || "A股纸交易模拟擂台：多回合买卖 hold，控制回撤";
}

/** 人格接口：统一用 GET + query（相对 API_ROOT）。 */
async function fetchSuggestApi(endpoint, payload) {
  const u = arenaApi(endpoint);
  for (const [k, v] of Object.entries(payload)) {
    if (v === undefined || v === null) continue;
    if (k === "providers" && Array.isArray(v)) {
      u.searchParams.set("providers", v.join(","));
      continue;
    }
    if (k === "avoid_brief" && typeof v === "string") {
      u.searchParams.set(k, v.slice(0, 2500));
      continue;
    }
    u.searchParams.set(k, String(v));
  }
  const res = await fetch(u.toString(), { method: "GET", cache: "no-store" });
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    let hint = `HTTP ${res.status}，响应非 JSON。API 基址 ${API_ROOT.href}`;
    if (res.status === 404) {
      hint +=
        "。若为 **Cursor 内置浏览器**，请改用 **`python scripts/serve_web.py`** 后用 **系统浏览器** 打开同一页；静态预览无法提供 /api/*。";
    }
    return { ok: false, error: hint };
  }
}

function avoidBriefForSlot(excludeIdx) {
  ensureFourSlots();
  const bits = [];
  for (let i = 0; i < activeCount; i++) {
    if (i === excludeIdx) continue;
    const p = slots[i].persona.trim();
    if (p) bits.push(p.slice(0, 400));
  }
  return bits.join("\n---\n");
}

async function genOneSlot(slotIdx) {
  ensureFourSlots();
  if (slotIdx < 0 || slotIdx >= activeCount) return;
  if (staticApiOnly) {
    $("apiHint").textContent =
      "当前未连上后端：网页**不能**自动启动 Python。请先在 Cursor 运行任务 **Arena: serve web (8765)**（或点「复制启动说明」），再用系统浏览器打开本页并点「从 serve_web 拉取最新配置」。也可手填人格后导出 YAML。";
    return;
  }
  const btn = document.querySelector(`.setup-gen-one[data-slot="${slotIdx}"]`);
  const prev = btn?.textContent;
  if (btn) {
    btn.disabled = true;
    btn.textContent = "生成中…";
  }
  $("apiHint").textContent = "";
  try {
    const j = await fetchSuggestApi("suggest-one", {
      writer: activeWriter(),
      topic: activeTopic(),
      provider: slots[slotIdx].provider,
      id_hint: slots[slotIdx].id,
      display_hint: slots[slotIdx].display,
      avoid_brief: avoidBriefForSlot(slotIdx),
    });
    if (!j.ok) {
      $("apiHint").textContent = j.error || "请求失败";
      return;
    }
    if (j.parse_error && (!j.item || Object.keys(j.item).length === 0)) {
      $("apiHint").textContent = "模型已返回但 YAML 未解析成功，请查看下方原始输出并手工粘贴。";
      $("rawOut").value = j.raw || "";
      $("rawPanel").hidden = false;
      return;
    }
    const it = j.item || (j.items && j.items[0]);
    if (it) {
      slots[slotIdx] = {
        id: String(it.id || slots[slotIdx].id).trim(),
        provider: String(it.provider || slots[slotIdx].provider).trim(),
        model: slots[slotIdx].model,
        display: String(it.display || "").trim(),
        persona: String(it.persona || "").trim(),
      };
      renderSlots();
      refreshPreview();
    }
    $("apiHint").textContent = j.parse_error ? "已应用首条；解析提示：" + j.parse_error : "已写入本槽。";
    if (j.raw) {
      $("rawOut").value = j.raw;
      $("rawPanel").hidden = false;
    }
  } catch (e) {
    $("apiHint").textContent = String(e.message || e);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = prev || "仅生成此槽";
    }
  }
}

async function genBatch() {
  ensureFourSlots();
  if (staticApiOnly) {
    $("apiHint").textContent =
      "当前未连上后端：网页**不能**自动启动 Python。请先在 Cursor 运行任务 **Arena: serve web (8765)**（或点「复制启动说明」），再用系统浏览器打开本页并点「从 serve_web 拉取最新配置」。也可手填人格后导出 YAML。";
    return;
  }
  const btn = $("btnBatch");
  btn.disabled = true;
  btn.textContent = "批量生成中…";
  $("apiHint").textContent = "";
  try {
    const providers = [];
    for (let i = 0; i < activeCount; i++) providers.push(slots[i].provider);
    const j = await fetchSuggestApi("suggest-personas", {
      writer: activeWriter(),
      slots: activeCount,
      topic: activeTopic(),
      providers,
    });
    if (!j.ok) {
      $("apiHint").textContent = j.error || "请求失败";
      return;
    }
    if (j.raw) {
      $("rawOut").value = j.raw;
      $("rawPanel").hidden = false;
    }
    const items = j.items || [];
    if (!items.length) {
      $("apiHint").textContent = j.parse_error || "未解析到 contestants_gen，请从原始输出手工处理";
      return;
    }
    for (let i = 0; i < activeCount && i < items.length; i++) {
      const it = items[i];
      slots[i] = {
        id: String(it.id || slots[i].id).trim(),
        provider: String(it.provider || slots[i].provider).trim(),
        model: slots[i].model,
        display: String(it.display || "").trim(),
        persona: String(it.persona || "").trim(),
      };
    }
    renderSlots();
    refreshPreview();
    $("apiHint").textContent = j.parse_error
      ? "已按顺序写入；解析提示：" + j.parse_error
      : `已写入前 ${Math.min(activeCount, items.length)} 个上场槽。`;
  } catch (e) {
    $("apiHint").textContent = String(e.message || e);
  } finally {
    btn.disabled = false;
    btn.textContent = "一键生成上场槽人格";
  }
}

function downloadYaml() {
  setExportHint("正在触发浏览器下载…", "ok");
  const blob = new Blob([buildExportYaml()], { type: "text/yaml;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "arena-contestants-snippet.yaml";
  a.click();
  URL.revokeObjectURL(a.href);
  setTimeout(() => setExportHint("若未出现下载，请检查浏览器是否拦截了下载。", "ok"), 400);
}

function copyCliLineFallback(line) {
  const ta = $("cliOut");
  if (!ta) return false;
  const prevReadonly = ta.readOnly;
  ta.readOnly = false;
  ta.focus();
  ta.select();
  ta.setSelectionRange(0, line.length);
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  ta.readOnly = prevReadonly;
  ta.blur();
  window.getSelection()?.removeAllRanges();
  return ok;
}

function copyCli() {
  refreshPreview();
  const cmd = buildCliCommand();
  if (!cmd.ok) {
    setExportHint(cmd.msg, "err");
    return;
  }
  const line = cmd.line;
  if (!navigator.clipboard || !navigator.clipboard.writeText) {
    if (copyCliLineFallback(line)) setExportHint("已复制命令到剪贴板（备用方式）。", "ok");
    else setExportHint("无法访问剪贴板：请在「推荐命令」框内全选 (Ctrl+A) 后复制 (Ctrl+C)。", "err");
    return;
  }
  navigator.clipboard
    .writeText(line)
    .then(
      () => setExportHint("已复制命令到剪贴板。", "ok"),
      () => {
        if (copyCliLineFallback(line)) setExportHint("已复制命令（备用方式）。", "ok");
        else setExportHint("复制失败：请在「推荐命令」框内全选后手动 Ctrl+C。", "err");
      }
    )
    .catch(() => {
      if (copyCliLineFallback(line)) setExportHint("已复制命令（备用方式）。", "ok");
      else setExportHint("复制失败：请在「推荐命令」框内全选后手动 Ctrl+C。", "err");
    });
}

async function writeConfigToDisk() {
  refreshPreview();
  if (staticApiOnly) {
    setExportHint(
      "未连上后端：请先「启动后端」并点「从 serve_web 拉取最新配置」，再写回磁盘。",
      "err"
    );
    return;
  }
  const cmd = buildCliCommand();
  if (!cmd.ok) {
    setExportHint(cmd.msg, "err");
    return;
  }
  const yaml = buildExportYaml();
  const tokEl = $("writeTokenInp");
  const write_token = tokEl ? String(tokEl.value || "").trim() : "";
  const btn = $("btnWriteCfg");
  const prev = btn?.textContent;
  if (btn) {
    btn.disabled = true;
    btn.textContent = "写入中…";
  }
  setExportHint("正在请求写回接口…", null);
  try {
    const u = arenaApi("write-contestants").toString();
    const res = await fetch(u, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contestants_yaml: yaml, write_token }),
    });
    const text = await res.text();
    let j;
    try {
      j = JSON.parse(text);
    } catch {
      setExportHint(`HTTP ${res.status}，响应非 JSON（后端是否为最新 serve_web？请重启后再试）`, "err");
      return;
    }
    if (!j.ok) {
      setExportHint(j.error || "写入失败", "err");
      return;
    }
    const okMsg = j.message || "已写入配置文件。";
    try {
      const r = await fetchConfigJson(arenaApi("arena-config").href);
      if (r.res.ok && r.parsed.ok) {
        staticApiOnly = false;
        applyLoadedConfig(r.parsed, { fromLive: true });
        setExportHint(okMsg + " 表单已同步。", "ok");
      } else {
        setExportHint(okMsg + " 请手动点「从 serve_web 拉取最新配置」刷新表单。", "ok");
      }
    } catch {
      setExportHint(okMsg + " 请手动点「从 serve_web 拉取最新配置」刷新表单。", "ok");
    }
  } catch (e) {
    setExportHint(String(e.message || e), "err");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = prev || "写回 configs/arena_config.yaml";
    }
  }
}

function bindGlobals() {
  document.querySelectorAll('input[name="activeCount"]').forEach((r) => {
    r.addEventListener("change", () => {
      activeCount = Number(r.value);
      renderSlots();
      refreshPreview();
    });
  });
  $("btnBatch").addEventListener("click", genBatch);
  $("btnDl").addEventListener("click", downloadYaml);
  $("btnCopyCli").addEventListener("click", copyCli);
  const wbtn = $("btnWriteCfg");
  if (wbtn) wbtn.addEventListener("click", () => writeConfigToDisk());
  $("topicInp").addEventListener("input", () => {});
  const liveBtn = $("btnLiveCfg");
  if (liveBtn) liveBtn.addEventListener("click", () => pullLiveConfigFromServeWeb());
  const copyServe = $("btnCopyServeCmd");
  if (copyServe) {
    copyServe.addEventListener("click", () => {
      navigator.clipboard.writeText(SERVE_WEB_CLIPBOARD).then(
        () => {
          $("apiHint").textContent = "已复制启动说明到剪贴板；按其中步骤在 Cursor 里运行任务或终端命令。";
        },
        () => {
          $("apiHint").textContent = "复制失败，请手动全选保存的说明文本。";
        }
      );
    });
  }
}

export async function bootArenaSetup() {
  initSlotsFromConfig();
  renderWriterSelect();
  renderSlots();
  refreshPreview();
  bindGlobals();
  const r = document.querySelector(`input[name="activeCount"][value="${String(activeCount)}"]`);
  if (r) r.checked = true;
  try {
    await loadConfig();
  } catch (e) {
    $("cfgStatus").textContent =
      "请求异常（是否已在本机运行 python scripts/serve_web.py？）。错误：" + String(e.message || e);
    serverConfig = { ...CONFIG_FALLBACK, contestants: [] };
    initSlotsFromConfig();
    renderWriterSelect();
    renderSlots();
    refreshPreview();
  }
}
