# InsightRadar V3.0 Pilot — Scope Frozen

## 材料用途

本包用于外部专家评审已通过 P0 验收的 InsightRadar V3.0 Pilot。评审重点是安全、状态一致性、真实晨间使用价值和试用观察设计，不再征集四页信息架构、核心闭环或责任边界的改版方案。

## 冻结状态

- 正式版本标记：**InsightRadar V3.0 Pilot — Scope Frozen**
- P0 验收通过时间：2026-07-25（Asia/Shanghai）
- Git 基线：`14caf531c830606a0571fa6a18fb6db5d9713445`
- 快照性质：该 Git 基线加当前工作区；P0 代码与材料尚未整理成独立干净提交。
- 冻结范围：今日计划、组合风险、标的研究、复盘账本四页；规则优先、人工确认、无自动交易的责任边界；`Observe -> Explain -> Decide -> Verify` 核心闭环。

## P0 验收结论

- 真实 after-close 产物已生成；
- 今日数量严格等于当前需要人工处理且为 `pending` 的计划数；
- `blocked` 计划无法采纳，只能确认知悉、提出异议、稍后或作废旧计划；
- 首次生成、规则/版本变化和仅执行状态变化已分离；
- 全量测试 250/250 通过，三项专项测试 3/3 通过；
- 四页浏览器运行错误和控制台错误均为 0；
- 未启动 P1/P2。

## 建议阅读顺序

1. [12-外部评审导航.md](12-外部评审导航.md)
2. [01-产品概述.md](01-产品概述.md)
3. [03-功能地图与实现状态.md](03-功能地图与实现状态.md)
4. [04-核心用户流程.md](04-核心用户流程.md)
5. [09-运行结果与测试情况.md](09-运行结果与测试情况.md)
6. [10-已知问题与技术限制.md](10-已知问题与技术限制.md)
7. [13-Scope-Frozen与10次试用协议.md](13-Scope-Frozen与10次试用协议.md)

## 包内证据

- `artifacts/InsightRadar-V3.0-Pilot-Scope-Frozen-sanitized.html`：由当前生产 renderer 和状态契约生成的脱敏四页运行快照；
- `screenshots/09`—`12`：当前冻结版四页脱敏截图；
- `screenshots/01`—`08`：冻结前的历史设计探索，仅供理解演进，不能代表当前信息架构或实现状态；
- `diagrams/`：当前系统、闭环和责任边界；
- `review-delivery/codex-summary.md` 与 `extra-context.md`：执行摘要和负责人补充上下文。

## 隐私边界

材料不包含 `.env`、API Key、Cookie、真实券商文件、账户、真实持仓数量、成本、精确金额或私有报告。脱敏 HTML 和当前截图全部使用合成持仓；真实 after-close 只记录路径和验收统计，不被复制进分享包。
