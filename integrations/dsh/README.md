# DeepSeek Harness bundle (DSH)

This folder is a ready-made [DSH](https://github.com/deepseek-ai/deepseek-harness) bundle.
Installed through the DSH plugin page, it registers the MCP server in this repository as
`mcp__wemust__*` tools, with a card and an on/off switch in the plugin page.

## 安装（中文）

1. 先按本仓库根目录的 README 把 Python 依赖和登录方式准备好（只要 Python 3.9+ 能跑
   `python -m wemust.mcp_server` 就行）。
2. 打开 [`cordis.patch.yml`](cordis.patch.yml)，改两处占位符：
   - `cwd`：你 clone 本仓库的绝对路径（Windows 用 `C:/...` 或 `C:\\...`）
   - `WEMUST_USERNAME`：你的 WeMust 学号
3. 在系统环境变量里存密码（**不要写进任何文件**）：
   ```powershell
   setx WEMUST_PASSWORD "你的密码"
   ```
4. 打开 DSH → 侧栏「插件」→ 右上「添加插件」→「本地目录」→ 选这个
   `integrations/dsh` 目录。
5. 插件页会出现「WeMust 门户」卡片，打开开关。**第一次设完环境变量后，要完全退出 DSH
   再重开**，否则宿主进程读不到 `WEMUST_PASSWORD`。
6. 工具列表里会出现 `mcp__wemust__get_timetable` 等 11 个工具。

## 关闭 / 更新

- 关闭：插件页把「WeMust 门户」开关关掉即可，不会影响仓库里的 Python 代码。
- 更新：`git -c http.sslBackend=openssl pull`（Windows 证书有问题时加这个参数），
  然后完全退出 DSH 再重开 —— 工具是在宿主启动时注册的，开关一次不够。

## 设计说明

- **密码零落盘**：patch 里只写 `!!js process.env.WEMUST_PASSWORD`，DSH 在加载时从环境变量
  求值并注入子进程；patch 文件本身、git 历史里都没有密码。
- **成绩永远不进来**：不设置 `WEMUST_ENABLE_GRADES`，`get_grades` 根本不会注册。
- **全部只读**：不提交作业、不发消息、不改任何数据。
- 每次工具调用都会真登录一次（上游客户端在进程内缓存会话），所以别在循环里高频调用。

## English

Edit the two placeholders in `cordis.patch.yml` (`cwd`, `WEMUST_USERNAME`), store the
password with `setx WEMUST_PASSWORD "..."`, then in DSH use **Plugins → Add plugin →
Local folder** and pick this `integrations/dsh` directory. Toggle the new card on and
restart DSH once so the host process picks up the environment variable. Toggle off to
disable; `git pull` + a full restart to update.