# InsightRadar

Current product version: **InsightRadar V3.0 Pilot — Scope Frozen**. P0 is accepted; the project is running ten real morning decision trials. See [PRODUCT_VERSION.md](PRODUCT_VERSION.md) and [ADR-0010](docs/memory/decisions/0010-v3-pilot-scope-frozen.md).

InsightRadar 是面向个人投资者和资产出资人的独立 AI 风险官。它持续过滤市场信息，区分事实、推断、传闻、情绪与 unknown，结合真实持仓、账户风险、产业基本面、市场状态和可验证行动证据，给出可追溯、可复核、必须由用户人工确认的风险等级与条件计划。

短定义：**不是帮用户知道更多，而是帮助用户识别少数真正值得改变仓位的信息。**

Canonical workspace: `D:\work\InsightRadar`. New code, local data, generated reports, and Codex automation context belong in this directory.

## 冻结基线文档

- [产品基线](docs/PRODUCT_BASELINE.md)
- [V3.0 已实现冻结面](docs/V3.0_FROZEN.md)
- [V3.1 增量候选与状态](docs/V3.1_DELTA.md)
- [架构](docs/ARCHITECTURE.md)
- [数据与公开边界](docs/DATA_BOUNDARIES.md)
- [本轮决策日志](docs/DECISION_LOG.md)

V3.1 尚未获准开发。不得新增第五个一级菜单、用原型数据冒充真实能力、自动交易，或让 AI/实名观点来源覆盖规则和人工确认。

## Windows 一键使用

不需要先打开 PowerShell。直接在项目根目录双击：

- `InsightRadar.cmd`：启动本地应用并打开持仓导入页面；页面内可粘贴、预览、批准保存、查看自动 beta 计算进度、打开最新报告和关闭应用；
- `生成盘后报告.cmd`：生成并自动打开最新盘后报告；
- `导入持仓.cmd`：与主入口相同，打开仅监听 `127.0.0.1` 的本地持仓导入页面；
- `打开最新报告.cmd`：不刷新数据，直接打开最近一次盘后报告。

启动器会优先使用 `.venv\Scripts\python.exe`，该环境缺失时会寻找已经安装好项目依赖的系统 Python。若环境不可用或生成失败，窗口会保留并显示明确错误。

## 当前四个一级任务

本地工作台固定保留四个一级任务：

- **今日计划**：盘后计划、晨间新鲜度复核、市场约束、变化队列和人工响应；
- **组合风险**：已知/未知仓位、自动 beta 证据、数据完整度、严格就绪、风险阻塞和持仓计划；
- **标的研究**：按意图建立研究任务并查看已有证据；真实技术图与 P1 研究编排尚未实现；
- **复盘账本**：计划版本、用户响应和 T+1/T+5/T+20 后验成熟度；真实成交执行流水尚未接入。

市场证据是上游约束和页面抽屉，不是第五个一级任务。

## 工程模块

InsightRadar 收敛为四个产品模块：

- **Portfolio Intelligence**：持仓、风险线、交易假设、复盘和盘后动作。
- **Research Intelligence**：研报、公告、外部观点、产业线索和 thesis delta。
- **Market Radar**：A股、跨市场、crypto、事件风险和异常监控。
- **Product Ops**：产品地图、验证状态、运行历史和自我进化 backlog。

这四个模块是 CLI 和代码的工程分类，不是另一套页面导航。

生成当前产品地图：

```powershell
.venv\Scripts\python -m stock_assist.cli product-map
```

## 长程项目记忆

非简单任务先读根目录 `PROJECT_MEMORY.md` 和 `CURRENT_STATE.md`，再按触发词只加载对应主题。`progress.md` 与 `session-handoff.md` 是按功能编号或最新尾部查询的历史证据，不再整份作为启动上下文。项目方向见 `docs/product-charter.md`，重要取舍通过 `docs/memory/decisions/` 下的 ADR 留存。

```powershell
.venv\Scripts\python scripts\validate_project_memory.py
.venv\Scripts\python -m stock_assist.cli architecture-view
```

交互式架构拓扑写入 `docs/architecture.html`。新增或重命名产品命令后，记忆校验会检查它是否已进入 `configs/architecture.json`，并拒绝把旧拓扑当作当前事实。

### 独立交易纪律提醒器

Windows 个人交易纪律提醒器已完成两阶段拆分并由独立项目 `D:\work\reminder` 持有。Windows 登录任务、源码、配置、构建脚本和本地日志均由该项目管理；本仓不再包含或发布该应用。拆分结果与扩张冻结计划见 `docs/extractions/README.md`。

## 数据源连通性检查

先安装 SDK wheel：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install .vendor\xysz-src\xysz\xysz_tools\tgw-1.0.8.7-py3-none-any.whl .vendor\xysz-src\xysz\xysz_tools\AmazingData\AmazingData-1.1.8-cp313-none-any.whl
```

配置账号密码。推荐复制 `.env.example` 为 `.env`，然后填写真实账号：

```powershell
Copy-Item .env.example .env
notepad .env
```

`.env` 内容类似：

```dotenv
AD_USERNAME=your_username
AD_PASSWORD=your_password
AD_HOST=101.230.159.234
AD_BACKUP_HOST=140.206.44.234
AD_PORT=8600
AD_CACHE_DIR=data/amazingdata
AD_PERMISSION_START=2026-05-22
AD_PERMISSION_END=2027-05-22
```

`.env` 已被 `.gitignore` 忽略，不会提交到仓库。也可以只在当前 PowerShell 中临时设置：

```powershell
$env:AD_USERNAME="your_username"
$env:AD_PASSWORD="your_password"
$env:AD_HOST="101.230.159.234"
$env:AD_BACKUP_HOST="140.206.44.234"
$env:AD_PORT="8600"
$env:AD_CACHE_DIR="data/amazingdata"
$env:AD_PERMISSION_START="2026-05-22"
$env:AD_PERMISSION_END="2027-05-22"
```

运行最小自检：

```powershell
.venv\Scripts\python -m stock_assist.data_sources.xysz doctor --code 000001.SZ
```

## 工作流命令

安装本项目为可编辑模式：

```powershell
.venv\Scripts\python -m pip install -e .
```

项目是 Python `>=3.10` 模块化单体。没有 `package.json`、Node 前端构建链、独立数据库服务或 ORM；页面由 Python 生成自包含 HTML/CSS/JavaScript。

### 本地工作台（127.0.0.1:8765）

```powershell
.venv\Scripts\python -m stock_assist.cli portfolio-import --serve
```

该命令只监听 `127.0.0.1`。根路径提供四任务工作台，`/portfolio-import` 提供本地粘贴/预览/批准导入页；保存后先运行 `portfolio-beta`，以沪深300为基准、120个交易日窗口和至少60个有效样本计算 beta，再继续风险刷新。样本不足、过期或异常保持 `unknown`。所有状态写操作要求当前进程生成的随机 Token，服务不接受交易指令。

安装后可使用新的产品命令 `insight-radar`；`shenyan-radar` 和原 `stock-assist` 命令保留为兼容别名。下面仍使用 `python -m stock_assist.cli`，避免本地入口脚本未刷新时影响运行。

### Portfolio Intelligence

生成盘后持仓指引和 HTML dashboard：

```powershell
.venv\Scripts\python -m stock_assist.cli after-close
```

`after-close` now writes one cross-client payload and two renderers with the same timestamp:

- `reports/*-after-close.json`: Portfolio Intelligence payload for future iOS / Android / Windows / Web clients;
- `reports/*-after-close.md`: CLI/text review report;
- `reports/*-after-close.html`: InsightRadar dashboard renderer.

Each run also updates the private `data/signal_outcomes.jsonl` ledger. One signal is kept per stock and calendar day, then refreshed after 1/5/20 trading sessions with raw return, direction-adjusted hit/miss, and 20-session maximum favorable/adverse excursion. Horizons remain `pending` until enough trading sessions exist; InsightRadar does not publish an early hit rate from immature samples. Use `data/signal_outcomes.example.jsonl` only as the public schema example.

### Research Intelligence

同步中证1000历史成员区间：

```powershell
.venv\Scripts\python -m stock_assist.cli factor-universe-sync
```

该命令把 AmazingData `get_index_constituent` 规范化为私有 `data/factor_universe/csi1000_membership.csv`，同时生成审计用 JSON、Markdown 和 HTML。每次同步都会计算 `manifest_hash`；历史模型按 `universe_id + manifest_hash` 隔离，不能和原20股试验账本静默混训。要启用历史成分实验，可复制 `configs/factor_lab.csi1000.example.json` 和 `configs/factor_pipeline.csi1000.example.json`，并使用独立数据目录。

运行本地多因子滚动检验（日线、未来5日相对中证1000收益）：

```powershell
.venv\Scripts\python -m stock_assist.cli factor-lab
```

配置文件为 `configs/factor_lab.json`。默认股票池明确标为研究试验池，不冒充完整中证1000成分。流程对每个交易日做横截面MAD去极值和排序标准化，用带5日隔离期的滚动岭回归估权，并输出RankIC、扣费后Top组合相对收益、回撤、换手率及最新研究排名。排名仅供纸面研究；行业/市值中性化、涨跌停可交易性和冲击成本完成前，不进入实盘。

个人模型的日更MVP：

```powershell
.venv\Scripts\python -m stock_assist.cli factor-pipeline
```

`factor-pipeline` 使用无需GPU的 `Ridge v1`。每次运行会按 `universe_id + date + code` 更新私有观察账本，将T+5已成熟的相对收益标签加入训练集，用最近约252个交易日全量重训候选模型，再通过RankIC、分层收益、单调性、VIF和条件数等硬门槛决定是否覆盖 `champion.json`。失败候选只留在模型注册表，不进入正式评分。

需要工作日15:40自动运行时，可手动安装本地计划任务：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-factor-pipeline-task.ps1
```

当前阶段不需要云服务器；数据规模扩大到数百/数千股票、分钟级特征或单次训练持续超过约30分钟后，再把同一数据账本和模型注册协议迁移到按任务计费的云CPU。

监测研报和 thesis delta：

```powershell
.venv\Scripts\python -m stock_assist.cli research-monitor
```

生成产业股票池：

```powershell
.venv\Scripts\python -m stock_assist.cli industry-pool 机器人
```

以下实名观点/社区命令属于可选 Extension 或历史兼容能力，不是正式产品依赖，也不能直接授权仓位动作。

生成观点来源技能库：

```powershell
.venv\Scripts\python -m stock_assist.cli influencer-skills
```

生成回复情绪指示器：

```powershell
.venv\Scripts\python -m stock_assist.cli influencer-sentiment
```

采集 X/Twitter 用户最新帖子：

```powershell
.venv\Scripts\python -m stock_assist.cli x-user-posts aleabitoreddit -n 5
```

将 X/Twitter 原始采集转成大V观点流水：

```powershell
.venv\Scripts\python -m stock_assist.cli x-sync-observations
```

### Market Radar

生成 A 股当日市场脉冲 PPT-style dashboard。优先使用 Galaxy AmazingData `query_snapshot`，公开分时数据只作为 fallback：

```powershell
.venv\Scripts\python -m stock_assist.cli market-pulse
```

配置文件：

```text
configs/a_share_pulse.json
```

`market-pulse` 会优先使用有日期对齐的已完成收盘 IF/IH/IC/IM 基差；盘中静态收盘数据会被拒绝并串行回退到 AmazingData 实时适配器。没有真实的前序盘中观测时不会伪造 4 分钟变化。

- 结构化 payload：`reports/*-market-pulse.json`，作为未来 iOS / Android / Windows / Web App 的跨端契约；
- Markdown 报告：`reports/*-market-pulse.md`，保留给 CLI 和文本复盘；
- HTML dashboard：`reports/*-market-pulse.html`，由同一份 JSON payload 渲染；
- 期指基差表：现货、期指、当前基差、短窗口变化；
- 操作建议表：顺势观察、不开激进仓、冲高控仓等条件化动作；
- 后台审计：数据来源和每条基差记录写入 `data/market_pulse_sources.jsonl`，不显示在前台卡片里。

生成大盘多周期点位指示。默认分析上证指数的月、周、日、60分钟、15分钟和3分钟结构；3分钟线由1分钟线聚合：

```powershell
.venv\Scripts\python -m stock_assist.cli market-levels
```

配置文件为 `configs/market_levels.json`。报告同时生成 JSON、Markdown 和 HTML。点位区间只在分型/前低、均线、BOLL/ATR、中枢边界、波段回撤等至少两类证据聚合时展示，并给出守住、跌破、重新站回三类条件。这里的缠论口径是可复现的程序化近似，不替代人工严格画笔，也不输出确定性涨跌预测。

### Product Ops

查看当前 Agent 分工：

```powershell
.venv\Scripts\python -m stock_assist.cli agents
```

生成架构工作流前端视图：

```powershell
.venv\Scripts\python -m stock_assist.cli architecture-view
```

扫描近期报告并生成自我进化 backlog：

```powershell
.venv\Scripts\python -m stock_assist.cli evolve
```

生成产品模块、命令和数据边界地图：

```powershell
.venv\Scripts\python -m stock_assist.cli product-map
```

报告默认写入 `reports/`；架构视图默认写入 `docs/architecture.html`，可以直接用浏览器打开。

## 每天盘后运行

先用 Windows 任务计划程序或 `schtasks` 调度盘后命令。例如交易日 15:30 运行：

```powershell
$repo = (Get-Location).Path
$python = Join-Path $repo ".venv\Scripts\python.exe"
schtasks /Create /TN InsightRadar-after-close /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 15:30 /TR "`"$python`" -m stock_assist.cli after-close"
```

如果后续要接入 Codex 自动解读报告，可以把这个命令作为固定的项目侧产物，再由 Codex 读取最新 `reports/*-after-close.md` 做二次研究。

## 本地数据文件

InsightRadar 把文件分成四类：

- **product_config**：入库配置，例如 `configs/agents.json`、`configs/architecture.json`、`configs/industries.json`、`configs/influencers.json`、`configs/event_calendar.json`、`configs/crypto_watchlist.json`、`configs/research_sources.json`。
- **private_runtime_data**：本地私有数据，例如 `.env`、`data/portfolio.manual.tsv`、`data/portfolio.json`、`data/portfolio.galaxy.tsv`、`data/portfolio_context.json`、`data/research_deltas.jsonl`、`data/influencer_observations.jsonl`。这些不应提交。
- **template/schema**：可复制的示例和轻量契约，例如 `*.example.json`、`*.example.tsv`、`data/*.schema.json`。
- **generated_output**：生成产物，例如 `reports/*` 和 `docs/architecture.html`。

公开仓库只允许源代码、产品文档、测试、可复现配置、schema/example 和明确标注的合成截图。真实账户、持仓、交割单、原始截图、Cookie、Token、日志、数据库与私有行情缓存必须只保留本地，详见 `docs/DATA_BOUNDARIES.md`。

### Replayable portfolio context

- `data/portfolio.manual.tsv`: easiest manual holdings input. Copy broker position rows into this tab-separated file using the same header as `data/portfolio.manual.example.tsv`. InsightRadar uses `当前持仓` as the true current position and ignores rows where `当前持仓` is 0, so same-day sells or frozen historical balances do not become false holdings.
- `data/portfolio_context.json`: real local position context. Copy `data/portfolio_context.example.json`, then maintain buy thesis, initial/current risk line, adjustment history, horizon, and review status for each holding. This file is intentionally separate from broker snapshots so Galaxy data can refresh without deleting research memory.

## 开发验证

安装项目依赖并检查环境：

```powershell
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m pip check
```

当前基线的标准验证：

```powershell
.\.venv\Scripts\python -m compileall stock_assist
.\.venv\Scripts\python -m unittest discover -s tests -v
.\.venv\Scripts\python scripts\validate_project_memory.py
.\.venv\Scripts\python -m stock_assist.cli after-close
```

Production package build:

```powershell
.\.venv\Scripts\python -m build
```

冻结点没有仓库级 lint 或静态类型检查配置。基线审计会如实记录独立运行 `ruff`/`mypy` 的结果，不把“未配置”写成通过。
