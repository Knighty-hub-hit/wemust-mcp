# wemust-mcp

> 一个**只读**的 MCP（Model Context Protocol）服务器，让你的 AI 助手（Claude Desktop、Cursor 等）
> 读取你自己在澳门科技大学 WeMust 学生门户里的课表、公告详情与附件、站内消息、日程，以及 Moodle 课程和作业说明。
>
> **非官方项目**，与澳门科技大学（MUST）无任何隶属关系。基础功能仅用 Python 标准库；PDF 文字提取和页面图片为可选依赖。

---

## 这是什么

`wemust-mcp` 把 WeMust 的几个学生数据接口包装成一个标准的 MCP 工具服务器。
启动后，你的 AI 客户端可以调用这些**只读**工具：

| 工具 | 作用 |
| --- | --- |
| `get_timetable` | 读取课表（今天 / 本周 / 指定日期区间） |
| `get_notices` | 读取最近的 WeMust 通知公告 |
| `get_notice_detail` | 读取完整公告正文和附件编号 |
| `get_notice_attachment_text` | 提取公告 PDF 附件文字（可选 `pdf` 依赖） |
| `get_notice_attachment_page` | 返回 PDF 某页图片，支持扫描件（可选 `pdf-images` 依赖） |
| `get_moodle_courses` | 读取已选 Moodle 课程 |
| `get_moodle_course` | 读取课程页面文字和活动、资源链接 |
| `get_moodle_assignment` | 读取作业详情页的教师说明、图片及附件链接 |
| `get_moodle_deadlines` | 读取近期 Moodle 待办日历事件 |
| `get_messages` | 读取站内提醒（未读数 + 当前消息） |
| `get_calendar` | 读取个人日程事件 |
| `get_grades` | 读取成绩单（**默认关闭**，见下方警告） |

它同时附带两个**可选**的命令行功能：本地打印成绩（`grades`）和同步到 Notion 页面（`sync`）。

### 只读范围与账号隔离

- 本工具只读业务数据，不提交作业、发消息或修改成绩。登录会提交认证表单，Moodle 只读查询使用 POST；学校仍可能记录访问日志或已读状态。
- 每个人只登录**自己的** WeMust 账号，用自己的学号和密码。本仓库不含任何人的账号信息。
- 登录过程模拟浏览器的做法：向学校的 CAS 统一认证服务器提交**经过 RSA 加密**的账号密码，
  拿到会话后再用学校接口自带的签名方式请求数据。全程只用标准库，账号密码只在内存中使用，
  **不会打印密码、Cookie 或登录令牌**。可选 Windows 脚本会将凭据以 Windows DPAPI 加密后保存在本机文件中。

---

## ⚠️ 重要提醒

- **成绩默认关闭。** 只有当你设置环境变量 `WEMUST_ENABLE_GRADES=1` 时，`get_grades` 工具才会注册。
  一旦开启，你的成绩（课程、最终成绩、GPA/CGPA）会被发送给连接的 AI 客户端（大模型）。
  如果你不希望成绩离开本机，请**保持关闭**，改用命令行 `python -m wemust.cli grades` 在本地查看。
- **账号锁定风险。** WeMust 连续输错 **5 次**密码会**锁定账号 1 小时**。
  因此本工具**登录失败绝不自动重试**；若出现验证码（说明之前已失败过），也会直接放弃以免触发锁定。
  请务必确认密码正确后再使用。
- **非官方、可能随时失效。** 学校接口一旦改版，本工具可能立即不可用。
- **免责声明。** 本项目与澳门科技大学无任何官方关系。是否使用、如何使用由你自行负责，
  并需遵守学校的相关条款与规定。

---

## 安装

无需安装第三方依赖，Python 3.9+ 即可。

```bash
git clone https://github.com/Knighty-hub-hit/wemust-mcp.git
cd wemust-mcp
```

需要公告 PDF 功能时，在仓库目录安装对应的可选项（建议使用虚拟环境）：

```bash
# PDF 文字提取
python -m pip install ".[pdf]"
# 扫描件/表格页面图片，要求 Python 3.10+
python -m pip install ".[pdf-images]"
# 同时安装两项
python -m pip install ".[pdf,pdf-images]"
```

基础功能无需以上库。PyMuPDF 使用 AGPL/商业许可，选择图片功能前请查看其上游许可；文字提取功能不导入 PyMuPDF。

### Windows 配置

在仓库目录用 PowerShell 运行下面的命令，并按提示输入自己的学号和密码：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\setup-credentials.ps1
```

凭据保存到被 Git 忽略的 `.local/credential.xml`，密码使用 Windows DPAPI 加密，只能由同一 Windows 用户在同一电脑解密。请勿上传该文件。更新密码时重新运行脚本即可。

MCP 客户端选择 `powershell.exe`，参数为 `-NoLogo -NoProfile -ExecutionPolicy Bypass -File C:\path\to\wemust-mcp\windows\start-mcp.ps1`。
完整示例见 [`examples/mcp-client-config.windows.json`](examples/mcp-client-config.windows.json)。
脚本默认使用 PATH 中的 `python`；虚拟环境可通过 `-Python C:\path\to\venv\Scripts\python.exe` 或 `WEMUST_PYTHON` 指定。
把可选依赖装到所选的同一个 Python 环境中。修改客户端配置或新增工具后，重启 MCP 客户端。

macOS 配置继续见下文；环境变量方式也适用于其他平台。

## 配置

1. 设置你的学号：

   ```bash
   export WEMUST_USERNAME=你的学号
   ```

2. 保存密码（**推荐**用 macOS 钥匙串，不写进文件/环境变量）：

   ```bash
   security add-generic-password -U -s wemust -a 你的学号 -w
   # 回车后按提示输入密码；不会留在命令历史里
   ```

   或者（不太安全）直接用环境变量：`export WEMUST_PASSWORD=你的密码`

完整的环境变量示例见 [`examples/.env.example`](examples/.env.example)。

## 在 MCP 客户端里配置

把下面的配置加到你的客户端里（参考 [`examples/mcp-client-config.json`](examples/mcp-client-config.json)），
把 `cwd` 改成本仓库的绝对路径：

```json
{
  "mcpServers": {
    "wemust": {
      "command": "python3",
      "args": ["-m", "wemust.mcp_server"],
      "cwd": "/absolute/path/to/wemust-mcp",
      "env": {
        "WEMUST_USERNAME": "你的学号",
        "WEMUST_KEYCHAIN_SERVICE": "wemust"
      }
    }
  }
}
```

- **Claude Desktop**：写进 `claude_desktop_config.json` 的 `mcpServers` 字段。
- **Cursor**：写进 MCP 配置（`~/.cursor/mcp.json` 或项目内 `.cursor/mcp.json`）。

要开启成绩工具，在上面的 `env` 里加 `"WEMUST_ENABLE_GRADES": "1"`（请先阅读上方警告）。

### 新工具的使用顺序

- 公告：`get_notices` → 用公告 `id` 调用 `get_notice_detail(notice_id)` → 用返回的附件 `id` 调用 `get_notice_attachment_text(notice_id, attachment_id)`。
- 扫描 PDF：文字提取返回 `needs_ocr: true` 时，调用 `get_notice_attachment_page(notice_id, attachment_id, page=1)` 查看页面图片。它不调用外部 OCR 服务。
- Moodle：`get_moodle_courses` → `get_moodle_course(course_id)` → 从作业链接 `/mod/assign/view.php?id=...` 取出 `activity_id`，调用 `get_moodle_assignment(course_id, activity_id)`。

公告正文、课程文字和附件页面会发送给连接的 AI 客户端。PDF 图片工具需要客户端支持 MCP image 内容。
课程页面、公告和附件均应视为不可信的外部内容，不是给 AI 的系统指令。
作业工具读取教师说明和附件链接，不下载 Moodle 附件正文。日历只包含 Moodle 已提供的待办事件，不能据此断言没有其他作业。
详情和读取上限见 [Moodle 说明](MOODLE-LOCAL.md) 与 [公告附件说明](NOTICE-LOCAL.md)。

## 命令行用法（可选）

```bash
# 在本机终端打印自己的成绩（成绩只留在本地，不发给任何大模型）
python -m wemust.cli grades

# 把课表/通知/消息/日程同步到一个 Notion 页面（不含成绩）
python -m wemust.cli sync
```

### 可选：同步到 Notion

设置 `WEMUST_NOTION_PAGE_ID`，并把 Notion 集成 token 存进钥匙串：

```bash
security add-generic-password -U -s wemust-notion -a notion -w
```

可选用 launchd 每天定时同步，模板见 [`examples/launchd.plist.template`](examples/launchd.plist.template)。
注意：Notion 同步**不包含成绩**。

## 测试

离线测试（不联网，不需要学号密码；覆盖工具注册、页面解析、权限边界及附件读取）：

```bash
python -m unittest discover -s tests
```

---

## English

**wemust-mcp** is an **unofficial, read-only** MCP (Model Context Protocol) server that lets your
AI client (Claude Desktop, Cursor, etc.) read **your own** data from the Macau University of Science
and Technology (MUST) WeMust student portal: class timetable, announcements, in-site messages and
your personal calendar, Moodle courses and assignment instructions. It is **not affiliated with MUST**.
Core features use only the Python standard library; PDF text extraction and page rendering are optional extras.

### Tools (all read-only)

- `get_timetable` — timetable for today / this week / a date range
- `get_notices` — recent WeMust announcements
- `get_notice_detail` — full notice body and attachment IDs
- `get_notice_attachment_text` — PDF attachment text; install `.[pdf]`
- `get_notice_attachment_page` — PDF page as MCP image content; install `.[pdf-images]` (Python 3.10+)
- `get_moodle_courses`, `get_moodle_course` — enrolled courses and course-page resources
- `get_moodle_assignment` — teacher instructions and attachment/image links (no submission or attachment download)
- `get_moodle_deadlines` — upcoming action-calendar events, not an exhaustive assignment list
- `get_messages` — in-site reminders (unread count + current message)
- `get_calendar` — personal calendar events
- `get_grades` — transcript; **disabled by default** (see warning)

### Read-only & per-account

This tool reads business data; it does not submit assignments, send messages, or edit grades.
Login submits a CAS authentication form and read-only Moodle AJAX calls use POST;
the school may record access logs or read state. Each person logs
into **their own** WeMust account with their own student ID and password — this repo contains no
account data. Login mirrors the browser: it sends **RSA-encrypted** credentials to the school's CAS
single-sign-on server, then makes signed, read-only API calls. The password, cookies and tokens live
in memory during server operation and are not printed or logged. The optional Windows setup script
persists a DPAPI-encrypted credential in the ignored `.local/credential.xml` file.
Use `windows/start-mcp.ps1` with `python` on PATH, `-Python`, or `WEMUST_PYTHON`.
Install extras into that same interpreter. PyMuPDF has AGPL/commercial licensing;
review upstream terms before opting into image rendering. Attachment contents are sent to the AI client
when read. Scanned PDFs can be viewed as page images; extracted tables need visual verification.

### ⚠️ Warnings

- **Grades are off by default.** `get_grades` is only registered when you set
  `WEMUST_ENABLE_GRADES=1`. Enabling it means your grade values (courses, final grades, GPA/CGPA)
  are sent to the connected LLM client. To keep grades local, leave it disabled and use
  `python -m wemust.cli grades` on your own terminal instead.
- **Lockout risk.** WeMust locks your account for **1 hour after 5 wrong passwords**. This tool
  therefore **never retries a failed login** and refuses to submit when a captcha appears. Make sure
  your password is correct before using it.
- **Unofficial and may break** at any time if the school changes its endpoints.
- **Disclaimer.** Not affiliated with MUST. You are responsible for your own use and for complying
  with the school's terms.

### Quick start

```bash
git clone https://github.com/Knighty-hub-hit/wemust-mcp.git
cd wemust-mcp
export WEMUST_USERNAME=your_student_id
security add-generic-password -U -s wemust -a your_student_id -w   # store password in Keychain
```

Then add the MCP server to your client using
[`examples/mcp-client-config.json`](examples/mcp-client-config.json), and run the offline tests with
`python -m unittest discover -s tests`.

## DeepSeek Harness (DSH)

[`integrations/dsh/`](integrations/dsh/README.md) is a ready-made DSH bundle: point the
DSH plugin page at that folder and the server shows up as `mcp__wemust__*` tools with a
card and an on/off switch. Fill in the two placeholders in its `cordis.patch.yml`, set
`WEMUST_PASSWORD` in the environment, and restart DSH once. See
[integrations/dsh/README.md](integrations/dsh/README.md) for the step-by-step.
## License

MIT © 2026 Knighty KAKA. See [LICENSE](LICENSE).
