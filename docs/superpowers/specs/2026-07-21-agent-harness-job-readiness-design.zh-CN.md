# Agent Harness 研发工程与求职作品设计

> 本文是中文评审副本。相邻英文文档是规范性的 AI 执行依据；若两者存在差异，以英文文档为准。

- 状态：已确认；bootstrap 实施计划已完成；尚未开始执行
- 日期：2026-07-21
- 决策人：用户
- 产品：InsightRadar，用户的第一个 OPC 产品
- 公开项目暂定名：EvidenceHarness
- 目标岗位：Agent Harness 研发／工程

## 决策摘要

InsightRadar 继续作为真正帮助投资决策的私有产品，同时成为通用 Agent Harness 的第一个真实实验场。项目不会被改造成只展示多个 Agent 的玩具。我们使用高风险、数据不完整、跨会话的投资与软件工程任务，量化 Context、Memory、Checkpoint、工具权限和受控 Subagent 是否真正提高可靠性。

采用“一项真实产品、一个复用内核、两个交付面”的路线：

1. InsightRadar 私下产生真实任务、失败、用户纠正和产品价值约束；
2. 通用 Harness 控制、观测和评测契约先在 InsightRadar 内通过清晰接口稳定；
3. 通用代码、合成任务、脱敏失败模式和可复现实验再抽取为公开 EvidenceHarness 项目。

第一版可投递公开作品周期为六到八周。投资价值仍是发布门槛：如果 Harness 改动让演示更好看，但让投资建议、时延、隐私或安全变差，就不采用。

## 当前基础与关键缺口

InsightRadar 已具备成熟的项目级 Coding Agent Harness：启动指令、分层项目记忆、特性状态、进度与交接、单功能范围约束、验证命令、真实产物检查，以及缺失数据时的失败关闭。目前结构验证为 100/100。

这只能证明结构齐全，不能证明 Harness 行为有效。求职所需的关键缺口包括：

- 版本化真实任务基准与基线对照；
- task trace、成本、时延、人工纠正和失败分类；
- checkpoint 与超长程恢复实验；
- context、memory 和 multi-agent 消融；
- 模型后端与 Harness 策略的分离比较；
- 可复用的公开实现和可复现实验报告。

此前 `feat-054` 计划覆盖产品实验治理和只读 Codex 角色，但执行被暂缓。本设计把目标扩展为可评测的 Harness 工程作品；此时仍不启动实现。

## 目标

### 产品目标

提高 InsightRadar 在长时间、中断、证据密集任务中的可靠性，同时保持来源、时间、未知项、隐私和无交易权限边界。

### 工程目标

建设与模型后端解耦的 Harness 控制面、观测面和评测面，用可复现实验证明 Context、Memory、Checkpoint 和受控 Subagent 在什么条件下有效。

### 求职目标

形成一套能够展示架构、实现质量、开发者体验、实验评测、失败分析、隐私工程和诚实负结果的公开作品。

## 明确不做

首个周期不做自动交易、无限递归 Agent swarm、基础模型训练、KV Cache 引擎、默认向量数据库、复杂 Web 控制台、云多租户和计费，也不公开持仓、券商数据、个人风控规则、密钥或原始私有对话。

## 总体架构

```text
InsightRadar 私有产品
  -> 真实投资／工程任务、失败和纠正
        ↓
Harness 控制与观测内核
  -> task/goal、context、memory、tool policy
  -> checkpoint、受控 agent orchestration、trace
        ↓
Harness 评测层
  -> 确定性验收、基线、消融、失败分类
  -> 成本、时延、恢复与安全指标
        ↓
EvidenceHarness 公开项目
  -> 通用 CLI、schema、合成任务、实验和技术报告
```

第一版不自研新的 LLM Agent Runtime。Codex、Claude Code 或其他兼容 Agent 是可替换执行后端；项目负责 Harness 契约、策略、trace、评测和采用决策。

## 组件与权限边界

| 组件 | 主要职责 | 权限边界 |
|---|---|---|
| Product Governance | 实验准入、容量、负责人门禁、复查与停止条件 | 不自动启动或改优先级 |
| Agent Contracts | 角色、输入输出、工具权限和写入所有权 | Agent 数量不是成绩 |
| Task Manifest | 目标、初态、工具、预算、产物和验收 | 引用私有数据，不内嵌 |
| Context Builder | 加载最小必要上下文并记录实际加载项 | 不默认加载全部历史 |
| Memory Adapter | 结构化读取、冲突与过期检测、提出更新 | 不静默覆盖正式记忆 |
| Tool Registry | 能力、副作用、超时、重试和批准策略 | 不隐藏破坏性行为 |
| Trace Recorder | 状态、工具、checkpoint、验证、成本和失败 | 不记录密钥和隐藏思维链 |
| Checkpoint Manager | 保存可恢复状态并验证目标连续性 | 不把聊天记录当唯一状态 |
| Evaluator | 确定性检查、失败分类和 profile 对照 | 模型裁判不是唯一验收 |
| Privacy Exporter | 分级、脱敏、泄密扫描和公开导出 | private/secret 导出失败关闭 |

现有计划中的 `stock_assist/product_governance.py` 和 `stock_assist/agent_contracts.py` 继续作为治理基础。新增通用评测能力先进入聚焦的 `stock_assist/harness_eval/`，等边界稳定后再抽取。

## 执行与 Trace

执行顺序为：

1. task manifest 声明目标、初态、权限、预算、验收和隐私等级；
2. Harness profile 选择 context、memory、agent 角色和恢复策略；
3. Agent 后端通过已声明的工具注册表执行；
4. trace 记录结构化事件和产物引用；
5. checkpoint 保存目标状态、已验证进度、待办和产物哈希；
6. 确定性验证检查测试、产物、状态一致性、权限和安全；
7. evaluator 统计结果、成本、时延、人工纠正和失败类别；
8. 新策略先 shadow 运行，达标后才能进入正式流程；
9. 公开导出只接收 public 或成功脱敏的 sanitized 数据。

Trace 使用版本化 JSONL，初始事件包括 `run_started`、`context_loaded`、`memory_retrieved`、`tool_requested`、`tool_completed`、`checkpoint_saved`、`checkpoint_restored`、`verification_result`、`policy_blocked`、`human_correction`、`failure_classified` 和 `run_completed`。

Trace 保存结构化状态、引用、哈希、时间、可得的 Token／成本、错误码和产物路径，不保存模型隐藏思维链。

## 隐私分级

1. `public`：可直接进入公开任务集；
2. `sanitized`：必须确定性脱敏并通过泄密扫描；
3. `private`：仅限本地评测；
4. `secret`：永不进入 trace，只记录可用性或脱敏错误状态。

持仓、券商导出、成本、账户标识、个人投资规则、仓库外凭据和原始私有对话属于 `private` 或 `secret`。只要仍有禁用字段、私有绝对路径、凭据模式或未分类载荷，公开导出就失败。

## 失败分类与恢复

至少覆盖：上下文缺失／误路由、记忆过期／冲突／错误召回、工具超时／拒绝／异常副作用、范围漂移、测试通过但真实产物错误、完成声明与状态不一致、多 Agent 冲突或重复、checkpoint 损坏或目标变化、证据不足却给行动建议，以及隐私／凭据泄露。

恢复不能掩盖失败。重试预算耗尽、状态不可信、验证器冲突或隐私分类不完整时，任务终止并保留诊断证据；投资工作流继续对新增风险敞口失败关闭。

## 评测设计

首批建立 20–30 个私有／脱敏任务，覆盖：新会话恢复、项目记忆路由、缺失持仓、公告与快讯冲突、新增与累计事实、中断恢复、代码／测试／真实产物／状态一致性、单功能范围控制、工具超时和隐私导出拒绝。

公开任务用合成公司、持仓、报告、工具、路径和凭据保留同样的失败结构。

四套基线为：

1. 无项目 Harness；
2. 只有根指令；
3. 当前 InsightRadar Harness；
4. 改造后 Harness。

主要指标包括确定性任务成功率、证据正确率、虚假完成、越权行动、范围漂移、隐私泄露、checkpoint 恢复率、context 恢复准确率、Token／上下文体积、工具调用、耗时、人工纠正，以及缺失或陈旧数据下的不当投资行动率。

模型裁判只能辅助评估表达和有用性；确定性契约和部分人工盲审是主验收。

## 采用与停止门槛

安全不变量：

- 关键测试中的未授权投资行动为 0；
- 关键隐私泄露、越权写入和虚假完成为 0；
- 缺失、陈旧和冲突输入 100% 显式暴露；
- 关键外部证据保留来源和时间；
- 不降低严格决策就绪覆盖率，不增加交易权限。

Checkpoint：受控中断恢复率至少 90%，目标漂移或恢复状态未经验证即算失败。

Context：Token 或上下文体积至少下降 25%，成功率下降不超过 2 个百分点，关键安全案例不退化。

Memory：跨会话 context 恢复失败至少下降 20%，且不增加陈旧记忆覆盖新事实；正式记忆更新仍需校验或人工确认。

Multi-Agent：只在可拆分的只读任务中评测。默认采用需要成功率至少提升 5 个百分点或显著减少关键遗漏，且 Token 不超过单 Agent 的 1.8 倍。否则保留负结果并继续默认单 Agent。

首轮基线后只允许有记录地调整一次阈值，必须保存原阈值、证据、新阈值和原因，不能反复移动目标。

## 六到八周路线

### 第 1–2 周：治理与可观测性

- 实施并升级暂缓的 `feat-054`；
- 一项活跃、两项排队实验；
- 主 Agent 唯一写入，只读非递归任务 Agent；
- 修复 `evolve` 全功能目录；
- 增加 task、trace、checkpoint、privacy 和 failure schema；
- 生成真实 agents/evolve 报告与 trace 冒烟证据。

### 第 3–4 周：真实任务评测

- 建立 20–30 个任务；
- 实现四套 Harness profile；
- 完成确定性验证和失败分类；
- 产出含成本、时延、纠正、恢复和安全指标的基线报告。

### 第 5–6 周：重点实验

- bounded context 与全历史消融；
- 结构化 memory 与仅聊天历史消融；
- 单 Agent 与一主多只读 Agent 消融；
- checkpoint 和中断故障注入；
- 只 shadow 采用达到门槛的策略。

### 第 7–8 周：公开提取与作品包装

- 抽取 EvidenceHarness；
- 发布合成任务和一键复现；
- 发布架构、隐私模型、失败目录和 benchmark；
- 发布中英文文档；
- 发布 InsightRadar 脱敏案例与 5–10 分钟演示脚本；
- 完成《从真实投资决策系统构建可评测 Agent Harness》技术报告。

## InsightRadar 集成边界

Harness 实验先在 shadow 模式运行，未达标前不能阻塞或修改正式的 `after-close`、`risk-watch`、`market-pulse`、portfolio-import 等 Core 流程。

预期产品收益是：新会话准确恢复组合来源、风险状态、待办和缺口；同一重要事件不重复处理；中断后不重复昂贵或受限数据源；需要时并行只读核验但保持一个最终结论；所有建议可追溯到来源、上下文、规则、验证和复盘。

## 公开项目边界

EvidenceHarness 不依赖 InsightRadar 私有数据或金融数据商，公开内容包括：通用 task/trace/checkpoint/policy/eval schema、运行 profile 与汇总结果的 CLI、合成任务、故障注入、可复现 benchmark、隐私和泄密门、架构与开发者指南、失败分类、限制，以及脱敏的 InsightRadar 案例。

公开项目如实报告负结果。除非受控实验证明，不声称优于某个模型或其他 Harness。

## 优先级与状态转换

用户已明确批准把 Agent Harness 求职工程放到 `feat-044` 之前，确认了本书面规范，之后又明确恢复项目并授权编写实施计划。Bootstrap 计划是 `docs/superpowers/plans/2026-07-21-agent-harness-bootstrap.md`。在用户选择执行方式前，仓库 feature 状态继续不变：`feat-054` 未注册、未激活，`feat-044` 和 `feat-055` 保持 pending。

只有用户选择执行方式后：

1. 使用 bootstrap 新计划；与 2026-07-19 旧治理计划冲突之处由新计划取代；
2. 在实施前把 `feat-054` 注册为活跃 bootstrap feature；
3. 一致更新 `CURRENT_STATE.md` 和产品治理状态；
4. 每次只实施一个可独立验证的增量；
5. `feat-054` 完成前，`feat-044` 和 `feat-055` 继续 pending，除非用户再次改变优先级。

计划完成本身不授权注册 feature、派发实施 Agent 或改变正式产品行为。

## 最终验收

- `feat-054` 的治理、Agent、trace、checkpoint、privacy 和 evaluator 契约全部通过；
- 20–30 个任务和四套 baseline 可复现运行；
- Context、Memory、Checkpoint、Multi-Agent 实验同时报告收益和失败；
- 未授权行动、隐私泄露、越权写入和虚假完成的关键计数为 0；
- 正式投资流程没有安全或严格决策就绪回退；
- EvidenceHarness 能在干净环境中按一个文档化命令运行；
- 中英文文档、benchmark、限制、案例研究和演示完整；
- 审阅者无需访问真实持仓或私有仓库状态即可复现核心结论。
