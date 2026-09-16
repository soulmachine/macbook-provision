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
| go | Go 语言（通过 mise 安装） |
| nodejs | Node.js（通过 mise 安装） |
| bun | Bun JavaScript 运行时 |
| rust | Rust 工具链（通过官方 rustup 安装；额外含 rust-src、rust-analyzer 组件） |
| jdk | JDK（通过 mise 安装） |
| claude-code | Claude Code CLI 及插件（依赖 nodejs） |
| claude-extras | Claude Code 周边工具：npm `@inulute/cux`、uv 工具 `claude-swap`（依赖 nodejs、uv、claude-code） |
| codex | OpenAI Codex CLI（依赖 nodejs） |
| opencode | OpenCode CLI（npm `opencode-ai`）；并用 `npx oh-my-openagent` 写入 `~/.config/opencode/opencode.json`，由版本戳门控，避免每次 play 重装（依赖 nodejs） |
| kimi-code | Kimi Code CLI（通过官方 code.kimi.com 脚本安装） |
| omp | oh-my-pi：bun 全局 `@oh-my-pi/pi-coding-agent`（依赖 bun） |
| pi | pi coding agent：bun 全局 `@earendil-works/pi-coding-agent`，并下发 `~/.pi/agent/settings.json`（依赖 bun） |
| skills | 用 `npx skills@latest add` 安装十个技能源，并扇出到各 agent 的 skills 目录（依赖 claude-code、codex） |
| agent-reach | 多渠道触达工具；上游只提供面向 AI agent 的安装文档，故由 `claude -p` 按文档驱动安装（依赖 claude-code、python） |
| playwright | 浏览器自动化：npm 全局 `playwright@latest`（依赖 nodejs） |
| playwright-cli | Playwright CLI：npm 全局 `@playwright/cli@latest`，并安装其 skill（依赖 playwright） |
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


## 致谢

本项目参考了 [hayajo/macbook-provision](https://github.com/hayajo/macbook-provision)。
