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
- **bootstrap.sh** — Bootstrap script. Prepares a fresh Mac for Ansible. Also configures **passwordless sudo** so the playbook's sudo subprocesses (Homebrew casks, `pkgutil`/`rm` cleanup, Ansible `become`) run unattended: it installs a `/etc/sudoers.d/<user>-nopasswd` drop-in (`<user> ALL=(ALL) NOPASSWD: ALL`, mode 0440), validated with `visudo -cf` and rolled back if validation fails. The first `sudo` call prompts once on a fresh Mac (to write the drop-in); every `sudo` after — both in the rest of bootstrap and in the playbook — is passwordless, so no `SUDO_ASKPASS` helper or `sudo -A -v` priming is needed anywhere (and `ansible.cfg` uses plain `become_flags = -H`). The script is idempotent — it skips the sudoers setup if the drop-in already exists (`[[ -f ... ]]`, no sudo required to check). It also runs a no-op `osascript` against System Events to trigger the macOS Automation (AppleEvents) consent dialog for the host terminal (e.g. Ghostty) on first run; later runs no longer prompt. This pre-authorizes the terminal so headless osascript calls (e.g. `brew uninstall --cask`'s `tell app to quit`) don't hang on a dialog nobody is around to click.
- **`.env` / `.envrc`** — Optional. `.envrc` runs `dotenv_if_exists .env` so direnv loads `.env` into the shell. Currently only the `tailscale` role consumes this (reads `TAILSCALE_AUTH_KEY` to auto-run `tailscale up`, and optionally `TAILSCALE_API_ACCESS_TOKEN` to disable node-key expiry); new roles that need secrets should follow the same pattern — gate the task on `lookup('env', 'VAR') | length > 0` and document the var in `.env.example`.
- **roles/** — Each role provisions one tool or application.

#### Tailscale role specifics

**Scope of usage:** This role uses Tailscale **only as a network-connectivity layer** (private mesh + MagicDNS). It intentionally does NOT enable Tailscale SSH. Remote shell access is handled separately by standard OpenSSH; Tailscale just provides the routable mesh address. This is why there is no `--ssh` flag, no `tag:server`/`tag:laptop` advertisement, no ACL `tagOwners` management, no Full Disk Access prompt for `/Applications/Tailscale.app`, and no laptop-vs-server branching — every facility tied to Tailscale SSH or tags is deliberately absent. If you ever turn Tailscale SSH back on, you'll need to reintroduce: the FDA grant (so SSH child shells inherit working TCC), and — if you want per-machine ACL gating — `--advertise-tags` plus the API-driven `tagOwners` update.

- Installs the standalone **Tailscale.app** via the `tailscale-app` cask (the official build from tailscale.com, NOT the App Store sandboxed version). The cask is a `.pkg`-based install, so brew calls `sudo` internally without `-A`; passwordless sudo (configured by bootstrap.sh) lets that run unattended — no timestamp priming needed. The cask ships the GUI app, the embedded `tailscaled`, and a CLI shim at `/usr/local/bin/tailscale`. MagicDNS auto-configures through the Network Extension — no `/etc/resolver/ts.net` file is needed.
- **Network Extension auto-check.** Before `tailscale up`, the role runs `systemextensionsctl list | grep -i tailscale | grep -q '\[activated enabled\]'`. If that returns non-zero (extension disabled, in `activated waiting for user` state, or not yet registered because Tailscale.app has never been launched), the role does `open -a Tailscale` and pauses with instructions for System Settings → General → Login Items & Extensions → Network Extensions → toggle Tailscale ON. No marker file — the `systemextensionsctl` query is the source of truth, so the prompt only appears when the extension actually isn't enabled. The user may also see the "Tailscale would like to add VPN configurations" dialog on first launch; clicking Allow there is part of the same flow.
- **Auto-login when `TAILSCALE_AUTH_KEY` is set.** The role runs `tailscale up --accept-dns --accept-routes --operator=$USER --auth-key=...` under `become: true`. Skipped if the node is already in `BackendState: Running`. Note: `tailscale up` rejects a call that drops a previously-set non-default flag (it requires either `--reset` or re-stating every non-default flag), so the role must list every non-default flag the daemon was last brought up with — `--accept-routes` is included for that reason and to let this node receive subnet routes advertised by other nodes.
- **Key-expiry disable.** When `TAILSCALE_API_ACCESS_TOKEN` is also set, the role reads `Self.ID` from `tailscale status --json` (Tailscale's REST API accepts this as the device identifier) and `POST`s to `/api/v2/device/{id}/key` with `keyExpiryDisabled: true`. Skipped silently if the token isn't set. The token needs the `devices` write scope.

#### Agent-reach role specifics

- **Installed by an agent, not a script.** Upstream ships `docs/install.md` and `docs/update.md` as prompts addressed "For AI Agents" — they branch on environment detection, `agent-reach doctor` output, and which upstream CLIs already exist, so there is no idempotent one-liner to call. The role therefore shells out to `claude --dangerously-skip-permissions --effort xhigh -p "<instruction> <doc URL>"` and lets the sub-agent execute the doc. Both invocations `chdir` to `$HOME`: `install.md` forbids writing inside the working directory, and `$HOME` also keeps this repo's `CLAUDE.md` out of the sub-agent's context.
- **Idempotency hinges on `agent-reach check-update`'s stdout, not its exit code** — the command discards its own result and always exits 0. Install runs only when `command -v agent-reach` fails; update runs only when `check-update` prints the **positive** sentinel `有更新` (Chinese, hardcoded upstream). Do not invert this to "not up-to-date": `check-update` has two further branches — a GitHub rate-limit/network error (`无法检查更新`) and a no-releases fallback that prints the latest commit SHA (`最新提交:`) — and a negated match would fire on both, burning a full agent run on every converged playbook. The sentinel `有更新` appears in exactly one branch and not in the update instructions that branch prints alongside.
- **The install is verified.** Because an LLM following prose can report success while landing nothing on PATH, a post-install `command -v agent-reach` check fails the play loudly rather than letting every later run silently re-attempt the install.
- Optional channels (Twitter, 小红书, Reddit, …) need cookies or a Chrome extension click and are **not** provisioned — headless `claude -p` cannot answer the doc's "which channels do you want?" prompt, so only the zero-config core channels get set up. Run `agent-reach doctor` interactively to add the rest.

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
