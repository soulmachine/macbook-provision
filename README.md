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
| host-facts | 机器判定（`mac_family` / `mac_is_vm` / `mac_is_always_on`）；不装任何软件 |
| homebrew | 通用 Homebrew 包与 GUI 应用：git、curl、wget、jq、ripgrep、fd、tree、htop、docker、ffmpeg、gh、gnupg、tmux；cask 含 claude、gemini、pearcleaner、sublime-text、visual-studio-code（chatgpt 归 codex role）；`brew upgrade` 失败时记录下来、在 play 末尾才报错，不阻断后面的 role |
| github | gh CLI（brew）；若环境中有 `GITHUB_TOKEN`（由 `gh-token-fleet` 写入 `~/.zshenv`，不再来自 `.env`），另外配置 SSH key 与 git 签名 |
| shell | 默认 zsh 的基础配置：brew 装 starship、zoxide、fzf；`~/.config/zsh/` 设历史记录、补全与三者的 hook；登录 shell 设为 `/bin/zsh`；并从 oh-my-zsh 迁移（去掉其模板与 `~/.oh-my-zsh`，卸载 atuin） |
| omarchy | 从 Omarchy 移植的 shell 环境（bash → zsh）：aliases、envs、fns、`try` 与 Omarchy 的 `starship.toml`；brew 装 eza、bat、neovim、try、gum（依赖 shell） |
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
| 1password | 仅在有 `~/personal-agent` 的主机（m6、m2、macbook-air）上安装：1Password App（cask `1password`，`--adopt` 接管手装的 App）、官方 CLI `op`（cask `1password-cli`）与官方 Claude Code 插件 [`1password@1password`](https://github.com/1Password/1password-claude-plugin)（Developer Environments 的 skill、MCP、hook）；App 的 Settings → Developer 中「Integrate with 1Password CLI」与「Integrate with MCP clients」两个开关需手动打开（依赖 claude-code） |
| codex | OpenAI Codex CLI，并安装 [open-pstack](https://github.com/ericlitman/open-pstack) 的 `pstack` 插件（Claude Code 那一半在 claude-code role 的插件列表里；`/pstack:setup-pstack` 需手动运行）（依赖 nodejs） |
| opencode | OpenCode CLI（npm `opencode-ai`）；并用 `npx oh-my-openagent` 写入 `~/.config/opencode/opencode.json`，由版本戳门控，避免每次 play 重装（依赖 nodejs） |
| kimi-code | Kimi Code CLI（通过官方 code.kimi.com 脚本安装） |
| omp | oh-my-pi：bun 全局 `@oh-my-pi/pi-coding-agent`（依赖 bun） |
| pi | pi coding agent：bun 全局 `@earendil-works/pi-coding-agent`，并下发 `~/.pi/agent/settings.json`（依赖 bun） |
| copilot | GitHub Copilot CLI（npm `@github/copilot`）；只经 CLIProxyAPI 使用：`copilot-gw` 由 mac-mini-m2 上的 `cliproxy-tier` 写入（依赖 nodejs） |
| crush | Crush（Charm，npm `@charmland/crush`）；`~/.config/crush/crushrc` 里的网关 provider 由 `cliproxy-tier` 写入（依赖 nodejs） |
| gemini | Gemini CLI（npm `@google/gemini-cli`）；`gemini-gw` 与（没有 Google 登录时）`~/.gemini/settings.json` 由 `cliproxy-tier` 写入（依赖 nodejs） |
| grok | Grok CLI（xAI，npm `@xai-official/grok`，首次运行时下载原生二进制到 `~/.grok/bin`）；`~/.grok/config.toml` 的网关模型由 `cliproxy-tier` 写入（依赖 nodejs） |
| openclaw | OpenClaw（npm `openclaw`），只装在常驻 Mac 上（`mac_is_always_on`，同 hermes）；onboarding、网关 provider 与常驻 daemon 由 `cliproxy-tier` 负责（依赖 host-facts、nodejs） |
| agent-sync | tap `agent-sync-sh/tap`（按 URL tap）+ `brew trust` + brew `agent-sync`；把 `~/.agents/` 扇出到各 agent，并在技能被删除后清理悬空符号链接 |
| skills | 用 `npx skills@latest add` 安装十个整源 + 四个只取指定技能的源，并扇出到各 agent 的 skills 目录；详见下文「Agent CLI 与技能」（依赖 claude-code、codex） |
| agent-reach | 多渠道触达工具；上游只提供面向 AI agent 的安装文档，故由 `claude -p` 按文档驱动安装（依赖 claude-code、python） |
| playwright | 浏览器自动化：npm 全局 `playwright@latest`（依赖 nodejs） |
| playwright-cli | Playwright CLI：npm 全局 `@playwright/cli@latest`，并安装其 skill（依赖 playwright） |
| cua | Cua Driver（`cua.ai/driver/install.sh`）+ jev-use；每次运行 `cua-driver update --apply`，按前后版本号判断是否升级；检查权限前若 daemon 未运行先启动（重启后不会自启）；需先授予 Accessibility 与 Screen Recording，未授权时在 play 末尾报错并给出 `cua-driver permissions grant`（不阻断后面的 role） |
| ego-browser | Ego Lite（[citrolabs/ego-lite](https://github.com/citrolabs/ego-lite)）：agent 用 `ego-browser` CLI 驱动的 Chromium 浏览器。先 `npx skills add citrolabs/ego-lite --skill ego-browser -g -y` 装 skill（只在 `~/.agents/skills/ego-browser` 不存在时跑一次：首次 onboarding 会把 store 项和 claude/hermes 的链接改成指向 app 内自带的 skill，之后由 app 自己保持版本一致，再跑 `skills add` 会写进 app bundle）；`ego lite.app` 不存在时跑 skill 自带的 `scripts/install.sh`（下载 DMG、装到 `/Applications`、去 quarantine、打开 app）；onboarding 需人在屏幕前完成，它会生成 `~/.local/bin/ego-browser`，没生成时在 play 末尾报错（不阻断后面的 role）；之后每次运行 `ego-browser upgrade`（无需人工确认，升级后浏览器会自动重启），按前后 `ego-browser --version` 判断是否升级（依赖 nodejs） |
| intellij-idea | IntelliJ IDEA（依赖 jdk） |
| claude-mem | Claude 记忆插件；`npx -y claude-mem install` 为 claude-code / codex-cli / opencode 三者接线（依赖 nodejs、bun、uv） |
| cc-switch | Claude 配置切换器：tap `farion1231/ccswitch` + cask `cc-switch`（依赖 claude-code、codex） |
| hermes | Hermes 个人 agent（Nous Research）；**仅限常驻开机的机器** |
| lcu | Local Computer Use（[amontlabs/lcu](https://github.com/amontlabs/lcu)）：把 ChatGPT.app 的原生 computer use 作为 MCP server 接给各 agent。首次从 GitHub release 下载 tarball、按 `.sha256` 校验后跑 `scripts/install.sh --runtime-only --yes`；之后每次运行 `lcu update --yes`，按前后版本号判断是否升级，升级后 `lcu prune --yes`（只保留最新两个 release）；再对 `lcu_agents` 里已安装但未注册的 harness 逐个跑 `lcu setup --agent <x> --audio --chrome --yes`（开启 computer-audio recording 与 Chrome 控制；`~/.local/state/lcu/setup.json` 里两项还没都打开时对已安装的全部 harness 重跑一次），再按 `lcu browser status` 的 connector 行决定是否 `lcu browser install` 把 Chrome 的 native host 指向 LCU 的 relay，并把该 manifest 复制进 `Google Chrome CDP.app` 的克隆 profile `~/Library/Application Support/Google/Chrome-CDP/NativeMessagingHosts/`（在 Chrome 里启用官方 ChatGPT 扩展仍需手工）：claude-code、pi、omp、hermes（codex 自带 computer use，不注册；kimi、opencode、copilot、crush、gemini、grok、openclaw 上游没有 adapter）。`lcu` 刻意不进 PATH（`~/.local/share/lcu/current/bin/lcu`）；Accessibility、Screen Recording 授权与首次 `lcu doctor` 需人在屏幕前；仅 Apple Silicon 且装有 ChatGPT.app，否则跳过（依赖 codex，为了 ChatGPT.app cask） |
| browseros-neo | [BrowserOS neo](https://browseros.com)（给 agent 用的 Chromium 浏览器，用你自己的登录）：tap `browseros-ai/tap` 并 `brew trust`，cask `browseros-neo`（`present`，应用自更新）；`claude mcp add --scope user --transport http browseros-neo http://127.0.0.1:9200/mcp`（与 neo 自己的 Connect 按钮写的条目相同，已有则不动）；再装上游的 `browseros-neo` skill（`npx skills add browseros-ai/browseros --skill browseros-neo`）。不开机自启：neo 打开时 Claude Code 才连得上（依赖 claude-code、nodejs） |
| ponytail | 给所有 agent 安装 [ponytail](https://github.com/DietrichGebert/ponytail) 插件——Claude Code / Codex / OpenCode / pi / oh-my-pi / Hermes 各用其原生安装方式；其中 Hermes 部分**仅限常驻开机的机器** |
| paseo | agent 多路复用：MacBook 装桌面版（cask `paseo`）；常驻开机的机器改装 npm `@getpaseo/cli`（CLI + daemon），并卸载 cask、移除 mise 里的旧版本 pin，同时安装并加载由本 role 管理的 `sh.paseo.daemon` LaunchAgent（`paseo daemon run`），并开启 relay（配对仍需手动 `paseo daemon pair`），打开 `pluginsEnabled` 并安装插件 `npm:@oliexe/paseo-bots`（只装不自动更新）；tag `agent-multiplexer`（依赖 host-facts、claude-code、codex） |
| ghostty | 终端模拟器（cask `ghostty`） |
| cmux | 多 agent 工作区：tap `manaflow-ai/cmux` + cask `cmux`，并把 CLI 链接到 `~/.local/bin`（依赖 ghostty） |
| obsidian | Obsidian（cask）+ npm 全局 `defuddle`（依赖 claude-code） |
| cloudflare | Cloudflare CLI：npm 全局 `cf`（依赖 claude-code） |
| multica-cli | tap `multica-ai/tap` + brew `multica-ai/tap/multica` |
| purelymail | Purelymail API CLI（GitHub release 单一二进制装入 `~/.local/bin`，跟随最新 release，无需 cargo）；token 手工放在 `~/.zshenv` |
| email | Himalaya 邮件 CLI（brew）+ ortie OAuth CLI（GitHub release 二进制装入 `~/.local/bin`，跟随最新 release）+ Proton Mail Bridge（cask）；账号配置手工完成 |
| macos-connectors | Apple 应用连接器 CLI（来源：[推文](https://x.com/Kevin_Logan/status/2109271248714784841)）：tap `steipete/tap`、`antoniorodr/memo`、`danielhopkins/formulae` 并 `brew trust`；brew `remindctl`（Reminders）、`imsg`（Messages）、`memo`（Notes）、`apple-tools`（`apple-calendar`、`apple-contacts`、`apple-mail`、`apple-maps`、`apple-phone` 等）；Photos、Find My 无 CLI。各项 macOS 授权（Reminders/Calendar/Contacts 弹窗、终端的完全磁盘访问与自动化）需每台机器手工批准一次，`apple status` 可查看 |
| tailscale | 独立版 Tailscale.app（cask）；若 `.env` 中有 `TAILSCALE_AUTH_KEY` 则自动登录，可选通过 OAuth client 关闭 key 过期 |
| apple-container | Apple `container`（brew）；**仅限 Apple Silicon**，安装后启动 container system |
| removemacai | tap `omlahore/tap` + brew `omlahore/tap/removemacai`；按 macbook-air 导出的配置关闭 Apple Intelligence、分析、广告等（`RemoveMacAI.mobileconfig`，每台机器需在系统设置 > 通用 > 设备管理里手动批准一次），并应用 10 项按用户的设置；**仅限 Apple Silicon** |
| moshi | tap `rjyo/moshi` + brew `moshi-hook`，并通过 brew services 常驻；tag `agent-multiplexer` |
| zellij | 终端复用器（brew `zellij`）；tag `terminal-multiplexer` |
| tmux | 终端复用器（brew `tmux`）；tag `terminal-multiplexer`（`homebrew` 的通用包列表中也有，两处都是 `state: latest`，重复无害） |
| herdr | 用 `npx skills add herdrdev/herdr` 安装 herdr skill，并以相对符号链接接入 `~/.claude/skills`；并用 herdr-rename-hook skill 的 `install.sh` 接上 `/rename` 钩子（Claude Code 与 Codex 的 `/rename` 同步成 Herdr 的 agent、pane 和 tab 名）；tag `terminal-multiplexer` |

### 仅限常驻开机的机器

`hermes` 会常驻一个长期运行的本地服务（Hermes 的 agent 进程），只有 24x7 开机的
机器才用得上。因此这个 role 以及 `ponytail` 里往 Hermes 里装插件的那一步，都以
`mac_is_always_on` 为开关。（`openclaw` 曾经也是这样的 role，2026-09-08 起已从所有
机器卸载；负责卸载的 role 在 2026-09-10 也已删除。）

这个 fact 由 `host-facts` role 设置。它同时是这两个 role 的 meta 依赖，并且被列在
`main.yml` 的 `roles:` 第一位——前者让单独运行某个 role 时也能自行判定（无需
`-e`），后者保证整套 playbook 在任何 role 之前先完成判定。Ansible 对无参数 role 会
去重，所以无论多少 role 依赖它，每次 play 只执行一次。

判断依据是**机型家族**（`mac_family`，取自 `system_profiler` 的 `machine_name`），
规则是一个 **MacBook 黑名单**：虚拟机（`mac_is_vm`）一律安装；`mac_family` 以
`MacBook` 开头（MacBook / MacBook Air / MacBook Pro）的跳过；其余所有机型——Mac mini、
Mac Studio，以及以后出现的任何新机型——都安装。（`sysctl -n hw.model` 在这里没用——所有
Apple Silicon 机型都只报 `MacN,M`，看不出机型家族。）

这条规则是**放行优先**的，属于有意为之（DECISIONS Q171，2026-10-04）。它取代了之前基于
ioreg `BatteryInstalled` 的保守规则：那条规则要求硬件明确报告"没有电池"才安装，因此把
没有电池节点的 2018 Intel Mac mini 挡在外面。现在这台机器也会安装。虚拟机那一条在目前
其实是多余的（虚拟机的机型名是 `Apple Virtual Machine 1`，不以 `MacBook` 开头），保留它
是因为规则本来就是这样定的。

全 fleet 实测结果（2026-10-04，下表每一行都是实测，没有推断）：

| 机器 | 机型 | `mac_family` | 判定 |
|------|------|--------------|------|
| franks-mac-mini-m2 | `Mac14,3`（M2） | Mac mini | **安装** |
| archs-mac-mini | `Mac16,10`（M4） | Mac mini | **安装** |
| mac-mini-m6 | `Mac18,5`（M6） | Mac mini | **安装** |
| franks-mac-studio | `Mac15,14`（M3） | Mac Studio | **安装** |
| dev-server-frank-lume | `VirtualMac2,1` | Apple Virtual Machine 1 | **安装**（虚拟机） |
| franks-mac-mini-2018 | `Macmini8,1`（Intel） | Mac mini | **安装** |
| franks-macbook-air | `Mac16,12`（M4） | MacBook Air | 跳过（MacBook） |
| macbook-pro-nickel | `Mac17,2`（M5） | MacBook Pro | 跳过（MacBook） |

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
| codex | **ChatGPT.app 自带**（`chatgpt` cask，由 codex role 安装，Apple Silicon 与 Intel 都装） | `~/.local/bin/codex` → `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex`，随 ChatGPT.app 自更新 |
| lcu | GitHub release tarball 里的 `scripts/install.sh`，之后由 `lcu update` 自更新 | `~/.local/share/lcu/current/bin/lcu`，**刻意不在 PATH** |
| opencode | npm 全局 `opencode-ai` | 命令 `opencode` |
| kimi-code | 官方 `install.sh`（curl \| bash） | `~/.kimi-code/bin/kimi`，命令是 **`kimi`** 而不是 `kimi-code` |
| omp | bun 全局 `@oh-my-pi/pi-coding-agent` | `~/.bun/bin/omp`，命令是 **`omp`** |
| pi | bun 全局 `@earendil-works/pi-coding-agent` | `~/.bun/bin/pi` |
| copilot | npm 全局 `@github/copilot` | 命令 `copilot`；经网关用 `copilot-gw` |
| crush | npm 全局 `@charmland/crush` | 命令 `crush` |
| gemini | npm 全局 `@google/gemini-cli` | 命令 `gemini`；经网关用 `gemini-gw` |
| grok | npm 全局 `@xai-official/grok` | 命令 `grok`；原生二进制在 `~/.grok/bin` |
| openclaw | npm 全局 `openclaw` | 命令 `openclaw`；常驻 daemon 由 `cliproxy-tier` 的 onboarding 安装 |
| claude-mem | `npx -y claude-mem install` | 不是独立命令，而是 Claude Code 插件，同时接线 codex-cli 和 opencode |
| cc-switch | tap `farion1231/ccswitch` + **cask** | GUI 应用 |
| agent-reach | **没有包管理器**，见下 | 由 `claude -p` 按上游文档安装 |

这五个 agent（copilot、crush、gemini、grok、openclaw）只在没有别的渠道（mise 工具、`~/.local/bin` 里的原生安装器、Homebrew）提供同名命令时才用 npm 安装和升级，否则 role 只打印已有的路径，交给那个渠道去升级，免得 `PATH` 上出现两份。

`codex` 不单独装（既不用 cask 也不用 npm）是刻意的：ChatGPT.app 里本来就带了一份并会自更新；
codex cask 每次升级都会运行 `codex completion`，在部分主机上这次首次启动会卡在没人点的
Gatekeeper 弹窗上（DECISIONS Q197）。role 会先装 `chatgpt` cask、再卸载旧的 codex cask。
`chatgpt` cask 有 Intel（x64）版，codex 在包里的路径相同，所以 mac-mini-2018 也一样处理（DECISIONS Q200）。
role 表里的「依赖 nodejs」指的是运行期依赖，不是安装渠道。

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
- **新装的 agent 要在 mac-mini-m2 上跑一次 `cliproxy-tier <host>`。** `copilot-gw`、`gemini-gw`（主机有自己的 Google 登录时 Gemini 保持原生）、grok、crush、openclaw 的网关配置以及 OpenClaw 的 onboarding 都由它完成，而它只处理已经装好的 agent。
- **rename 钩子装上或更新后**，Codex 下次启动会问是否信任这个钩子，选「Trust all and continue」；已经在跑的 Claude Code 会话要打开一次 `/hooks` 或重启才会用上。
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
