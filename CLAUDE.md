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
- **`.env` / `.envrc`** — Optional. `.envrc` runs `dotenv_if_exists .env` so direnv loads `.env` into the shell. Currently only the `tailscale` role consumes this (reads `TAILSCALE_AUTH_KEY` to auto-run `tailscale up`, and optionally `TAILSCALE_API_ACCESS_TOKEN` to disable node-key expiry); new roles that need secrets should follow the same pattern — gate the task on `lookup('env', 'VAR') | length > 0` and document the var in `.env.example`.
- **roles/** — Each role provisions one tool or application.

#### Tailscale role specifics

**Scope of usage:** This role uses Tailscale **only as a network-connectivity layer** (private mesh + MagicDNS). It intentionally does NOT enable Tailscale SSH. Remote shell access is handled separately by standard OpenSSH; Tailscale just provides the routable mesh address. This is why there is no `--ssh` flag, no `tag:server`/`tag:laptop` advertisement, no ACL `tagOwners` management, no Full Disk Access prompt for `/Applications/Tailscale.app`, and no laptop-vs-server branching — every facility tied to Tailscale SSH or tags is deliberately absent. If you ever turn Tailscale SSH back on, you'll need to reintroduce: the FDA grant (so SSH child shells inherit working TCC), and — if you want per-machine ACL gating — `--advertise-tags` plus the API-driven `tagOwners` update.

- Installs the standalone **Tailscale.app** via the `tailscale-app` cask (the official build from tailscale.com, NOT the App Store sandboxed version). The cask is a `.pkg`-based install, so brew calls `sudo` internally without `-A`; the role primes the sudo timestamp via an explicit `sudo -A -v` task first so brew's later un-flagged sudo calls reuse the cache. The cask ships the GUI app, the embedded `tailscaled`, and a CLI shim at `/usr/local/bin/tailscale`. MagicDNS auto-configures through the Network Extension — no `/etc/resolver/ts.net` file is needed.
- **Network Extension auto-check.** Before `tailscale up`, the role runs `systemextensionsctl list | grep -i tailscale | grep -q '\[activated enabled\]'`. If that returns non-zero (extension disabled, in `activated waiting for user` state, or not yet registered because Tailscale.app has never been launched), the role does `open -a Tailscale` and pauses with instructions for System Settings → General → Login Items & Extensions → Network Extensions → toggle Tailscale ON. No marker file — the `systemextensionsctl` query is the source of truth, so the prompt only appears when the extension actually isn't enabled. The user may also see the "Tailscale would like to add VPN configurations" dialog on first launch; clicking Allow there is part of the same flow.
- **Auto-login when `TAILSCALE_AUTH_KEY` is set.** The role runs `tailscale up --accept-dns --accept-routes --operator=$USER --auth-key=...` under `become: true`. Skipped if the node is already in `BackendState: Running`. Note: `tailscale up` rejects a call that drops a previously-set non-default flag (it requires either `--reset` or re-stating every non-default flag), so the role must list every non-default flag the daemon was last brought up with — `--accept-routes` is included for that reason and to let this node receive subnet routes advertised by other nodes.
- **Key-expiry disable.** When `TAILSCALE_API_ACCESS_TOKEN` is also set, the role reads `Self.ID` from `tailscale status --json` (Tailscale's REST API accepts this as the device identifier) and `POST`s to `/api/v2/device/{id}/key` with `keyExpiryDisabled: true`. Skipped silently if the token isn't set. The token needs the `devices` write scope.

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
