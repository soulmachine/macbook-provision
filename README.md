# Macbook 一键装机

基本思路是使用 Ansible 来自动化所有操作。Ansible有一个[Homebrew模块](http://docs.ansible.com/ansible/homebrew_module.html), 底层调用 homebrew来安装各种软件。

本项目参考了 [hayajo/macbook-provision](https://github.com/hayajo/macbook-provision)


## 1. 前期准备

执行本工程下的 `./prepare.sh` 进行前期准备，这个脚本做了以下4件事：

### 1.1 安装 Xcode Command Line Tools

    sudo xcodebuild -license
    xcode-select --install

### 1.2 安装 oh-my-zsh

`sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"`


### 1.3 安装 Homebrew

Homebrew 是 Mac OS X 上最流行的包管理工具，类似于 Ubuntu上的 Apt, CentOS上的yum. ，本书

    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    brew update


### 1.4 安装 Python

```bash
brew install pyenv
pyenv install 3.12.9 && pyenv global 3.12.9
pip install --upgrade pip setuptools wheel
```

And add the following lines before `plugins=`:

```bash
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init --path)"
```

And add `pyenv` to the line `plugins=(...)`, see [oh-my-zsh pyenv plugin](https://github.com/ohmyzsh/ohmyzsh/tree/master/plugins/pyenv).


### 1.5 安装 direnv

`brew install direnv`

Edit `~/.zshrc` and add `direnv` to the line `plugins=(...)`, see [oh-myzsh direnv plugin](https://github.com/ohmyzsh/ohmyzsh/tree/master/plugins/direnv).

### 1.6 Install NodeJS

Install nvm,

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.2/install.sh | bash
```

Add the following environment variables to `~/.zshrc`:

```bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion
```

Install NodeJS:

```bash
nvm install 22
nvm use 22
```

### 1.7 install JDK

Install sdkman,

```bash
curl -s "https://get.sdkman.io" | bash
```

Install JDK,

```
sdk install java 24-amzn
```

### 1.8 安装 Ansible

    pip install ansible

## 2 运行 playbook 开始一键装机

准备工作做完了，终于可以开始正式应用 playbook到本机，自动化一键装机了！

    ansible-playbook -i localhost, -vv all.yml
