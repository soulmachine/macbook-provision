# Macbook Provision

使用 Ansible 自动化 macOS 开发环境配置，通过 [Homebrew 模块](https://docs.ansible.com/ansible/latest/collections/community/general/homebrew_module.html) 安装和管理软件。

## 语言运行时

本项目使用 [mise](https://github.com/jdx/mise) 安装语言运行时（Go、Node.js、JDK 等），而非 Homebrew。mise 是一个多语言版本管理工具，支持在同一台机器上安装和切换多个版本，例如在 JDK 22 和 JDK 23 之间自由切换。

## 使用方法

### 1. 安装 Ansible

该脚本会自动安装 Xcode Command Line Tools、Homebrew、mise、Python 和 Ansible：

```bash
./install_ansible.sh
```

### 2. 运行 Playbook

```bash
ansible-playbook -vv all.yml
```

运行单个 role：

```bash
ansible localhost -m include_role -a name=openclaw
```

### 3. 试运行（不修改系统）

```bash
ansible-playbook -vv all.yml --check
```

## 包含的 Roles

### Playbook 中的 Roles（`all.yml`）

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

### 可选 Roles（未包含在 `all.yml` 中）

| Role | 说明 |
|------|------|
| pearcleaner | macOS 应用卸载清理工具 |
| pycharm | PyCharm IDE |
| webstorm | WebStorm IDE（依赖 nodejs） |
| scrapy | Scrapy 网络爬虫框架 |

## 致谢

本项目参考了 [hayajo/macbook-provision](https://github.com/hayajo/macbook-provision)。
