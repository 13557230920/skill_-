---
name: financial-ai-arena
version: 0.3.0
description: >-
  金融 AI 擂台赛：YAML 可扩展 providers + 多人格槽位；含 web 前端「擂台竞技页」「真实金融建议页」、arena_state.json 驱动 Canvas、
  arena_report.html 导出、real 模式提纲；密钥仅环境变量。并列 financial-analysis、jrj-quote、tushare、multi-search-engine、self-improving、moltpixel。
---

# 金融 AI 擂台赛（Financial AI Arena）

像素风「擂台」用于 **模拟模式** 的可视化；**真实分析/决策对话** 由 **前端建议页** 组织权重与各槽位要点备忘，并由宿主 Agent 结合 MCP/行情 skill 完成推理（非投资建议）。

## 前端展示（推荐）

在 **skill 根目录** 启动静态服务（勿用 `file://` 打开，否则无法 `fetch` JSON）：

```bash
cd financial-ai-arena
python scripts/serve_web.py
```

**一键起后端 + 内嵌配置页（Electron）**：进入 `financial-ai-arena/desktop/`，执行 `npm install` 后 `npm start`，或双击 `desktop/start_desktop.bat`。窗口工具栏可启动/停止由本进程拉起的 `serve_web.py`（详见该目录 `README.txt`）。

浏览器访问：

| 页面 | URL |
|------|-----|
| 入口 | http://127.0.0.1:8765/web/index.html（含 **模型接入**：向 `arena_config.yaml` 合并自定义 `providers`，配置页拉取后即可选用） |
| **擂台配置** | http://127.0.0.1:8765/web/arena-setup.html（选 2～4 上场槽、每人 provider/模型、一键或单槽生成人格；**`serve_web.py`** 提供 `GET /api/*` 与生成接口；**本机**可点「写回 configs/arena_config.yaml」经 `POST /api/write-contestants` 合并 contestants，会先备份 `arena_config.yaml.bak`。仅静态预览时自动读 **`web/api/arena-config.json`** 填表，**Cursor 内置浏览器**无法调大模型，请用系统浏览器 + `serve_web.py` 做「一键生成」） |
| **擂台竞技** | http://127.0.0.1:8765/web/arena.html（**全程序像素**擂台 + 读 `arena_state.json`；在 **serve_web** 下页顶**同一面板**含「开始比赛」与**只读本场参数**（`POST /api/run-sim` / `GET /api/run-sim-status`）；**赛间不推送逐回合 NAV**，结束后自动刷新 JSON。JSON 含 **`post_game_feedback`**：每场结束后**再各调一轮**模型，把**全员排名与你的名次**作为赛后文本反馈写入；非训练，省调用可设 `ARENA_POST_GAME_FEEDBACK=0`。真实行情后续再接） |
| **真实金融建议** | http://127.0.0.1:8765/web/advisor.html（单页对话：`GET /api/advisor-context` 拉权重、历练次数、上一场 sim 透明 JSON；`POST /api/advisor-chat` 调 yaml 中模型。模式：自选槽位 / 权重合议 / 历练优先。对话写入 `arena_advisor_memory.json` 并计质量分，下一场 sim 将高分摘要注入对应槽位系统提示。须运行 `serve_web.py` 并用本机浏览器打开） |

- 擂台页读取根目录 **`arena_state.json`**（跑完 `sim` 或 `python scripts/demo_report.py` 后刷新）。可选：用 **`assets/README.txt`** 里的烘焙脚本从参考 PNG 生成 GIF（宣传/附件用），与擂台页主 Canvas 无叠层依赖。
- 建议页另可加载 **`arena_real_prompt.md`**（CLI `arena_run --mode real` 生成）。

### 烘焙 `arena-poster.gif`（豆包整图 → 可选 GIF 资产）

- **`python scripts/bake_reference_gif.py -i assets/arena-reference.png`**（需 **Pillow**）默认生成 **`web/generated/arena-poster.gif`**：`--preset zoom` 为**整图中心推拉变焦**多帧 GIF；若在其它页面用 **`<img>`** 播放循环动效，**勿**指望 Canvas `drawImage(GIF)`（多数浏览器只画第一帧）。
- **`--preset idle`**：旧版轻微呼吸 + 像素化（可走智谱视觉等取色，逻辑同前）。
- **`--engine auto`（默认）**：有 **Gemini + `uv`** 时走 **`sprite-animator`**（输出仍由 `-o` 决定，常为精灵风而非整海报）；否则 Pillow 路径按 **`ZHIPU` → `DEEPSEEK` → `MINIMAX` → `MIMO` → `local`**。可选变量见 **`.env.example`**。

## 安全与分发

- **禁止**在仓库或 SKILL 中写入任何第三方 API Key；仅使用环境变量或本目录 `.env`（勿提交 Git）。
- 你在对话里粘贴过的密钥应视为已泄露，请立即在各控制台 **轮换/作废**。

## 依赖安装

```bash
cd financial-ai-arena
pip install -r requirements.txt
```

复制环境变量模板：

```bash
copy .env.example .env   # Windows
# 或：python scripts/init_dotenv.py（仅当尚无 .env 时从 .env.example 生成）
# 编辑 .env 填入各厂商 Key（不要加引号空格）
```

加载顺序（`arena_run` / `serve_web` / `suggest_personas` 共用 **`scripts/arena_dotenv.py`**）：若存在 **仓库根** `.env`（如本仓库 `skill_-/.env`）先读入，再读 **本 skill 根** `.env`（`financial-ai-arena/.env`），后者**覆盖**同名变量；便于把 Key 只写在仓库根一份。

可选模型覆盖（不设则用内置默认）：

| 变量 | 说明 |
|------|------|
| `ARENA_ZHIPU_MODEL` | 默认 `glm-4-plus`（可按智谱文档改为可用模型名） |
| `ARENA_DEEPSEEK_MODEL` | 默认 `deepseek-chat` |
| `ARENA_MINIMAX_MODEL` | 默认 `MiniMax-M2.7` |
| `ARENA_MIMO_MODEL` | 默认 `mimo-v2.5-pro` |
| `ARENA_ZHIPU_THINKING` | `enabled` / `disabled` |
| `ARENA_MIMO_THINKING` | `enabled` / `disabled`，默认 `disabled` |
| `ARENA_POST_GAME_FEEDBACK` | `1`（默认）每场 sim 结束后并行再问各槽位一轮「名次+复盘」短文；`0` / `false` / `off` 关闭以省 API |
| `ARENA_LIVE_PROGRESS` | `1`（默认）赛间写入 `arena_live.json`，`serve_web` 的 `run-sim-status` 附带 `live`，擂台页可刷新 NAV 条；`0` 关闭 |
| `ARENA_USE_TUSHARE_PRICES` | `1` 时开局用 Tushare 日线收盘初始化价（需 `TUSHARE_TOKEN`）；失败回退漂移价 |
| `ARENA_DDG_SEARCH` | `1` 时每回合前尝试 DuckDuckGo 摘要一句写入 user prompt（常为空，仅作「预检索」演示） |
| `ARENA_INJECT_PREV_FEEDBACK` | `1`（默认）新一场把上一场 `post_game_feedback` 摘要拼进系统提示；`0` 关闭 |
| `ARENA_EXTRA_SKILL_SUBDIRS` | 逗号分隔的 `skills/<名>/SKILL.md` 子目录名，合并进所有参赛模型的系统提示 |
| `ARENA_TRAINING_DIGEST_MIN_Q` | 建议页入库对话注入 sim 时的最低质量分阈值，默认 `0.42` |

## 并列技能（宿主应为每次调用加载）

以下与本 skill **同级** `skills/` 目录中的能力，会在系统提示里列出路径，供各参赛模型遵守边界；**实际数据**仍由宿主通过对应 skill / MCP 拉取：

- `financial-analysis/SKILL.md`
- `jrj-quote-skill/SKILL.md`（需 `JRJ_API_KEY`）
- `tushare-finance/SKILL.md`（需 `TUSHARE_TOKEN`）
- `multi-search-engine/SKILL.md`
- `self-improving/SKILL.md`（赛后总结与进化记录）
- `moltpixel/SKILL.md`（可选：赛后庆祝像素，非必须）

## 配置：`configs/arena_config.yaml`

- **`providers`**：扩展任意模型的接入方式。内置 `driver`：
  - `zhipu`：走 `zai-sdk`（`env_api_key` 指向环境变量名）。
  - `openai_compat`：任意 OpenAI Chat Completions 兼容网关；配置 `base_url`、`env_api_key`、`default_model`，可选 `openai_extra_body`、`invoke_style`（`deepseek` / `mimo` 用于默认思考参数差异）。
  - 新增厂商：复制 yaml 块改名即可（密钥仍不进仓库）。
- **`contestants`**：每个 **槽位** 一条：`id`（唯一）、`provider`（引用 `providers`）、`display`、`persona`（多行人格）、`system_extra`（可选）、`model`（可选覆盖默认模型）。
- **同一厂商 4 人格**：让 4 条 `contestants` 的 `provider` 都为 `deepseek`（或任意同一 provider），仅改 `id` / `persona` / `display`；比赛时用 `--contestants` 选其中 2~4 个上场。

## 模式一：模拟擂台（sim）

- **推荐**：`--contestants ds_aggressive,ds_value,ds_macro`（2~4 个槽位 id，逗号分隔）。同一厂商可出现多次（不同 `id`）。
- **兼容**：`--ais zhipu deepseek minimax`（每个 slug 对应一个默认空人格槽位，且必须在 yaml 的 `providers` 里存在）。
- `--duration`：目标时长（秒），如 `30`、`60`、`300`。
- `--symbols`：纸交易标的池，逗号分隔，默认 `600519.SH,000001.SZ`。
- 输出：
  - `arena_state.json`：终局排名、权重、`contestant_meta`、**`post_game_feedback`**、**`price_source`**（`tushare_daily` 或 `drift_synthetic`）；赛间另有 **`arena_live.json`**（进行中快照，结束后删除）。
  - `arena_report.html`：横幅图 + **本地 Canvas 像素条形榜**（无需 Moltpixel）+ 表格。
  - `data/learning_log.md`：追加简报。

示例：

```bash
python scripts/arena_run.py --mode sim --contestants ds_aggressive,ds_value,ds_quant --duration 60
python scripts/arena_run.py --mode sim --ais zhipu deepseek minimax --duration 60
```

### 人格草稿（可选）

由某个已配置的 `writer` 模型生成 **`contestants_gen` 的 JSON**（兼容旧版 YAML），人工粘贴进 `arena_config.yaml` 后再微调；也可在浏览器打开 **`web/arena-setup.html`**（同上需 `serve_web.py`）用表单生成并导出。

```bash
python scripts/suggest_personas.py --writer deepseek --slots 4 --topic "A股短线与价值混合擂台"
# 可用环境变量 ARENA_PERSONA_WRITER_MODEL 覆盖 writer 的模型名
```

浏览器打开本目录下 `arena_report.html` 查看版面。

**未跑 API 时预览像素擂台**：`python scripts/demo_report.py` 会生成本地示例 `arena_report.html`（含顶部 Canvas 擂台 + 右侧「实时排名」+ 下方 NAV 条形榜）。

## Moltpixel 公网画布（可选）

- **Key 获取**：按 `skills/moltpixel/SKILL.md` 调用注册接口 `POST https://pixelmolt-api.fly.dev/api/agents/register`，响应里的 `apiKey` 即密钥；也可访问 [moltpixel.com](https://moltpixel.com) 文档与心跳说明。
- **拿不到 Key**：本 skill 已在 `arena_report.html` 内嵌 **离线 Canvas 像素榜**，不依赖外网；公网 Moltpixel 仅作趣味加分项。

## 模式二：真实股票分析与决策对话（real）

在至少跑过一次 `sim` 生成 `arena_state.json` 后（**无需**再传 `--contestants` / `--ais`）：

```bash
python scripts/arena_run.py --mode real --user-query "请结合最新财报与资金面给出观察要点，不做买卖指令"
```

会生成 `arena_real_prompt.md` 并在 stdout 打印 **按上一场排名折算的权重说明**；宿主 Agent 应用该权重组织多轮对话（仍须接用户自配的金融 MCP / Tushare / JRJ 等）。

> 说明：当前 runner **不代替**宿主去调 MCP；它只负责 **多模型 API 编排 + 纸交易博弈 + 权重表**。每场 sim 结束会为上场槽位 **+1 历练次数**（`arena_advisor_memory.json`），与建议页对话入库共用同一文件。

## 自我进化（建议流程）

1. 跑完 `sim` 查看 `arena_report.html` 与 `arena_state.json`。
2. 将本场要点写入 `self-improving` 约定位置，或直接把 `data/learning_log.md` 交给宿主做下一场规则微调。
3. 下一场调整 `--duration` / `--symbols` / 参赛组合，形成赛季。

## 打包分发（上传 / 分享）

### 建议整包上传的目录与文件

将 **`financial-ai-arena/`** 作为 skill 根目录打包（zip / 私仓 / 附件），至少包含：

| 类别 | 路径 |
|------|------|
| 说明与元数据 | `SKILL.md`、`_meta.json` |
| 依赖 | `requirements.txt` |
| 环境模板（必带） | `.env.example`（**不要**带真实 `.env`） |
| 后端与 CLI | `scripts/` 下全部 `.py` |
| 前端 | `web/`（含 `index.html`、`arena.html`、`advisor.html`、`styles.css`、`*.js` 等） |
| 擂台配置示例 | `configs/arena_config.yaml`（其中 **`env_api_key` 只能是环境变量名**，如 `MOONSHOT_API_KEY`，**禁止**写入真实 key 字符串） |
| 可选 | `samples/` 示例赛题、`assets/`、`start_serve_web.bat`、`desktop/`（见下） |

**Electron 壳（可选）**：可上传 `desktop/` 里的源码与 `package.json`、`package-lock.json`、`README.txt`、启动脚本；接收方在 `desktop/` 执行 `npm install` 后再 `npm start`。**不要**上传 `desktop/node_modules/`（体积大且可重建）。

### 绝对不要上传（避免泄露密钥与隐私）

- **`.env`**：你所有模型 Key 所在；本仓库已在 `.gitignore` 忽略，打包前请确认压缩包里没有它。
- **`arena_advisor_memory.json`**：建议页对话与质量分，属个人数据。
- **运行产物（可删或清空后再传）**：`arena_state.json`、`arena_report.html`、`arena_live.json`、`data/learning_log.md`、`data/last_scenario_pack.json`（若含路径/内容隐私）、`configs/arena_config.yaml.bak`。
- **任何文件内的明文密钥**：若曾在 yaml / md / 脚本里粘贴过 `sk-` 等 token，应删掉或改回「仅环境变量名」，并在厂商控制台 **轮换密钥**（粘贴过即视为可能泄露）。

`configs/arena_config.yaml` 正确写法是：`env_api_key: MOONSHOT_API_KEY`，由接收方在自己机器上配置环境变量或 `.env` 填入值（见上文「依赖安装」与 **`.env.example`**）。

### 接收方第一次怎么用（操作顺序）

1. 解压到宿主工作区的 `skills/financial-ai-arena/`（与其它 skill 并列时路径与 `SKILL.md` 中「并列技能」一致）。若使用本独立仓库，则直接以 `financial-ai-arena/` 为 skill 根目录即可。
2. **`pip install -r requirements.txt`**
3. **复制环境变量**：`copy .env.example .env`（Windows）或手动复制；按 `.env.example` 注释填入**自己的**各厂商 Key（不要加引号、不要多余空格）。
4. **启动 Web**：在 skill 根目录执行 `python scripts/serve_web.py`（默认端口见终端输出，一般为 `8765`）。
5. **浏览器**打开 `http://127.0.0.1:8765/web/index.html`，按需进入擂台配置页、擂台页、建议页；**勿用 `file://` 直接打开 html**（否则无法请求本机 API）。
6. 若从配置页写回 yaml，会先备份 `arena_config.yaml.bak`；分发包中可不包含 `.bak`。

更完整的模式说明（`sim` / `real`、CLI 参数）见本文件上文各节。
