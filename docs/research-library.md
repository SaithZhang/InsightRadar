# Research Library：职责、最小模型与验证计划

日期：2026-11-08（Asia/Shanghai）。需求：`IR-BL-RLIB-001`；首个来源：`IR-BL-ZSXQ-001`。状态：**需求与边界已登记，产品模块未实现、未排期**。

本文件是现有需求池的工程细化，不另建产品版本。产品仍为 V3.1；Control 的 V0.01 是需求目录中的冻结切片，两者不是同一版本号。不得把本需求自动加入 V0.01，亦不启动 V3.2。业务需求主入口为原 [Notion 需求池](https://app.notion.com/p/41244bc3d1cd81e592aad8579bbd9b45)，本地副本为相邻 `InsightRadar-Control/PRD-InsightRadar-Agent-Pilot.md` 第 13 节；工程状态见 [feature_list.json](../feature_list.json) 与 [V3.1 Delta](V3.1_DELTA.md)。

## 本次范围与停止条件

只检查目录、模型和技术栈，登记模块职责、接口草案、已有证据及后续计划。验收为：沿用既有编号；来源能力与缺口有出处；原件/派生结果/权限分开；规划与运行图明确区分；项目记忆与文档一致性校验通过。达到即停。

本次不安装 Skill/MCP、不登录或刷新会员权限、不重新采集帖子/附件、不调用模型、不迁移资料，也不实现下述接口。历史验证只证明当时、指定样本可用，不能当作当前完整来源或产品集成验收。

## 定位与职责

Research Library 是 InsightRadar 内部统一研究证据模块：把非结构化资料变为可存储、可检索、可引用、可追溯的证据。**管理研究证据，不形成投资决策；Discovery ≠ Permission；trade_authority = none。**

| 职责 | 目标与边界 |
| --- | --- |
| Connectors | 每个来源独立适配；平台响应止于适配器。首个验证对象为知识星球「前沿信息收录」；手动取得与有界增量同步分期，不在业务模块内写采集逻辑 |
| Ingestion / Parsing | 提取、清洗正文，解析 PDF/Markdown/TXT；保留原件、附件、来源和元数据；记录取得及处理时间、失败、截断和缺页；不从文件名补写正文 |
| Evidence Store | 统一身份、来源关系、版本、原文与解析产物引用；区分第三方观点、预测、传闻及 AI 提取；不保存交易权限或研究卡状态 |
| Retrieval | 先关键词和公司/标的/行业/时间/来源过滤，返回原文定位及附件访问状态；语义/混合检索待真实需要，不以摘要替代证据 |
| 数据质量 | 来源 ID 与指纹去重、转载谱系、点时版本、解析失败、权限与使用限制可见；第三方观点不升级为事实，小作文/传闻保持未证实 |

Meet Kevin 字幕/原始观点属于后续来源候选；公司公告、财联社、券商资料按实际缺口评审。正式产品不依赖某位创作者或跟单身份。

## 已有工程盘点（代码基线 d8772e0）

| 当前路径 / 模型 | 已有能力 | 复用方式与缺口 |
| --- | --- | --- |
| [pyproject.toml](../pyproject.toml)、[portfolio_import_server.py](../stock_assist/portfolio_import_server.py) | Python ≥3.10；pandas、pypdf、pydantic、requests；本机 Python/HTML 与 loopback 服务 | 同一包、部署和四路由；无新框架/服务/客户端 |
| [data_sources/](../stock_assist/data_sources/)、[ProviderResult](../stock_assist/data_sources/contracts.py) | 独立来源适配；provider/source_time/fetched_at/status/gaps/errors | 复用来源边界与失败语义；不把股票行情的 trade_date/price_basis 强塞给文档模型 |
| [ResearchReport](../stock_assist/data_sources/eastmoney_reports.py)、[research_monitor.py](../stock_assist/workflows/research_monitor.py) | 研报标题、机构、作者、发布日期、代码/行业/原文/PDF 链接；ReportExtraction 状态与 ThesisDelta、JSONL 去重 | 复用已有输入与有限 PDF 能力；现有 ThesisDelta 是消费者分析，不迁入资料库，不宣称已有统一跨来源谱系 |
| [research_filings.py](../stock_assist/research_filings.py) | 受限 PDF 子进程读取、分页、原件、模型草稿与引用 | PDF 读取最多前 16 页，存在页内截断；未来接入须显式报覆盖。财务提取/草稿采纳留原模块，不能为 ZSXQ 放宽公告 URL 白名单 |
| [research_board.py](../stock_assist/research_board.py) | `data/research-board.json` 原子保存、卡片版本/事件、人工采纳 | 原卡与历史保持；消费者以后引用资料版本，不把卡片 schema 变成 Store 模型 |
| [refresh_jobs.py](../stock_assist/refresh_jobs.py) | `data/insightradar_state.sqlite3`；evidence_items 是绑定 workspace/run 的证据镜像 | 已有 SQLite 可作为未来索引实现候选；该表不是资料库，不直接复用其主键或引入 RefreshCoordinator/账户依赖 |
| [zsxq_pdf.py](../scripts/zsxq_pdf.py)、[用法](zsxq-single-pdf.md) | 官方 CLI 元数据、Cookie/Python 下载、完整性校验与本地分页；显式清单 ≤20、串行首错停止 | 保留工具及既有文件。未有统一 Connector、增量同步、全文索引或研究卡接入；不重写下载器 |

现有数据使用本地 JSON/JSONL、文件和 SQLite。最小落地先引用现有原件与分页文件，复用原子写入/哈希方式；数据库文件、表和索引选择在首个获准切片中确定，不预建新数据库，也不默认复制/迁移私库。SQLite 全文索引仅在普通检索确有瓶颈、目标环境能力验证后评估；现在不引入向量库、消息队列或新依赖。

## 模块边界与依赖方向（规划）

```text
手动文件 / 独立 Connector
          ↓ 统一来源记录
     Ingestion → Parsing → Evidence Store
                                ↑
                           Retrieval
                                ↑
     Thesis / 产业研究 / Journal / Review / 内部 Agent
```

可选目录为 `stock_assist/research_library/`，**尚未创建**。只需将连接、解析、存取和读取职责分开，不要求每项一个服务或抽象基类。消费者依赖统一读取接口；资料库不 import 研究卡、持仓、策略或交易模块。外部响应与凭据仅由 Connector 处理；业务不能依赖原始 ZSXQ JSON。现有流程不自动迁移，首次接入只加一个消费者的窄调用。

| 消费者 / 责任方 | 可以消费什么 | 资料库不负责什么 |
| --- | --- | --- |
| Thesis Book | 资料版本、引用、反证来源、覆盖缺口 | 形成/更新/证伪投资逻辑；不得直接写 Web/Human 所有的 Thesis |
| 06 产业逻辑 | 多来源、机构、日期及产业实体索引 | 产业趋势与产业链判断 |
| Daily Journal / Review | 当时可见资料的固定引用、失败与更新记录 | 交易日记、复盘结论、研究有效性评价；反向“某假设用了哪些资料”关联由消费者保存 |
| Strategy / Rulebook、Risk / Rulebook | 经消费者核验后的证据引用 | MA55、入退场规则、仓位/风险预算、Permission |
| Trading | 无执行入口 | BUY/SELL 输出、下单、交易确认；InsightRadar 无自动交易 |
| Meet Kevin 05C/05D | 未来按需复用存储/检索 | 现有视频采集和观点处理保留，不立即重构；编号指现有业务模块，不假定本仓库已有同名 Python 包 |
| 未来 Agent / Eval | 可追溯原文与派生结果 | 策略自进化、模型晋升、自动授权 |

内部读取合同草案（不是已发布 API，签名实施时确定）：

| 操作 | 输入 | 最小输出 |
| --- | --- | --- |
| `search` | query；公司/代码/产业/时间/来源过滤；limit/cursor；可选 as_of；授权上下文 | 命中列表、EvidenceRef、来源/发布时间、片段定位、处理状态、已知覆盖范围/截断/缺口；零命中不证明来源没有资料 |
| `get_document` | evidence_id + revision_id + 授权上下文 | 固定版本原文/元数据/出处及访问状态；不默认用最新版替换历史引用 |
| `get_attachment` | EvidenceRef + attachment_id + 授权上下文 | 允许时返回本地附件引用；否则明确 restricted/unavailable，禁止泄露签名地址/凭据 |
| `resolve_reference` | EvidenceRef + 授权上下文 | 原文页码/段落/字符或未来字幕时间戳、引文、原链接与可用性；原件不可得时返回缺口，不生成替代原文 |

手动采集和未来增量调用均走 Connector→Ingestion；不是消费者读接口的隐式副作用。只返回证据/质量状态，无投资结论或权限变更。未来 API/MCP 可包装这些合同；当前不增加 Server、远程传输或调度。

## 最小统一资料模型（逻辑草案，非数据库迁移）

以下为同一资料记录及关联对象的最小约束，可用简单字典/JSON 表达；不要求新 ORM。字段缺失用 null/unknown 和原因，不能猜测作者、机构、标题、日期、代码。

| 对象 | 最小字段 / 规则 |
| --- | --- |
| Document / Revision | `evidence_id`、`revision_id`、`schema_version`、`source_platform`、`source_id`（字符串）、`source_url`、`url_origin`（供应方返回/模板构造/手工）、`original_title`、`title_kind`（原题/展示摘要/缺失）、`raw_ref` 或原始正文、`attachments`、`author`、`publisher`、`published_at`、`collected_at`、`document_type`、`content_hash`、`processing_status`、`gaps`；发布原始值/时区/精度保留，来源未给时不以采集时间冒充发布时间 |
| 处理信息 | `parsed_at`、解析器及版本、总页数/已解析页数、正文范围/截断、错误码/脱敏原因、`previous_revision_id`；采集/下载/解析分别记录状态，`metadata_only`、`partial`、`failed`、`unavailable` 不算成功全文 |
| SourceOccurrence | 渠道/群组范围、source_id、原链接、发布者、转载时间与首次取得时间、指向固定资料版本；原作者/机构/报告日期与转发者/帖子日期分开，疑似原始来源标 unknown，允许原件来源未明 |
| Attachment | 附件来源 ID、原文件名、媒体类型、大小、SHA-256、本地引用、下载与解析状态、页数/范围、访问限制；附件元数据不等于附件全文 |
| EvidenceRef | `evidence_id` + `revision_id` + 可选 attachment_id + 原文定位（PDF 一基页码；文本段落/字符区间；后续字幕起止秒）+ 原文引文及 hash；定位基于保留的版本，清洗后须保留映射 |
| ExtractedClaim / DerivedArtifact | 主张或摘要/标签/实体、`claim_type`（observation/opinion/forecast/rumor/unknown）、`verification_status`、`origin`（source/human/ai）、支撑 EvidenceRef、生成时间、工具/模型/提示版本（若 AI）；允许一文多类主张，AI 提取出的原话仍是第三方主张，不变成已核实事实 |
| 可渐进补充的关联 | 公司、带市场股票代码、产业方向；每项标注人工/来源/AI 及依据，无法确认不强绑代码 |
| AccessPolicy | 会员/付费/保密/版权标签、权限来源与核验时间、允许的读者与用途、外部模型处理/再分发限制（allowed/denied/unknown）；未知不视为允许，内部 Agent 的授权也需匹配 |

原件不可变、AI 结果单独保存；AI 摘要、标签、结构化字段均须链接原件及生成依据。兼容现有 fact/inference/rumor/sentiment/unknown 时保留细分类和核验状态：观点/预测不能机械映射为 fact；来源官方或作者机构名本身也不证明主张为真。

去重两层：先按平台+来源范围+source_id 检查重复，内容 hash 相同保持幂等；同 ID 内容变化追加 revision，不覆盖旧正文。相同附件 SHA-256 可归为同一文档版本，但保留每次转载关系和各自访问限制；正文规范化指纹只作辅助，不能因同题/相似文本就合并。近似去重、原始发布者判定均可保持待核验。多份转载不能当作独立机构证据。

历史检索除 published_at 外还须约束 collected_at：后来发现的旧报告不能冒充当时已知。单页/部分检索须报告覆盖，不称“全月全部研报”；最早收录不等于全网首发。撤权后不能用缓存或公开转载放宽受限原件/派生摘要的分发；派生结果继承输入中适用的限制。权限失败保留允许保存的最小元数据和失败记录，不绕过控制。

## 首个来源：ZSXQ 技术可行性台账

目标为「前沿信息收录」。以下复用 2026-11-08 既有私有实测记录；本次只读核对，不重跑，不公开会员/附件正文及账号信息。

| 验证项 | 已有证据 | 仍需验证 / 后续通过条件 |
| --- | --- | --- |
| 官方 Skill/CLI 会员读取 | 用户 OAuth、目标访问、最新 30 条、四词搜索、两帖详情当时通过；`data/acceptance/zsxq-20261108/REPORT.md` | 新会话权限/到期需重验；不将登录等同于内容写权限 |
| 最新、历史搜索与原文链接 | 有界关键词搜索有结果；链接按真实 ID 和官方模板构造，未逐条打开 | 任意月份历史完整性、翻页、游标与删除/更新未验；一次明确时间窗的有界检查需报告页数/覆盖/未完成原因，并抽查来源链接 |
| 官方 MCP 附件能力 | `data/acceptance/zsxq-mcp-one-pdf-20261108/REPORT.md`：握手/详情成功，当时工具表无下载工具 | 不能称官方 MCP 已支持 PDF 下载；若后续新增，先验证一个指定附件，不猜测接口 |
| 授权附件原文 | 官方网页及既有 Cookie 工具读过同一份四页 PDF，大小/SHA-256 一致；`data/acceptance/zsxq-cookie-20261108/`，25 项合成测试为当时记录 | 只证明这个样本与通道。网站内部接口无稳定承诺；加密/扫描页、OCR、长期运行、多附件真实压力未验；当前解析器保留限制 |
| 统一资料模型与消费 | 本文件完成合同草案；原件及分页已有本地路径 | Connector、Store、检索、统一去重和消费者接入均未实现；一份指定资料按合同登记、重入幂等、定位原文及失败可见后才算切片通过 |

增量同步的后续合同：限定星球与窗口/页数/请求预算；仅在该页资料与处理回执持久化后推进游标，未完成页保持可重试；终止、限流、授权失败不写成功或完整覆盖。更新追加版本、重复不重复计证。此处只定义未来约束，不启定时器或批量历史回填。

## 后续顺序（未排期，无自动开工）

1. **需求/可行性阶段：本次到此。** 固定职责、来源台账、模型、消费者边界及验收。历史通过项不反复验证；其余缺口明确保留。
2. **首个候选切片：一份指定授权 ZSXQ PDF → 可追溯引用。** 用户明确准入后，以现有工具和本地原件登记最小资料；指定一张研究卡作为消费者。先检验 ID/版本/重复、页码/原文、受限访问/缺源/解析失败、重启后引用；不改 Thesis 或交易状态。先用已有样本，不为此创建平台或迁移旧流程。
3. **随后按缺口选择：有界历史/增量与关键词检索。** 单来源、明确时间窗；覆盖与权限可核验，重跑/中断恢复可复现；必要时才使用既有 SQLite 技术。不得与第 2 步并行启动。
4. **后排：** 实体索引、多来源转载谱系、Meet Kevin/公告等来源、语义/混合检索、API/MCP；需真实用例证明现有方式不足再准入，不预定版本/工期。

停止/否决条件：授权不清、下载通道不可用、无法定位原文、身份/版本冲突或重复计证不能解释时，不进入消费者集成；保留已有手动途径和失败证据。现有工具足以满足单份用例时，不因本规划重写它。

## 建成后的目标验收（当前未执行）

| 用户问题 | 资料库必须提供的证据 | 由消费者负责 |
| --- | --- | --- |
| 最近一月沪电股份有哪些券商研报？ | 明确日期窗口、机构/公司映射、来源/报告日期、去重后的版本与原文；覆盖不全明确说明 | 组织答案，不夸大全量 |
| 机构如何预测 PCB/CCL 需求与利润？ | 不同机构的预测原话、页码、前提/期间、日期，预测与事实区分 | 比较、解释分歧 |
| 某机器人消息最初来自哪里？ | 转载关系、最早已知来源及时间、仍缺的一手出处 | 在覆盖边界内表述，不能把最早收录说成首发 |
| 三个月 AI 数据中心 CapEx 观点如何变化？ | 带时间和版本的原始观点、反证与缺期 | 趋势判断；无回填当时未知信息 |
| 某投资假设引用了哪些原始资料？ | 按消费者保存的 EvidenceRef 解析到原件及固定版本 | Thesis/Review 持有假设→引用关系与研究结论 |

每条引用必须可解析或明确 unavailable/restricted；不存在的证据不能以生成文本补齐。产品验收须真实样本与失败样本通过，本次文档检查不等于这些能力已经建成。
