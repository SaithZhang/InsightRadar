# NGA 大时代监控

`nga-monitor` 是只读 Extension，不接入自动交易，也不作为 Core 决策链的硬依赖。

## 一次性保存登录信息

运行：

```powershell
.venv\Scripts\python -m stock_assist.cli nga-auth set
```

在隐藏输入提示中粘贴浏览器请求头里的完整 Cookie。Cookie 保存在
`%LOCALAPPDATA%\InsightRadar\secrets\nga_cookie.txt`，位于仓库之外，不会被 Git 提交。

查看是否已配置（不会显示 Cookie）：

```powershell
.venv\Scripts\python -m stock_assist.cli nga-auth status
```

删除本机 Cookie：

```powershell
.venv\Scripts\python -m stock_assist.cli nga-auth clear
```

Cookie 等同于账号密码。不要放入聊天、命令行参数、配置 JSON、日志或截图。

## 采集

```powershell
.venv\Scripts\python -m stock_assist.cli nga-monitor
```

每次运行会追加 `data/nga/board_snapshots.jsonl` 并生成一份 Markdown 报告。第一轮只建立
基线；第二轮起按相邻快照计算回复增量。HTTP 401/403 会明确提示 Cookie 失效或访问校验，
不会继续输出伪实时结果。

配置位于 `configs/nga_monitor.json`。`nga-monitor` 保留为事件日手动热度快照，不建议常态高频抓取。

## 一日报告与 AI 综述

手动、脱离 Codex 自动任务运行时，可选择外部 AI 生成主题综述：

```powershell
.venv\Scripts\python -m stock_assist.cli nga-daily --llm
```

程序通过 NGA JSON 接口采集当日主题、首帖和高赞回复；外部模型只返回主题聚类、综述文字和
引用的 thread id，链接、楼层、点赞和原文均由程序校验后回填，避免模型编造证据。每次
正式日报只调用一次 OpenAI-compatible API。若密钥、网关或模型输出不可用，仍生成明确
标注的规则降级版，不把关键词摘要冒充自然语言情绪判断。

AI key 通过隐藏输入保存在仓库外：

```powershell
.venv\Scripts\python -m stock_assist.cli llm-auth set
.venv\Scripts\python -m stock_assist.cli llm-auth status
.venv\Scripts\python -m stock_assist.cli llm-auth clear
```

默认兼容网关为 `https://aiapi.world/v1`，默认模型为 `gpt-4o-mini`；可用
`OPENAI_BASE_URL` 和 `STOCK_ASSIST_LLM_MODEL` 覆盖。不要把密钥放入聊天、命令参数、
配置 JSON 或 Git。

当前默认自动化不调用上述外部 API：08:50 运行 `nga-daily --window morning`，严格使用
当天 00:00–09:00 证据；15:50 运行 `nga-daily --window day`，严格使用当天
00:00–15:59 证据。两个分支均不带 `--llm`，再由 Codex 自动任务自身完成综述。写作质量
以 [NGA 大时代今日话题 2026-07-15](https://bbs.nga.cn/read.php?tid=47185220)
为合同样例，要求每个主题包含核心矛盾、多方分歧、论坛归因、情绪迁移、资金分流和隐含
判断，并回填真实相关主题与高赞回复。外部 API 代码与本地配置仅作为以后手动运行和调优
的备用路径。盘前扫描最多 5 页元数据并取 20 个详情；盘后扫描最多 10 页元数据并取 35 个
详情，以支持五个主题各自选择 4–6 条相关帖子。翻页只扩展候选元数据，不会对所有帖子抓
详情；详情请求约每 3 秒一次，优先读取首页，仅在首页没有时间窗内回复时补读末页。每个
时间窗仍只运行一次。

HTML 报告采用“视觉摘要 + 渐进披露”：首屏自动把固定字段渲染为今日结论卡、100%多空
构成条、风险偏好/恐慌/亢奋/分歧强度条、板块温度、大V信号和五个主题结论卡；完整综述、
相关帖子与高赞回复保留在默认折叠的证据区。自动任务必须保持固定指标行名，五个主题正文
控制在 120–180 字，先写结论再写最必要的分歧和证据。

## 大V观察名单

`configs/nga_monitor.json` 中的 `influential_authors` 使用稳定 UID 维护重点账号。当前名单包括
fuelish、文驹、幸运阿sai、-阿狼-、神之使Ty、铁锤狂砸盘、路过的帅小伙、Plezl、
村上吹树。大V主题会优先进入详情池，主题和回复均保留 `author_id`；报告把大V观点与大众
情绪分开，大V本人观点不重复计入大众看多/看空比例。

长期主帖通过 `tracked_threads` 显式维护。采集器使用 NGA 主题内 `authorid` 筛选页，只读取
指定 UID 的楼层，并从作者自己的末页向前回溯到报告时间窗；这能覆盖大V在旧主题里的盘中
更新，而无需扫描数千条普通回复。NGA 的作者筛选 JSON 对内容较长的页面可能截断，因此该
路径使用完整 HTML 响应并再次校验楼层作者 UID。窗口内回复、当日新主题和仅作背景的历史
活跃主题在 payload 中分开，未命中只能写成“当前配置范围采样未命中”，不能断言当日没有
发言；这仍不是按 UID 的全站完整时间线。

`signal_prior_weight` 只用于大V信号层，范围硬限制为 0.75–1.25，不进入大众看多/看空比例。
幸运阿sai 当前为 1.15；其科技多头及资产/收益画像的 `source_type=user_provided`、
`verification_status=unverified`，报告必须明确标注尚未独立核验。后续权重应由可验证的历史
观点、影响和事后命中记录校准并替代该先验，其他账号默认 1.00。
