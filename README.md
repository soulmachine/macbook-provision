# Macbook Provision

使用 Ansible 自动化 macOS 开发环境配置，通过 [Homebrew 模块](https://docs.ansible.com/ansible/latest/collections/community/general/homebrew_module.html) 安装和管理软件。

## 语言运行时

本项目使用 [mise](https://github.com/jdx/mise) 安装语言运行时（Go、Node.js、JDK 等），而非 Homebrew。mise 是一个多语言版本管理工具，支持在同一台机器上安装和切换多个版本，例如在 JDK 22 和 JDK 23 之间自由切换。

## 包含的 Roles

| Role | 说明 |
|------|------|
| oh-my-zsh | Zsh 框架 |
| direnv | 目录级环境变量管理 |
| go | Go 语言（通过 mise 安装） |
| nodejs | Node.js（通过 mise 安装） |
| jdk | JDK（通过 mise 安装） |
| gpg | GnuPG 加密工具 |
| docker | Docker 容器引擎 |
| vscode | Visual Studio Code |
| sublime-text | Sublime Text 编辑器 |

## 使用方法

### 1. 安装 Ansible

该脚本会自动安装 Xcode Command Line Tools、Homebrew、mise、Python 和 Ansible：

```bash
./install_ansible.sh
```

### 2. 运行 Playbook

```bash
ansible-playbook -i localhost, -vv all.yml
```

Or apply a single role,

```bash
ansible -i localhost, -c local -m include_role -a name=claude-code localhost -vv
```

## 致谢

本项目参考了 [hayajo/macbook-provision](https://github.com/hayajo/macbook-provision)。
