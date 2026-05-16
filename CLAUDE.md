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
- **bootstrap.sh** — Bootstrap script. Prepares a fresh Mac for Ansible. Also installs a `SUDO_ASKPASS` helper: it stores the user's sudo password in the macOS Keychain, writes `~/.local/bin/sudo-askpass` (a script that prints that password to stdout), and appends `export SUDO_ASKPASS=...` to `~/.zshrc`. Note that sudo only consults this helper when invoked with the `-A` flag — it does **not** auto-use `$SUDO_ASKPASS` otherwise. So roles whose inner subprocesses call sudo internally **without** `-A` (e.g. `brew uninstall --cask tailscale-app`, which removes root-owned `pkg` payload files) must run an explicit `sudo -A -v` priming task first; brew's subsequent un-flagged sudo calls then reuse the cached timestamp within sudo's default ~5-minute window. See `roles/tailscale/tasks/main.yml` for the canonical pattern. The script is idempotent — it skips the askpass setup if `~/.local/bin/sudo-askpass` already exists. It also runs a no-op `osascript` against System Events to trigger the macOS Automation (AppleEvents) consent dialog for the host terminal (e.g. Ghostty) on first run; later runs no longer prompt. This pre-authorizes the terminal so headless osascript calls (e.g. `brew uninstall --cask`'s `tell app to quit`) don't hang on a dialog nobody is around to click.
- **`.env` / `.envrc`** — Optional. `.envrc` runs `dotenv_if_exists .env` so direnv loads `.env` into the shell. Currently only the `tailscale` role consumes this (reads `TAILSCALE_AUTH_KEY` to auto-run `tailscale up`); new roles that need secrets should follow the same pattern — gate the task on `lookup('env', 'VAR') | length > 0` and document the var in `.env.example`.
- **roles/** — Each role provisions one tool or application.

#### Tailscale role specifics

- Installs the CLI/`tailscaled` via Homebrew (not the App Store GUI cask — sandboxed builds can't enable Tailscale SSH). See header comment in `roles/tailscale/tasks/main.yml` for the full rationale.
- The auto-login task uses `become: true` and is gated on `TAILSCALE_AUTH_KEY`; if the var is unset, the role just installs the binary and the user must run `tailscale up` manually.
- MagicDNS on macOS needs two things: (1) enabled tailnet-wide in the admin console (one-time), and (2) `/etc/resolver/ts.net` containing `nameserver 100.100.100.100` so macOS routes `*.ts.net` queries to tailscaled. The role writes that file because tailscaled itself only adds the search domain; without the resolver file, `ssh host.<tailnet>.ts.net` fails with NXDOMAIN even though MagicDNS is enabled.
- Leftover GUI CLI shim: the standalone Tailscale.app installs a `#!/bin/sh` shim at `/usr/local/bin/tailscale` that execs `/Applications/Tailscale.app/Contents/MacOS/tailscale`. The cask uninstall removes the `.app` but orphans this shim. On Apple Silicon `/usr/local/bin` precedes `/opt/homebrew/bin` on PATH, so the dead shim shadows the Homebrew CLI and every `tailscale` call fails with "No such file or directory" — which surfaces as a censored `non-zero return code` on the `tailscale up` task because of its `no_log: true`. The role removes the shim with a stat + `file: state=absent` pair gated on `exists and not islnk` (Homebrew's CLI is always a Cellar symlink; the GUI shim is a regular file). Note `/usr/local/bin/tailscaled` is a real binary that `tailscaled install-system-daemon` copies there on purpose (the LaunchDaemon plist references it) — do not remove it.
- Full Disk Access for tailscaled: Tailscale SSH spawns the login shell as a child of tailscaled, so the shell inherits tailscaled's TCC sandbox. Without FDA on `/usr/local/bin/tailscaled`, commands like `cd ~/Desktop` and `cd ~/Documents` fail with "Operation not permitted" inside SSH sessions. macOS TCC can't be granted programmatically on an unmanaged Mac (`tccutil` only resets permissions, the system `TCC.db` is SIP-protected, and unsigned PPPC profiles still require manual approval), so the role opens System Settings → Privacy & Security → Full Disk Access via the `x-apple.systempreferences:` URL scheme and pauses with `ansible.builtin.pause` for the user to add the binary. A marker file at `~/.local/state/macbook-provision/tailscaled-fda-acknowledged` suppresses the prompt on subsequent runs — delete it to re-trigger. After acknowledgment, the role bounces tailscaled via `launchctl kickstart -k system/com.tailscale.tailscaled` because TCC permissions are checked at process start; the already-running daemon wouldn't otherwise see the new grant.

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
