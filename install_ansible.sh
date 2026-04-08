#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

install_galaxy_deps() {
  if [[ -f requirements.yml ]]; then
    echo "Installing Ansible Galaxy dependencies..."
    ansible-galaxy install -r requirements.yml
  fi
}

if command -v ansible >/dev/null 2>&1; then
  echo "Ansible is already installed: $(ansible --version | head -1)"
  install_galaxy_deps
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
  grep -q 'mise activate zsh' ~/.zshrc 2>/dev/null || echo 'eval "$(mise activate zsh)"' >> ~/.zshrc
fi
# Activate mise in the current shell (needed for steps below)
eval "$(mise activate bash)"

# 5. Install Python via mise if not already managed by mise
if ! command -v python3 2>/dev/null | grep -q mise; then
  mise use --global python@3
fi

# 6. Install Ansible
pip3 install --quiet ansible

# 7. Install Ansible Galaxy dependencies
install_galaxy_deps
