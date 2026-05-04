金融 AI 擂台 — Electron 桌面壳（一键起后端 + 内嵌网页）

【一次性】在本目录执行：
  npm install

【每次使用】
  npm start
  或在资源管理器中双击本目录下的 start_desktop.bat（首次会自动 npm install）

窗口顶部可：
  · 启动后端 — 在本机启动 python scripts/serve_web.py（工作目录为上一级 skill 根）
  · 停止后端 — 仅结束「由本窗口启动」的进程；若你在别处开的 serve_web，请在那边关
  · 勾选「打开时自动启动后端」— 偏好保存在本机 localStorage

若 Python 不在 PATH，可在启动 Electron 前设置环境变量 ARENA_PYTHON（完整路径，如 C:\Python311\python.exe）。

依赖与密钥仍与 skill 一致：上一级目录 pip install -r requirements.txt，.env 放在 skill 根或仓库根（见 SKILL.md）。
