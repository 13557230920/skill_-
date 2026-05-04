/**
 * 首页「模型接入」：POST /api/add-provider，合并进 configs/arena_config.yaml。
 * 需 serve_web + 本机访问；密钥只写在 .env，通过 env_api_key 变量名引用。
 */

const API_ROOT = new URL("../api/", import.meta.url);

function apiUrl(name) {
  return new URL(String(name || "").replace(/^\//, ""), API_ROOT).href;
}

async function pingServe() {
  try {
    const r = await fetch(apiUrl("ping"), { cache: "no-store" });
    const j = await r.json();
    return r.ok && j && j.handler === "arena-serve-web";
  } catch {
    return false;
  }
}

function $(id) {
  return document.getElementById(id);
}

function syncDriverUi() {
  const drv = ($("pcDriver") && $("pcDriver").value) || "openai_compat";
  const row = $("pcBaseUrlRow");
  const inv = $("pcInvokeRow");
  if (row) row.style.display = drv === "openai_compat" ? "" : "none";
  if (inv) inv.style.display = drv === "openai_compat" ? "" : "none";
}

export async function bootProviderConnect() {
  const warn = $("providerApiWarn");
  const ok = await pingServe();
  if (!ok && warn) {
    warn.textContent =
      "未检测到 serve_web：请先在 skill 根目录运行 python scripts/serve_web.py，再用 http://127.0.0.1:8765/web/index.html 打开本页后再提交。";
  } else if (warn) {
    warn.textContent = "";
  }

  const drv = $("pcDriver");
  if (drv) drv.addEventListener("change", syncDriverUi);
  syncDriverUi();

  const form = $("formAddProvider");
  if (!form) return;

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const out = $("providerResult");
    if (!out) return;
    out.textContent = "提交中…";
    const body = {
      id: ($("pcId").value || "").trim().toLowerCase(),
      driver: ($("pcDriver").value || "").trim(),
      env_api_key: ($("pcEnvKey").value || "").trim(),
      default_model: ($("pcModel").value || "").trim(),
      base_url: ($("pcBaseUrl").value || "").trim(),
      invoke_style: ($("pcInvoke").value || "").trim(),
      openai_extra_body_json: ($("pcExtraJson").value || "").trim(),
      overwrite: $("pcOverwrite").checked,
      write_token: ($("pcWriteToken").value || "").trim(),
    };
    try {
      const r = await fetch(apiUrl("add-provider"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const text = await r.text();
      let j;
      try {
        j = JSON.parse(text);
      } catch {
        out.textContent = `HTTP ${r.status}，响应非 JSON`;
        return;
      }
      if (!j.ok) {
        out.textContent = j.error || "失败";
        return;
      }
      out.textContent = j.message || "已写入";
      out.style.color = "#7bdc7b";
    } catch (e) {
      out.textContent = String(e.message || e);
      out.style.color = "";
    }
  });
}
