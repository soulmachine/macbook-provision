# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ansible-based macOS development environment provisioner. Uses Homebrew (via Ansible's `community.general.homebrew` and `community.general.homebrew_cask` modules) to install and configure software.

## Commands

```bash
# First-time setup (installs Xcode CLI Tools, Homebrew, mise, Python, Ansible)
./bootstrap.sh

# Run full provisioning
ansible-playbook main.yml

# Dry run
ansible-playbook main.yml --check
```

## Architecture

- **main.yml** — Main playbook that runs roles in order. Add new roles here.
- **playbook.yml** — Legacy playbook (not actively used). Defines packages inline with Japanese comments.
- **bootstrap.sh** — Bootstrap script. Prepares a fresh Mac for Ansible. Also configures `SUDO_ASKPASS` — sudo's standard mechanism for fetching a password from a helper program instead of prompting interactively. The script stores the sudo password in macOS Keychain and writes `~/.local/bin/sudo-askpass`, so Homebrew and other sudo subprocesses spawned during the playbook can read the password non-interactively (they don't inherit `sudo -v`'s cached credentials, so without this they would pop a GUI password prompt and stall the run). The script is idempotent — it skips the askpass setup if `~/.local/bin/sudo-askpass` already exists.
- **`.env` / `.envrc`** — Optional. `.envrc` runs `dotenv_if_exists .env` so direnv loads `.env` into the shell. Currently only the `tailscale` role consumes this (reads `TAILSCALE_AUTH_KEY` to auto-run `tailscale up`); new roles that need secrets should follow the same pattern — gate the task on `lookup('env', 'VAR') | length > 0` and document the var in `.env.example`.
- **roles/** — Each role provisions one tool or application.

#### Tailscale role specifics

- Installs the CLI/`tailscaled` via Homebrew (not the App Store GUI cask — sandboxed builds can't enable Tailscale SSH). See header comment in `roles/tailscale/tasks/main.yml` for the full rationale.
- The auto-login task uses `become: true` and is gated on `TAILSCALE_AUTH_KEY`; if the var is unset, the role just installs the binary and the user must run `tailscale up` manually.
- MagicDNS does not auto-configure with `tailscaled` — user must enable it in the admin console; the role already passes `--accept-dns`.

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
