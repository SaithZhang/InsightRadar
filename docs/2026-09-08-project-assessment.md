# InsightRadar 去留与 Mac 迁移评估

日期：2026-09-08。性质：研究建议，尚未实施合并、归档或产品路线变更。

## 结论

建议选择 **收缩保留、按能力归并**：Shadow-Portfolio 继续承担策略研究、验证和前向模拟主线；InsightRadar 暂停广泛功能开发，作为真实持仓决策与人工复盘的候选组件库和独立回退基线保留。先验证一个最小人工闭环，再决定是否保留独立运行台。当前不建议完整搬迁旧系统，也不建议直接合并两个仓库，更不建议删除代码。

这不是两个完全重复的项目。InsightRadar 问的是“我当前持仓有什么风险、计划是否要改、实际做得怎样”；Shadow 问的是“某种方法是否有效、如何验证、真实时间模拟表现如何”。两者共享行情、证据和复盘基础设施，但账户含义、决策权限和评价对象不同。

## 本次实际核验

- InsightRadar 当前 HEAD 为 `f0a1a9b`，最后提交时间 2026-08-21；距离本次检查约 18 天。更大的问题是旧运行状态未随下载迁移，不能仅按停更时间判废。
- 检查前工作树干净。`stock_assist` 有 99 个 Python 文件、43,206 行；tests 有 46 个 Python 文件、13,715 行。这是规模证据，不是质量或价值评分。
- 本机缺少项目 `.venv`、私有 `data/portfolio.json`、`.env` 和 reports；Git 下载不是旧业务状态的恢复。
- 在现有全局公开数据 Python 环境中运行了 9 个相关 unittest 模块：133 项全部通过。覆盖计划版本、持仓导入/管理、beta、日线契约、盘中规则、盘中证据、信号结果和刷新任务。
- 同一环境下 `python -m stock_assist.cli --help` 成功；系统 Python 执行 `scripts/validate_project_memory.py` 成功。
- 未安装或修改任何全局依赖，未启动银河/Docker，未访问真实账户，未运行实时报价、after-close 完整流程或 MCP 传输测试。未验证 Mac UI、调度或盈利效果。
- Shadow 的对照使用其当前本机源码和文档，包含尚未提交的工作；未将其工作树当作已发布基线，也未修改该项目。

复现测试（本次使用的现有环境，不作为未来正式启动依赖）：

```sh
/Users/zhangjiawen/.local/share/a-stock-data/venv/bin/python -m unittest -q \
  tests.test_decision_workspace tests.test_portfolio_import \
  tests.test_portfolio_management tests.test_portfolio_beta \
  tests.test_daily_kline_contract tests.test_intraday_radar \
  tests.test_intraday_evidence tests.test_signal_outcomes tests.test_refresh_jobs
```

## 重叠与独特价值

| 能力 | InsightRadar 当前情况 | Shadow 当前情况 | 建议归属 |
|---|---|---|---|
| 策略版本与实验 | 有因子 Lab、固定盘中案例回放；无已晋级因子 champion | 有冻结模板版本、快照、实验及比较；通用 Python 策略执行仍待实现 | 统一由 Shadow 承担，不再发展第二套 Lab |
| 前向模拟与账本 | 重点是人类计划响应和结果跟踪 | 独立模拟账户、Broker、订单/成交、证据及审计 | 由 Shadow 承担，禁止合并真实与模拟资金历史 |
| 真实持仓与计划管理 | 导入预览/批准、版本绑定、人工响应、过期计划撤权 | 当前以模拟账户为中心；人工运行台关联列为后续 P3 | InsightRadar 最值得保留的领域能力 |
| 数据质量与阻断修复 | ProviderResult、复权隔离、完整序列兜底、计划级 repair issues | 接收时间、证据冻结、模拟执行资格与来源检查 | 上游标准化进入 Gateway；各业务保留自己的资格判断 |
| 实际交易复盘 | 用户提供成交的分时复盘、MAE/MFE、信号 T+1/5/20 | 模拟成交复盘、实验逐笔结果 | 复用分析方法，保留执行来源和账本隔离 |
| 盘中风控 | 有风险/催化失败/机会/再进入规则与回放；实盘时点校准不足 | 有模拟风险与交易约束 | InsightRadar 规则仅作为待验证策略或风险假设 |
| 公告、行情、新闻、观点 | 存在独立采集与行业专项逻辑 | 也有采集，已提出 Gateway 统一计划 | 避免新增第三套采集；按现有独立项目契约逐项归并 |
| 前端与工作流 | Python 自包含 HTML、四个人工任务路由 | React 策略工作台、四个策略能力入口 | 暂不拼接菜单，不整搬旧页面 |

Shadow `docs/PRODUCT_DIRECTION.md` 已明确：人工 InsightRadar/Notion 是关联来源，后续优先连接成果，避免重复日报和知识库；它也明确通用代码策略尚未实现。因此不能用 Shadow 的未来规划宣称其已经替代全部 InsightRadar。

## 值得复用与不宜直接搬运的代码

优先复用并补齐跨系统契约：

1. `stock_assist/decision_workspace.py`：内容寻址计划版本、版本限定响应、过期状态和修复问题。
2. `stock_assist/portfolio_import.py`、`stock_assist/decision_workspace.py`、`stock_assist/refresh_jobs.py`：批准导入、空值保留、个性化与数据状态分离、可靠串行刷新。
3. `stock_assist/intraday/evidence.py`、`evidence_contracts.py`：决策时点与结果窗口分离的分时复盘。
4. `stock_assist/data_sources/contracts.py`、日线契约及相关测试：来源、时点、复权与隔离规则。
5. `stock_assist/signal_outcomes.py`：样本成熟度、结果跟踪和价格口径隔离；需要适配 Shadow 的对象标识，不能直接合库。

需要先参数化、验证或停放：

- `intraday/rules.py` 的 AccountRiskEngine 直接包含科技主题、40/50/60 集中度、固定利润金额和减仓范围。这些是场景假设，不能成为通用平台默认裁决。
- `workflows/after_close.py` 内仍有锂行业和特定股票同业分组。可保留为研究配置，不能扩大为平台硬编码。
- Factor Lab 没有经过验证的 champion；盘中案例不构成普适收益证据。历史文档明确十次晨间 pilot 未完成、IR-002 开盘校准不足。
- Crypto/RWA、X/NGA 和旧多代理治理功能保持冻结。独立 NGA 项目已经存在于工作区背景中，但本次未审计其接口，不能视为已完成替换。

## Mac 障碍分层

1. **基础逻辑：已有可运行证据。** 核心 Python 使用 pathlib 等跨平台机制，本次相关测试和 CLI 成功；无需因 Windows 出身重写业务层。
2. **启动与运维：明确需要改造。** `init.sh` 仍调用 `.venv/Scripts/python`；启动器和定时任务使用 PowerShell；AGENTS/CURRENT_STATE 仍声明 `D:\work\InsightRadar`。本次按用户明确指定的 Mac 工作区评估，未执行旧 Windows 路径。
3. **依赖与取数：主要迁移成本。** pyproject 将 AmazingData/tgw 等列为必装；after-close、beta 和其他工作流仍直接使用 AmazingDataClient。存在公开源适配不等于整个核心已能在无银河情况下运行。应将核心分析和供应商环境分离，公开源优先、银河只兜底，并保留全局技能与凭据位置。
4. **私有状态：需要独立恢复或重新开始。** 旧持仓、计划账本和报告未在此次下载中出现。不能用示例数据或今天的资料冒充旧记录；不恢复历史也可从新的真实快照开始。
5. **运行验收：尚未完成。** 当前环境缺 MCP/pydantic 等传输依赖，未验证服务安装；日历、数据口径、启动停止、刷新和重启恢复均需真实验收。

## 建议后续仅做一个受限验证

暂不继续旧路线的所有待办。若进入实施，先做“Mac 最小人工复盘闭环”：新建独立核心环境，修正入口；经用户批准导入当前快照或从明确合成样例开始；用公共数据获得当日有效证据；产生同版本 JSON/Markdown/HTML；记录一条人工计划响应；重启后恢复；向 Shadow 只读关联一个结果，不连接自主交易员上下文。

验收关注：真实日期和口径、未知不补零、旧计划不能继续授权、真实/模拟账本隔离、无手工修复即可重复启动、对照用户现有人工流程确实省时或发现遗漏。

建议给此验证一个最多 3 个工程日的止损预算（建议上限，不是已承诺工期），之后进行 5 个交易日的实际使用观察。此观察只判断使用价值，不能证明投资优势：

- 若频繁使用持仓风险与计划反馈，且和 Shadow 分工清晰：保留 InsightRadar 为轻量独立人工运行台，共用数据层。
- 若只使用复盘分析而不使用独立运行台：把通过验证的模块迁入 Shadow 人工计划/复盘领域，待功能和历史读取验证完成后归档旧运行台。
- 若用户现有 Notion/人工流程已经覆盖，且旧模块没有带来可验证帮助：归档 InsightRadar 应用，保留测试和参考代码，不再修复全部旧数据链路。

完整合并的前提是明确需要一个统一产品入口，并完成域对象映射。最少应区分 source/evidence、strategy_version、experiment、human_plan、execution_claim 与 simulated_fill；真实成交声明不等于券商验证成交，人工资料也不能进入隔离 AI 实验。

## 依据入口

- InsightRadar：`docs/PRODUCT_BASELINE.md`、`docs/V3.0_FROZEN.md`、`docs/V3.1_DELTA.md`、`CURRENT_STATE.md`、`docs/product-charter.md`、`docs/extractions/README.md`。
- 本次按 feat-058 精确读取功能记录和近期 progress；它仍等待最终用户验收，不标记完成。
- Shadow：`../Shadow-Portfolio/docs/PRODUCT_DIRECTION.md`、`../Shadow-Portfolio/docs/GATEWAY_MIGRATION.md`、`../Shadow-Portfolio/shadow_portfolio/workbench.py`。

本次只新增评估与进展记录；不改产品版本、功能状态、实际账户、运行源或任何远端仓库。
