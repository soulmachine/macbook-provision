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
sudo -v # 某些task有 become: true, 需要root权限
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

### 可选 Roles（未包含在 `main.yml` 中）

| Role | 说明 |
|------|------|
| pearcleaner | macOS 应用卸载清理工具 |
| pycharm | PyCharm IDE |
| webstorm | WebStorm IDE（依赖 nodejs） |
| scrapy | Scrapy 网络爬虫框架 |

## 致谢

本项目参考了 [hayajo/macbook-provision](https://github.com/hayajo/macbook-provision)。
