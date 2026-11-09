# InsightRadar · 本机股票研究工作台

当前开发以 V0.02 的 Java / Vue 工程为基线。产品合同为 [冻结 PRD](docs/01_PRD_产品需求_冻结版.md)，技术合同为 [TECH](docs/02_TECH_技术设计_实施版.md)。旧 Python 工程已归档。本机手工持仓及三页导航见 [持仓管理增量](docs/TECH-持仓管理.md)。

**当前为 PARTIAL 版本，尚未完成整版验收。** BaoStock 0.9.4 已通过沪电股份 120 根真实日 K 验收。其他市场及 D+1 实股验收仍需补跑。页面可用官方公告、PDF、模型证据提炼和只读历史，报告按实际处理范围声明覆盖。详细实测见 [验收记录](docs/IMPLEMENTATION_PROGRESS.md) 和 [来源实测](docs/data-provider-spike.md)。

## macOS 启动

前提：Java 21、Maven ≥3.6.3、Node 24、Python 3.13（也可准备兼容 Python 3.11+ 环境）、本机 PostgreSQL 17。运行和测试均不需要 Docker。测试采用 JUnit 5，直接启动 Spring 和独立的临时本机 PostgreSQL 集群。实际应用依赖锁定在 pom.xml、package-lock.json、bridge/requirements.lock；本机 PostgreSQL 当前已验证 17.11。

```bash
cd /path/to/insightradar
# 只在尚未安装 PostgreSQL 17 时执行：
brew install postgresql@17
python3 -m venv .venv
.venv/bin/python -m pip install -r bridge/requirements.lock
npm ci --prefix web
export JAVA_HOME=$(/usr/libexec/java_home -v 21)
scripts/start.sh
```

打开 [股票分析](http://127.0.0.1:15173)。API 为 `127.0.0.1:18080`，PostgreSQL 为 `127.0.0.1:15432`。这三个端口必须空闲。首次安装依赖需要联网。启动脚本构建生产资源，用本机 `pg_ctl` 管理本工程的数据库集群，再启动单个 Java 进程与页面静态服务器；不安装开机服务，也不启动 Homebrew 的全局数据库服务。

```bash
scripts/stop.sh
```

停止只作用于本工程记录的进程与 `data/postgres-native` 数据库集群，不删除历史。数据端口保持 15432，不占用全局默认 5432。`scripts/postgres.sh start|stop|status` 可单独管理数据库。不要手动修改已应用迁移。原项目恢复方式仍在原项目 README/CHECKPOINT。

2026-11-09 已将原容器库逻辑迁移到本机集群，6 张表的行数和 SHA-256 全部一致。旧 `data/postgres` 原件仍保留为离线回退资料，不再使用；迁移回执为 `data/acceptance/native-migration/`。如果旧数据存在但没有迁移成功标记，启动脚本会拒绝创建空库，防止把空历史当作迁移完成。当前用户“移除 Docker 依赖”的指令替代冻结附件中 Testcontainers/Docker 的实现选择，附件原文仍保留。

开发时分别开终端：

```bash
scripts/postgres.sh start
cd server
JAVA_HOME=$(/usr/libexec/java_home -v 21) mvn spring-boot:run
# 另一终端从工程根目录：
npm run dev --prefix web
```

Windows 需自行准备 PostgreSQL 17 和数据库连接变量，建立 `.venv` 后将 `BRIDGE_PYTHON` 设为完整的 `.venv\Scripts\python.exe`，`BRIDGE_PATH` 指向 bridge 脚本，`DATA_DIR` 指向本地 data，再使用 Maven/npm。Bash 启动脚本和原生数据库测试夹具仅验证 macOS；Windows 未实测，不承诺直接执行上述脚本。

## 持仓管理

从顶栏打开「持仓」或直接打开 [持仓管理](http://127.0.0.1:15173/#/positions)。手工录入股数、可选成本和 MA55 条件触发后的预设动作。北京时间当天确认的持仓可用于生成个人动作。持仓只保存在本机 PostgreSQL，生成报告时保存当次记录。首轮启动自动应用 Flyway V4。

## 配置

无模型配置也能运行。可将 `.env.example` 复制为 `.env`，由启动脚本加载；手动启动需自己导出变量。`.env` 不入 Git，不要把密钥粘贴到聊天或前端。

| 变量 | 默认 / 用途 |
|---|---|
| DB_URL / DB_USER | 本机 15432 / insightradar |
| DB_PASSWORD | 示例中的开发占位密码，仅本机隔离 DB；自行改时同时调整已有 DB 用户密码 |
| PG_BIN | 可选，PostgreSQL 17 可执行文件目录；自动查找 Homebrew 常用路径、Linux 17 路径及 PATH |
| BRIDGE_PYTHON | 从 server 启动时为 `../.venv/bin/python` |
| BRIDGE_PATH | `../bridge/baostock_bridge.py` |
| DATA_DIR | `../data` |
| LLM_BASE_URL / LLM_MODEL | 空时降级；目前使用 `https://api.openai.com/v1` 和 `gpt-6.1-sol` |
| LLM_KEY_ENV_FILE / LLM_API_KEY | 启动时引用已有 `OPENAI_API_KEY` 文件，或从环境传入 `LLM_API_KEY` |
| LLM_HTTP_PROXY | 可选 HTTP CONNECT 代理 `host:port`，仅用于模型请求 |
| LLM_MONTHLY_BUDGET_USD | 本应用按北京时间自然月默认 100 美元，无单日额度。每次发出前保守预留 0.20 美元，按预留额控制；不读取其他项目用量 |
| DISCLOSURE_MAX_PDFS | 8，最大 30；超过处理上限必为 PARTIAL |

API 和页面固定 loopback。API_PORT 只供单独手动运行，配套代理和 Origin 白名单目前按固定端口配置；一键脚本使用固定端口。服务不含登录、调度、通知或交易执行。所有报告 `trade_authority=none`。

## 数据与规则

- BaoStock 0.9.4 通过本地 Python 子进程调用，使用官方公开服务 public-api.baostock.com:10030，免费匿名连接。单次 socket 超时 60 秒、整个子进程上限 180 秒；异步报告页面会显示处理阶段。网络仍可能慢或失败，失败保留真实缺口。Fuyao 本地 URL/授权尚未验证，未创建伪 Adapter。
- 证券按供应商主数据唯一匹配。来源失联时 `canonicalCode=null`、身份待核验，巨潮发行人名称单独展示，不能据此确认交易所。
- 原价、供应商 qfq、稀疏复权事件、交易日历及规范化 qfq 一并冻结。Java 校验 OHLC、停牌、来源身份、日期、复权比例；同日 OHLC 比率误差容忍上限为供应商四位精度对应的 0.001 元，不是交易比较阈值。技术判断始终使用 DECIMAL128，UI 只格式化。
- 普通分析按证券、北京时间自然日和本次请求截止日复用行情快照。跨日或盘后切到当日终值时重新取数。六位代码首次仍须由来源确认身份，之后同日带正确交易所后缀也能复用该输入。每次分析重新校验、计算并保存独立报告，可在「规则版本与复现指纹」查看 `marketCacheHit` 与原始 `providerFetchAt`。D+1 后验仍按所需区间重新查询。
- 窗口默认回看 730 个自然日，取最近最多 120 根有效日 K；不足明确标出。至少 60 根才能完成趋势判断。长期停牌导致窗口不足仍为缺口，不承诺全历史回填。
- 盘前、盘中和非交易日使用最近已完成的交易日。交易日 15:00 后，报告期待当日终值。本机从 18:00 起请求 BaoStock 当日原价、前复权与复权数据，校验通过才更新技术判断。等待期间可展示上一交易日的参考收盘，报告标明缺口，暂停依赖新终值的判断。固定 D+1 也在目标日终值确认后可检查。
- 个股页可先展示腾讯已收盘的不复权价格，需同一证券、同一交易日、市场明确已收盘且日线与快照收盘一致。BaoStock 技术日线与复权数据就绪后，通过「更新技术指标」生成新报告。
- D 日计划冻结，复核固定 D+1；价格口径变化不能安全比较时返回 `ADJUSTMENT_CHANGED_RECHECK`。晚到数据只补验原目标。已触发后跌破下沿另追加记录，首次触发记录不修改。
- 90 个自然日官方目录完整分页；另检索定期报告目录，按报告期优先、同期间披露时间选择最新全文，排除摘要、提示和关于报告的公告。标出更正/补充。PDF 有大小、页数、官方域名和重定向限制，无 OCR。
- 单次默认抽取 8 份 PDF；目录、PDF 与模型覆盖分别声明。已有文档保留真实物理页码和 SHA-256；模型事实逐条校验 documentId/page/quote，未核验数字推导拒绝入正式结论。引文匹配不等于语义判断必然正确。
- 「生产」默认复用同一模型、提示词与实际输入的证据结果，报告生成时间不参与匹配。「调试」总是尝试发出新请求；结果有通过校验的事实时可供后续生产复用。失败或没有合格事实的响应不进入缓存。命中仍生成新报告且不占用新额度；预算用尽时也可命中。模型优先处理最新定期报告，输入上限 30,000 字节、输出上限 2,400 token，截断会在报告中标为 PARTIAL。
- 原型 `prototype/index.html` 是离线 demo；运行前端不导入其中任何模拟行情。

## 验证与复现

```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 21)
mvn -f server/pom.xml test
.venv/bin/python -m unittest discover -s bridge/tests -v
.venv/bin/python scripts/check_reference.py
npm run test --prefix web
npm run build --prefix web
npm run test:e2e --prefix web
```

集成测试使用本机 PostgreSQL 17 的 `initdb` / `pg_ctl` 在系统临时目录创建独立集群，随机 loopback 端口，结束后关闭并删除。它不读取应用的 DB_URL，不接触报告库；找不到 PostgreSQL 时明确失败，不跳过数据库验证。无需 Docker。Playwright 默认使用本机 Chrome 的隔离临时浏览器，不读取日常登录资料；两种视口为 1440×900、390×844。需先启动本工程并生成一份真实来源报告；无报告时真实历史 E2E 明确 skip，不能计为通过。

真实 PDF 引用验收可显式设置 `OFFICIAL_PDF_TEST=/absolute/path/report.pdf` 运行 Maven；未提供时该项跳过，不冒充已验。当前本机产物在 `data/acceptance/cninfo-report.pdf`，不随源码分发。

```bash
.venv/bin/python scripts/gate0.py
.venv/bin/python scripts/live_acceptance.py
```

两者均访问真实来源、串行执行、保留拒绝状态，原始响应与日志在 `data/acceptance`。失败时不要删除旧快照或把 FAILED 改为完成。报告/计划重现以冻结输入、TECH-R1、冻结 LLM 响应为准，重复请求模型不保证同一答案。

REST 路由见 [TECH 第 5 节](docs/02_TECH_技术设计_实施版.md)。另外提供 `GET /api/v1/health`。分析为 202 异步任务，2 个有界工作线程、队列 8；重启把未完成任务标为明确失败，已完成报告不变。数据库运行锁阻止第二实例抢先执行恢复。

## 保存与接续

先读 [CHECKPOINT.md](CHECKPOINT.md) 和 [实现记录](docs/IMPLEMENTATION_PROGRESS.md)。跨项目恢复入口为 `../InsightRadar-Control/CHECKPOINT.md`。Git 仅保存源码、规则、合成测试和说明；真实 PDF、市场响应、数据库、日志、模型响应、凭据均在忽略目录。当前开发分支为 `codex/v002-baseline`，沿用原 [InsightRadar GitHub 仓库](https://github.com/SaithZhang/InsightRadar)。

来源协议参考：[BaoStock 官方发布包与示例](https://pypi.org/project/baostock/0.9.4/)、[Spring Boot 4.1.2 系统要求](https://docs.spring.io/spring-boot/system-requirements.html)、[巨潮资讯](https://www.cninfo.com.cn/)、[PDFBox](https://pdfbox.apache.org/)。这些文档能力不等于本机所有来源已通过验收。
