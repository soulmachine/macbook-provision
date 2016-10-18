#!/bin/bash
# Xcode Command Line Tools
if ! xcode-select -p; then
  sudo xcodebuild -license
  xcode-select --install
fi

# Homebrew
command -v brew >/dev/null 2>&1 || /usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
brew doctor
brew update

# Remove python installed from pkg
sudo rm -rf /Library/Frameworks/Python.framework/
sudo rm -rf "/Applications/Python 2.7"
cd /usr/local/bin/
ls -l /usr/local/bin | grep '../Library/Frameworks/Python.framework/Versions/2.7' | awk '{print $9}' | tr -d @ | xargs rm

# Install python2
brew install python
pip install --upgrade pip setuptools wheel
brew linkapps python

# Install Python3
brew install python3
pip3 install --upgrade pip setuptools wheel
brew linkapps python3

# Add PATH
echo "export PATH=\"/usr/local/bin:/usr/local/sbin:\$PATH\"" >> ~/.zshrc

pip install ansible
# Ansible doesn't support Python 3 yet
#pip3 install ansible

