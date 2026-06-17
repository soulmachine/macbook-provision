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
ansible localhost -m include_role -a name=openclaw
```

### 3. 试运行（不修改系统）

```bash
ansible-playbook main.yml --check
```

### 4. 可选：Tailscale 配置

`roles/tailscale` 通过 `brew install --cask tailscale-app` 安装独立版 Tailscale.app（tailscale.com 官网下载的版本，**不是** App Store 的沙盒版）。MagicDNS 会通过 Network Extension 自动配置，无需手工写入 `/etc/resolver/ts.net`。

> **使用范围说明**：本 role 只把 Tailscale 当作**网络连接层**使用（私有 mesh + MagicDNS），**不启用 Tailscale SSH** 这个 feature。远程 shell 仍然走标准 OpenSSH，Tailscale 只负责提供可达的 mesh 地址。也正因为如此，role 里没有 `--ssh` flag、没有 `tag:server` / `tag:laptop` 这些 ACL tag、没有 ACL `tagOwners` 自动管理、没有 `/Applications/Tailscale.app` 的 Full Disk Access 提示，也没有按机型分服务器/笔记本两条 profile——所有围绕 Tailscale SSH 和 tag 的额外步骤都被刻意去掉了。如果之后改用 Tailscale SSH，需要重新加回：FDA 授权（保证 SSH 子 shell 继承到正确的 TCC 沙盒），以及（如果想按机器粒度限制 ACL）`--advertise-tags` 和通过 API 维护 `tagOwners`。

#### Network Extension 自动检测

在执行 `tailscale up` 之前，role 会用 `systemextensionsctl list` 检查 Tailscale 的 Network Extension 是否处于 `[activated enabled]` 状态。如果没有（包括「尚未启用」「等待用户授权」或「Tailscale.app 从未启动过所以扩展还没注册」三种情况），role 会自动 `open -a Tailscale` 并暂停，提示用户在 GUI 中完成下面这一步：

> System Settings → General → Login Items & Extensions → Network Extensions → 把 **Tailscale** 开关打开

如果同时弹出 "Tailscale would like to add VPN configurations" 对话框，点 **Allow** 即可（Touch ID / 密码）。

打开开关后按 Enter 继续。检测以 `systemextensionsctl` 的实时输出为准——没有 marker 文件，下次运行会自动重新探测：扩展已启用则跳过这一步，扩展被关掉则会再次提示。

#### 环境变量

将 `.env.example` 复制为 `.env`，按需填写以下变量，然后 `direnv allow`，最后运行 `ansible-playbook main.yml`：

| 变量 | 作用 | 必填 |
|------|------|------|
| `TAILSCALE_AUTH_KEY` | 自动执行 `sudo tailscale up --accept-dns --operator=$USER --auth-key=...` 把本机加入 tailnet。在 https://login.tailscale.com/admin/settings/keys 创建一个 **Reusable** key 即可。 | 否（不设则需手工 `tailscale up`） |
| `TAILSCALE_API_ACCESS_TOKEN` | 通过 Tailscale REST API 关闭本机 node-key 过期（避免节点定期下线）。token 需要 `devices` 写权限。 | 否 |

`tailscale up` flag 说明：

- `--accept-dns`：启用 MagicDNS（需提前在 https://login.tailscale.com/admin/dns 的 tailnet 层面启用一次）。
- `--operator=$USER`：把当前用户登记为 operator，之后跑 `tailscale status`、`tailscale set` 等命令不再需要 `sudo`。

## 包含的 Roles

### Playbook 中的 Roles（`main.yml`）

| Role | 说明 |
|------|------|
| oh-my-zsh | Zsh 框架及插件管理 |
| direnv | 目录级环境变量管理 |
| go | Go 语言（通过 mise 安装） |
| nodejs | Node.js（通过 mise 安装） |
| bun | Bun JavaScript 运行时 |
| rust | Rust 工具链（通过官方 rustup 安装；额外含 rust-src、rust-analyzer 组件） |
| jdk | JDK（通过 mise 安装） |
| gpg | GnuPG 加密工具 |
| docker | Docker CLI |
| vscode | Visual Studio Code |
| sublime-text | Sublime Text 编辑器 |
| intellij-idea | IntelliJ IDEA（依赖 jdk） |
| claude-code | Claude Code CLI 及插件（依赖 nodejs） |
| codex | OpenAI Codex CLI（依赖 nodejs） |
| gemini | Google Gemini CLI（依赖 nodejs） |
| openclaw | OpenClaw 及 ClawHub CLI（依赖 nodejs） |
| beads | Beads 任务追踪工具（依赖 go、nodejs） |
| ralph-tui | Ralph TUI 及技能（依赖 bun、claude-code） |
| tailscale | 独立版 Tailscale.app（cask）；若 `.env` 中有 `TAILSCALE_AUTH_KEY` 则自动登录，可选通过 API token 关闭 key 过期 |

### 可选 Roles（未包含在 `main.yml` 中）

| Role | 说明 |
|------|------|
| pearcleaner | macOS 应用卸载清理工具 |
| pycharm | PyCharm IDE |
| webstorm | WebStorm IDE（依赖 nodejs） |
| scrapy | Scrapy 网络爬虫框架 |

## 致谢

本项目参考了 [hayajo/macbook-provision](https://github.com/hayajo/macbook-provision)。
