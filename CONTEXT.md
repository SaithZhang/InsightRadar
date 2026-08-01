# InsightRadar Decision Context

This context names the position evidence used to separate current risk decisions from historical strategy review.

## Language

**Original Entry Thesis（原始买入假设）**:
The user-recorded reason for opening a position. If it was not recorded at entry time, it remains `unknown` and is not reconstructed later as fact.
_Avoid_: using the overloaded term “买入逻辑” for both a historical thesis and a current risk rule

**Original Entry Invalidation（历史失效条件）**:
The entry-time condition that would have disproved the original thesis. Missing history limits strategy review but is not itself a current risk rule.
_Avoid_: backfilled stop line, hindsight invalidation

**Current Risk Rule（当前风险规则）**:
A present-tense, user-reviewable condition for observing, reviewing, or changing position risk. It is distinct from the reason the position was originally opened.
_Avoid_: original thesis, historical stop line

**Current Decision Context（当前决策上下文）**:
The current risk rule and review state needed to evaluate a present plan. Missing or conflicting current context blocks that plan.
_Avoid_: treating all historical position memory as a current authority requirement

**Historical Entry Context（历史买入上下文）**:
The original entry thesis and original invalidation used to evaluate strategy discipline. Missing history remains visible and limits review quality without blocking a current risk plan.
_Avoid_: current decision context
