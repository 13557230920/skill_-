@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "node_modules\electron\" (
  echo 首次运行：正在 npm install，请稍候…
  call npm install
  if errorlevel 1 (
    echo npm install 失败。请确认已安装 Node.js 并加入 PATH。
    pause
    exit /b 1
  )
)
call npm start
