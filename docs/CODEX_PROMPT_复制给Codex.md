# Codex 开发任务｜InsightRadar V0.02 单股决策分析 MVP

> 将本文件连同 `docs/01_PRD_产品需求_冻结版.md`、`docs/02_TECH_技术设计_实施版.md`、`prototype/index.html` 放在 Codex 能读取的同一工作目录（建议解压 `InsightRadar_V0.02_Codex_Handoff/` 到仓库根目录），然后**把下面“开始执行”到“结束”之间的内容完整粘贴给 Codex**。

---

## 开始执行（粘贴此段）

你是 InsightRadar 的主程与测试负责人。现在执行一个**已经由产品负责人确认并冻结**的新项目：**InsightRadar V0.02｜单股决策分析 MVP**。不要再与我讨论要不要做、不要设计新需求。任务是把该 PRD 落到**可在本地启动、用真实市场数据核验、结果可复现的完整代码**。

### 0. 先读文件与工作区，不要盲写

1. 先确认当前 Git 仓库、分支、`git status --short`，读取根目录 `AGENTS.md`、`CURRENT_STATE.md`、`PROJECT_MEMORY.md` 与适用的 repository 约束。不要覆盖现有未提交变更。
2. 读取以下文件（相对仓库根目录，若解压目录名不同请按实际路径查找）：
   - `InsightRadar_V0.02_Codex_Handoff/docs/01_PRD_产品需求_冻结版.md`（**业务真相 / 最高优先级**）
   - `InsightRadar_V0.02_Codex_Handoff/docs/02_TECH_技术设计_实施版.md`（技术与测试方案）
   - `InsightRadar_V0.02_Codex_Handoff/prototype/index.html`（HTML/CSS 视觉及交互参考，不是数据源）
   - `InsightRadar_V0.02_Codex_Handoff/README.md`（交付说明）
3. 在现有 `InsightRadar` 主仓库中开发时，请保持旧 Python V3.1 系统和四个既有路由原样，**新增或维护隔离目录 `insightradar-v002/`**；不要用这次工作修改旧产品主线、持仓/账户数据或现有自动化。
4. 如果当前工作树已有此前交付的 `insightradar-v002/` 切片一代码：**先审计可编译性、真实依赖、真实数据和测试**，合格的直接复用，不合格的重构/修复；不能默认“之前已验收”。如果不存在，按 TECH 文件创建。仅需一个后端服务、一个数据库、一个单页面。
5. 在动代码前写入一份简短的实现顺序与“完成/未完成判定”到 `insightradar-v002/docs/IMPLEMENTATION_PROGRESS.md`。不必为此等待我再次确认。

### 1. 产品与技术不能偏离的规则

- 技术栈：Java 21、Spring Boot 4.1.x、Vue 3 + TypeScript + Vite、Element Plus、ECharts、PostgreSQL 17 + Flyway、PDFBox；**BaoStock 免费数据优先**，Tushare 不作为本版必需依赖。
- 数据适配层：`MarketDataProvider`，通过真实 BaoStock Python CLI 取得 raw/qfq/日历/身份/停牌，独立做数据资格校验。已有同花顺 Fuyao 在 ChatGPT 中已证实有历史日 K，但并不等于你的本地环境可以调用；**只有拿到实际可用的本地访问 URL/鉴权后**才做可选 FuyaoAdapter。不能伪造凭证、接口或数据。北交所必须真实测试，覆盖不足不得假称通过。
- 只分析最近目标 120 根**已完成且能确认终值**的前复权日 K；程序计算 MA20、MA55、Wilder ATR14、UP/DOWN/MIXED/UNKNOWN、支撑压力中心与 `0.5×ATR14` 半宽。数值逻辑只能在 Java 计算，严格比较不能因显示舍入改变结果。
- **买入计划方案 A 已冻结**：D 日只在 UP 且有有效支撑时创建不可变计划；仅用**下一交易所开放日 D+1**的完整 K 检查，条件 `low∈[支撑下沿,支撑上沿] && close>支撑上沿 && close>open`。收盘 `< 支撑下沿` 标 INVALIDATED；其他未满足的完整 D+1 标 EXPIRED_NO_SIGNAL。D+1 停牌/资料缺失不能顺延 D+2，也不能假装未触发；仅允许原 D+1 迟到数据补验。所有旧记录不可改，追加判定记录。
- 卖出：只有连续两交易所开放日各自 `close<MA55` 提示人工复核；停牌不能跳日拼接。
- 公告：最近 90 个自然日官方公告 + 最新一期真正已披露的定期报告。官方 PDF 与真实页码保存；LLM 只输出最多 5 条关键事实/风险、3 条待人工确认的核验点。逐项验证 `documentId + page + quote`；无真实引文不能进入正式事实。LLM 不能改写技术信号。
- 页面：只做一个“股票分析”主页面，包括趋势/K线、支撑压力、买卖条件、风险/证据，支持历史查看、来源与缺口详情。以 prototype 的视觉层级为参考，但**不要把里面的模拟价格、K 线、历史或公告写成正式运行数据**。
- 用户系统：本地单人，仅 `127.0.0.1`；无登录、微服务、消息队列、选股、实时盯盘、组合、回测、多 Agent、自动交易。`trade_authority=none`。

### 2. 严格按切片逐步交付（不要停留在计划）

**Gate 0：真实数据接入验证（优先执行）。** 用用户电脑能实际访问的免费接口测试沪、深、科创、创业、北交所各样本，验证合法代码、可用 K 数、raw/qfq 同源价格、复权因子口径、交易日历、停牌和未收定；检查巨潮/交易所能否合法自动拿到公告目录+PDF。把每项实测证据、命令、时间、缺口记录到 `docs/data-provider-spike.md`。如果北交所免费数据源不可用，提供明确 COVERAGE_UNAVAILABLE；不要强行猜值，也不要掩盖验收缺口。

**切片一：** 实现证券身份 → 真实日 K 与质量 → TECH-R1 纯函数 → 支撑/压力 → D+1 冻结计划 / 卖出复核 → Spring REST → Vue/ECharts 主页面。用独立参考对指标进行逐项对账；先验收真实 API，不要只演示 mock。

**切片二：** 实现官方公告/财报目录（分页及更正识别）→ PDF 按页提取 → LLM 严格 JSON Schema → 证据复核 → 风险卡/未来核验点。LLM 或官网不可用时保持技术分析可用；覆盖状态为 PARTIAL/UNAVAILABLE，不得假装 90 天资料已全部审核。

**切片三：** 实现 PostgreSQL 不可变报告快照 → 历史展示 → D+1 追加式后验结果 → 异常与等号/59-61 根/停牌/复权测试 → 10 只不同状态真实股票验收。关键路径 E2E 通过才允许写“完成”。

### 3. API、数据、测试交付要求

- API 以技术文档第 5 节为基准：解析证券、创建分析、轮询结果、历史、读取与主动复核 D+1 计划、公告文档信息。
- 所有报告带 `asOfTradeDate`, `knowledgeCutoff`, `source`, `priceBasis`, `technicalStatus`, `eventStatus`, `dataGaps`, `techRuleVersion`, `runId` 和可复核证据。
- 用 JUnit 5 + Testcontainers 验证真实 PostgreSQL；Python unittest/pytest 验证 BaoStock bridge；Vitest/Playwright 验证网页。至少覆盖 TECH 文档 T01–T20，尤其 59/60/61 根、严格等号、没有未来数据、D+1 不顺延、历史不可覆盖。
- 真实发布前完成 `mvn test`、`npm run build`、Python tests、Flyway migration、启动本地服务及**真实行情 E2E**，不能把 `javac` 的规则单测等同 Spring 完整运行。
- 启动必须简单：`README.md` 写清 `python venv`、数据库、Java、前端启动方式及停止方式，`.env.example` 只含占位。页面和 API 仅本机端口。
- 保留已验证数据与拒绝状态的区分，不允许 Mock fallthrough：如果没有真实行情，正式 API 就返回实际错误/UNKNOWN；只在明确标为 `demo` 的离线原型里用假数。

### 4. 工作方法与权限

- 自主修复编译/测试失败、优化结构，但**不得增加范围外功能**；不用问我每个微观实现细节。
- 不把真实持仓、账户、凭证、PDF 原件、.env、缓存或日志提交到仓库；公开 Git 改动先扫描敏感文件。已有 GitHub 仓库若需写入远端，**先本地完成并给出变更摘要，不要未经我明确许可自行 push、PR 或 merge**。
- 若某个外部数据源或 LLM 密钥不可用，继续实现可本地验证的其余部分，精确描述阻塞、所需配置和可重现步骤。禁止把未验证功能标记为 DONE。
- 每完成一个切片，更新 `IMPLEMENTATION_PROGRESS.md`：真实运行命令、测试数量、失败原因、文件清单、下一步。不要只回复“计划好了”。

### 5. 你最终必须交付

1. `insightradar-v002/` 完整源码（可执行启动，不是只有接口壳）。
2. `README.md` 的本地启动指引、环境变量表和数据源限制。
3. 测试代码与实际运行日志摘要，尤其数据 Gate 0、Spring/PostgreSQL、前端和 10 股票真实验收。
4. 版本化技术规则、LLM 原文证据 Schema、报告快照与 D+1 状态迁移的可核验实例。
5. 一个清楚的状态表：`DONE / PARTIAL / BLOCKED`，标出哪些功能确实实际运行，哪些仍缺真实授权/行情/公告，不能用原型代替验收。

**现在直接读取文件、检查仓库、开始编码和测试；能验证的部分当轮做完。**

## 结束
