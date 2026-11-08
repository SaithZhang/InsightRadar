# 知识星球 PDF 后台下载与读取

独立的手动启动工具。默认用本机 Cookie 和 Python `requests` 下载，不打开、切换或操作浏览器。官方 CLI 仍负责帖子与附件元数据；解析器、输出目录和交易逻辑保持原状。AppleScript 留作显式备用，失败时不会自动切换。

## 一次性准备

需要已有官方 `zsxq-cli` OAuth 登录和 macOS Chrome 知识星球登录。网页登录 Cookie 与 CLI OAuth 各自独立。

```bash
# 仅首次导入使用 cryptography，当前机器已有。
# 新机器缺少时：.venv/bin/python -m pip install -e '.[zsxq-cookie]'
.venv/bin/python scripts/zsxq_pdf.py --import-chrome-cookie
```

导入只以只读方式查询指定 Chrome 配置中的 `.zsxq.com` / `zsxq_access_token`，通过 macOS 钥匙串解密并核对域名，不复制浏览器数据库，不读取其他站点 Cookie。钥匙串可能要求本人确认；拒绝或超时即停止。默认配置 `Default`，可用 `--chrome-profile 'Profile 1'` 指定。仅支持当前 Mac Chrome `v10` Cookie 格式，格式变化时停止。

Cookie 保存在 `~/Library/Application Support/InsightRadar/zsxq-cookie.json`，权限 `600`，在项目之外。可用 `--cookie-file '/私有路径/cookie.json'` 指定另一文件。它等同于当前网页登录凭据，不要粘贴到聊天、命令行参数或 Git。删除该文件即可撤销本地副本。日常下载不访问 Chrome 或钥匙串，浏览器可以关闭；Cookie 失效后需本人重新登录并再次导入。脚本不自动登录、刷新凭据或改变系统权限。

## 单份与批量

```bash
.venv/bin/python scripts/zsxq_pdf.py 'https://wx.zsxq.com/group/123456/topic/789012' '示例纪要.pdf'
```

替换为有权访问的真实帖子与完整附件名。只接受上述官方帖子 URL 格式，不接受短链、查询参数、通配符或目录。

批量只接收明确列出的 1–20 个附件，不搜索或遍历历史帖子。将以下示例保存为本地清单并替换链接和文件名：

```json
[
  {"topic_url": "https://wx.zsxq.com/group/123456/topic/789012", "attachment_name": "示例纪要.pdf"},
  {"topic_url": "https://wx.zsxq.com/group/123456/topic/789013", "attachment_name": "另一份纪要.pdf"}
]
```

```bash
.venv/bin/python scripts/zsxq_pdf.py --batch '/私有路径/pdf-list.json'
```

先校验整份清单并拒绝重复项，再串行执行，项目间隔 2 秒。任意一项失败即停止，返回已完成回执、失败序号（从 0 开始）及未启动数量；已完成文件保留。重新运行会复用校验通过的缓存。无并发、定时任务、自动重试或历史采集。

## 下载及产物

1. 官方 CLI 读取单帖，精确匹配附件名，核对大小和 SHA-256。
2. 只将登录 Cookie 发往 `https://api.zsxq.com/v2/files/<file_id>/download_url`。此路径来自当时官方网页实际加载的代码，**不是官方 Skill/MCP 已承诺的接口**。
3. 仅接受 HTTPS `files.zsxq.com` 返回地址，使用独立请求、不携带登录 Cookie 下载 PDF。不跟随 HTTP 重定向；TLS 校验开启，网络沿用系统/环境代理配置。
4. 检查大小、PDF 标识和 SHA-256 后，沿用已有子进程解析，保存到 Git 忽略的 `data/zsxq-pdf/<帖子与附件摘要>/`：`source.pdf`、`text.txt`、`pages.json`、`result.json`。不在 `~/Downloads` 新建文件。

重复运行会重新读取官方元数据并检查本地 Cookie 有效期；项目副本校验通过则返回 `cached: true`，不请求下载接口。缓存命中不代表服务器此刻仍接受网页 Cookie，服务端撤销在下一次实际下载时检测。本地副本校验失败时不静默覆盖。不同单文件任务互斥执行。

成功返回 JSON（退出码 0），失败为稳定错误码和中文提示（退出码 1）；参数格式错误退出码 2。正文只存本地；凭据、原始认证响应和签名 URL 不输出或写入回执。批量结果保留已完成的单文件回执。

## 失败与限制

| code | 处理 |
|---|---|
| `CLI_LOGIN_REQUIRED` | 运行 `zsxq-cli auth login`，本人完成 OAuth |
| `COOKIE_FILE_MISSING` / `COOKIE_LOGIN_REQUIRED` | 在 Chrome 登录后重新运行 `--import-chrome-cookie` |
| `COOKIE_FILE_PERMISSIONS` | 确认文件属于当前用户，权限设为 `600` |
| `KEYCHAIN_ACCESS_REQUIRED` | 本人处理 macOS 钥匙串提示，不会绕过或自动重试 |
| `COOKIE_DATABASE_UNAVAILABLE` / `COOKIE_FORMAT_CHANGED` | 检查 Chrome 配置或格式变化，不修改数据库 |
| `DOWNLOAD_ACCESS_DENIED` | 可能是会员/下载权限、验证、限流或接口变化，停止检查 |
| `DOWNLOAD_API_CHANGED` / `DOWNLOAD_FILE_FAILED` | 地址格式、官方域名、响应或重定向变化，不跟随、不自动降级 |
| `DOWNLOAD_NETWORK_FAILED` / `DOWNLOAD_TIMEOUT` | 检查网络，不会自动重试或打开浏览器 |
| `FILE_MISMATCH` / `DOWNLOAD_TOO_LARGE` | 停止保存或读取不匹配的新文件 |
| `PDF_UNREADABLE` | 原解析器拒绝加密 PDF、无文本层、超限或超时；保留原文件，不 OCR |

下载默认 60 秒，`--timeout 120` 可调整，范围 5–180 秒；另有每次连接/读取超时，正在阻塞的网络读取可能稍晚退出。上限 50 MB、200 页、单页 20 万字符、解析 30 秒。`image_pages` 只标识含图片页，`ocr_performed` 恒为 false。本次没有改 PDF 解析规则，权限加密但可手动阅读的 PDF 也可能报 `PDF_UNREADABLE`。读取成功不证明内容真实性或研报发布身份。

## AppleScript 备用

```bash
.venv/bin/python scripts/zsxq_pdf.py --transport browser 'https://wx.zsxq.com/group/123456/topic/789012' '示例纪要.pdf'
```

仅支持单文件。需要 Chrome 开启并登录、macOS 自动化授权，以及本人启用 Chrome“显示/查看 → 开发者 → 允许 Apple 事件中的 JavaScript”。脚本不会更改这些设置。此方式可能把 Chrome 带到前台；必要时打开帖子标签页并点击官方文件/下载按钮各一次。默认监测 `~/Downloads`，可用 `--downloads '/实际目录'`。控制超时不重复点击；`LOGIN_REQUIRED`、`BROWSER_SCRIPT_DISABLED`、`BROWSER_PERMISSION_DENIED`、`ATTACHMENT_NOT_VISIBLE` 分别提示登录、设置、系统权限或页面变化。

## 已验证边界

2026-11-08：一次真实 Cookie 下载，新文件大小/SHA-256 与官方一致，沿用解析得到 4 页/2,760 字符；下载函数零浏览器调用，前后活动应用和标签页一致，下载目录零新增。缓存复跑与单项清单 CLI 通过；25 项合成测试覆盖导入范围、密文域名核验、凭据隔离、失效/限流/重定向、文件完整性、缓存及多项清单顺序/中止。未做真实多文件批量压力测试，也未承诺网页接口长期稳定。

参考：[官方网页当前接口定义](https://wx.zsxq.com/chunk-5LGB6CKA.js)、[官方 Skill](https://github.com/unnoo/zsxq-skill)、[Chromium AppleScript 说明](https://www.chromium.org/developers/applescript/)。
