# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ansible-based macOS development environment provisioner. Uses Homebrew (via Ansible's `community.general.homebrew` and `community.general.homebrew_cask` modules) to install and configure software.

## Commands

```bash
# First-time setup (installs Xcode CLI Tools, Homebrew, mise, Python, Ansible)
./bootstrap.sh

# Run full provisioning on THIS machine.
# --limit 127.0.0.1 is mandatory; see "Runs per-host only" below.
ansible-playbook main.yml --limit 127.0.0.1

# Dry run
ansible-playbook main.yml --limit 127.0.0.1 --check

# Provision another fleet host — over ssh, in a LOGIN shell so brew is on PATH
ssh -o BatchMode=yes -o ConnectTimeout=15 <host> \
  'zsh -lc "cd ~/github.com/soulmachine/macbook-provision && git pull && ansible-playbook main.yml --limit 127.0.0.1"'
```

## Architecture

- **main.yml** — Main playbook that runs roles in order. Add new roles here.
- **playbook.yml** — Legacy playbook (not actively used). Defines packages inline with Japanese comments.
- **bootstrap.sh** — Bootstrap script. Prepares a fresh Mac for Ansible. Also configures **passwordless sudo** so the playbook's sudo subprocesses (Homebrew casks, `pkgutil`/`rm` cleanup, Ansible `become`) run unattended: it installs a `/etc/sudoers.d/<user>-nopasswd` drop-in (`<user> ALL=(ALL) NOPASSWD: ALL`, mode 0440), validated with `visudo -cf` and rolled back if validation fails. The first `sudo` call prompts once on a fresh Mac (to write the drop-in); every `sudo` after — both in the rest of bootstrap and in the playbook — is passwordless, so no `SUDO_ASKPASS` helper or `sudo -A -v` priming is needed anywhere (and `ansible.cfg` uses plain `become_flags = -H`). The script is idempotent — it skips the sudoers setup if the drop-in already exists (`[[ -f ... ]]`, no sudo required to check). It also runs a no-op `osascript` against System Events to trigger the macOS Automation (AppleEvents) consent dialog for the host terminal (e.g. Ghostty) on first run; later runs no longer prompt. This pre-authorizes the terminal so headless osascript calls (e.g. `brew uninstall --cask`'s `tell app to quit`) don't hang on a dialog nobody is around to click.
- **`.env` / `.envrc`** — Optional, gitignored, and **per-machine**. `.envrc` runs `dotenv_if_exists .env` so direnv loads `.env` into the shell. The `tailscale` role reads `TAILSCALE_AUTH_KEY` (to auto-run `tailscale up`) and optionally `TAILSCALE_API_ACCESS_TOKEN` (to disable node-key expiry); the `github` and `bun` roles read `GITHUB_TOKEN`, plus an optional `GITHUB_SSH_KEY` (unset across the fleet; see `.env.example`). Values legitimately differ across the fleet — a Tailscale auth key is tailnet-scoped, so hosts on different tailnets must carry different ones, and a host may deliberately carry no `GITHUB_TOKEN` at all. That divergence is correct, not drift to reconcile. New roles that need secrets should follow the same pattern — gate the task on `lookup('env', 'VAR') | length > 0` and document the var in `.env.example`.
- **inventory** — Lists all five fleet hosts, but the playbook must only ever target the local one. See "Runs per-host only, never from a control node" below.
- **roles/** — Each role provisions one tool or application.

#### Runs per-host only, never from a control node

`main.yml` targets `hosts: all` and `inventory` lists all five fleet machines, so **every
invocation needs `--limit 127.0.0.1`** — each host provisions itself. The extra inventory
entries are there for ad-hoc fan-out (`ansible all -m ping`) and as fleet documentation,
NOT for the playbook to drive.

The roles read `lookup('env', 'HOME')` in 79 places across 25 roles, with zero uses of
`ansible_env.HOME`, and pull the `.env` secrets the same way. Ansible evaluates every
`lookup()` on the **control node**, not the target. Drop the limit and one machine's
`$HOME` and `.env` reach all of them: provisioning `mac-studio-m3` (home
`/Users/developer`) would write into `/Users/frankdai/…` on that box, and every host
would receive the control node's tailnet-scoped Tailscale auth key. This was tried on
2026-08-23, failed on all five hosts, and was reverted on 2026-08-24.

Making the playbook control-node-safe is a project, not a flag: convert all 79 lookups to
`ansible_env.HOME`, move the `.env` secrets into `host_vars` under `ansible-vault`, and
re-test every role against a remote target.

#### Remote runs need a login shell

Driving another host over ssh must go through `zsh -lc "..."`. Homebrew is put on PATH by
`~/.zprofile`'s `brew shellenv`, which only a **login** shell sources; a plain
`ssh host 'cmd'` gets a non-interactive shell that reads just `~/.zshenv`, where `brew`
is absent — on every fleet Mac, including the one you are typing on. Without the login
shell the homebrew role dies at its third task with `brew: command not found`. It also
resolves the Intel/Apple-Silicon split (`/usr/local/bin/brew` on mac-mini-2018,
`/opt/homebrew/bin/brew` elsewhere), since each host's own shellenv decides.

`~/.local/bin` is a separate question and needs no login shell — it is on the
non-interactive PATH via each host's `~/.zshenv`, so bare `ansible-playbook` resolves
over plain ssh. Only Homebrew needs this.

#### Tailscale role specifics

**Scope of usage:** This role uses Tailscale **only as a network-connectivity layer** (private mesh + MagicDNS). It intentionally does NOT enable Tailscale SSH. Remote shell access is handled separately by standard OpenSSH; Tailscale just provides the routable mesh address. This is why there is no `--ssh` flag, no `tag:server`/`tag:laptop` advertisement, no ACL `tagOwners` management, no Full Disk Access prompt for `/Applications/Tailscale.app`, and no laptop-vs-server branching — every facility tied to Tailscale SSH or tags is deliberately absent. If you ever turn Tailscale SSH back on, you'll need to reintroduce: the FDA grant (so SSH child shells inherit working TCC), and — if you want per-machine ACL gating — `--advertise-tags` plus the API-driven `tagOwners` update.

- Installs the standalone **Tailscale.app** via the `tailscale-app` cask (the official build from tailscale.com, NOT the App Store sandboxed version). The cask is a `.pkg`-based install, so brew calls `sudo` internally without `-A`; passwordless sudo (configured by bootstrap.sh) lets that run unattended — no timestamp priming needed. The cask ships the GUI app and the embedded `tailscaled`, but **not** the CLI — its `.pkg` installs only the app bundle (`pkgutil --files com.tailscale.ipn.macsys`), the bundle contains no CLI binary, and nothing creates `/usr/local/bin/tailscale` automatically. Per <https://tailscale.com/kb/1080/cli> the standalone build installs that launcher only when the user clicks Settings → CLI integration → "Show me how" → Install Now and authenticates. Symlinking the app binary there is not a substitute (it stays in GUI mode and exits `Tailscale.CLIError error 3`), and on Apple Silicon `/usr/local/bin` may not exist at all since Homebrew lives in `/opt/homebrew`. MagicDNS auto-configures through the Network Extension — no `/etc/resolver/ts.net` file is needed.
- **Two GUI-only steps are gated, and they FAIL the play rather than prompt.** `ansible.builtin.pause` degrades badly on a non-interactive stdin — Ansible only warns ("Not waiting for response to prompt") and continues, so the play used to barrel past the gate and die several tasks later on something unrelated-looking (`tailscale up` reporting `No such file or directory: b'tailscale'`). Both gates now fail at the point of detection with the actual remedy, which behaves identically interactively and headless. Re-run the playbook after doing the step.
  - **Network Extension.** The role captures `systemextensionsctl list | grep -i tailscale` (not `grep -q`, so the failure message can quote the observed state) and gates on whether `[activated enabled]` appears in it. If not — extension disabled, in `activated waiting for user` state, or no row at all because Tailscale.app has never been launched — the role does `open -a Tailscale` (which is what registers the extension and makes the toggle appear at all) and then fails, pointing at System Settings → General → Login Items & Extensions → Network Extensions → toggle Tailscale ON. No marker file — the `systemextensionsctl` query is the source of truth. The user may also see the "Tailscale would like to add VPN configurations" dialog on first launch; clicking Allow there is part of the same flow.
  - **CLI launcher.** Gated on `stat /usr/local/bin/tailscale`, and deliberately placed *inside* the `TAILSCALE_AUTH_KEY` block — only `tailscale up` and the key-expiry tasks need the CLI, so with no auth key the role still converges on the cask install alone.
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

#### Self-update tasks: diff state, don't grep output

Roles that shell out to a tool's own updater (`claude update`, `codex update`,
`npx skills update`) must decide `changed` from **observable state measured
before and after the call**, not from a phrase in the tool's stdout. Record the
version or checksum, run the updater with `changed_when: false`, then re-measure
and set `changed_when` on the difference.

Output-matching looks equivalent and isn't. These updaters exit 0 on every path,
so a missing sentinel is indistinguishable from success, and each has no-op
branches that never print the phrase — `skills update` alone stays silent about
being current when a source is skipped, when there is nothing to check, and when
the check itself fails, the last of which is routine because the unauthenticated
GitHub API allows only 60 calls an hour. Every one of those reports a phantom
change on a converged machine. `agent-reach` (below) is the deliberate exception:
it has no version to compare, so it matches a **positive** sentinel — never a
negated one, for exactly the reason above.

#### Borrowing gh's token for GitHub-API rate limits

That 60-calls-an-hour ceiling is per **IP**, shared across every tool on the box,
so it is regularly spent by the time a play runs. `bun upgrade` is the role that
feels it hardest: it resolves the newest release from
`api.github.com/repos/Jarred-Sumner/bun-releases-for-updater/releases/latest` and,
on a 403, exits **non-zero** with `Bun upgrade failed with error: HTTPForbidden`
even though the installed bun is current. An authenticated call gets 5000/hr
instead, so the bun role makes sure one is available.

bun reads `GITHUB_TOKEN` / `GITHUB_ACCESS_TOKEN`, which is why `.env` names the
PAT `GITHUB_TOKEN` — set there, it reaches bun through direnv with no plumbing at
all. The role's `gh auth token` lookup is the **fallback**, for a machine whose
`.env` carries no token; an ambient `GITHUB_TOKEN` wins over it.

Two details that are easy to get wrong:

- **Blank both `GH_TOKEN` and `GITHUB_TOKEN` when shelling out to
  `gh auth token`.** gh resolves in the order `GH_TOKEN`, `GITHUB_TOKEN`,
  keyring — it honours *both* env vars, not just its own — so leaving either set
  makes the command echo back the very value the fallback exists to replace. With
  a stale PAT the request then fails 401 instead of 403, which reads as an
  unrelated bug. `environment: {GH_TOKEN: "", GITHUB_TOKEN: ""}` on the lookup
  task forces the keyring credential.
- **Use `failed_when: false`, not `ignore_errors: true`.** A spent rate limit is
  an expected outcome. `ignore_errors` still prints a full red `fatal:` block and
  counts the task under `ignored=`, which trains you to skim past red and makes a
  genuine failure indistinguishable from routine noise. `failed_when: false` plus
  a `when: rc != 0` debug task says the same thing without crying wolf.

### Adding a New Role

1. Create `roles/<name>/tasks/main.yml`
2. Add the role name to the `roles:` list in `main.yml`
3. If it depends on another role, add `meta/main.yml` with `dependencies:`
