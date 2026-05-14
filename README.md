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

### 2. 配置 SUDO_ASKPASS

Ansible 中标注 `become: true` 的任务可以通过 `sudo -v` 提前缓存密码。但某些命令会派生子进程执行 `sudo`（例如 Homebrew），子进程不继承父进程的 sudo 凭证，仍会弹出密码框。配置 `SUDO_ASKPASS` 后，sudo 在需要密码时会调用指定脚本从 Keychain 自动获取，避免中断。

```bash
# 1. 把密码存入 Keychain（一次性，按提示输入）
security add-generic-password -a "$USER" -s "sudo-askpass" -w

# 2. 创建 askpass 脚本
mkdir -p ~/.local/bin
cat > ~/.local/bin/sudo-askpass <<'EOF'
#!/bin/bash
security find-generic-password -a "$USER" -s "sudo-askpass" -w
EOF
chmod 700 ~/.local/bin/sudo-askpass

# 3. 导出环境变量（建议写入 ~/.zshrc 以持久化）
export SUDO_ASKPASS="$HOME/.local/bin/sudo-askpass"
```

脚本首次运行时 Keychain 会弹窗确认权限，选 "Always Allow" 即可。

### 3. 运行 Playbook

```bash
ansible-playbook main.yml
```

运行单个 role：

```bash
ansible localhost -m include_role -a name=openclaw
```

### 4. 试运行（不修改系统）

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
