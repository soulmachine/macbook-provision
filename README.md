# Macbook 一键装机

基本思路是使用 Ansible 来自动化所有操作。Ansible有一个[Homebrew模块](http://docs.ansible.com/ansible/homebrew_module.html), 底层调用 homebrew来安装各种软件。

本项目参考了 [hayajo/macbook-provision](https://github.com/hayajo/macbook-provision)


## 1. 安装Ansible

```bash
./install_ansible.sh
```

## 2 运行 playbook 开始一键装机

```bash
ansible-playbook -i localhost, -vv all.yml
```
