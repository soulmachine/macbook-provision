# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ansible-based macOS development environment provisioner. Uses Homebrew (via Ansible's `community.general.homebrew` and `community.general.homebrew_cask` modules) to install and configure software.

## Commands

```bash
# First-time setup (installs Xcode CLI Tools, Homebrew, mise, Python, Ansible)
./bootstrap.sh

# Run full provisioning
sudo -v # sudo is needed for tasks with become: true, for example tailscale role's `tailscale up` task
ansible-playbook main.yml

# Dry run
sudo -v
ansible-playbook main.yml --check
```

## Architecture

- **main.yml** — Main playbook that runs roles in order. Add new roles here.
- **playbook.yml** — Legacy playbook (not actively used). Defines packages inline with Japanese comments.
- **bootstrap.sh** — Bootstrap script. Prepares a fresh Mac for Ansible. Also configures `SUDO_ASKPASS` — sudo's standard mechanism for fetching a password from a helper program instead of prompting interactively. The script stores the sudo password in macOS Keychain and writes `~/.local/bin/sudo-askpass`, so Homebrew and other sudo subprocesses spawned during the playbook can read the password non-interactively (they don't inherit `sudo -v`'s cached credentials, so without this they would pop a GUI password prompt and stall the run). The script is idempotent — it skips the askpass setup if `~/.local/bin/sudo-askpass` already exists.
- **roles/** — Each role provisions one tool or application.

### Role Structure

Every role has `tasks/main.yml`. Some also have:
- `vars/main.yml` — Data (e.g., npm package lists in `nodejs`)
- `meta/main.yml` — Dependencies (e.g., `intellij-idea` depends on `jdk`, `webstorm` depends on `nodejs`)

### Common Task Patterns

- CLI tools: `community.general.homebrew` with `state: latest`
- GUI apps: `community.general.homebrew_cask` with `state: present`
- Complex setup (oh-my-zsh, direnv): shell commands, git clone, sed modifications

### Adding a New Role

1. Create `roles/<name>/tasks/main.yml`
2. Add the role name to the `roles:` list in `main.yml`
3. If it depends on another role, add `meta/main.yml` with `dependencies:`
