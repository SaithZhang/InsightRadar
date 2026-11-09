# Gate 0 · 真实来源实测

日期：2026-11-09，Asia/Shanghai。来源能力与本机可用性分开记录。最新状态：**沪电单股真实行情已恢复 / 全市场验收仍未完成 / 官方披露 PARTIAL**。下方初始失败记录保留为历史。

## 19:21 修复回执

原实现锁定 2024 年的 0.8.9，仍连 www.baostock.com:10030。经[官方 PyPI 发布包](https://pypi.org/project/baostock/0.9.4/)核验，0.9.4 的公开地址为 public-api.baostock.com:10030；本机升级时核对 wheel SHA-256 `0bf71c6069ab5890ff3596632f9c3f8f1fbc6bfcac582c2f9d6a5c11ab2cfaf8`。此前仅依据旧地址失败而归为外部网络阻塞，诊断不完整。

更新 SDK 后，第一次独立 bridge 实测 74.74 秒成功，返回原价/前复权各 484 根、日历 772 行及 2 次复权事件；随后一次旧 20 秒 socket 配置的登录超时，不能只凭第一次成功宣称稳定。另一次登录定时诊断 TCP 1.058 秒、响应等待 12.044 秒成功。将 socket 上限调为 60 秒、Java/验收脚本全程上限统一 180 秒，保留失败降级。

正式 API 新 run `edc70f21-9b7f-45db-8a4a-7c5400b06954` 用时 24.1 秒，技术 READY、120 根、截止 2026-11-06、质量 reliable/fresh、errors 为空。事件 PARTIAL：43 份公告目录/解析 8 份、LLM 未配置。页面桌面/手机图表与指标已验证，五个指标用独立 50 位 Decimal 对账误差 <1e-28；旧失败报告 hash 不变。证据在本机 data/acceptance/baostock-debug/verification.json。没有换数据源、付费或改变交易规则；本次只验沪电，不能将其他四个 Gate 0 样本或十股全验收标为通过。

## BaoStock

已安装锁定 SDK 0.8.9，调用真实 `login → stock_basic → raw/qfq → calendar → adjust_factor` 链路。原始请求运行脚本 `scripts/gate0.py`，证据在本机 `data/acceptance/gate0-summary.json`、`gate0-*.json/.log`。

| 样本 | 请求开始（北京时间） | 实际结果 |
|---|---|---|
| 600519.SH 沪市主板 | 18:30:13 | 登录 10002007；0 raw/qfq/calendar |
| 002463.SZ 深市主板 | 18:30:54 | 同上 |
| 688001.SH 科创板 | 18:31:34 | 同上 |
| 300750.SZ 创业板 | 18:32:14 | 同上 |
| 920029.BJ 北交所 | 18:32:55 | 同上；登录失败先于证券查询，不能把它当作覆盖拒绝的实测 |

直连 `www.baostock.com:10030` 的 TCP 探测超时。进一步使用本机已有 loopback SOCKS 仅作一次诊断，协商成功但完整 BaoStock 登录仍在 10 秒后返回 10002007（本机 `baostock-socks-probe.json`）；未将未经验证的代理传输接入正式代码，未改系统代理。首轮直接桥接也返回相同错误。

因此证券真实身份、120 根、raw/qfq 比率、稀疏因子、官方日历、真实停牌和 59/60/61 新股样本都**没有通过真实来源验收**。边界算法合成测试通过不能替代这些缺口。北交所无覆盖的错误分支已测试；当前网络拒绝不证明它今天是“无覆盖”。本地未取得 Fuyao 接入 URL/鉴权，未构造接口或复用其他项目密钥。

## 巨潮官方目录与 PDF

真实访问：`https://www.cninfo.com.cn/new/data/szse_stock.json`、`https://www.cninfo.com.cn/new/hisAnnouncement/query`、`https://static.cninfo.com.cn/`。通过公开网站允许的单股只读请求，未使用登录 Cookie，未绕过验证码/付费访问。网站内部端点不是承诺稳定的公开 API。

沪电样本（18:33 创建报告）：2026-08-12～2026-11-09，目录 42 份，分页已核对总数；独立定期报告检索完整，最新为 2026-Q3。抽取 8 份 PDF，0 抽取失败，其余 34 份明确未处理，状态 PARTIAL。2026 年三季度报告真实 PDF 8 页；PDFBox 逐页抽取和第 1 页真实短句定位校验通过，hash 记录在本机 `server/target/official-pdf-check.json`。

原始下载使用 curl 的系统信任链成功；Python urllib 系统证书链失败；正式 Java HttpClient HTTPS/证书验证成功，不关闭 TLS 验证。PDF 原件与逐页文本仅在 data/数据库，不进入 Git。

## 终值与验收限制

BaoStock 无可靠显式终值标记时排除北京时间当日 K，仅 prior-date policy；这次没有取到行情，不能以该政策声称实际行情正确。10 股真实 API 回执见实现记录；目录与原文的可用降级不构成技术链路成功或沪深北完整覆盖。恢复网络后先重跑同一 Gate 0，再进行不同技术状态/停牌/除权的真实验收；不购买数据、不迁移平台。
