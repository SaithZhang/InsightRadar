# InsightRadar · 接续入口

保存日期 2026-11-09，Asia/Shanghai。当前开发目录为 `insightradar`，基线为 V0.02。分支 `codex/v002-baseline`，远端为原 `SaithZhang/InsightRadar` 仓库。精确提交以当前分支 HEAD 为准。

切换接续 · 旧 Python 项目归档在同级 `insightradar-archive-20261109`。此前目录名 `insightradar-v002` 作为历史路径的兼容链接。新工程沿用既有 PostgreSQL 数据。盘后先显示腾讯确认的当日不复权收盘，BaoStock 校验后通过「更新技术指标」生成新报告。详见 [实现记录](docs/IMPLEMENTATION_PROGRESS.md)。

行情终值修复 · 按北京时间分析时点区分盘前、盘中、盘后和非交易日。盘后从 18:00 起请求 BaoStock 当日终值及复权数据，旧日期缓存不会遮住盘后更新。沪电股份 11 月 9 日盘后实际报告为 77.10 元，120 根 K 线，技术 READY，事件覆盖仍为 PARTIAL。旧报告内容与 hash 一致。证据见 `data/acceptance/session-finality/receipt.json`。

持仓增量接续 · 已实现并在本机启动。详见 [持仓管理 PRD](docs/PRD-我的持仓.md) 和 [技术方案](docs/TECH-持仓管理.md)。三个入口已可用，正式库已升级至 Flyway V4，21 条旧分析记录指纹一致，持仓表起始为空。50 项 Java、4 项前端单测、10 项桌面／手机浏览器测试通过。持仓测试用隔离数据库和合成记录，模型缓存用本机测试替身。下一步由用户录入一条真实持仓并核对报告首屏。

最新接续：用户批准用现有 OpenAI Key 生成报告，本应用月预算 $100、无日限。`gpt-6.1-sol` 经本机代理已实跑；调试发新请求，生产按实际输入、模型及提示词复用证据结果，Flyway V3 的本地账本保存预留和结果。沪电两次实测 27.38 秒 / 3.81 秒，共一次模型调用，4 条通过引文校验的事实及 3 个核验点。11/33 页进入模型，1 条引用被剔除，事件覆盖 PARTIAL。报告和回执在 `data/acceptance/llm-modes/`。配置通过忽略的 `.env` 引用原凭据文件。44 后端、4 前端、2 真实报告浏览器检查通过。

最新接续：普通分析已按股票和北京时间自然日缓存行情。沿用 PostgreSQL 的不可变 `market_snapshots`，Flyway V2 增加请求代码和日期索引。只复用终值范围匹配、质量可靠且未过期的行情输入，命中仍重算 TECH-R1 并生成新报告；D+1 后验按原区间重新查询。43 项 Java 测试通过。沪电真实两次分析从 28.54 秒降到 3.57 秒，第二次命中，120 根 K 线、指标、源时间与输入指纹一致，旧报告 hash 保持。回执在 `data/acceptance/daily-market-cache/receipt.json`。

最新接续：用户要求移除非必要 Docker 依赖，已安装本机 PostgreSQL 17.11；compose 配置与 Testcontainers 依赖已移除。`scripts/start.sh` / `stop.sh` 使用 `scripts/postgres.sh` 管理 `data/postgres-native`（127.0.0.1:15432），不注册开机服务。Docker Desktop 关闭时，42 Java 测试、2 项真实历史浏览器检查、新库初始化、重复启动和应用重启全部通过。6 张表共 432 行迁移前后及测试/重启后指纹完全一致；原 `data/postgres` 离线保留。回执在 `data/acceptance/native-migration/receipt.json`。本轮移除 Docker 的验收已完成，行情及 LLM 原缺口保持。

目标：按用户冻结 PRD-V0.02.2 与 TECH-V0.02.2 实现本地单股分析。范围：一个 Java 后端、一个 PostgreSQL DB、一张 Vue 页面；trade_authority=none。原项目独立保留并暂停，见 `../insightradar-archive-20261109/CHECKPOINT.md`（暂停文档提交 94d9228，原业务代码基线 f64bea7）。跨项目恢复从 `../InsightRadar-Control/CHECKPOINT.md` 进入。

先读 AGENTS、README、docs/IMPLEMENTATION_PROGRESS 和冻结文档。已实现技术规则/真实适配/官方目录与 PDF/可配置 LLM/不可变报告/追加后验/历史 UI，不是空接口。已跑 42 项 Java（真实 Spring/PostgreSQL）、8 Python、4 Vitest、6 Playwright及生产构建；6 个浏览器检查中的 2 个是合成技术向量，其余实际读取真实来源降级报告。服务只监听 127.0.0.1；`scripts/start.sh` / `scripts/stop.sh` 已验。重启保留报告内容及 hash。

当前总状态 PARTIAL，整版尚未验收。最新修复：BaoStock 由过时的 0.8.9 / www 地址更新至官方 0.9.4 / public-api 地址，socket 60 秒、整次请求 180 秒有界超时。沪电真实 run edc70f21-9b7f-45db-8a4a-7c5400b06954 已为技术 READY：120 根、基准日 2026-11-06、质量 reliable/fresh，无行情错误；五个指标独立 Decimal 对账及真实桌面/手机图表验证通过。42 Java + 8 Python 通过，原失败快照 hash 不变。初始十股均失败的历史证据保留，其他板块、停牌/除权及 D+1 实股验收未补齐，不能据此宣称整版通过。原阶段 LLM 未配置，当前状态见顶部。本次证据在 data/acceptance/baostock-debug。

本地证据在 data/acceptance，数据库/PDF/模型输出/日志/凭据不入 Git。测试无真实持仓、账户或旧业务数据库。普通克隆不带验收原件，真实 PDF 测试需自行指定 OFFICIAL_PDF_TEST，否则明确 skip。

原冻结范围的下一步：在已恢复的 BaoStock 0.9.4 上补其余真实样本与 D+1 验收，保留来源失败证据；不要扩成新网关、微服务、选股或多 Agent 平台。未取得本地 Fuyao URL/鉴权前不得声称它可用于 Spring。
