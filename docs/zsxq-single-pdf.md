# 单份知识星球 PDF 下载与读取

这是一个手动启动的 macOS 小工具，不接入交易逻辑、研究卡、调度或批量采集。

```bash
.venv/bin/python scripts/zsxq_pdf.py \
  'https://wx.zsxq.com/group/123456/topic/789012' \
  '示例纪要.pdf'
```

把两个参数替换为有权访问的真实帖子链接和**完整附件名**。仅支持官方上述链接格式与一个 PDF，不支持短链、通配符、目录或多个附件。

前提：已有官方 `zsxq-cli` OAuth 登录；Google Chrome 已打开并登录知识星球；macOS 允许运行脚本的终端控制 Chrome；Chrome“显示/查看 → 开发者 → 允许 Apple 事件中的 JavaScript”已由用户自行确认启用。脚本不会修改任何权限或浏览器设置，不复制 Cookie、不打开调试端口、不调用未公开下载接口。该 Chrome 开关允许获授权的本机程序通过 Apple Events 在网页执行脚本，属于额外浏览器自动化权限；仅在接受这一范围后开启。不再使用时可手动关闭。

默认监测 `~/Downloads`；Chrome 使用其他下载目录时加 `--downloads '/实际目录'`。默认等候下载 60 秒，可用 `--timeout 120`，范围 5–180 秒。若 Chrome 弹出另存为窗口，脚本会等待后明确报错；应先把 Chrome 配成用户期望的下载方式，脚本不替用户更改偏好。

## 行为与产物

1. 用官方 CLI 读取**一个帖子**，按完整文件名唯一匹配附件，取得大小和 SHA-256。
2. 复用当前 Chrome 的精确帖子标签页，必要时在当前窗口新开一个帖子标签页。检查可见登录/会员/验证码提示。
3. 点击该附件和文件详情中的“下载文件”，每次运行最多一次。出现控制超时不重试点击，因为动作可能已经发生。
4. 等待下载目录中新完成的同名文件，校验 PDF 标识、大小、SHA-256；旧手动下载不冒充新下载。
5. 用项目已有 `pypdf` 在有超时的子进程中提取文本。结果保存在 Git 忽略目录 `data/zsxq-pdf/<帖子与附件摘要>/`：`source.pdf`、`text.txt`、`pages.json`、`result.json`。下载目录原文件保留。

重复运行会重新检查官方元数据和网页登录页面；已有校验通过的项目副本则复用，返回 `cached: true`，不再下载。不同任务也互斥运行。本地缓存不符合最新元数据时明确报错，不静默覆盖。

正常返回 JSON（退出码 0），失败返回 `status: error`、稳定的 `code` 和中文提示（退出码 1）；参数格式错误退出码 2。正文只保存本地文件，不打印到终端；原始认证响应、Cookie、签名下载 URL 都不保存。

## 失败提示

| code | 处理 |
|---|---|
| `CLI_LOGIN_REQUIRED` | 执行 `zsxq-cli auth login`，本人完成官方 OAuth 后重跑 |
| `LOGIN_REQUIRED` | 在同一 Chrome 窗口登录知识星球后重跑，CLI 登录与网页登录彼此独立 |
| `BROWSER_SCRIPT_DISABLED` | 用户检查上述 Chrome Apple Events 开关；脚本不会自动启用 |
| `BROWSER_PERMISSION_DENIED` | 检查 macOS 隐私与安全性 → 自动化中当前终端对 Chrome 的权限 |
| `ACCESS_DENIED` / `CLI_ACCESS_FAILED` | 检查会员权限、OAuth 状态或官方限流，不绕过 |
| `VERIFICATION_REQUIRED` | 本人完成页面验证后重跑 |
| `ATTACHMENT_NOT_UNIQUE` / `ATTACHMENT_NOT_VISIBLE` | 核对文件名、登录状态或网页结构变化 |
| `DOWNLOAD_TIMEOUT` / `BROWSER_TIMEOUT` | 先检查 Chrome 下载记录和目录，避免盲目重复下载 |
| `FILE_MISMATCH` | 停止读取；保留文件供检查，不以错误文件生成成功结果 |
| `PDF_UNREADABLE` | 加密、无文本层、超限或解析超时；保留原文件，不自动 OCR |

上限为 50 MB、200 页、单页 20 万字符、解析 30 秒。`image_pages` 标明含图片的页；普通文本提取不包含图片文字，`ocr_performed` 恒为 false。原文的真实性、研报身份及观点并未因此验证。工具只下载和提取，不生成交易建议。

网页 DOM 和浏览器版本变化可能使脚本停止。官方 MCP 下载 API 缺口仍在；这不是知识星球官方提供的下载 CLI。

参考：[Chromium AppleScript 支持说明](https://www.chromium.org/developers/applescript/)、[官方知识星球 Skill](https://github.com/unnoo/zsxq-skill)。
