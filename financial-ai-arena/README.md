# Financial AI Arena · 金融 AI 擂台

多模型 **纸交易模拟对战（sim）** + 像素风擂台可视化 + **真实金融建议页（advisor）**。通过 YAML 扩展厂商与模型、为 2～4 个「人格槽位」配置上场阵容；密钥仅走环境变量或 `.env`，**勿提交密钥到 Git**。

> **重要声明**：本项目用于技术演示与多模型行为对比，**不构成投资建议**。实盘决策请咨询持牌专业人士。

---

## 功能概览

| 模块 | 说明 |
|------|------|
| **擂台配置** | 选槽位、provider/模型、人格生成与写回 `configs/arena_config.yaml`（需本机 `serve_web.py`） |
| **擂台竞技** | 页内发起 sim、轮询状态、Canvas 擂台与 NAV 榜、**回合回放**（`turn_logs`）、赛后反馈（`post_game_feedback`） |
| **真实金融建议** | 多模式对话、权重与上一场 sim 透明数据、对话记忆与质量分（写入 `arena_advisor_memory.json`） |
| **CLI** | `scripts/arena_run.py` 支持 sim / real 等模式，产出 `arena_state.json`、`arena_report.html` 等 |
| **桌面壳（可选）** | `desktop/` Electron 一键拉起 `serve_web.py` 并内嵌页面 |

更细的变量表、并列 skill 说明、YAML 字段释义见本目录 **[SKILL.md](./SKILL.md)**（面向 Agent 与深度使用者，内容最全）。

---

## 环境要求

- **Python 3.10+**（推荐；需已加入 `PATH`，Windows 下命令一般为 `python`）
- 现代浏览器（**请用系统浏览器**访问 `http://127.0.0.1:8765/...`；勿用 `file://` 打开 `web/`，否则无法 `fetch` JSON）
- **Electron 桌面壳（可选）**：Node.js + `desktop/` 下 `npm install`

---

## 快速开始

### 1. 进入本目录并安装依赖

```bash
cd financial-ai-arena
pip install -r requirements.txt
```

### 2. 配置密钥（不要提交到 Git）

```bash
# Windows 示例：复制模板后编辑
copy .env.example .env
```

也可在**仓库根目录**放 `.env`；加载顺序为先读仓库根、再读本 skill 根，**后者同名变量覆盖前者**（见 `scripts/arena_dotenv.py`）。

### 3. 启动 Web 服务

```bash
python scripts/serve_web.py
```

默认监听 **`http://127.0.0.1:8765`**。

### 4. 浏览器打开

| 页面 | URL |
|------|-----|
| 首页 / 入口 | http://127.0.0.1:8765/web/index.html |
| 擂台配置 | http://127.0.0.1:8765/web/arena-setup.html |
| 擂台竞技 | http://127.0.0.1:8765/web/arena.html |
| 真实金融建议 | http://127.0.0.1:8765/web/advisor.html |

健康检查：`http://127.0.0.1:8765/api/ping`

---

## 可选：Electron 桌面壳

适合希望「一个窗口里起停后端」的用户。

```bash
cd desktop
npm install
npm start
```

或双击 `desktop/start_desktop.bat`（详见 [desktop/README.txt](./desktop/README.txt)）。若系统找不到 Python，可在启动前设置环境变量 **`ARENA_PYTHON`** 指向解释器完整路径。

---

## 命令行跑一场 sim（示例）

在 **skill 根目录**（本 README 所在目录）执行：

```bash
python scripts/arena_run.py --mode sim --contestants ds_aggressive,ds_value,ds_quant --duration 60
```

更多参数（`--max-rounds`、`--symbols` 等）见 **SKILL.md** 或 `python scripts/arena_run.py --help`。

---

## 赛制与「回合回放」条数

- **总时长上限** 与 **最多回合** 为 **先到先停**；若填了较多回合但总时长偏短，实际完成回合数会少于上限，**回合回放条数 = 各槽位实际已完成的回合数**（与 `arena_state.json` 中 `rounds` 一致）。
- 需要跑满更多回合时：适当**增大总时长**或调整**每回合预算**。

---

## 主要产出文件（skill 根目录）

| 文件 | 说明 |
|------|------|
| `arena_state.json` | 上一场 sim 结果：排名、权重、`turn_logs`、`post_game_feedback` 等 |
| `arena_live.json` | 进行中快照（若开启 live 进度）；结束后由脚本清理 |
| `arena_report.html` | 报告导出 |
| `arena_advisor_memory.json` | 建议页对话与质量分等 |
| `configs/arena_config.yaml` | 擂台与模型、槽位配置 |

---

## 仓库中已有说明文件

| 路径 | 用途 |
|------|------|
| **[SKILL.md](./SKILL.md)** | 完整能力说明、环境变量表、配置与 CLI 细节 |
| [desktop/README.txt](./desktop/README.txt) | Electron 壳使用说明 |
| [web/api/README.txt](./web/api/README.txt) | 静态 `arena-config.json` 与预览说明 |
| [assets/README.txt](./assets/README.txt) | 可选 GIF 等资源说明 |

---

## 许可证

若本目录未单独提供 `LICENSE`，请以**上层仓库**的许可证为准；贡献前请阅读仓库根目录的许可条款。
