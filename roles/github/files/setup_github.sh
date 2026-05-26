#!/usr/bin/env bash
set -euo pipefail

PRIVATE_KEY_FILE="$HOME/.ssh/id_ed25519"
CHANGED=false

# ── Preflight checks ─────────────────────────────────────────────────────────

if ! command -v gh &>/dev/null; then
    echo "Error: gh CLI is not installed." >&2
    echo "Install it from: https://github.com/cli/cli#installation" >&2
    exit 1
fi

# ── Require GH_TOKEN ─────────────────────────────────────────────────────────

REQUIRED_SCOPES=(admin:ssh_signing_key admin:public_key user:email read:user)
ALL_SCOPES_CSV="admin:ssh_signing_key,admin:public_key,user:email,read:user"
PAT_URL="https://github.com/settings/tokens/new?scopes=${ALL_SCOPES_CSV}&description=setup_github"

if [[ -z "${GH_TOKEN:-}" ]]; then
    echo "Error: GH_TOKEN is not set." >&2
    echo "" >&2
    echo "Create a Personal Access Token (PAT) with the required scopes:" >&2
    echo "  1. Open: $PAT_URL" >&2
    echo "  2. Set an expiration date, then click 'Generate token'" >&2
    echo "  3. Copy the token and re-run:" >&2
    echo "     export GH_TOKEN=<token> && bash setup_github.sh" >&2
    exit 1
fi

# ── Check scopes ──────────────────────────────────────────────────────────────

CURRENT_SCOPES=$(gh api -i /user 2>/dev/null | grep -i '^x-oauth-scopes:' | cut -d: -f2- || true)
MISSING_SCOPES=()
for s in "${REQUIRED_SCOPES[@]}"; do
    echo "$CURRENT_SCOPES" | grep -qF "$s" || MISSING_SCOPES+=("$s")
done

if [[ ${#MISSING_SCOPES[@]} -gt 0 ]]; then
    echo "Error: GH_TOKEN is missing scopes: ${MISSING_SCOPES[*]}" >&2
    echo "" >&2
    echo "Option A — update your existing token (token value stays the same):" >&2
    echo "  1. Open: https://github.com/settings/tokens" >&2
    echo "  2. Click the token name, check the missing scopes, click 'Update token'" >&2
    echo "  3. Re-run: bash setup_github.sh" >&2
    echo "" >&2
    echo "Option B — create a new token with all scopes pre-filled:" >&2
    echo "  1. Open: $PAT_URL" >&2
    echo "  2. Set an expiration date, click 'Generate token', copy it" >&2
    echo "  3. Re-run: export GH_TOKEN=<new-token> && bash setup_github.sh" >&2
    exit 1
fi

# ── Resolve GitHub identity ───────────────────────────────────────────────────

# Prefer a verified primary email from the API; fall back to git config.
GITHUB_EMAIL=$(gh api /user/emails --paginate -q '.[] | select(.primary and .verified) | .email' 2>/dev/null | head -1 || true)
if [[ -z "$GITHUB_EMAIL" ]]; then
    GITHUB_EMAIL=$(git config --global user.email 2>/dev/null || true)
fi
if [[ -z "$GITHUB_EMAIL" ]]; then
    echo "Error: could not determine a verified GitHub email." >&2
    echo "Set one with: git config --global user.email <your-github-email>" >&2
    exit 1
fi

GITHUB_NAME=$(gh api /user -q '.name // empty' 2>/dev/null || true)
if [[ -z "$GITHUB_NAME" ]]; then
    GITHUB_NAME=$(git config --global user.name 2>/dev/null || true)
fi
if [[ -z "$GITHUB_NAME" ]]; then
    echo "Error: could not determine GitHub display name." >&2
    echo "Set one with: git config --global user.name \"Your Name\"" >&2
    exit 1
fi

echo "Using name:  $GITHUB_NAME"
echo "Using email: $GITHUB_EMAIL"

# ── Generate SSH key if absent ────────────────────────────────────────────────

if [[ ! -f "$HOME/.ssh/id_ed25519.pub" && \
      ! -f "$HOME/.ssh/id_ecdsa.pub"   && \
      ! -f "$HOME/.ssh/id_rsa.pub" ]]; then
    echo ""
    echo "── Generating SSH key ───────────────────────────────────────────────────"
    mkdir -p -m 700 "$HOME/.ssh"
    ssh-keygen -t ed25519 -f "$PRIVATE_KEY_FILE" -N '' -C "$GITHUB_EMAIL"
    echo "Key pair created at $PRIVATE_KEY_FILE"
    CHANGED=true
fi

# ── Select SSH key ───────────────────────────────────────────────────────────

echo ""
echo "── Select SSH key ───────────────────────────────────────────────────────"
KEY_FILES=()
for f in "$HOME/.ssh/id_ed25519.pub" "$HOME/.ssh/id_ecdsa.pub" "$HOME/.ssh/id_rsa.pub"; do
    [[ -f "$f" ]] && KEY_FILES+=("$f")
done

if [[ ${#KEY_FILES[@]} -eq 0 ]]; then
    echo "Error: no SSH public key found." >&2
    exit 1
elif [[ ${#KEY_FILES[@]} -eq 1 ]]; then
    PUBLIC_KEY_FILE="${KEY_FILES[0]}"
    echo "Using key: $PUBLIC_KEY_FILE"
else
    echo "Multiple SSH keys found. Select one to register on GitHub:"
    for i in "${!KEY_FILES[@]}"; do
        echo "  $((i+1))) ${KEY_FILES[$i]}"
    done
    if [[ ! -t 0 ]]; then
        echo "Error: multiple keys found but stdin is not a TTY — cannot prompt." >&2
        echo "Re-run interactively or remove unwanted key files." >&2
        exit 1
    fi
    while true; do
        read -rp "Enter number [1-${#KEY_FILES[@]}]: " choice
        if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#KEY_FILES[@]} )); then
            PUBLIC_KEY_FILE="${KEY_FILES[$((choice-1))]}"
            break
        fi
        echo "Invalid selection, try again."
    done
    echo "Using key: $PUBLIC_KEY_FILE"
fi

PRIVATE_KEY_FILE="${PUBLIC_KEY_FILE%.pub}"

# ── SSH config: pin github.com to selected key ───────────────────────────────

SSH_CONFIG="$HOME/.ssh/config"
echo ""
echo "── SSH config ───────────────────────────────────────────────────────────"
IDENTITY_LINE="IdentityFile ${PRIVATE_KEY_FILE/#$HOME/\~}"
if grep -qF "$IDENTITY_LINE" "$SSH_CONFIG" 2>/dev/null; then
    echo "github.com IdentityFile already configured — skipping."
else
    {
        echo ""
        echo "Host github.com"
        echo "    $IDENTITY_LINE"
    } >> "$SSH_CONFIG"
    chmod 600 "$SSH_CONFIG"
    echo "Added github.com IdentityFile to $SSH_CONFIG"
    CHANGED=true
fi

# ── Add GitHub to known_hosts ─────────────────────────────────────────────────

echo ""
echo "── Known hosts ──────────────────────────────────────────────────────────"
if ssh-keygen -F github.com &>/dev/null; then
    echo "github.com already in known_hosts — skipping."
else
    echo "Adding github.com to known_hosts…"
    ssh-keyscan github.com >> "$HOME/.ssh/known_hosts"
    CHANGED=true
fi

KEY_BODY=$(awk '{print $1, $2}' "$PUBLIC_KEY_FILE")
KEY_TITLE="$(hostname -s) $(date +%Y-%m-%d)"

# ── 1. Signing key ────────────────────────────────────────────────────────────

echo ""
echo "── Signing key ──────────────────────────────────────────────────────────"
EXISTING_SIGNING=$(gh api /user/ssh_signing_keys --paginate -q '.[].key' 2>/dev/null || true)
if echo "$EXISTING_SIGNING" | grep -qF "$KEY_BODY"; then
    echo "Signing key already present on GitHub — skipping."
else
    echo "Adding SSH signing key to GitHub…"
    gh ssh-key add "$PUBLIC_KEY_FILE" --title "$KEY_TITLE (signing)" --type signing
    echo "Signing key added."
    CHANGED=true
fi

echo "Testing SSH signing…"
if echo "test" | ssh-keygen -Y sign -f "$PRIVATE_KEY_FILE" -n git - >/dev/null 2>&1; then
    echo "Signing test passed."
else
    echo "Warning: signing test failed — check that $PRIVATE_KEY_FILE is accessible." >&2
fi

# ── 2. Authentication key ─────────────────────────────────────────────────────

echo ""
echo "── Authentication key ───────────────────────────────────────────────────"
EXISTING_AUTH=$(gh api /user/keys --paginate -q '.[].key' 2>/dev/null || true)
if echo "$EXISTING_AUTH" | grep -qF "$KEY_BODY"; then
    echo "Authentication key already present on GitHub — skipping."
else
    echo "Adding SSH authentication key to GitHub…"
    gh ssh-key add "$PUBLIC_KEY_FILE" --title "$KEY_TITLE (auth)" --type authentication
    echo "Authentication key added."
    CHANGED=true
fi

echo "Testing SSH authentication…"
SSH_TEST=$(ssh -T git@github.com 2>&1 || true)
if echo "$SSH_TEST" | grep -q "successfully authenticated"; then
    echo "$SSH_TEST"
else
    echo "Warning: SSH authentication test failed." >&2
    echo "  $SSH_TEST" >&2
    echo "  If the key was just added, wait a moment and retry: ssh -T git@github.com" >&2
fi

# ── 3. Git config ─────────────────────────────────────────────────────────────

echo ""
echo "── Git config ───────────────────────────────────────────────────────────"
git_config_set() {
    local key=$1 val=$2
    local current
    current=$(git config --global "$key" 2>/dev/null || true)
    if [[ "$current" != "$val" ]]; then
        git config --global "$key" "$val"
        echo "  set $key = $val"
        CHANGED=true
    else
        echo "  ok  $key = $val"
    fi
}
git_config_set user.name        "$GITHUB_NAME"
git_config_set user.email       "$GITHUB_EMAIL"
git_config_set gpg.format       "ssh"
git_config_set user.signingkey  "$PUBLIC_KEY_FILE"
git_config_set commit.gpgsign   "true"
git_config_set tag.gpgsign      "true"

# ── 4. Allowed signers (local verification) ───────────────────────────────────

echo ""
echo "── Allowed signers ──────────────────────────────────────────────────────"
ALLOWED_SIGNERS="$HOME/.ssh/allowed_signers"
ENTRY="$GITHUB_EMAIL $KEY_BODY"
if [[ -f "$ALLOWED_SIGNERS" ]] && grep -qF "$KEY_BODY" "$ALLOWED_SIGNERS"; then
    echo "Entry already in $ALLOWED_SIGNERS — skipping."
else
    echo "$ENTRY" >> "$ALLOWED_SIGNERS"
    echo "Added entry to $ALLOWED_SIGNERS"
    CHANGED=true
fi
git_config_set gpg.ssh.allowedSignersFile "$ALLOWED_SIGNERS"

echo ""
if [[ "$CHANGED" == "true" ]]; then
    echo "CHANGED"
fi
echo "Done. Future commits will be SSH-signed and show 'Verified' on GitHub."
