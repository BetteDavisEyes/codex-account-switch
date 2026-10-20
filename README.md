# Codex Account Switch

给 Codex 换账号、换模型的本地小工具，支持 **Mac 和 Windows**。

比如：平时用自己的 ChatGPT 账号，额度不够时切到另一个自己的账号，或改用 DeepSeek、自己的 API / 中转。首次设置好，以后敲一条命令就能切换。

> 不是 OpenAI 官方工具。换模型不等于绕过额度，也不保证所有厂商的模型都能直接用。你的账号、密码、Key 不会上传到这个仓库。

## 开始前，只需要知道这三件事

- **Codex 桌面端**：你平时聊天、打开项目的那个软件。
- **Codex CLI**：安装在电脑里的命令行工具，本项目靠它打开官方登录页面；不是让你以后都改用命令行聊天。
- **API Key**：模型服务给你的“使用钥匙”，会产生该服务的费用。它不是 ChatGPT 登录密码，不要发给别人或贴到聊天里。

先安装 Python 3.11 或以上版本、Git 和 [Codex CLI](https://developers.openai.com/codex/cli/)。如果电脑已经装过，不用重复安装。

下面命令里的 `python`，Mac 通常要换成 `python3`；Windows 也可以用 `py -3`。

## 第一步：把工具下载到自己的电脑

打开电脑的终端（Windows 可以用 PowerShell），依次执行：

```sh
git clone https://github.com/BetteDavisEyes/codex-account-switch.git
cd codex-account-switch
```

后面的命令都在这个文件夹里执行。准备添加或切换账号前，先完全退出 Codex 桌面端和其他正在运行的 Codex 命令行；Mac 要按 ⌘Q，不只是关窗口。

## 第二步：选择你要添加的账号类型

只做自己需要的那一种即可。

### A. 用 ChatGPT 账号

```sh
python codex_account_switch.py login personal
```

按提示在浏览器里登录自己的账号。工具不会问你要密码。想再加一个账号，就换个名字：

```sh
python codex_account_switch.py login work
```

`personal` 和 `work` 只是你起的名字，不是固定账号。添加好不等于已经切过去。

### B. 用 DeepSeek

先在 [DeepSeek 官网](https://platform.deepseek.com/)准备自己的 API Key，再执行：

```sh
python codex_account_switch.py api deepseek --url https://api.deepseek.com --model deepseek-flash
```

随后在终端输入 Key。输入时看不到字符是正常的，不要把 Key 接在命令后面。

这是一条基础配置示例，不代表已用你的账号验证成功；不同模型仍可能需要额外设置。官方已有 [Codex 接入教程](https://api-docs.deepseek.com/quick_start/agent_integrations/codex/)。**本工具不会自动套用那份教程的全部设置，也不要同时运行两套配置工具。**遇到问题先看[DeepSeek 与定时任务避坑](docs/deepseek-and-troubleshooting.md)。

### C. 用其他 API / 中转

向服务提供方确认“地址、模型名、是否支持 Codex 使用的 Responses 接口”，然后把下面的大写部分换成他们提供的内容：

```sh
python codex_account_switch.py api relay --url https://YOUR_RELAY_HOST/v1 --model YOUR_SUPPORTED_MODEL_ID
```

`relay` 也是自己起的名字。只有 Key、不知道地址和模型名时，先问服务提供方；不是所有“兼容 OpenAI”的服务都适合 Codex。

## 第三步：以后这样切换

```sh
python codex_account_switch.py personal
python codex_account_switch.py work
python codex_account_switch.py deepseek
python codex_account_switch.py relay
```

只运行你已经添加的名字。切换成功后，重新打开 Codex；API 模式下也重开原来的终端。Mac 从 Dock/Launchpad 打开，Windows 从开始菜单打开，避免沿用旧进程的设置。

想看当前保存了哪些账号、配置选了什么：

```sh
python codex_account_switch.py status
```

状态页不会显示 Key；它只能核对本地配置，不代表已经成功发过请求。首次请新开一个无敏感资料的聊天，问一句简单问题，成功后再用于正式工作。

## 第四步：想和示例一样用短命令？可选安装

```sh
python codex_account_switch.py install
```

Mac 以后可以这样用：

```sh
~/.codex/bin/codex-account-switch personal
```

Windows PowerShell 以后可以这样用：

```powershell
& "$env:USERPROFILE\.codex\bin\codex-account-switch.cmd" personal
```

电脑已有同名工具时安装会停止，不会覆盖。还有其他安装/更新方式，见[进阶说明](docs/advanced.md)。

## 切到 DeepSeek 前，特别留意

- **普通聊天成功，不代表定时任务也没问题。**任务可能自己指定了另一个模型，也可能继续使用旧聊天；切换器不会替你修改任务。
- **旧聊天报错，先试新聊天，不要删历史。**本工具的历史检查只修有限的侧边栏索引，不会自动修复所有旧消息。
- **缓存命中不是“免单”。**它只是重复输入可能少花钱；输出仍计费，以服务商实际用量和账单为准。本工具目前不显示真实缓存命中率。
- **切换会把后续发送的资料交给相应服务。**公司代码、客户资料先确认是否允许发送，便宜不等于适合所有工作。

[查看完整避坑说明：定时任务、旧聊天、缓存、联网和常见报错](docs/deepseek-and-troubleshooting.md)。

## 出问题先做什么？

| 看到的情况 | 先做这一步 |
| --- | --- |
| 提示 Codex 还在运行 | 完全退出桌面端和命令行，再操作；别在聊天里让 Agent 强行切换自己 |
| 切完仍像旧账号 / 找不到 Key | 重开桌面端与终端；Mac 电脑重启后再运行一次切换命令 |
| 模型选择框里没有目标模型 | 看[模型列表设置](docs/advanced.md#4-中转的模型选择框包括-gpt-61-sol)；显示出来也不代表服务端有权限 |
| 旧聊天或定时任务报错 | 先看[避坑说明](docs/deepseek-and-troubleshooting.md)，记录错误，不要连续重跑有写入/付费动作的任务 |
| 想回到原账号 | 完全退出 Codex，再运行原来的账号名；需要恢复文件时看进阶说明 |

账号资料和备份只存在你电脑的 Codex 数据目录，不要把那个目录上传 GitHub，也不要把工具运行目录设成仓库。它们不是加密保险箱，只在自己的可信电脑使用。

更多： [安装、备份恢复和技术细节](docs/advanced.md) · [DeepSeek 与自动化避坑](docs/deepseek-and-troubleshooting.md) · [测试结果](https://github.com/BetteDavisEyes/codex-account-switch/actions)

本项目做了 Windows / Mac 的自动测试，不代表已经登录你的真实账号、确认每一家 API 都能用。第三方模型的设置和支持范围可能变化，请以提供方说明和你的首次测试为准。
