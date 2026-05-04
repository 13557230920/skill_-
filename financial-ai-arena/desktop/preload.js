const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("arenaShell", {
  ping: () => ipcRenderer.invoke("backend:ping"),
  start: () => ipcRenderer.invoke("backend:start"),
  stop: () => ipcRenderer.invoke("backend:stop"),
  status: () => ipcRenderer.invoke("backend:status"),
  openExternal: (url) => ipcRenderer.invoke("shell:open-external", url),
  onBackendEvent: (fn) => {
    const listener = (_e, payload) => fn(payload);
    ipcRenderer.on("backend:event", listener);
    return () => ipcRenderer.removeListener("backend:event", listener);
  },
});
