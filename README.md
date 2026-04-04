# Macbook Provision

使用 Ansible 自动化 macOS 开发环境配置，通过 [Homebrew 模块](https://docs.ansible.com/ansible/latest/collections/community/general/homebrew_module.html) 安装和管理软件。

## 包含的 Roles

| Role | 说明 |
|------|------|
| oh-my-zsh | Zsh 框架 |
| direnv | 目录级环境变量管理 |
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

## 致谢

本项目参考了 [hayajo/macbook-provision](https://github.com/hayajo/macbook-provision)。
