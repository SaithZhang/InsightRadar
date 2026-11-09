# 可核验实例（全部数值例子为合成测试，不是真实股票结论）

TECH-R1 纯函数：`server/src/main/java/io/insightradar/v002/technical/TechR1.java`。
输入快照：`market_snapshots.source_jsonb` 保存完整 raw/qfq/calendar/events；`normalized_jsonb` 保存 Java 规范化输入。
模型 Schema：`server/src/main/resources/schemas/evidence-v1.json`；提示版本 EVIDENCE-P1；报告版本 report-v1。

冻结计划 D=2026-11-06，固定目标 D+1=2026-11-09，冻结区 [10,12]：

| D+1 输入 | 结果 |
|---|---|
| O=12,L=10,C=13，完整、同口径 | TECHNICAL_CONDITION_MET |
| O=11,L=10,C=12 | EXPIRED_NO_SIGNAL（收盘等于上沿） |
| O=11,L=9,C=9.9 | INVALIDATED |
| D+1 停牌 / 无终值 | NEEDS_RECHECK / WAITING_NEXT_BAR |
| D+2 有触及价格，但 D+1 缺失 | NEEDS_RECHECK，不能改 targetTradeDate |
| D+1 除权口径不可比 | ADJUSTMENT_CHANGED_RECHECK |
| 已有触发记录，之后完整日 C=9 | 追加 INVALIDATED_AFTER_TRIGGER |

`TechR1Test` 与 `PlanReviewTest` 验证边界和目标输入幂等；`PostgresIntegrationTest` 在真实 PostgreSQL 上证明 UPDATE/DELETE 终态报告、市场输入、文档与评估受限。模型事实/页码/引文造假由 `EvidenceTest` 拒绝。无事实不得输出“无风险”。

独立数值核验：Maven 写出 `server/target/technical-vector.json`，Python Decimal 50 位参考脚本逐项对账 MA20/MA55/五根前均线/Wilder ATR14，容差 1e-28。测试参考不进入运行链路。
