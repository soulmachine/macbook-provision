#!/bin/bash
set -euo pipefail

if command -v ansible >/dev/null 2>&1; then
  echo "Ansible is already installed: $(ansible --version | head -1)"
  exit 0
fi

# 1. Xcode Command Line Tools
if ! xcode-select -p >/dev/null 2>&1; then
  sudo xcodebuild -license
  xcode-select --install
fi

# 2. Install Homebrew if it doesn't exist
command -v brew >/dev/null 2>&1 || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew doctor
brew update

# 3. Uninstall Python versions installed via official .dmg files from python.org.
if [[ -d /Library/Frameworks/Python.framework ]] \
  || ls -d /Applications/Python\ * >/dev/null 2>&1 \
  || pkgutil --pkgs 2>/dev/null | grep -q '^org\.python\.Python\.'; then
  echo "Cleaning up python.org framework installs..."

  sudo rm -rf /Library/Frameworks/Python.framework
  sudo rm -rf /Applications/Python\ *
  find /usr/local/bin -lname '*Python.framework*' -delete 2>/dev/null

  pkgutil --pkgs 2>/dev/null | grep '^org\.python\.Python\.' | while read -r receipt; do
    sudo pkgutil --forget "$receipt" >/dev/null
  done
fi

# 4. Install mise
if ! command -v mise >/dev/null 2>&1; then
  curl https://mise.run | sh
  grep -q 'mise activate zsh' ~/.zshrc 2>/dev/null || echo 'eval "$(mise activate zsh)"' >> ~/.zshrc
  # Activate mise in the current shell
  eval "$(mise activate bash)"
fi

# 5. Install Python via mise if not already managed by mise
if ! which python3 2>/dev/null | grep -q mise; then
  mise use --global python@3
fi

# 6. Install Ansible
pip3 install ansible
