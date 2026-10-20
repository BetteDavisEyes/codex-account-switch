# 进阶说明：安装、恢复与配置边界

[返回小白入门](../README.md)。本页保留完整技术说明；命令都在仓库根目录执行，不是在 docs 目录执行。DeepSeek 和定时任务另见[避坑说明](deepseek-and-troubleshooting.md)。

## 准备

1. 安装 **Python 3.11 或更高版本**、Git，以及 [Codex CLI](https://developers.openai.com/codex/cli/)，确认 `codex --version` 可用。Windows 安装 Python 时启用 PATH。
2. 所有写操作前，完全退出 Codex Desktop（Mac 使用 ⌘Q）及其他 Codex CLI 会话，在外部终端操作。不要让运行中的 Agent 切换自己的账号。
3. 仅在自己的可信电脑运行。本地 OAuth、API Key 与备份可被同一系统用户读取；它们不是加密密码保险箱。Windows 请确认个人用户目录没有向其他用户共享读取权限。

```sh
git clone https://github.com/BetteDavisEyes/codex-account-switch.git
cd codex-account-switch
```

下文统一使用 `python`；Mac 若只有 `python3` 请替换，Windows 也可使用 `py -3`。首次配置后无需再填写同一账号的密码或 Key，除非登录过期或服务商轮换凭据。

## 1. 添加自己的官方账号

```sh
python codex_account_switch.py login personal
python codex_account_switch.py login work
```

每次按终端提示在浏览器中登录对应账号，登录前核对浏览器选中的身份。登录只保存授权，不自动切换。无浏览器环境可尝试 `login personal --device-auth`，是否可用以官方账号/组织设置为准。

如果已经登录 Desktop 且有文件形式的 OAuth 凭据，可以直接保存：

```sh
python codex_account_switch.py save personal
```

找不到 `auth.json` 不代表没登录，凭据可能在系统钥匙串。此时使用上面的 `login`，它在隔离目录中调用官方 CLI 的 file 凭据存储，不导出系统钥匙串或替换当前登录。

同名配置不会静默覆盖。确需更新时使用 `login personal --replace` 或 `save personal --replace`；旧版本另存本地 profile-backups。

## 2. 添加自己的 API / 中转

```sh
# OpenAI API：模型名称自行确认
python codex_account_switch.py api openai-api --url https://api.openai.com/v1 --model YOUR_SUPPORTED_MODEL_ID

# 自己的中转服务：替换 URL 和模型 ID
python codex_account_switch.py api relay --url https://YOUR_RELAY_HOST/v1 --model gpt-6.1-sol
```

命令会隐藏输入 API Key，不把 Key 放入命令行参数或仓库。不要在聊天里发 Key。URL 只接受无内嵌账号密码、查询参数和片段的 HTTPS 地址。

**需要 Responses API 兼容性**。只有 `/chat/completions` 的服务不能因为“OpenAI 兼容”就直接用于 Codex；模型 ID、工具调用、推理参数和账号权限也必须匹配服务商实际能力。本工具不探测或调用收费模型接口。

API 配置自动生成当前模型的选择框目录。更换现有 API 配置的 endpoint 时建议新建名称；已存在且不同的同名 Provider 配置会被拒绝覆盖。

## 3. 日常切换

```sh
python codex_account_switch.py personal
python codex_account_switch.py work
python codex_account_switch.py relay
python codex_account_switch.py status
```

前三条也可写成 `switch NAME`。切换会修改当前 Codex Home 的根路由配置、官方登录文件和活动标记，并先备份。其他配置表和已有 Provider 保留，不会删除项目、对话或归档。

API Key 除本地文件外，还提供给当前用户的环境：Mac 使用 `launchctl setenv`；Windows 使用用户环境注册表并通知系统刷新。**API 切换后完全重开 Desktop；原终端也需重开**。Mac 从 Dock/Launchpad 打开，Windows 从开始菜单/Explorer 打开；已有终端父进程可能仍持有旧环境。Mac 的 Key 会短暂作为 launchctl 子进程参数传递，同一用户或管理员可能观察到它。Windows 环境可能在重启后保留；Mac 重启后请再次运行切换命令。

回到 OAuth 会清掉自定义路由和目录引用，但不清除曾配置的用户环境变量；旧 Key 不再被当前官方路由选用，不等于已从系统安全擦除。卸载/撤销访问时，还应在服务商后台撤销 Key，并从对应系统环境删除 `CODEX_SWITCH_*_KEY`。本工具不配置系统级/所有用户的环境。

如环境中已有 `OPENAI_API_KEY` 或组织强制登录/Provider 策略，需要自行核对，不能把状态页的配置结果当作真正请求身份的证明。不要用此工具绕过组织策略。

## 4. 中转的模型选择框（包括 GPT-6.1 Sol）

只写 `model = "..."` 不一定能让客户端选择框显示该模型。本工具同时提供独立模型目录，并在 API 切换时设置 `model_catalog_json`。

```sh
python codex_account_switch.py models relay gpt-6.1-sol OTHER_SUPPORTED_MODEL_ID
python codex_account_switch.py relay
```

重启 Desktop 后检查。目录始终包含该 API 配置的默认模型；此命令**替换**额外模型列表，旧目录留备份。只填写自己的服务端确实支持的 ID；`gpt-6.1-sol` 是此次需求的示例，不是宣称任何中转都会支持它，也不代表永远是最新模型。

生成目录不复制任何人的提示词、账号权限、模型缓存或实验开关。通用条目仅提供 medium 推理选项、保守的文本上下文元数据；不同模型的推理等级/上下文需要按服务商实际能力调整本地 `catalog.json`，不能把此示例元数据当模型规格。客户端升级可能改变目录格式，届时需复核兼容性。不要自动抓服务商 `/models` 后假定它们全都适用于 Codex。

## 5. 安装短命令（可选）

```sh
python codex_account_switch.py install
```

安装器复制单个独立 Python 工具和启动器到当前 Codex Home 的 `bin`。有同名文件会停止，不覆盖已有工具，也不修改 PATH。

Mac：

```sh
~/.codex/bin/codex-account-switch personal
~/.codex/bin/codex-account-switch relay
```

Windows PowerShell：

```powershell
& "$env:USERPROFILE\.codex\bin\codex-account-switch.cmd" personal
& "$env:USERPROFILE\.codex\bin\codex-account-switch.cmd" relay
```

也可以手动把该 bin 加入 PATH，直接运行 `codex-account-switch personal`。自定义 `CODEX_HOME` 时，使用它的实际 bin 路径。安装器记住运行安装时的 Python 路径；卸载/移动该 Python 后须重新安装入口。更新仓库不会自动覆盖已安装工具；先备份旧入口再更新，或一直从仓库直接执行。

## 6. 回滚、历史与边界

每次切换打印本地 `BACKUP_ID`：

```sh
python codex_account_switch.py restore BACKUP_ID
python codex_account_switch.py doctor
# 确认确需修改已知侧边栏索引后：
python codex_account_switch.py doctor --apply
```

- `restore` 回滚 config/auth/活动标记，并先备份当前状态；不会回滚 OS 环境或配置仓库。API 如需重新启用，请重新切换该配置。
- `doctor` 默认只读，只识别已知 `state_5.sqlite` 的有限列。`--apply` 在 SQLite backup 后同步已知 Provider/用户消息标记；不修改原始 sessions，不删除历史，不把第三方响应改写成用户消息。
- SQLite 修复备份需在完全退出 Codex 后手工恢复；`restore BACKUP_ID` 不恢复数据库。无对应 schema 就跳过，不猜新字段。项目归属、远端会话、历史工具协议不兼容等问题不在这个有限修复器的保证范围。
- 换 Provider 不保证所有旧对话都能继续；必要时保留旧对话并新开任务。不要为了恢复选择框或会话而删除整个 Codex Home。
- 若设置了 `config.profile` 或以 CLI `--profile` 运行，嵌套路由可能覆盖根配置。本工具对已检测的根 `profile` 会拒绝切换；请先明确实际生效配置。
- 不支持自动批量迁移既有切换器的账号目录；在新工具中重新登录/保存，不复制他人的 OAuth 文件。

## 数据存放与隐私

默认运行目录为 `~/.codex/account-switch/`（或 `$CODEX_HOME/account-switch`），不在仓库内：

```text
profiles/<自定义名称>/profile.json, auth.json 或 api.key, catalog.json
active.json
backups/<BACKUP_ID>/...
profile-backups/...
```

OAuth 与 API Key 都是敏感凭据。macOS 新建私有目录/文件分别设置 700/600；Windows 依赖个人用户目录 ACL，请勿把运行目录放在共享磁盘。备份也包含凭据和可能的私人会话索引，请勿上传 GitHub。公开仓库只放程序、说明和虚构测试数据；不要把 `--home` 指向仓库目录。

## 可选安装为 Skill

可让支持 Agent Skills 的工具读取此仓库根目录的 `SKILL.md`；不安装 Skill 也能用全部命令。不要覆盖自己的同名本地技能，先比较版本。Skill 不授予读取或公开凭据、在运行中的客户端强行切换的权限。

## 验证

```sh
python -m unittest discover -s tests -v
```

CI 在 macOS/Windows、Python 3.11/3.13 上运行合成数据测试。它不登录真实账号、不调用收费模型。CLI 模型列表可另用隔离 home 做本地验证；**CI 通过不等于在同事的 Desktop 上完成浏览器登录、API 请求或 UI 点击验收**。

官方资料：[认证](https://developers.openai.com/codex/auth/)、[配置参考](https://developers.openai.com/codex/config-reference/)。模型目录、凭据存储与环境机制会随客户端版本变化；以安装版本和实测为准。
