# Implementation progress

Started 2026-11-09 Asia/Shanghai. Independent repository, branch `codex/v002-mvp`.
Original repository clean at f64bea7; preserved in place. No existing V0.02 code found.

## Order and acceptance (written before implementation)
1. Gate 0: real BaoStock identity/raw/qfq/factors/calendar and five exchange/board samples; official CNInfo directory and one PDF. Record command, timestamp and gaps.
2. Slice 1: Java quality + TECH-R1 + fixed D+1 + REST + Vue/ECharts. Independent decimal reference and T01–T15/T17/T20; real API.
3. Slice 2: bounded official directory pagination/latest periodic report, PDFBox pages, strict LLM schema and quote validation. Preserve technical result on failure. No credential reuse from other projects.
4. Slice 3: PostgreSQL/Flyway immutable snapshots and append-only evaluations, history/replay, Testcontainers, browser responsive E2E, ten real stocks.

DONE requires actual commands/artifacts: Maven tests, Python tests, frontend tests/build, PostgreSQL migration, Spring startup, real market E2E, official quote verification and ten-stock acceptance. External coverage/configuration failures stay PARTIAL/BLOCKED. No implementation claim based on prototype. Stop after these criteria, no extra features.

Current: all gates pending. Missing handoff README is replaced by this repository's startup README; the four supplied files are preserved in docs/prototype.

## 2026-11-09 · 本轮交付回执（Asia/Shanghai）

用户在本轮明确选择暂不配置模型，保留公告与明确降级。新工程独立 Git；旧仓库只做可逆的暂停标记（本地提交 94d92288205c2233ce8444a1ba15226eebb7a289），其源码和业务数据未动。没有远程 push、PR 或 merge。

| 范围 | 状态 | 实际证据 / 尚缺 |
|---|---|---|
| 本地独立工程与启动 | DONE | Java 21 / Spring Boot 4.1.2 启动；PostgreSQL 17.6 Flyway V1；Vue 生产构建；15173/18080/15432 均只监听 127.0.0.1 |
| Gate 0 行情 | BLOCKED | 五个板块/交易所样本真实请求均在 BaoStock 登录失败；直连与一次既有 SOCKS 诊断均未完成登录；没有真实日 K |
| 切片一技术代码 | PARTIAL | Java TECH-R1、质量审查、D+1 固定目标、卖出连续日、REST、ECharts 已实现；独立 Decimal 对账通过；真实行情数值/停牌/除权与北交所覆盖未验 |
| 切片二官方证据 | PARTIAL | 9 股官方目录、70 份 PDF 抽取、真实 8 页季报定位校验；按 8 PDF 上限明确部分覆盖；1 股官方发行人缺口；LLM 按用户决定未配置，客户端实调用未验 |
| 切片三持久化与 UI | PARTIAL | 真 PostgreSQL 上终态报告、市场输入、文档、后验记录不可改；评估幂等、重复实例锁、重启完整性通过；真实技术状态多样性与 D+1 实股事件尚缺 |
| V0.02 整版验收 | BLOCKED | 10 股均无真实行情，不能声称全链路通过；没有把原型或测试向量当作实盘结果 |

### 已实际运行的检查

- `OFFICIAL_PDF_TEST=.../data/acceptance/cninfo-report.pdf JAVA_HOME=.../jdk-21... mvn -f server/pom.xml test`：**42 tests, 0 failures, 0 errors, 0 skipped**。包括真实 PostgreSQL Testcontainers/Flyway/Spring HTTP，T01–T20 对应边界及来源失联测试。日志 `data/acceptance/maven-test-final.log`。
- `.venv/bin/python -m unittest discover -s bridge/tests -v`：**8 passed**（主数据别名、错后缀、指数/B 股拒绝、重复身份、北交所缺口、非法输入、供应商错误）。`python-tests.log`。
- `.venv/bin/python scripts/check_reference.py`：5 个指标对账，独立 50 位 Decimal，误差 < 1e-28。`reference-check.log`；这是合成输入，不是实股指标验收。
- `npm run test --prefix web`：**4 passed**；`npm run build --prefix web`：成功。`vitest.log` / `web-build.log`。
- `npm run test:e2e --prefix web`：**6 passed**。4 项覆盖桌面/手机真实降级报告、历史、原文弹窗、无横向溢出；另外 2 项是明确标注的 Java 合成向量图表消费测试，不能替代真实行情 E2E。`playwright-final.log` / `playwright-results.json`。
- `scripts/start.sh`、`scripts/stop.sh` 再启动：成功；正式历史报告的 JSON 和 SHA-256 完全一致，见 `restart-integrity.json`。
- 真实 CNInfo PDF：PDFBox 8 页，实际第 1 页引文匹配通过，`server/target/official-pdf-check.json`。不说明模型摘要或所有文档已审阅。
- Python 依赖锁文件、Maven parent/依赖版本、npm package-lock 已保存；原型和冻结交付文件的原始 hash 在 `docs/handoff-sha256.json`。

### 10 只真实样本（新运行，不是 mock）

| 股票 | 最终运行状态 | 行情 | 公告目录 / 抽取 PDF |
|---|---|---|---|
| 002463.SZ | PARTIAL | UNKNOWN，0 K | 42 / 8 |
| 600519.SH | PARTIAL | UNKNOWN，0 K | 11 / 8 |
| 688001.SH | PARTIAL | UNKNOWN，0 K | 24 / 8 |
| 300750.SZ | PARTIAL（补跑） | UNKNOWN，0 K | 64 / 7，1 份抽取失败 |
| 920029.BJ | PARTIAL | UNKNOWN，0 K | 28 / 7，1 份抽取失败 |
| 000001.SZ | PARTIAL | UNKNOWN，0 K | 20 / 8 |
| 600036.SH | PARTIAL | UNKNOWN，0 K | 21 / 8 |
| 300308.SZ | PARTIAL | UNKNOWN，0 K | 61 / 8 |
| 688256.SH | PARTIAL | UNKNOWN，0 K | 23 / 8，部分空白/图像页 |
| 920982.BJ | PARTIAL | UNKNOWN，0 K | 来源不可用，0 / 0 |

最终清单 `data/acceptance/live-acceptance-final-summary.json`；每份报告带独立 runId/错误/来源/指纹。300750 首轮记录 `INTERRUPTED_RESTART`，原 FAILED 记录保留，不覆盖、不计通过；之后新建 run `80034b2b-3250-406c-aab4-8582b2f5826a` 完成明确降级。已补数据库运行锁与重复实例测试；首轮触发恢复的进程来源未证实，不推断原因。

9 份提供真实公告和明确缺口，不代表满足“10 股不同技术状态”验收。真实技术链路仍 0 通过，北交所身份/行情覆盖仍未证实。来源故障下 UI 只显示官方发行人名称，不把输入后缀冒充证券身份。

### 文件与恢复

- `bridge/`：真实 BaoStock 进程协议与测试。
- `server/`：Java 规则、行情质量、受控官方下载/PDF、证据 Schema/LLM、快照仓库、REST 与数据库触发器。
- `web/`：单页、图表、历史/证据展示和浏览器测试；不读取 prototype。
- `scripts/`：启动/停止、真实 Gate 0/10 股/单样本补跑、独立参考计算。
- `docs/`：原冻结文件、来源实测、规则示例和本进度；`CHECKPOINT.md` 是恢复入口。

已结束本轮可独立验证的实现。唯一下一步：恢复/确认 BaoStock 可达性，或取得用户允许的已有 Fuyao 本地 URL/鉴权，再重跑同一 Gate 0；随后补真实技术链路、北交所/停牌/除权/D+1 验收。暂不配置 LLM 是用户选择，不自动复用其他项目凭据或另建来源平台。

## 2026-11-09 · 移除 Docker 必需依赖（DONE）

用户要求优先使用本机依赖，没有可安装。本轮范围仅启动/停止、数据库集成测试和必要数据迁移；冻结 PRD/TECH 原件不改，当前用户指令替代其中 Testcontainers/Docker 的部署测试选择。验收：Docker 关闭下启动成功；现有数据库所有表的行数和内容指纹迁移前后一致；真实 PostgreSQL 集成测试及应用重启通过。旧数据库原件保留，测试使用临时本机集群，不能触碰业务库。

- 本机安装 PostgreSQL 17.11，复用已有 Java/Node/Python。Homebrew 命令行工具选择仅作用本次安装，不修改系统 Xcode 选择或接受其许可；没有安装开机服务。
- 删除 compose.yaml 与两个 Testcontainers Maven 依赖。新增 scripts/postgres.sh，以 pg_ctl 管理本工程独立集群；启动初始化认证为 SCRAM，绑定 127.0.0.1:15432。停止先等待 Java/Web 结束，再停止本工程数据库。
- PostgreSQL 集成测试改为本机随机端口临时集群；独立目录/角色/数据库，清除继承的 PG 配置，结束后关闭清理。仍验证真实 Flyway、Spring HTTP、不可变触发器、后验幂等和单实例锁，没有以 mock 替代存储验收。
- 旧容器只临时启动以做 pg_dump / pg_restore 逻辑迁移，完成后 Docker Desktop 关闭。6 张表共 432 行，迁移前后、集成测试后和应用重启后的 SHA-256 指纹完全一致。旧 data/postgres 原件保留；当前数据为 data/postgres-native。已移除本次临时传输 dump，未删除旧数据。
- 实测：42 Java、0 fail/error/skip（含实际 PDF）；2 项桌面/手机真实历史页面；新建原生集群初始化/重复启动/status/stop；应用 stop/start；生产构建及 API/web HTTP 200。三个服务只监听 loopback。Docker daemon 已关闭，临时测试集群已清理。
- 本地证据：data/acceptance/native-migration 下 receipt.json、before/after/after-tests/after-restart.json、maven-test.log、browser-history.log、fresh-startup.json 和启动日志。凭据和数据库不入 Git。

本轮 DONE 仅指移除 Docker 依赖；V0.02 仍 PARTIAL，真实行情 Gate 0 仍 BLOCKED，用户仍不配置 LLM。下一步回到既有真实行情连接问题，不扩大部署或数据平台。分支 codex/v002-mvp，本轮仅本地提交，未 push/PR/merge。

## 2026-11-09 · BaoStock 技术未知排查（单股修复 DONE）

用户指出“技术未知 / 数据不足，暂不判定”，最新 002463 报告的直接错误为 BaoStock login 10002007，原始日 K 为零；公告 42 份/解析 8 份、LLM 未配置形成独立 PARTIAL 状态。范围：核对并修复本工程 SDK/桥接，保留不可变历史，不改变规则或切换数据平台。验收：已核验官方 SDK 依赖和服务地址；单股真实 bridge/API 日 K 与技术计算成功，或准确保留剩余外部失败；相关回归通过，事件部分可用不得伪装完整。

实际修复：两个依赖清单锁定 BaoStock 0.9.4，官方公开地址由 SDK 使用 public-api.baostock.com。原 0.8.9 的旧地址问题此前漏查，不能再笼统归为本机网络不可达。单次 socket 等待由 20 秒放宽到 60 秒；Java 子进程及 Gate 0 统一 180 秒整体上限，仍有限制、失败不填价格。匿名免费接入，没有改系统代理或增加数据平台。

真实 bridge 返回 484 raw / 484 qfq / 772 calendar / 2 factors，首个冷请求 74.74 秒，说明原脚本 65 秒上限不足；之后一次 20 秒登录接收超时保留原 PARTIAL 报告。更新超时并重启后，正式 API run edc70f21-9b7f-45db-8a4a-7c5400b06954 于 19:21 用时 24.1 秒完成：canonicalCode=002463.SZ，技术 READY、120 根、2026-11-06、质量 reliable/fresh=true、errors=[]。DOWN 为 TECH-R1 的计算输出，不是交易授权。事件 PARTIAL 保持，原因是 43 份目录只解析 8 份、LLM_NOT_CONFIGURED。

验证：42 Java（无失败/错误/跳过）、8 Python、2 项真实桌面/手机历史浏览器检查全部通过；实际图表可见，未使用合成价格。五个指标独立 50 位 Decimal 对账 <1e-28。原失败报告 f46e4389-58c1-4861-9d59-01c45e81b304 的 reportHash 未变。证据：data/acceptance/baostock-debug/{verification.json,api-final.json,final-summary.json,maven-test.log,python-tests.log,browser-history.log,login-timing.log}；真实响应和截图不入 Git。

本次修复完成；V0.02 整体验收仍 PARTIAL，其他样本、停牌/除权/北交所与真实 D+1 尚未补跑。用户可重新分析生成新报告，旧历史失败不会被覆盖。后续只补已有真实验收，当前不自动配置模型。分支 codex/v002-mvp，仅本地提交，未 push/PR/merge。

## 2026-11-09 · 按股票与北京时间自然日缓存行情（DONE）

用户要求补行情数据缓存。普通分析从 PostgreSQL 的既有不可变行情快照查找同日输入。仅复用可靠、最新应有交易日完整、满足当日终值边界的数据；裸代码须曾由来源确认过身份。查找、取数和落盘串行衔接，避免同一请求并发重复拉取。命中保留来源获取时间和存储指纹，重新校验与计算，并生成独立报告。D+1 后验按所需区间取数。

43 项 Java 测试通过，真实 PostgreSQL 集成测试覆盖北京时间午夜、不同证券、错误交易所后缀、跨日、过期及校验失败。Flyway V2 已在本机启动时应用。沪电股份两次真实分析：`002463` 首次用时 28.54 秒，`002463.SZ` 同日命中用时 3.57 秒。两次均有 120 根有效日 K，行情时间、K 线、指标与输入指纹一致，分别保存为新报告；旧报告 hash 不变。报告可查看 `marketCacheHit` 和 `providerFetchAt`。回执在 `data/acceptance/daily-market-cache/receipt.json`。

## 2026-11-09 · OpenAI 报告与调试 / 生产模式（DONE）

用户批准现有 OpenAI Key 和每月 100 美元预算，无日限。仅模型请求使用本机 HTTP CONNECT 代理，启动时引用既有凭据文件。本地 PostgreSQL V3 按北京时间自然月保守预留每请求 0.20 美元。额度仅控制本应用的请求，真实用量保留供应商 token 回执。生产先按实际序列化输入、模型、提示词和端点找已校验的结果，调试绕过读取，成功输出可以供之后生产复用。两种模式均新建不可变报告。

沪电真实调试 run `b615ce44-31d6-4a5b-b6fa-81186b6ebc47` 耗时 27.38 秒，调用 OpenAI 一次。技术 READY，目录 43 份，8 份正文共 33 页，模型读取 2 份的 11 页。4 条事实通过逐页校验，1 条因引文无法定位剔除，3 项人工核验。生产 run `29894997-92d0-4860-a145-66f44710fc99` 3.81 秒，复用同一模型回执，新增调用与额度预留均为零；旧历史指纹未改。事件覆盖为 PARTIAL。

44 项 Java 测试通过，真 PostgreSQL 测试验证跨实例复用、输入变化、调试绕过和预算耗尽后仍可命中。4 项前端测试、生产构建及 2 项桌面/手机真实历史报告检查通过。报告 `data/acceptance/llm-modes/沪电股份-分析试跑报告.md`，回执 `data/acceptance/llm-modes/receipt.json`。下一步由用户查看这份报告后给出提示词和覆盖调整意见。

## 2026-11-09 · 持仓管理增量（设计完成）

用户确认持仓增量需求。 [PRD](PRD-我的持仓.md) 与 [技术方案](TECH-持仓管理.md) 记录三页导航、手工持仓、TECH-R1 动作映射、报告快照与缓存边界。对照现有 Flyway V1–V3、行情质量校验、分析队列、报告持久化及模型请求键完成设计核查。运行时与数据库尚未修改，应用测试留待实现。首个实施步骤是 V4 持仓表与本地 API。

## 2026-11-09 · 持仓管理增量（实现与本机验证完成）

- Vue 顶栏开放「持仓」「个股分析」「分析记录」。持仓支持新增、编辑、确认未变、标记清仓和参考估值。个股与历史共用报告视图，历史支持按北京时间生成日期筛选。
- Flyway V4 增加持仓表。并发保存按版本匹配，冲突返回 409。分析入队前捕获持仓，只匹配已核验的证券身份。报告首屏显示持仓状态、MA55 价格信号、预设动作与下次检查，报告 hash 覆盖当次快照。
- 50 项 Java 测试全部通过，含独立 PostgreSQL 17 的 V3→V4 迁移和重启、旧报告 hash、版本并发保护、提交后改仓以及缓存隐私检查。使用本机测试模型验证两次生产分析只发一次请求，调试再次发出，模型请求不包含持仓数据。
- 4 项前端单测、10 项桌面／手机 Playwright 测试及生产构建通过。浏览器覆盖合成持仓增改清仓、回到原位置、历史直接访问、现有真实来源报告和图表回归。生产构建报告入口包约 1.6 MB，仍有大小提示。
- 本机服务已通过标准启动脚本升级到 V4。升级前后 21 条分析记录及其报告 hash 的指纹一致。正式库持仓表为空，测试记录均在隔离环境，验证未产生付费模型请求。迁移指纹在 `data/acceptance/holdings-run/`。

## 2026-11-09 · 按分析时段确认当日行情终值（DONE）

- 复现 21:46 生成的沪电报告仍用 11 月 6 日，根因是旧桥接和校验固定排除当日。北京时间盘前与盘中使用上一交易日终值。15:00 起期待当日收盘，18:00 起请求 BaoStock 当日不复权、前复权和复权数据，通过校验才更新判断。终值缺失时保留可用参考价格并显示缺口。固定 D+1 同样使用该终值门槛。
- 缓存按证券、上海自然日和请求截止日区分，重算阶段与时效。盘后取当日时避开盘前的快照，待发布期间和数据缺失时分别显示明确状态。
- 本机 21:55 重跑沪电，交易日为 11 月 9 日，收盘 77.10 元，与腾讯行情独立核对一致。120 根日 K 完整，技术 READY。旧报告 JSON 与 hash 保持一致。公告覆盖 PARTIAL，重跑提交一次正常生产模型请求。回执在 `data/acceptance/session-finality/receipt.json`。
- 52 项 Java、9 项 Python、4 项前端单测、10 项浏览器测试及生产构建通过。盘前、盘中、收盘待发布、发布后、非交易日和缓存切换由固定时点回归覆盖。

## 2026-11-09 · 腾讯收盘展示及正式基线切换

- 分析提交后可单独读取腾讯盘后收盘。证券、交易日、市场已收盘状态、日线与报价一致且有成交才展示。使用五分钟有效报价缓存，缺失可重试。BaoStock 继续决定技术指标、持仓动作和固定 D+1。
- 桌面与手机均验证报价可以在报告行情阶段独立显示。固定时点覆盖盘中、陈旧、停牌、错代码和报价冲突。54 项 Java、4 项前端单测、12 项浏览器测试和生产构建通过。
- 本机目录已切为 `insightradar`，旧 Python 工程移至 `insightradar-archive-20261109`，旧持仓导入服务已停止。既有 PostgreSQL 报告、持仓、行情和公告的指纹在重启前后一致。腾讯接口实时核对沪电 11 月 9 日收盘为 77.10 元。回执位于本地 `data/acceptance/canonical-switch/`。
- 发布分支为原公开仓库 `SaithZhang/InsightRadar` 的 `codex/v002-baseline`。以公开主分支为父提交发布当前源码，旧 Python 本地历史和运行数据保留在本机。全市场与 Windows 验收待补。
