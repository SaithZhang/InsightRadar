# InsightRadar V0.02｜技术设计与实现路径

> **TECH-V0.02.2｜2026-11-09｜与 PRD-V0.02.2 对齐**  
> 权威边界：`01_PRD_产品需求_冻结版.md` 是业务与验收标准，本文给出实现方式。不得以实现困难为理由悄悄修改产品规则。  
> 原有 `InsightRadar` 仓库的 V3.1 与当前 V0.02 是**不同开发线**。本版优先在独立 `insightradar-v002/` 下实现，不覆盖旧 Python 主程序、四路由和历史账本。

## 0. 一页结论：选型与原因

| 层 | 固定技术 | 原因 | 不用什么 |
|---|---|---|---|
| 前端 | Vue 3 + TypeScript + Vite | 单页交互、低开发成本、类型化 API | 不用 SSR / Next.js |
| UI | Element Plus + CSS 变量 | 快速完成表单、折叠、状态卡片，允许按原型微调 | 不造组件库 |
| K 线 | Apache ECharts 6（实际锁定兼容版本） | 蜡烛图、均线、标线、价区叠加 | 不手写图表引擎 |
| API | Java 21 + Spring Boot 4.1.x + Spring MVC + Jakarta Validation | 用户熟悉 Java 生态，单体足够 | 不上微服务、网关、MQ |
| 规则 | 纯 Java `technical`，BigDecimal | 冻结算法，独立测试，不能被 LLM 改写 | 不用 LLM 算价区 |
| 持久化 | PostgreSQL 17 + JDBC/JdbcTemplate + Flyway | JSONB 冻结快照，SQL 简洁，持久化准确 | 不用 Redis、ES、向量库 |
| 行情首选 | **BaoStock Python CLI adapter（免费）** | 文档明确日 K、raw/qfq、交易日历、停牌标记；单股请求量低 | 不购买 Tushare |
| 可选行情候选 | 已有 Fuyao/同花顺、合规备用源 | ChatGPT 中已验证历史 K 与部分财务数据，但本地 API/鉴权**未验证** | 不假设 MCP 在 Spring 本地直接可用 |
| 公告/财报 | 巨潮资讯、三交易所官方披露 + PDFBox 3.x | 原文可溯源、PDF 页码引用 | 不用券商二手摘要替代原文 |
| LLM | 一个可配置 API、JSON Schema 校验、证据后置校验 | 只处理语义与可核验未来指标 | 不用多 Agent、RAG 基础设施 |
| 构建测试 | Maven + JUnit 5 + AssertJ + Testcontainers + Vitest | 单元/边界/集成测试可重复 | 不靠人工截图当逻辑测试 |
| 运行方式 | 本地 macOS / Windows；Compose 只起 DB；API/页面本地进程 | 一个用户、最低运维成本 | 暂不公开上云 |

> **关于版本**：Spring Boot 4.1.x 支持 Java 21（官方要求 Java≥17），但不要无验证地写死未安装的补丁版本；由 Codex 锁定可构建且安全受支持的具体 patch，并写入依赖锁文件/构建配置。ECharts、Vue 同理锁版本。

### 数据源现状——文档能力 ≠ 已本地验收

1. BaoStock 官方 Python API `query_history_k_data_plus()` 支持 `adjustflag=2` 前复权、`3` 不复权，并有 `tradestatus`、`query_adjust_factor()`、`query_trade_dates()`、`query_stock_basic()` 等。**必须实际测试北交所覆盖**，不能从沪深覆盖推断北交所。
2. 同花顺 Fuyao MCP 已在 ChatGPT 环境用沪电股份 `002463.SZ` 与北交所 `920029.BJ` 返回历史前复权日 K，并可读原价/财务数据；但该 ChatGPT 连接**不表示** Codex 在用户电脑可直接调用。需要 URL/认证/许可证明确后才允许建立 `FuyaoAdapter`。
3. 官方披露网站可用网页，不意味着无限制公开 API。要验证合法自动访问、分页、官方 PDF、实际可访问性。
4. `Gate 0` 如北交所无法由可用免费源可靠覆盖，保留明确 `MARKET_COVERAGE_UNAVAILABLE`；不伪造覆盖通过，也不偷偷缩小沪深北验收范围。

## 1. 架构：独立单体、Adapter 隔离

```text
[Vue 3 / TS single page]
    │ HTTP JSON
    ▼
[Spring Boot 4.1 local :8080]
  API Controller / Validation
    │
    ▼
  AnalysisOrchestrator ───────────────────────────────────────────────┐
    │                                                                │
    ├→ SecurityResolver                                              │
    ├→ MarketDataProvider                                             │
    │    ├→ BaoStockAdapter → local Python subprocess/CLI             │
    │    └→ FuyaoAdapter (ONLY after local auth & endpoint verified)  │
    │       ↓                                                        │
    │    DataQualityValidator → NormalizedMarketSnapshot             │
    │                            ↓                                   │
    ├→ TechR1Engine (pure Java, NO IO/DB/LLM)                       │
    │       └→ indicators / trend / zones / D+1 plan / sell review   │
    ├→ DisclosureProvider (official source) → PDFPageExtractor        │
    │       └→ LlmEvidenceExtractor → EvidenceValidator              │
    └→ SnapshotRepository + PlanEvaluationRepository ◀───────────────┘
              PostgreSQL JSONB + controlled PDF cache
```

**技术依赖边界：** `technical` 不依赖 Spring、数据库或外部 API；`analysis` 负责编排与降级；`providers` 不读取用户私有历史交易。`Local CLI` 可选择输出单个 JSON 响应，日志/错误走 stderr，不把 Python stdout 的提示混进协议。

建议目录（在既有仓库中新建或维护独立目录）：

```text
insightradar-v002/
  README.md
  compose.yaml
  .env.example
  bridge/
    baostock_bridge.py             # CLI，不启动长期 Python 服务
    tests/
  server/
    pom.xml
    src/main/java/io/insightradar/v002/
      security/                    # 身份解析、代码标准化
      market/                      # MarketDataProvider, quality, adjustment
      technical/                   # TechR1Engine, PlanEvaluator
      disclosure/                  # 文档目录、官方 PDF、页级文本
      intelligence/                # LLM client, JSON Schema, 引用验证
      analysis/                    # 任务运行、状态、报告封装
      api/                         # REST endpoints
      persistence/                 # JDBC repositories
    src/main/resources/db/migration/
    src/test/
  web/
    src/{components,pages,api,types}/
  data/disclosures/               # 本地忽略，不入公开 Git
  docs/
```

## 2. 数据模型与接入

### 2.1 证券身份（必须按官方/供应商主数据确认）

- 允许纯 6 位输入或标准 `000001.SZ` / `600000.SH` / `920029.BJ` 等有后缀输入（例子**不是**代码号段推理规则）。
- 后端基于**唯一证券主数据记录**判定 `canonicalCode, sixDigitCode, name, exchange, type=COMMON_A, listStatus`，仅字符串合法不足以认定股票存在。
- 退市、长期停牌、北交所或新股等按真实状态降级；交易所上市范围禁止只用首位数字猜测。
- 若用户输入 `002463` 与 `002463.SZ`，必须解析到**同一个 canonicalCode**，历史检索与冻结计划按 canonicalCode 关联。

### 2.2 日 K、复权和交易日历

**读取策略：**

- 对每个分析请求取**足够长自然日窗口**，保证拿到**最近目标 120 根有效交易 K**（不能取最近 120 天代替 120 根）；至少校验 60 根趋势数据需求。
- BaoStock **分别获取**原价（`adjustflag=3`）与前复权序列（`adjustflag=2`），核查日期、OHLC、成交量与停牌。完整两套序列与来源响应 hash 一起冻结。
- BaoStock `query_adjust_factor()` 可返回稀疏复权事件，不要误以为是逐交易日因子数组；如不足以直接复现该源前复权，则记录派生比率、变动日和误差，不要伪造独立因子。
- 统一“本次快照锚点”到最后有效完整日 K `T`，`normalizedQfq(d) = providerQfq(d) × rawClose(T) / providerQfqClose(T)`（四个 OHLC 同比例缩放）；`T` 当日标准化后的 close 必须等于 rawClose(T)。保存原始 qfq 与标准化后 qfq，不能覆盖历史源数据。
- 若 raw/qfq 对应交易日不一致、复权比例在同日 OHLC 不一致、最新价不合法、负价格、重复日期、缺失因子、未来日期、前复权时间序列质量未过，则对应技术状态 `UNKNOWN`/受影响计算不可用。
- 全部指标使用同一标准化前复权序列，输入数值存 decimal-string/BigDecimal，UI 仅负责显示格式化。

**有效交易 K 校验：** 日期递增、成交日可在交易日历确认、OHLC 全部 `>0`、`low<=min(open,close)<=max(open,close)<=high`，且成交量/金额合法。停牌 `tradestatus=0` 不转换成“正常交易的 0 成交 K”。

**终值资格：** 时区 `Asia/Shanghai`。BaoStock 没有可靠显式终值标记时，MVP 采取保守门禁：**北京时间当日的行情若不能证明已终值，先不纳入；可明确展示数据截至昨日，并在实测后配置可验证的终值条件。** 不允许仅因 `now>15:00` 就假定数据已收定。更新时不得偷偷引入当天实时价。

**源切换**：同一分析快照 **只使用同一家 Provider 的完整 OHLC 序列**；全源不可用才 fallback；严禁混合拼接日 K。其他源的差异只作校验/告警，不能悄悄改写主源数据。

### 2.3 免费数据可用性闸门 Gate 0

创建 `docs/data-provider-spike.md`，至少记录下列真实请求、时间、提供方、响应类型、成功/失败原因：

| 样本 | 主要验证 |
|---|---|
| 沪市主板 600xxx.SH | 120 根完整 raw/qfq，交易日历与价格基准 |
| 深市主板 002463.SZ | 同上，分红复权与真实已完成交易日 |
| 科创板 688xxx.SH | 高价格、复权/停牌、代码识别 |
| 创业板 300xxx.SZ | 同上 |
| 北交所真实 920xxx.BJ | 是否真正由当前 SDK 返回 >= 60 根有效数据；不能假定可用 |
| 停牌/新上市样本 | 停牌日不能虚增 bar；有效 59/60/61 根样本测试 |

如 BaoStock 不支持 BSE，优先尝试已有 Fuyao 的**可在本地合法访问**数据接口，或其他有文档可实际测试的免费来源；若实测不通，输出缺口并阻塞“沪深北完整验收通过”宣称。无需购买数据权限。

## 3. 技术引擎 TECH-R1（纯函数实现）

输入 `TechInput{canonicalCode, bars[<=120], exchangeCalendar, asOfTradeDate, quality, ruleVersion}`，输出不可变 `TechResult`。规则版本固定为 `TECH-R1`；未来改公式必须提升版本。

### 3.1 指标精确定义

`C,H,L,O` 全部为本次统一标准化前复权价格。每根 K 按**有效 bar 顺序**，不是日历自然日序号。

```text
MA_n(t) = [ C(t-n+1) + ... + C(t) ] / n
TR(t) = max(H(t)-L(t), abs(H(t)-C(t-1)), abs(L(t)-C(t-1)))
ATR14 seed = mean(TR(第2根)...TR(第15根))
ATR14(t) = [13×ATR14(t-1)+TR(t)]/14 (第16根以后)
```

第一根没有前收盘，不形成 TR；第 15 根才能计算第一组 14 个 TR。指标内部使用 `BigDecimal` + 固定 `MathContext`（例如 DECIMAL128）；**所有布尔比较采用非舍入数值**，UI 可保留 2~4 位小数。

**最低有效数量：** MA20=20，MA55=55，MA55(t-5)=60，ATR14=15，20 日极值=20，60 日极值=60。59 有 MA55 但没有可用于完整趋势的 MA55(t-5)；60 根趋势才可做完整判断。时间序列少于要求不可补 0。

### 3.2 趋势

```text
UP   := C(t)>MA20(t) && MA20(t)>MA55(t)
        && MA20(t)>MA20(t-5) && MA55(t)>MA55(t-5)
DOWN := C(t)<MA20(t) && MA20(t)<MA55(t)
        && MA20(t)<MA20(t-5) && MA55(t)<MA55(t-5)
MIXED := 质量全部通过 && !(UP || DOWN)
UNKNOWN := 输入/价格基准/长度/时点无法满足完整判定
```

`MA_n(t-5)` 是用“截止第 t-5 根的前 n 根 bar”计算，不是 `(MA_n(t) - 5)`，不可 off-by-one。

### 3.3 支撑/压力

六个候选：`MA20(t)`、`MA55(t)`、`LOW20=min(L(t-19)..L(t))`、`HIGH20=max(H(...))`、`LOW60`、`HIGH60`。仅纳入对应指标有效的候选。

- 严格 `< C(t)` 且距离最小为支撑中心；严格 `> C(t)` 且距离最小为压力中心。中心恰好等于收盘价时剔除。
- 半宽 `W = 0.5×ATR14(t)`；区间 `[center-W, center+W]`。
- 某侧无候选，则该侧“无清晰区域”。ATR 非正/异常则两侧均不生成。
- 若两侧都存在且 `support.upper >= resistance.lower`，两侧标记“无清晰区域”、理由 `ZONE_OVERLAP`；不硬给点位。
- 输出候选 ID、中心、计算窗口、半宽、区间、落选原因，以便审计。

### 3.4 D+1 观察计划：严格方案 A

**D=该报告所用的最后完整有效交易 K 日**，保存：`planId, baseRunId, canonicalCode, D, targetSession(D+1 open exchange day), zone.lower, zone.upper, normalizedPriceBasis, anchor, sourceHash, TECH-R1`。计划创建时间可以晚于 D，但**不得在 D+1 已完成时回溯创建“等待 D+1”的新计划**；如果用户晚分析，只能以当时已确认最新完整日 K 作为 D。相同 D 上多次分析可各成独立快照和计划。

**已完成 D+1 且完整时，判定顺序：**

```text
if D+1 close < zone.lower             → INVALIDATED
else if D+1 low >= zone.lower
    && D+1 low <= zone.upper
    && D+1 close > zone.upper
    && D+1 close > D+1 open           → TECHNICAL_CONDITION_MET
else                                    → EXPIRED_NO_SIGNAL
```

其中 `>= / <=` 包含等号；收盘站上上沿与阳线都要严格大于。 **只检查固定 D+1**，不滑动到 D+2。交易所关市前 `WAITING_NEXT_BAR`；D+1 无成交/停牌/迟到数据为 `NEEDS_RECHECK`（不将无数据视为未触发），除权导致不能同口径比较为 `ADJUSTMENT_CHANGED_RECHECK`。迟到数据恢复后可以追加 D+1 新的事实核验版本，历史记录不覆盖；不能在 D+2 或更晚以 D+2 价格补触发。已满足后发生新跌破可追加 `INVALIDATED_AFTER_TRIGGER`，不消除旧的已满足记录。

**触发检查时点：** 用户点击“分析”或在历史页面选择“复核 D+1”；没有常驻自动巡检。所有记录都要记下 `evaluatedAt` 和 `targetTradeDate`，与计划原始 `ruleVersion` 一起保存。

### 3.5 卖出复核

```text
PRICE_RISK_REVIEW := C(D) < MA55(D)
    && C(D-1) < MA55(D-1)
    && exchangeCalendar shows D-1,D are adjacent exchange-open sessions
    && both sessions completed, valid and comparable
```

任何两条不满足、缺失、停牌或口径冲突，不生成触发；明确 `NOT_TRIGGERED` 或 `UNKNOWN`（未知不当作未触发）。事件风险不参与这个算式，另列 `EVENT_RISK_REVIEW`。

## 4. 官方公告、PDF 与 LLM

### 4.1 文档采集

- 检索 90 个自然日公告 + 最新一期真正**已披露**定期报告，搜索截止为本次 `knowledgeCutoff`，用交易所/巨潮官方链接。即使最新报告不在 90 天内也要抓取。
- 文档元信息 `documentId, canonicalCode, title, publishedAt, reportPeriod, category, officialUrl, pdfUrl, source, fetchedAt, pdfSha256, textExtractionStatus`。
- 记录页码、原始文本/标准化文本、官方 PDF hash，检查翻页是否完整、是否有更正/补充。PDFBox 逐页读正文；OCR 不在 V0.02，扫描件给 `EXTRACTION_UNAVAILABLE`。
- 下载入口只允许白名单官方域名，响应重定向也需校验目标域名；大小、类型、超时限制；保留源 URL，不缓存受限个人敏感数据到 Git。

### 4.2 LLM 输出（最多 5+3）

结构化输出 schema 示例：

```json
{
  "facts": [
    {
      "statement": "在某份公告/报告中被披露或能支持的事实",
      "classification": "DISCLOSED_FACT",
      "impact": "MIXED",
      "whyItMatters": "为什么重要（标清推断）",
      "asOf": "YYYY-MM-DD",
      "evidence": [
        {"documentId": "doc-001", "page": 12, "quote": "来自 PDF 第12页的真实短句"}
      ]
    }
  ],
  "followUps": [
    {
      "question": "下一次要检验什么",
      "evidenceSource": "下一份季报/官方公告",
      "criterion": "明确可核查的判定标准",
      "manualConfirmationRequired": true
    }
  ]
}
```

枚举：`classification=DISCLOSED_FACT|COMPANY_EXPLANATION|MODEL_INFERENCE`；`impact=POSITIVE|NEGATIVE|MIXED|UNCERTAIN`。不得给未来收益率、目标价、计算 MA/ATR 或交易建议。

### 4.3 证据门禁

1. 结构 schema/长度/枚举必须合法；一个事实引用的 `documentId` 必须确实在本次官方来源集合内。
2. `page` 必须存在，`quote` 必须能在该页归一化文本中精确定位；失配条目拒绝入正式结论，记录拒绝原因。
3. `MODEL_INFERENCE` 不得伪装公司结论。涉及具体数值差异的推导由程序按原文结构化数字核验；不能不加验证复述模型生成的百分比。
4. 有明确反证时必须尽可能展示；如果由于截断没审阅，覆盖标 `PARTIAL`，不能宣称“无反证”。
5. 模型失败只影响语义分析，原文列表/技术分析保留。
6. 保存 `modelId, modelParams, promptVersion, schemaVersion, requestHash, rawResponseHash, validatedJson, rejectedItems, coverageJson`；**重现**是从冻结的模型输出与原始证据重算规则，不保证重复请求模型返回逐字一致文本。

## 5. REST API 合约与错误

| 方法 | 路径 | 行为 |
|---|---|---|
| GET | `/api/v1/securities/resolve?code=002463` | 按唯一身份解析，非法/不唯一 422 |
| POST | `/api/v1/analyses` | `{ "code": "002463" }`；立即返回 202 + `runId,status=QUEUED`，后台有限线程池处理**这次用户请求** |
| GET | `/api/v1/analyses/{runId}` | 查询 `QUEUED/RUNNING/COMPLETED/PARTIAL/FAILED` 与报告 |
| GET | `/api/v1/analyses?code=002463&page=0&size=20` | 返回只读历史列表/来源覆盖状态 |
| GET | `/api/v1/analyses/{runId}/plan-evaluations` | 只读历史计划的后验评估 |
| POST | `/api/v1/plans/{planId}/evaluations` | 用户主动触发 D+1 重核，结果只追加；采用目标日期+输入指纹保证幂等 |
| GET | `/api/v1/disclosures/{documentId}` | 官方来源元数据与页码，不做任意 URL 文件代理 |

建议分析报告 JSON 顶层：

```json
{
  "runId":"uuid", "canonicalCode":"002463.SZ", "identity":{"name":"...","exchange":"SZ"},
  "createdAt":"ISO-8601", "asOfTradeDate":"YYYY-MM-DD", "knowledgeCutoff":"ISO-8601",
  "status":"PARTIAL", "technicalStatus":"READY", "eventStatus":"UNAVAILABLE",
  "dataQuality":{"provider":"baostock","barsValid":120,"gaps":[],"lastFinalizedDate":"YYYY-MM-DD"},
  "candles":[], "indicators":{"ma20":"...","ma55":"...","atr14":"..."},
  "trend":{"state":"UP","reasons":[]},
  "support":{"valid":true,"center":"...","lower":"...","upper":"...","source":"MA20"},
  "resistance":{"valid":false,"reason":"NO_VALID_CANDIDATE"},
  "buyPlan":{"id":"uuid","baseTradeDate":"YYYY-MM-DD","targetTradeDate":"YYYY-MM-DD","status":"WAITING_NEXT_BAR"},
  "sellReview":{"state":"NOT_TRIGGERED"},
  "eventReview":{"state":"UNKNOWN"}, "facts":[], "followUps":[],
  "coverage":{"state":"UNAVAILABLE","reason":"OFFICIAL_SOURCE_UNREACHABLE"},
  "provenance":{"techRuleVersion":"TECH-R1","providerFetchAt":"ISO-8601","inputHash":"sha256"}
}
```

**错误结构**：`{"code":"MARKET_DATA_STALE","message":"行情只更新到...","stage":"MARKET","retryable":true,"details":{}}`。业务缺口可生成 `PARTIAL`，不统一抛 500。状态为 `UNKNOWN` 时所有值为空，不得默认为 0。

**服务边界**：只绑定 `127.0.0.1`，前端开发端口 CORS 精确白名单，不用 `*`；不要把 API 暴露到 `0.0.0.0`。不允许浏览器直接持有 LLM API key/数据源凭证。

## 6. 数据库：五张核心表 + 文件仓

| 表 | 关键字段 | 特性 |
|---|---|---|
| `securities` | canonical_code PK, code, name, exchange, type, list_status, provider, updated_at | 证券主数据，不通过模式猜股票 |
| `market_snapshots` | id, canonical_code, as_of_date, provider, fetched_at, raw_jsonb, qfq_source_jsonb, normalized_jsonb, calendar_jsonb, quality_jsonb, input_sha256 | 每次技术输入冻结；以分析 ID 关联 |
| `disclosures` | doc_id, canonical_code, title, published_at, official_url, pdf_path, pdf_sha256, pages_jsonb, fetch_status | 允许文档下载幂等、原始文件 hash 标识版本 |
| `analysis_runs` | run_id, canonical_code, created_at, status, stage, market_snapshot_id, report_jsonb, tech_rule_version, prompt_version, report_hash, error_jsonb | 运行状态可改变；终态的**报告字段不可改**，每次新分析新 run |
| `plan_evaluations` | id, plan_id, base_run_id, target_date, evaluated_at, status, input_sha256, record_jsonb | **只追加**后验记录；不更新旧报告 |

文件仓 `data/disclosures/<safe-doc-id>/<sha256>.pdf`（gitignore）；DB `timestamptz` 保存时点，`date` 保存交易日，hash 与版本确保重放。相关二级数据（证据、模型输出）可首版存 JSONB，而非为了规范化再创建十几个表。

**快照不变量**：`analysis_runs` 一旦终态不可重写 `report_jsonb`；修正必须产生新 run。`plan_evaluations` 追加新记录，重复读取同一输入 hash 不重复增加相同事实；较晚取得合法 D+1 源数据时可追加新“补验”版本，并保留旧 `NEEDS_RECHECK` 记录。

## 7. 可运维性与安全

- `.env.example` 仅占位；真实 `.env`、本地 PDF、日志、用户资料、缓存/数据库、API Token 禁止提交 Git。公开仓库 commit 前必须检查 secrets。
- BaoStock Python CLI 以 `ProcessBuilder` 调用参数数组，不拼接 shell 字符串；限制超时、stdout JSON 上限与返回码；调用锁或限流避免频繁登录/失败打爆上游。
- 外部调用统一记录 `provider, requestedAt, fetchedAt, sourceAsOf, status, errorCode`；日志不回显私有令牌、PDF 原文大段正文或用户账户信息。
- 报告有 `codeVersion, techRuleVersion, promptVersion, providerVersion, schemaVersion, sourceHash`，可回放；没有来源链路即不发布事实结论。
- 单人本地运行暂不做认证，但必须固定 loopback，HTTP 安全响应头、受控文件读写路径；用户若后来提出远程/公网使用视为新产品需求。

## 8. 实施路径与验收门禁

### Gate 0｜免费数据与证据源 Spike

交付：`docs/data-provider-spike.md`，真实沪/深/北、停牌和除权样本。重点测试 BaoStock 可达、120 根、raw/qfq 日期/价格比较、终值资格、交易日历、公告 PDF。未经验证不能写“全部市场支持”。

### Slice 1｜真实行情 + TECH-R1 + 界面

- `SecurityResolver` 和 BaoStock CLI adapter 完成同源主数据。
- `MarketDataProvider` 和 `DataQualityValidator` 具备 fail closed 语义、原因码、来源元信息。
- 纯 Java `TechR1Engine` 实现上述所有边界；JUnit 测试涵盖 59/60/61 根、ATR 首次可用位置、等号、数据冲突、跨停牌、重叠区域。
- 可使用真实数据返回趋势、价区、冻结计划、卖出复核；页面四个主要区按原型布局（事件区域此时明确 `NOT_IMPLEMENTED`），图来自报告 JSON。
- 可一键启动并调用真实分析 API；不是只有 Mock 页面/Stub 数据。

### Slice 2｜官方披露 + LLM

- 实现90天公告与最新一份定期报告，记录分页/来源与缺口。
- PDF 页级文本和引用验证；关键事实最多 5、后续核验最多 3、反证与缺口明确。
- 严格 Schema，单模型失败只降级事件区；保存 prompt/version/hash。

### Slice 3｜快照 + 完整验收

- 完成只读历史、追加式 D+1 复核接口及老计划状态读取。
- Postgres/Flyway/Testcontainers 与 Vue 实际构建通过；运行状态、失联、数据缺失测试。
- 10 只真实股票验收：**零严重错误，至少 8 份可核验/有用降级结果**；页面 1440×900 + 390px 通过，更新状态真实。

### 定义完成 (Definition of Done)

只有同时满足：`mvn test` 实际通过、`npm run build` 实际通过、Python bridge tests 实际通过、Docker/PostgreSQL migration/真实分析 E2E 通过、官方原文引用校验通过、10 只真实股票验证通过，并形成证据文件，才可以标记 V0.02 验收完成。不能把 `javac` 纯规则自测误报为 Spring 集成全绿。

## 9. 核心测试用例索引

| 编号 | 输入 | 预期 |
|---|---|---|
| T01 | 59 根有效 bar | 趋势 UNKNOWN，MA55 可显示，MA55(t-5) 不可用 |
| T02 | 60 根有效 bar | 趋势可以确定（若数据资格满足） |
| T03 | 61/120 根 | 结果正确并不读取未来第 121 根 |
| T04 | C == MA20、均线平斜率 | 严格不等不成立 → MIXED |
| T05 | ATR 14 TR 首次可用（15 bar） | 不 off-by-one |
| T06 | 支撑上沿 >= 压力下沿 | 两区无清晰区域且标记 ZONE_OVERLAP |
| T07 | D 分析生成计划 | WAITING_NEXT_BAR，不检查 D 本日回踩 |
| T08 | D+1 最低价等于支撑边界 | `low` 区间边界含等号；其余条件严格大于 |
| T09 | D+1 close == support.upper | 不触发买入观察 |
| T10 | D+1 close < support.lower | INVALIDATED |
| T11 | D+1 未触发但数据已完成 | EXPIRED_NO_SIGNAL；D+2 再碰不能复活 |
| T12 | D+1 停牌或未收定 | NEEDS_RECHECK；不顺延；后补验只查 D+1 |
| T13 | D+1 除权价不可比 | ADJUSTMENT_CHANGED_RECHECK，不跨基准比较 |
| T14 | 已触发后再次跌破旧下沿 | 追加 INVALIDATED_AFTER_TRIGGER，旧结论不改 |
| T15 | 连续开放日两日 close<各自 MA55 | PRICE_RISK_REVIEW；中间停牌时 UNKNOWN |
| T16 | 官方 PDF 引用页码/引文失配 | 拒绝事实进入正式结论 |
| T17 | 证券输入纯码/后缀码 | 解析唯一 canonicalCode、历史统一 |
| T18 | 旧报告重开且供应商数据已变 | 原快照完全一致；新分析生成独立 run |
| T19 | 技术源正常但公告或 LLM 挂了 | 技术可用，事件部分降级并展示具体原因 |
| T20 | 北交所数据源没有覆盖 | 明确 COVERAGE_UNAVAILABLE，不伪造通过 |

## 10. 依据与参考链接（供 Codex 核验，不授权扩功能）

- BaoStock Python API：https://github.com/zxygithub/baostock/blob/master/docs/pythonAPI.md
- BaoStock PyPI：https://pypi.org/project/baostock/
- Spring Boot 系统需求：https://docs.spring.io/spring-boot/system-requirements.html
- Vue：https://vuejs.org/guide/quick-start.html
- ECharts：https://echarts.apache.org/en/index.html
- PostgreSQL：https://www.postgresql.org/docs/17/
- PDFBox：https://pdfbox.apache.org/
- 巨潮资讯：https://www.cninfo.com.cn/
- 上交所：https://www.sse.com.cn/；深交所：https://www.szse.cn/；北交所：https://www.bse.cn/

---

**变更控制：** 当前版本只允许修复实现和数据错误；新增指标、实时信号、组合/选股/Agent 属于 V0.03 候选，不在 V0.02 开发。
