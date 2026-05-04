@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Arena serve_web 8765
echo.
echo 启动本地擂台后端: http://127.0.0.1:8765
echo 关闭本窗口即停止服务。用浏览器打开 web\arena-setup.html 或上述地址。
echo.
python scripts/serve_web.py
if errorlevel 1 (
  echo.
  echo 若提示找不到 python，请先安装 Python 并加入 PATH，或用 Cursor 任务 Arena: serve web ^(8765^)。
  pause
)
