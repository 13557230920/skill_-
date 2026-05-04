/* global arenaShell */
const $ = (id) => document.getElementById(id);

const SETUP_URL = "http://127.0.0.1:8765/web/arena-setup.html";

function setHint(text, show) {
  const el = $("hint");
  el.textContent = text || "";
  el.classList.toggle("show", !!show);
}

function setStatus(text, kind) {
  const el = $("status");
  el.textContent = text;
  el.classList.remove("ok", "err");
  if (kind === "ok") el.classList.add("ok");
  if (kind === "err") el.classList.add("err");
}

async function refreshFrame() {
  const f = $("frame");
  const on = await arenaShell.ping();
  if (on) {
    f.src = SETUP_URL;
    setStatus("后端在线 · 已加载擂台配置页", "ok");
    $("btnStart").disabled = true;
  } else {
    f.src = "about:blank";
    setStatus("后端未就绪 · 请点击「启动后端」", "err");
    $("btnStart").disabled = false;
  }
}

async function doStart() {
  setHint("", false);
  $("btnStart").disabled = true;
  setStatus("正在启动 Python …", null);
  const r = await arenaShell.start();
  if (r && r.ok) {
    setStatus(r.reused ? "已连接（复用已有进程）" : "后端已启动", "ok");
    $("frame").src = SETUP_URL;
    if (r.message) setHint(r.message, true);
    setTimeout(() => setHint("", false), 4000);
  } else {
    setStatus("启动失败", "err");
    setHint((r && r.error) || "未知错误", true);
    $("btnStart").disabled = false;
  }
}

async function doStop() {
  setHint("", false);
  const r = await arenaShell.stop();
  setHint(r.message || "", !!r.message);
  setTimeout(() => setHint("", false), 5000);
  await refreshFrame();
}

document.addEventListener("DOMContentLoaded", async () => {
  const autostart = $("autostart");
  try {
    autostart.checked = localStorage.getItem("arenaDesktopAutostart") === "1";
  } catch {
    /* ignore */
  }

  autostart.addEventListener("change", () => {
    try {
      localStorage.setItem("arenaDesktopAutostart", autostart.checked ? "1" : "0");
    } catch {
      /* ignore */
    }
  });

  $("btnStart").addEventListener("click", () => doStart());
  $("btnStop").addEventListener("click", () => doStop());
  $("btnReload").addEventListener("click", () => refreshFrame());
  $("btnBrowser").addEventListener("click", () => arenaShell.openExternal(SETUP_URL));

  arenaShell.onBackendEvent((ev) => {
    if (ev && ev.type === "exited") {
      setStatus("后端进程已退出", "err");
      $("btnStart").disabled = false;
      refreshFrame();
    }
    if (ev && ev.type === "ready") {
      refreshFrame();
    }
  });

  await refreshFrame();

  if (autostart.checked && !(await arenaShell.ping())) {
    await doStart();
  }
});
