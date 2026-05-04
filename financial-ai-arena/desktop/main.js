const { app, BrowserWindow, ipcMain, shell } = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const http = require("http");

const PORT = 8765;
const BASE = `http://127.0.0.1:${PORT}`;
const SKILL_ROOT = path.join(__dirname, "..");

/** @type {import('child_process').ChildProcess | null} */
let pyChild = null;
/** @type {Promise<unknown>} */
let startQueue = Promise.resolve();

function pythonCmd() {
  const v = process.env.ARENA_PYTHON;
  if (v && String(v).trim()) return String(v).trim();
  return process.platform === "win32" ? "python" : "python3";
}

function httpPing() {
  return new Promise((resolve) => {
    const req = http.get(
      `${BASE}/api/ping`,
      { timeout: 1200 },
      (res) => {
        let data = "";
        res.on("data", (c) => {
          data += c;
        });
        res.on("end", () => {
          try {
            const j = JSON.parse(data);
            const hasAdvisor =
              j &&
              j.features &&
              (j.features.advisor_api === true || j.features.advisor_api === "true");
            resolve(
              res.statusCode === 200 &&
                j &&
                j.handler === "arena-serve-web" &&
                hasAdvisor
            );
          } catch {
            resolve(false);
          }
        });
      }
    );
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

function waitForBackend(msTotal = 25000) {
  const deadline = Date.now() + msTotal;
  return new Promise((resolve) => {
    const tick = async () => {
      if (await httpPing()) resolve(true);
      else if (Date.now() > deadline) resolve(false);
      else setTimeout(tick, 350);
    };
    tick();
  });
}

function killPyTree() {
  if (!pyChild || pyChild.killed) return;
  const pid = pyChild.pid;
  if (process.platform === "win32" && pid) {
    try {
      spawn("taskkill", ["/PID", String(pid), "/T", "/F"], {
        windowsHide: true,
        stdio: "ignore",
      });
    } catch {
      pyChild.kill();
    }
  } else {
    try {
      pyChild.kill("SIGTERM");
    } catch {
      /* ignore */
    }
  }
  pyChild = null;
}

function broadcast(channel, payload) {
  const w = BrowserWindow.getAllWindows()[0];
  if (w && !w.isDestroyed()) w.webContents.send(channel, payload);
}

async function doStartBackend() {
  if (await httpPing()) {
    return {
      ok: true,
      reused: true,
      message:
        "8765 上已是带 advisor API 的擂台后端，直接使用。若建议页仍异常，请点「停止后端」后在本机任务管理器结束其它占用 8765 的 python，再点「启动后端」。",
    };
  }

  const cmd = pythonCmd();
  let stderrBuf = "";
  try {
    pyChild = spawn(cmd, ["scripts/serve_web.py"], {
      cwd: SKILL_ROOT,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env },
    });
  } catch (e) {
    return { ok: false, error: `无法 spawn：${e.message || e}` };
  }

  pyChild.stderr?.on("data", (d) => {
    stderrBuf += d.toString();
    if (stderrBuf.length > 12000) stderrBuf = stderrBuf.slice(-8000);
  });
  pyChild.on("error", (err) => {
    stderrBuf += `\nspawn error: ${err.message || err}`;
  });
  pyChild.on("exit", (code) => {
    pyChild = null;
    broadcast("backend:event", { type: "exited", code });
  });

  const ok = await waitForBackend(28000);
  if (!ok) {
    killPyTree();
    const tail = stderrBuf ? `\n\nPython stderr（尾部）：\n${stderrBuf.slice(-1200)}` : "";
    return {
      ok: false,
      error:
        `在约 28 秒内未收到 /api/ping。请确认本 skill 已 pip install -r requirements.txt，且命令「${cmd}」在 PATH 中。` +
        tail,
    };
  }
  broadcast("backend:event", { type: "ready" });
  return { ok: true, message: "后端已启动。" };
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1320,
    height: 880,
    minWidth: 900,
    minHeight: 600,
    title: "金融 AI 擂台 · 桌面壳",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      // 主文档为 file://，iframe 指向 http://127.0.0.1；仅本机桌面壳使用
      webSecurity: false,
    },
  });
  win.loadFile(path.join(__dirname, "shell.html"));
}

app.whenReady().then(() => {
  ipcMain.handle("backend:ping", () => httpPing());

  ipcMain.handle("backend:status", async () => ({
    listening: await httpPing(),
    base: BASE,
    skillRoot: SKILL_ROOT,
    managed: !!(pyChild && !pyChild.killed),
  }));

  ipcMain.handle("backend:start", async () => {
    const task = startQueue.then(() => doStartBackend());
    startQueue = task.catch(() => {});
    return task;
  });

  ipcMain.handle("backend:stop", async () => {
    if (!pyChild || pyChild.killed) {
      return { ok: true, message: "当前没有由本窗口启动的 Python 进程（端口上可能仍有其它实例）。" };
    }
    await new Promise((resolve) => {
      const c = pyChild;
      if (!c) return resolve();
      c.once("exit", () => resolve());
      killPyTree();
      setTimeout(resolve, 2000);
    });
    return { ok: true, message: "已尝试结束本应用启动的后端进程。" };
  });

  ipcMain.handle("shell:open-external", (_e, url) => {
    const u = String(url || "").trim() || `${BASE}/web/arena-setup.html`;
    return shell.openExternal(u);
  });

  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  killPyTree();
  if (process.platform !== "darwin") app.quit();
});
