#!/bin/bash
# Provision a new macOS machine (MacBook, Mac mini, etc).
# Runnable version of macos-provision-omz-plus-cli-stack.md — oh-my-zsh plus the
# modern CLI stack (starship, zoxide, atuin, fzf-tab), uv-managed Python, mise.
#
# Usage: bash macos-provision-omz-plus-cli-stack.sh
# Idempotent: safe to re-run. One sudo password prompt on a fresh machine; the
# rest runs unattended (except the macOS GUI consent dialogs it primes).
set -euo pipefail

log()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33mWARN: %s\033[0m\n' "$*" >&2; }

# ---------------------------------------------------------------- Passwordless sudo
# /etc/sudoers.d drop-in so later sudo subprocesses (Homebrew casks, Ansible
# `become`, cleanup) run unattended. First sudo call prompts once.
log "Passwordless sudo"
SUDOERS_FILE="/etc/sudoers.d/$(whoami)-nopasswd"
if [[ ! -f "$SUDOERS_FILE" ]]; then
  echo "Configuring passwordless sudo for $(whoami) (one-time password prompt)..."
  echo "$(whoami) ALL=(ALL) NOPASSWD: ALL" | sudo tee "$SUDOERS_FILE" > /dev/null
  sudo chmod 0440 "$SUDOERS_FILE"
  if sudo visudo -cf "$SUDOERS_FILE"; then
    echo "DONE: passwordless sudo enabled for $(whoami)"
  else
    sudo rm -f "$SUDOERS_FILE"
    echo "REVERTED: validation failed, file removed" >&2
    exit 1
  fi
fi

# ---------------------------------------------------------- Xcode Command Line Tools
log "Xcode Command Line Tools"
if ! xcode-select -p >/dev/null 2>&1; then
  xcode-select --install 2>/dev/null || true
  echo "Waiting for Command Line Tools (click 'Install' in the dialog)..."
  until xcode-select -p >/dev/null 2>&1; do sleep 15; done
fi
# xcodebuild needs full Xcode; on a CLT-only machine there is no license to accept.
if [[ -d /Applications/Xcode.app ]]; then
  sudo xcodebuild -license accept
fi

# ------------------------------------------------------------------ Terminal Automation
# Prime the terminal's Automation (AppleEvents) permission. macOS shows a
# one-time consent dialog the first time the terminal sends AppleEvents to
# another app; later runs no longer prompt. Without this, headless steps that
# invoke osascript — e.g. `brew uninstall --cask <gui-app>` running
# `tell application "<App>" to quit` — hang on a dialog nobody is around to click.
log "Terminal Automation (AppleEvents) priming"
echo "If a consent dialog appears, click 'OK' to grant access."
osascript -e 'tell application "System Events" to count processes' >/dev/null 2>&1 || true

# ---------------------------------------------- Install Homebrew (and ensure it's on PATH)
log "Homebrew"
if ! command -v brew >/dev/null 2>&1; then
  # Homebrew may be installed but not on PATH (common on Apple Silicon)
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  else
    NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    if [[ -x /opt/homebrew/bin/brew ]]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [[ -x /usr/local/bin/brew ]]; then
      eval "$(/usr/local/bin/brew shellenv)"
    fi
  fi
fi
# Persist for login shells — .zprofile, not .zshenv (path_helper would demote it).
BREW_BIN="$(command -v brew)"
grep -q 'brew shellenv' ~/.zprofile 2>/dev/null || \
  echo "eval \"\$(${BREW_BIN} shellenv)\"" >> ~/.zprofile
brew doctor || true
brew update

# ------------------------------------------------------------------- Install oh-my-zsh
# Before any .zshrc edits: the installer overwrites the file.
log "oh-my-zsh"
if [[ ! -d "$HOME/.oh-my-zsh" ]]; then
  sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended
fi

# -------------------------------------------- Remove python.org Python (.dmg installs)
# Uninstall Python versions installed via official .dmg files from python.org,
# so they can't shadow the uv-managed interpreters below. No-op when absent.
log "Remove python.org framework installs"
if [[ -d /Library/Frameworks/Python.framework ]] \
  || ls -d /Applications/Python\ * >/dev/null 2>&1 \
  || pkgutil --pkgs 2>/dev/null | grep -q '^org\.python\.Python\.'; then
  echo "Cleaning up python.org framework installs..."

  sudo rm -rf /Library/Frameworks/Python.framework
  sudo rm -rf /Applications/Python\ *
  if [[ -d /usr/local/bin ]]; then
    find /usr/local/bin -lname '*Python.framework*' -delete 2>/dev/null || true
  fi

  pkgutil --pkgs 2>/dev/null | grep '^org\.python\.Python\.' | while read -r receipt; do
    sudo pkgutil --forget "$receipt" >/dev/null
  done
fi

# ----------------------------------------------------------------------------- Python
# uv manages the global interpreter and per-project pythons (see macos-global-python-uv.md).
log "Python via uv"
if ! command -v uv >/dev/null 2>&1 && [[ ! -x "$HOME/.local/bin/uv" ]]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
# (the uv omz plugin is enabled by `omz plugin enable` in the CLI-stack
#  section below, together with the rest of the plugin set)
uv python find 3.14 >/dev/null 2>&1 || \
  uv python install 3.14 --default   # prebuilt CPython → ~/.local/bin/python3.14 + python3 + python
uv python pin --global 3.14          # idempotent: rewrites the same user-level pin

# ------------------------------------------------------------------------ Install mise
# mise manages language runtimes (Go, nodejs, jdk, rust) — except python (uv's job).
log "mise"
if ! command -v mise >/dev/null 2>&1 && [[ ! -x "$HOME/.local/bin/mise" ]]; then
  curl -fsSL https://mise.run | sh
fi
# shellcheck disable=SC2016
grep -q 'export PATH="$HOME/.local/bin:$PATH"' ~/.zshrc 2>/dev/null || \
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
grep -q 'mise activate zsh' ~/.zshrc 2>/dev/null || \
  echo 'eval "$(mise activate zsh)"' >> ~/.zshrc
MISE_BIN="$(command -v mise || echo "$HOME/.local/bin/mise")"
eval "$("$MISE_BIN" activate bash)"

# ------------------------- Install Modern CLI Stack (starship, zoxide, atuin, fzf-tab)
log "Modern CLI stack"
brew install starship zoxide atuin fzf   # fzf is fzf-tab's engine

ZSH_CUSTOM="${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}"
[[ -d "$ZSH_CUSTOM/plugins/fzf-tab" ]] || \
  git clone https://github.com/Aloxaf/fzf-tab "$ZSH_CUSTOM/plugins/fzf-tab"
[[ -d "$ZSH_CUSTOM/plugins/zsh-autosuggestions" ]] || \
  git clone https://github.com/zsh-users/zsh-autosuggestions "$ZSH_CUSTOM/plugins/zsh-autosuggestions"
[[ -d "$ZSH_CUSTOM/plugins/zsh-syntax-highlighting" ]] || \
  git clone https://github.com/zsh-users/zsh-syntax-highlighting "$ZSH_CUSTOM/plugins/zsh-syntax-highlighting"

# Hand OMZ's overlapping jobs to the stack. Invariants:
#  - ZSH_THEME="" : starship must be the only prompt owner
#  - zoxide plugin, never the legacy z plugin (the `z` command collides)
#  - plugin order: fzf-tab → autosuggestions → syntax-highlighting (last);
#    OMZ runs compinit before sourcing plugins, so fzf-tab's requirement holds
#  - atuin eval is the last line so nothing rebinds Ctrl-R after it
if grep -q '^ZSH_THEME=' ~/.zshrc; then
  sed -i '' 's/^ZSH_THEME=.*/ZSH_THEME=""/' ~/.zshrc
else
  warn 'no ZSH_THEME= line found in ~/.zshrc; is oh-my-zsh installed?'
fi
# `omz` is a zsh function, so both calls run in an interactive zsh. Plugins
# are appended in argument order, which preserves the ordering invariant on a
# fresh plugins=(git) line; already-enabled plugins are skipped in place, so
# re-runs and plugins added by the Ansible roles (rust, direnv) are left
# alone. When EVERY plugin is already enabled omz exits 1 — that's the
# converged state, not a failure, hence the "already enabled" whitelist.
zsh -ic 'omz plugin disable z' >/dev/null 2>&1 || true   # legacy z collides with zoxide
omz_out=$(zsh -ic 'omz plugin enable git uv zoxide fzf-tab zsh-autosuggestions zsh-syntax-highlighting' 2>&1 </dev/null) \
  || [[ "$omz_out" == *"already enabled"* ]] \
  || warn "omz plugin enable failed: $omz_out"
grep -q 'starship init zsh' ~/.zshrc || echo 'eval "$(starship init zsh)"' >> ~/.zshrc
grep -q 'atuin init zsh'    ~/.zshrc || echo 'eval "$(atuin init zsh)"'    >> ~/.zshrc

# Guard against compinit "insecure directories" complaints from brew-owned dirs.
chmod -R go-w "$(brew --prefix)/share" 2>/dev/null || true

# atuin: import local history once; login/sync are interactive — left to the user.
if command -v atuin >/dev/null 2>&1 && [[ ! -s "$HOME/.local/share/atuin/history.db" ]]; then
  atuin import auto || true
fi

# ---------------------------------------------------------------------- Install Ansible
# Last step: Ansible for the provisioning playbooks.
# ansible-core ships the console scripts; --with ansible adds the
# community-collections bundle.
log "Ansible"
command -v ansible >/dev/null 2>&1 || uv tool install --with ansible ansible-core
ansible --version | head -1

# ------------------------------------------------------------------------------- Done
log "Provisioning complete"
cat <<'EOF'
Next steps (manual):
  1. Open a NEW terminal tab (login+interactive shell) and verify:
       - starship prompt renders, `z <fragment>` jumps after a few cd's,
         Ctrl-R opens atuin, Tab opens the fzf picker
       - time zsh -i -c exit   # expect ~100-300 ms (the oh-my-zsh tax)
  2. Cross-machine history sync:  atuin login && atuin sync
  3. Credentials go in ~/.zshenv (chmod 600); PATH edits in ~/.zprofile.
EOF
