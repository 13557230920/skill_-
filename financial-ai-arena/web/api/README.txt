arena-config.json
-----------------
供「仅静态文件」的预览（例如 Cursor 内置 Simple Browser、python -m http.server）加载擂台配置：
与 GET /api/arena-config 返回结构相同（{ "ok": true, "config": { ... } }）。

更新方式（可选）：在 skill 根目录执行
  python -c "import json,sys; from pathlib import Path; sys.path.insert(0,'scripts'); from persona_api import public_config_snapshot, DEFAULT_CONFIG; d=public_config_snapshot(DEFAULT_CONFIG); d.pop('config_path',None); Path('web/api/arena-config.json').write_text(json.dumps({'ok':True,'config':d},ensure_ascii=False,indent=2),encoding='utf-8')"

人格「一键生成」仍须运行 scripts/serve_web.py（Python 提供 /api/suggest-*）。
