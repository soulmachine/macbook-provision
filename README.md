# Macbook Provision

使用 Ansible 自动化 macOS 开发环境配置，通过 [Homebrew 模块](https://docs.ansible.com/ansible/latest/collections/community/general/homebrew_module.html) 安装和管理软件。

## 语言运行时

本项目使用 [mise](https://github.com/jdx/mise) 安装语言运行时（Go、Node.js、JDK 等），而非 Homebrew。mise 是一个多语言版本管理工具，支持在同一台机器上安装和切换多个版本，例如在 JDK 22 和 JDK 23 之间自由切换。

## 使用方法

### 1. 安装 Ansible

```bash
./bootstrap.sh
```

该脚本会自动安装 Xcode Command Line Tools、Homebrew、mise、Python 和 Ansible，并配置 `SUDO_ASKPASS`。

> **关于 `SUDO_ASKPASS`**：`SUDO_ASKPASS` 是 `sudo` 标准的密码获取机制——指向一个辅助程序，`sudo` 在需要密码时会调用它读取密码，而非交互式提示用户输入。Ansible 中标注 `become: true` 的任务可以用 `sudo -v` 提前缓存凭证，但 Homebrew 等命令会派生子进程执行 `sudo`，子进程不继承父进程的缓存，仍会弹出 GUI 密码框打断 playbook。脚本会把密码存入 macOS Keychain，并生成 `~/.local/bin/sudo-askpass`——`sudo` 在需要密码时会调用该脚本从 Keychain 读取，使整个过程无需人工干预。
>
> 首次运行会一次性提示输入 macOS 用户密码（写入 Keychain），随后 Keychain 弹窗确认权限时选 "Always Allow" 即可。`bootstrap.sh` 重复执行时会跳过已完成的配置。

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

如果 `.env` 文件存在且包含 `TAILSCALE_AUTH_KEY`，`roles/tailscale` 会额外执行一个步骤完成本机登录，等价于手工执行 `sudo tailscale up --auth-key=tskey-auth-xxxxxxxxxxxxx --accept-dns --ssh --operator=$USER`。

#### 获取并配置 Tailscale auth key

1. 访问 https://login.tailscale.com/admin/settings/keys ，创建一个启用了 "Reusable" 的 auth key。
2. 把 auth key 写入 `.env`：先 `cp .env.example .env`，然后把里面的 `tskey-auth-xxxxxx` 替换成真实 key，接着 `direnv allow`，最后运行 `ansible-playbook main.yml`。

`tailscale up` flag 说明：

- `--accept-dns`：启用 MagicDNS，详见下一节。
- `--ssh`：开启 Tailscale SSH，使用 tailnet 身份认证，无需维护 `authorized_keys`。
- `--operator=$USER`：把当前用户登记为 operator，之后跑 `tailscale status`、`tailscale set` 等命令不再需要 `sudo`。

#### 启用 MagicDNS

GUI 版的 Tailscale 会自动配置 DNS，使用 `tailscaled` CLI 时需要两步：

1. 访问 https://login.tailscale.com/admin/dns ，在 tailnet 层面启用 MagicDNS（一次性配置）。
2. 在 `tailscale up` 命令上追加 `--accept-dns`（本 role 已自动追加）。

`tailscaled` 在 macOS 上只会写入 `/etc/resolver/search.tailscale`（只有 search domain，没有 nameserver），所以 `*.ts.net` 的 DNS 查询不会走到 tailscaled，会返回 NXDOMAIN。本 role 会额外写入 `/etc/resolver/ts.net`（内容为 `nameserver 100.100.100.100`），让 macOS 把 `*.ts.net` 的查询交给 tailscaled 的 MagicDNS resolver 处理。

若只通过 Tailscale IP 访问主机，可以跳过此节。

## 包含的 Roles

### Playbook 中的 Roles（`main.yml`）

| Role | 说明 |
|------|------|
| oh-my-zsh | Zsh 框架及插件管理 |
| direnv | 目录级环境变量管理 |
| go | Go 语言（通过 mise 安装） |
| nodejs | Node.js（通过 mise 安装） |
| bun | Bun JavaScript 运行时 |
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
| tailscale | Tailscale CLI 及 `tailscaled` 守护进程；若 `.env` 中有 `TAILSCALE_AUTH_KEY` 则自动登录 |

### 可选 Roles（未包含在 `main.yml` 中）

| Role | 说明 |
|------|------|
| pearcleaner | macOS 应用卸载清理工具 |
| pycharm | PyCharm IDE |
| webstorm | WebStorm IDE（依赖 nodejs） |
| scrapy | Scrapy 网络爬虫框架 |

## 致谢

本项目参考了 [hayajo/macbook-provision](https://github.com/hayajo/macbook-provision)。
