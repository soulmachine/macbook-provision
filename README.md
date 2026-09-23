# Macbook Provision

使用 Ansible 自动化 macOS 开发环境配置，通过 [Homebrew 模块](https://docs.ansible.com/ansible/latest/collections/community/general/homebrew_module.html) 安装和管理软件。

## 语言运行时

本项目使用 [mise](https://github.com/jdx/mise) 安装语言运行时（Go、Node.js、JDK 等），而非 Homebrew。mise 是一个多语言版本管理工具，支持在同一台机器上安装和切换多个版本，例如在 JDK 22 和 JDK 23 之间自由切换。

## 使用方法

### 1. 安装 Ansible

```bash
./bootstrap.sh
```

该脚本会自动安装 Xcode Command Line Tools、Homebrew、mise、Python 和 Ansible，并配置免密 sudo（passwordless sudo）。

> **关于免密 sudo**：Ansible 中标注 `become: true` 的任务，以及 Homebrew cask 等会在内部派生 `sudo` 子进程的命令，都需要 `sudo` 在无人值守时不弹密码框。脚本通过在 `/etc/sudoers.d/<用户名>-nopasswd` 写入一条 `<用户名> ALL=(ALL) NOPASSWD: ALL` 规则（权限 0440，写入后用 `visudo -cf` 校验，校验失败自动回滚）来实现免密 sudo，使整个 provisioning 过程无需人工输入密码。
>
> 首次运行会一次性提示输入 macOS 用户密码（用于写入 sudoers 文件），之后所有 `sudo` 调用都免密。`bootstrap.sh` 重复执行时若该 drop-in 文件已存在会自动跳过。
>
> **安全提示**：`NOPASSWD: ALL` 意味着以当前用户身份运行的任何进程都能静默取得 root 权限。如需收紧，可改为仅对特定命令免密，或改用 Touch ID（`pam_tid`，但需交互、不适合无人值守）。

### 2. 运行 Playbook

```bash
ansible-playbook main.yml
```

运行单个 role：

```bash
ansible localhost -m include_role -a name=hermes
```

`hermes` 只装在常年开机的桌面机上（详见下文"仅限常驻开机的机器"）。
判定所需的 fact 由 `host-facts` role 提供，而它是该 role 的 meta 依赖，
所以上面这条单 role 命令**不需要任何额外参数**就能正常工作。

### 3. 试运行（不修改系统）

```bash
ansible-playbook main.yml --check
```

### 4. 可选：Tailscale 配置

`roles/tailscale` 通过 `brew install --cask tailscale-app` 安装独立版 Tailscale.app（tailscale.com 官网下载的版本，**不是** App Store 的沙盒版）。MagicDNS 会通过 Network Extension 自动配置，无需手工写入 `/etc/resolver/ts.net`。

> **使用范围说明**：本 role 只把 Tailscale 当作**网络连接层**使用（私有 mesh + MagicDNS），**不启用 Tailscale SSH** 这个 feature。远程 shell 仍然走标准 OpenSSH，Tailscale 只负责提供可达的 mesh 地址。也正因为如此，role 里没有 `--ssh` flag、没有 `tag:server` / `tag:laptop` 这些 ACL tag、没有 ACL `tagOwners` 自动管理、没有 `/Applications/Tailscale.app` 的 Full Disk Access 提示，也没有按机型分服务器/笔记本两条 profile——所有围绕 Tailscale SSH 和 tag 的额外步骤都被刻意去掉了。如果之后改用 Tailscale SSH，需要重新加回：FDA 授权（保证 SSH 子 shell 继承到正确的 TCC 沙盒），以及（如果想按机器粒度限制 ACL）`--advertise-tags` 和通过 API 维护 `tagOwners`。

#### Network Extension 自动检测

在执行 `tailscale up` 之前，role 会用 `systemextensionsctl list` 检查 Tailscale 的 Network Extension 是否处于 `[activated enabled]` 状态。如果没有（包括「尚未启用」「等待用户授权」或「Tailscale.app 从未启动过所以扩展还没注册」三种情况），role 会自动 `open -a Tailscale`（这一步本身就是注册扩展、让开关出现的前提），然后**直接让 play 失败**，并在失败信息里给出下面这一步：

> System Settings → General → Login Items & Extensions → Network Extensions → 把 **Tailscale** 开关打开

如果同时弹出 "Tailscale would like to add VPN configurations" 对话框，点 **Allow** 即可（Touch ID / 密码）。

打开开关后**重新运行 playbook**。这里刻意用 `fail` 而不是 `pause`：`ansible.builtin.pause` 在非交互 stdin 下只会警告一句 "Not waiting for response to prompt" 就继续往下跑，于是 play 会在几个 task 之后死在看似无关的地方（`tailscale up` 报 `No such file or directory: b'tailscale'`）。`fail` 在交互和 headless 下行为一致。

检测以 `systemextensionsctl` 的实时输出为准——没有 marker 文件，下次运行会自动重新探测：扩展已启用则跳过这一步，扩展被关掉则会再次提示。

#### 环境变量

将 `.env.example` 复制为 `.env`，按需填写以下变量，然后 `direnv allow`，最后运行 `ansible-playbook main.yml`：

| 变量 | 作用 | 必填 |
|------|------|------|
| `TAILSCALE_AUTH_KEY` | 自动执行 `sudo tailscale up --accept-dns --accept-routes --operator=$USER --auth-key=...` 把本机加入 tailnet。在 https://login.tailscale.com/admin/settings/keys 创建一个 **Reusable** key 即可。 | 否（不设则需手工 `tailscale up`） |
| `TAILSCALE_OAUTH_CLIENT_ID` + `TAILSCALE_OAUTH_CLIENT_SECRET` | 通过 Tailscale REST API 关闭本机 node-key 过期（避免节点定期下线）。在 https://login.tailscale.com/admin/settings/trust-credentials 创建 OAuth client，勾选 `devices:core` 写权限即可——该 scope 的 endpoint 列表正好包含 `POST /api/v2/device/{id}/key`。client secret **不过期**，归属于 tailnet 而非个人，使用记录会进入 configuration audit log。两个变量要么都设，要么都不设；只设一个会让 play 直接失败。 | 否 |
| `TYPESAFE_API_KEY` | `typesafe` role 用它给 fast-jev-compaction 与 claude-jev 两个 Claude Code 插件授权：写入 `~/.claude/settings.json` 的 `env`（同时写入 `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`）。在 https://console.typesafe.ai/keys 创建。 | 否（不设则跳过这两个插件；`typesafe-ai` skill 仍会安装） |

`tailscale up` flag 说明：

- `--accept-dns`：启用 MagicDNS（需提前在 https://login.tailscale.com/admin/dns 的 tailnet 层面启用一次）。
- `--accept-routes`：接受其它节点广播的 subnet route。这个 flag 是**必须写全**的——`tailscale up` 不允许悄悄丢掉上一次带过的非默认 flag，要么 `--reset`，要么把每个非默认 flag 重新写一遍，所以 role 里必须原样列出。
- `--operator=$USER`：把当前用户登记为 operator，之后跑 `tailscale status`、`tailscale set` 等命令不再需要 `sudo`。

> `TAILSCALE_API_ACCESS_TOKEN`（个人 API access token）**已不再支持**：它是 fully-permitted（没有 scope）且 90 天后过期。role 现在**根本不读这个变量**：`.env` 里留着它不会报错，但也不会有任何作用——node key 照样会过期。曾经有一个迁移 tripwire 会在这种情况下让 play 失败，在全部七台机器确认清理干净后于 2026-09-10 撤掉了。请改配上面的 OAuth client。

### 5. 可选：启用 pre-commit 检查

```bash
pre-commit install
```

仓库自带三条 `repo: local` 检查，针对的都是本仓库自身的不变量：`ansible-lint`（production profile）、`DECISIONS.md` 编号连续性、README role 表与 `main.yml` 的顺序一致性。三条在干净工作树上都通过，所以新出现的失败是**可见的**，而不会淹没在既有噪音里。

`pre-commit install` 写入的是 `.git/hooks/pre-commit`，**git 不携带这个文件**，所以每个 clone 都要各自执行一次。想手工跑一遍全部检查：

```bash
pre-commit run --all-files
```

## 包含的 Roles

### Playbook 中的 Roles（`main.yml`）

按 `main.yml` 中的执行顺序排列。

| Role | 说明 |
|------|------|
| host-facts | 机器判定（`mac_family` / `mac_battery_installed` / `mac_is_vm` / `mac_is_always_on`）；不装任何软件 |
| homebrew | 通用 Homebrew 包与 GUI 应用：git、curl、wget、jq、ripgrep、fd、tree、htop、docker、ffmpeg、gh、gnupg、tmux；cask 含 claude、gemini、pearcleaner、sublime-text、visual-studio-code，Apple Silicon 另加 chatgpt |
| github | gh CLI（brew）；若 `.env` 中有 `GITHUB_TOKEN`，另外配置 SSH key 与 git 签名 |
| oh-my-zsh | Zsh 框架及插件管理 |
| direnv | 目录级环境变量管理 |
| dotenv | 不装任何软件；把 `.env` 以托管块写入 `~/.zshenv`，让非交互式 shell（`ssh host 'cmd'`、git hook、launchd）也能读到其中的变量 |
| uv | Python 包与工具管理器（通过官方 astral.sh 脚本安装） |
| python | 用 uv 安装 Python 命令行工具：yamllint、ansible-lint、ruff、pre-commit、httpie；Apple Silicon 另加 openai-whisper、whisper-ctranslate2（依赖 uv） |
| mise | 运行时版本管理器（由 bootstrap.sh 独立安装）；本 role 用 `mise self-update` 保持其最新，go、nodejs、jdk 都建立在它之上 |
| go | Go 语言（通过 mise 安装） |
| nodejs | Node.js（通过 mise 安装） |
| bun | Bun JavaScript 运行时 |
| rust | Rust 工具链（通过官方 rustup 安装；额外含 rust-src、rust-analyzer 组件） |
| jdk | JDK（通过 mise 安装） |
| claude-code | Claude Code CLI 及插件（依赖 nodejs） |
| claude-extras | Claude Code 周边工具：npm `@inulute/cux`、uv 工具 `claude-swap`（依赖 nodejs、uv、claude-code） |
| typesafe | TypeSafe Jev 模型相关的一切：官方 `typesafe-ai` skill（`npx skills add typesafe-ai/skills`，不需要 key，2026-09-19 从 skills role 移来），以及两个 Claude Code 插件 fast-jev-compaction（Jev 决策式压缩，需 function hooks）与 claude-jev（MCP，`jev_*` 判断工具）；把 `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS` 与 `TYPESAFE_API_KEY` 写入 `~/.claude/settings.json` 的 `env`；`.env` 无 `TYPESAFE_API_KEY` 时只跳过插件部分（依赖 claude-code、nodejs） |
| codex | OpenAI Codex CLI（依赖 nodejs） |
| opencode | OpenCode CLI（npm `opencode-ai`）；并用 `npx oh-my-openagent` 写入 `~/.config/opencode/opencode.json`，由版本戳门控，避免每次 play 重装（依赖 nodejs） |
| kimi-code | Kimi Code CLI（通过官方 code.kimi.com 脚本安装） |
| omp | oh-my-pi：bun 全局 `@oh-my-pi/pi-coding-agent`（依赖 bun） |
| pi | pi coding agent：bun 全局 `@earendil-works/pi-coding-agent`，并下发 `~/.pi/agent/settings.json`（依赖 bun） |
| agent-sync | tap `agent-sync-sh/tap`（按 URL tap）+ `brew trust` + brew `agent-sync`；把 `~/.agents/` 扇出到各 agent，并在技能被删除后清理悬空符号链接 |
| skills | 用 `npx skills@latest add` 安装十个整源 + 四个只取指定技能的源，并扇出到各 agent 的 skills 目录；详见下文「Agent CLI 与技能」（依赖 claude-code、codex） |
| agent-reach | 多渠道触达工具；上游只提供面向 AI agent 的安装文档，故由 `claude -p` 按文档驱动安装（依赖 claude-code、python） |
| playwright | 浏览器自动化：npm 全局 `playwright@latest`（依赖 nodejs） |
| playwright-cli | Playwright CLI：npm 全局 `@playwright/cli@latest`，并安装其 skill（依赖 playwright） |
| cua | Cua Driver（`cua.ai/driver/install.sh`）+ jev-use；需先授予 Accessibility 与 Screen Recording，未授权时报错并给出 `cua-driver permissions grant` |
| intellij-idea | IntelliJ IDEA（依赖 jdk） |
| claude-mem | Claude 记忆插件；`npx -y claude-mem install` 为 claude-code / codex-cli / opencode 三者接线（依赖 nodejs、bun、uv） |
| cc-switch | Claude 配置切换器：tap `farion1231/ccswitch` + cask `cc-switch`（依赖 claude-code、codex） |
| hermes | Hermes 个人 agent（Nous Research）；**仅限常驻开机的机器** |
| ponytail | 给所有 agent 安装 [ponytail](https://github.com/DietrichGebert/ponytail) 插件——Claude Code / Codex / OpenCode / pi / oh-my-pi / Hermes 各用其原生安装方式；其中 Hermes 部分**仅限常驻开机的机器** |
| paseo | agent 多路复用 GUI（cask `paseo`）；tag `agent-multiplexer`（依赖 claude-code、codex） |
| ghostty | 终端模拟器（cask `ghostty`）（依赖 oh-my-zsh） |
| cmux | 多 agent 工作区：tap `manaflow-ai/cmux` + cask `cmux`，并把 CLI 链接到 `~/.local/bin`（依赖 ghostty） |
| obsidian | Obsidian（cask）+ npm 全局 `defuddle`（依赖 claude-code） |
| cloudflare | Cloudflare CLI：npm 全局 `cf`（依赖 claude-code） |
| multica-cli | tap `multica-ai/tap` + brew `multica-ai/tap/multica` |
| tailscale | 独立版 Tailscale.app（cask）；若 `.env` 中有 `TAILSCALE_AUTH_KEY` 则自动登录，可选通过 OAuth client 关闭 key 过期 |
| apple-container | Apple `container`（brew）；**仅限 Apple Silicon**，安装后启动 container system |
| moshi | tap `rjyo/moshi` + brew `moshi-hook`，并通过 brew services 常驻；tag `agent-multiplexer` |
| zellij | 终端复用器（brew `zellij`）；tag `terminal-multiplexer` |
| tmux | 终端复用器（brew `tmux`）；tag `terminal-multiplexer`（`homebrew` 的通用包列表中也有，两处都是 `state: latest`，重复无害） |
| herdr | 用 `npx skills add herdrdev/herdr` 安装 herdr skill，并以相对符号链接接入 `~/.claude/skills`；tag `terminal-multiplexer` |

### 仅限常驻开机的机器

`hermes` 会常驻一个长期运行的本地服务（Hermes 的 agent 进程），只有 24x7 开机的
机器才用得上。因此这个 role 以及 `ponytail` 里往 Hermes 里装插件的那一步，都以
`mac_is_always_on` 为开关。（`openclaw` 曾经也是这样的 role，2026-09-08 起已从所有
机器卸载；负责卸载的 role 在 2026-09-10 也已删除。）

这个 fact 由 `host-facts` role 设置。它同时是这两个 role 的 meta 依赖，并且被列在
`main.yml` 的 `roles:` 第一位——前者让单独运行某个 role 时也能自行判定（无需
`-e`），后者保证整套 playbook 在任何 role 之前先完成判定。Ansible 对无参数 role 会
去重，所以无论多少 role 依赖它，每次 play 只执行一次。

判断依据是**有没有内置电池**，取自 ioreg 的 AppleSmartBattery `BatteryInstalled`
字段，而不是机型白名单。规则是**保守的**：该字段**存在且等于 `No`** 才安装，另外对
虚拟机开一个显式例外（见下）。（`sysctl -n hw.model` 在这里没用——所有 Apple Silicon
机型都只报 `MacN,M`，看不出机型家族。）

全 fleet 实测结果（下表每一行都是实测，没有推断）：

| 机器 | 机型 | `mac_family` | `BatteryInstalled` | 判定 |
|------|------|--------------|--------------------|------|
| franks-mac-mini-m2 | `Mac14,3`（M2） | Mac mini | `No` | **安装** |
| archs-mac-mini | `Mac16,10`（M4） | Mac mini | `No` | **安装** |
| franks-mac-studio | `Mac15,14`（M3） | Mac Studio | `No` | **安装** |
| dev-server-frank-lume | `VirtualMac2,1` | Apple Virtual Machine 1 | 不存在 | **安装**（虚拟机例外） |
| franks-macbook-air | `Mac16,12`（M4） | MacBook Air | `Yes` | 跳过（便携机） |
| macbook-pro-nickel | `Mac17,2`（M5） | MacBook Pro | `Yes` | 跳过（便携机） |
| franks-mac-mini-2018 | `Macmini8,1`（Intel） | Mac mini | 不存在 | 跳过 |

Intel 机器和虚拟机都压根没有 AppleSmartBattery 节点，整棵 ioreg 树里都找不到
`BatteryInstalled`。**跳过这台 2018 Intel Mac mini 是预期行为**：要求硬件明确报告
"没有电池"才安装，探测不到就不装，比"只要不是 `Yes` 就装"更安全。

**虚拟机是唯一的例外**，由 `mac_is_vm`（`'Virtual' in mac_family`）放行：虚拟机没有
电池硬件，永远给不出那个肯定的 `No`，但它本身就是常驻开机的，而且
`dev-server-frank-lume` 本来就由本仓库负责 provision，且已装有这两个 role。注意例外的写法
是**对机型名做正向判断**，而不是放宽电池规则，所以物理 Intel 机器依旧被挡在外面。

需要**覆盖**硬件判定时用 `-e mac_is_always_on=true`（或 `=false`），extra vars
优先级最高——但这只是覆盖手段，日常使用不需要传。

### Agent CLI 与技能

`main.yml` 里有十来个 role 装的是各家 coding agent 的 CLI 和它们共用的技能
（skills）。上面的表格每个 role 只有一行，而这一块恰恰有几处「一行说不清、说清了
反而容易误解」的地方，集中写在这里。

#### 安装渠道各不相同

这一组没有统一的安装方式，排查问题时先看清楚该用哪个包管理器：

| 工具 | 安装渠道 | 落地位置 / 命令名 |
|------|----------|-------------------|
| claude-code | 官方 `install.sh` | `~/.local/bin/claude` |
| codex | Homebrew **cask** | 命令 `codex`；`codex update` 会自己转调 `brew upgrade --cask codex` |
| opencode | npm 全局 `opencode-ai` | 命令 `opencode` |
| kimi-code | 官方 `install.sh`（curl \| bash） | `~/.kimi-code/bin/kimi`，命令是 **`kimi`** 而不是 `kimi-code` |
| omp | bun 全局 `@oh-my-pi/pi-coding-agent` | `~/.bun/bin/omp`，命令是 **`omp`** |
| pi | bun 全局 `@earendil-works/pi-coding-agent` | `~/.bun/bin/pi` |
| claude-mem | `npx -y claude-mem install` | 不是独立命令，而是 Claude Code 插件，同时接线 codex-cli 和 opencode |
| cc-switch | tap `farion1231/ccswitch` + **cask** | GUI 应用 |
| agent-reach | **没有包管理器**，见下 | 由 `claude -p` 按上游文档安装 |

`codex` 用 cask 而不是 npm 是刻意的：npm 全局包会装进当前 node 版本的 prefix 里，
而 node 由 mise 管理，一换版本这个包就静默消失了。role 表里的「依赖 nodejs」指的是
运行期依赖，不是安装渠道。

#### 每次运行都会被覆盖的配置文件

**`~/.pi/agent/settings.json` 每次 play 都会被仓库里的版本整个覆盖。** `pi` role 用
`copy: src=agent/ dest=~/.pi/agent/` 下发整个目录，没有任何 gate，所以在 pi 里通过
`/settings` 改的东西会在下一次 provisioning 时被抹掉。要让改动活下来，得改
`roles/pi/files/agent/` 里的文件。同一份 payload 还带着 `models.json`、主题和
`extensions/`。

这是一次**合并**而不是同步：`~/.pi/agent/` 下面没被 payload 覆盖到的东西（尤其是
`skills` role 维护的 `~/.pi/agent/skills/`，以及 pi 自己的运行时状态）不受影响。

另一处是 `~/.config/opencode/opencode.json`，由 `npx oh-my-openagent` 重写，每次重写
都会留下一个 `opencode.json.backup-<时间戳>`（2026-09-15 清理前累计了 81 个）。这一步
有 gate——配置里没有 `oh-my-openagent` 字样，或者 npm 上的版本与
`~/.config/opencode/.oh-my-openagent-version` 记录的不一致时才跑——所以正常情况下它并
不会每次都动。

#### 技能：一个存储 + 符号链接扇出

所有技能只存在一份，在 `~/.agents/skills/`。`skills` role 用
`npx skills@latest add` 安装十个「整源」和四个「只取其中某几个技能」的源，然后由 CLI
扇出到各 agent。

关键在于**不是每个 agent 都拿符号链接**：Claude Code、pi、Hermes 的技能目录是指回存储
的符号链接农场；而 Codex、OpenCode、Kimi Code、Cursor、Gemini 属于 CLI 所说的
「universal agent」，它们**直接读 `~/.agents/skills/`**，永远不会收到链接。所以
`~/.codex/skills/` 里没有链接是正常的，不是掉了东西——本仓库从不往那里写。（那个目录
里如果有真实子目录，那是别的安装器留下的 per-agent 副本，与本 role 无关。）

这个 role **故意不加 gate**，每次 play 都重新跑一遍安装器：这是唯一能把上游改动拉下来
的机制。`changed` 由前后对 `~/.agents/skills/` 做校验和指纹比对得出。代价是每个源一次网
络请求：十四个源加上前后两次指纹扫描，**实测 136 秒**（mac-mini-m2，2026-09-16），是整
个 playbook 里最慢的 role 之一——单独跑一次 `ansible-playbook` 时值得预期。
另外 `skills add` **从不删除**任何东西，上游下架的技能会作为孤儿目录留在存储里。

#### 看起来像报错、其实是预期输出

这一组 role 在正常运行时会打印几段很像错误的东西，事先知道能省很多排查时间：

- **每个技能源都会报两个 per-agent 失败**（Eve 和 PromptScript 拒绝全局安装）。每个源
  都这样，属于正常噪音。
- **Hermes 拒绝安装 ponytail**，理由是插件扫描器给出 `dangerous` 判定（`--force` 也压不
  住）。role 把这一种失败明确放行并打印补救办法，其它任何错误仍然会让 play 失败。要接受
  这些发现，得自己在 `~/.hermes/config.yaml` 里设 `plugins.scan_on_install: false`——这
  是安全姿态的选择，role 不替你做。
- **claude-mem 每次都报 changed。** 它的安装器无论有没有实际动作都会退出 0 并打印
  "installed successfully"，自己说不清有没有变，所以 role 直接写死 `changed_when: true`。
- 万一某个「只取几个技能」的源里的技能被上游改名或下架，CLI 会退出 1 并打印
  `● Available skills:` 加一整份清单——**读起来像帮助信息，其实是错误**。这时用
  `npx skills@latest add <源> -l` 看上游现在到底有什么（`-l` 只列不装），然后改
  `roles/skills/vars/main.yml`。这类失败被**推迟到整个 play 的末尾**才抛出，这样一个技能改名
  不会挡住它后面的二十个 role，但 PLAY RECAP 里依然是 `failed=1`。

#### role 代劳不了、需要人工的步骤

- **Codex 的 hook 信任**是一次性的、每台机器各做一次：跑 `codex`、打开 `/hooks`，
  审核并信任 ponytail 的三个生命周期 hook（SessionStart、UserPromptSubmit、
  SubagentStart），然后开一个新 thread。role 只负责提醒——替你写入信任就等于预先信任了
  上游下次推送的任何内容，而这正是这道审核存在的意义。
- **opencode 的 provider 认证**没有做：安装器带的是 `--skip-auth`。
- **agent-reach 只配好了零配置的渠道。** 其余渠道要 cookie 或点一下浏览器扩展，headless
  的 `claude -p` 回答不了文档里「你要哪些渠道」这个问题。要补齐就自己交互式跑一次
  `agent-reach doctor`。
- **`claude-mem` 的模型 id 要手工升级。** `roles/claude-mem/vars/main.yml` 里的
  `claude_mem_model` 目前是 `claude-opus-4-8`。claude-mem 不接受 `opus` 这类别名（尽管它
  自己的文档在用），只认完整 id，而且可用集合每次发版都在缩小——id 一旦下架就是一个硬
  错误 `Fatal error: Unknown Claude model`，**会让 play 失败**。

#### kimi-code 只装不升

`kimi-code` 的安装整个挂在 `creates: ~/.kimi-code/bin/kimi` 后面，而且这个 role 里没有
任何 update 任务，所以**它装好之后就再也不会升级**。要升级就把那个二进制删掉再跑一次
playbook。这一点和同组其它 role 不一样——`pi`、`omp`、`codex`、`claude-code` 都会每次
play 调一次各自的 updater。

顺带一提，`pi`、`omp`、`agent-reach` 三家的 updater **在任何情况下都退出 0**，包括被
GitHub 限流的时候。所以前两个是靠比对 `--version` 来判断有没有变，agent-reach 则是匹配
一个**肯定式**的中文标记 `有更新`（不能反过来匹配「已是最新」，因为限流和「仓库没有
release」两条分支也都不含那句话，一反就会每次都白跑一整轮 agent）。

## 致谢

本项目参考了 [hayajo/macbook-provision](https://github.com/hayajo/macbook-provision)。
