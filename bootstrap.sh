#!/bin/bash
set -euo pipefail

# Configure passwordless sudo so the playbook's sudo subprocesses (Homebrew casks,
# the pkgutil/rm cleanup below, Ansible `become`) run unattended via a /etc/sudoers.d
# drop-in. The first sudo call prompts once on a fresh Mac; every sudo after is passwordless.
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

# Prime the terminal's Automation (AppleEvents) permission. macOS shows a
# one-time consent dialog the first time the terminal sends AppleEvents to
# another app; later runs no longer prompt. Without this, headless steps that
# invoke osascript — e.g. `brew uninstall --cask <gui-app>` running
# `tell application "<App>" to quit` — hang on a dialog nobody is around to
# click. See roles/tailscale/tasks/main.yml for the canonical case.
echo "Priming Automation (AppleEvents) permission for the terminal..."
echo "If a consent dialog appears, click 'OK' to grant access."
osascript -e 'tell application "System Events" to count processes' >/dev/null 2>&1 || true

if command -v ansible >/dev/null 2>&1; then
  echo "Ansible is already installed: $(ansible --version | head -1)"
  exit 0
fi

# 1. Xcode Command Line Tools
if ! xcode-select -p >/dev/null 2>&1; then
  sudo xcodebuild -license
  xcode-select --install
  echo "Waiting for Xcode Command Line Tools installation to complete..."
  until xcode-select -p >/dev/null 2>&1; do
    sleep 5
  done
fi

# 2. Install Homebrew (and ensure it's on PATH)
if ! command -v brew >/dev/null 2>&1; then
  # Homebrew may be installed but not on PATH (common on Apple Silicon)
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  else
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add newly installed Homebrew to PATH
    if [[ -x /opt/homebrew/bin/brew ]]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [[ -x /usr/local/bin/brew ]]; then
      eval "$(/usr/local/bin/brew shellenv)"
    fi
  fi
fi
brew doctor || true
brew update

# 3. Uninstall Python versions installed via official .dmg files from python.org.
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

# 4. Install mise
if ! command -v mise >/dev/null 2>&1; then
  curl -fsSL https://mise.run | sh
  # shellcheck disable=SC2016
  grep -q 'export PATH="$HOME/.local/bin:$PATH"' ~/.zshrc 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
  grep -q 'mise activate zsh' ~/.zshrc 2>/dev/null || echo 'eval "$(mise activate zsh)"' >> ~/.zshrc
fi
# Activate mise in the current shell (needed for steps below)
export PATH="$HOME/.local/bin:$PATH"
eval "$(mise activate bash)"

# 5. Install Python via mise if not already managed by mise
if ! command -v python 2>/dev/null | grep -q mise; then
  mise use --global python@3
fi

# 6. Install Ansible
mise exec -- pip install --quiet ansible
