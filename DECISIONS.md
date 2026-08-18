<!-- AI-maintained, append-only -->

## Q1 — interactive/omz-role-move — deviation

**Question:** When moving "enable uv plugin" from bootstrap.sh into the oh-my-zsh role, should the uv role keep its own `omz plugin enable uv` task?
**Options considered:** keep both (idempotent but duplicated) / delete the uv role's task and its oh-my-zsh meta dependency (single owner)
**Chosen:** Delete the uv role's enable task and `roles/uv/meta/main.yml`; the oh-my-zsh role's `omz plugin enable git uv zoxide …` call is now the single owner of the plugin set.
**Decided-by:** agent
**Justification:** The request ("move enable uv plugin … to the oh-my-zsh role") reads as consolidating ownership; keeping the duplicate would leave two roles converging the same .zshrc line. Least-surprising single-owner layout.
**Outcome:** assumed
**Ref:** (pending)

## Q2 — interactive/omz-role-move — gate-resolution

**Question:** Does the oh-my-zsh role need to re-ensure the `mise activate zsh` line in .zshrc, even though bootstrap.sh (which owns mise) already appends it?
**Options considered:** leave it to bootstrap only / add a lineinfile in the role (exact line) / add a lineinfile in the role with a regexp matching any spelling
**Chosen:** Regexp-based lineinfile in the role, placed after the omz install task.
**Decided-by:** agent
**Justification:** With the omz installer now running from the playbook (after bootstrap), a fresh machine's installer replaces ~/.zshrc and drops bootstrap's appends, so the role must restore the line — same reason the role already re-ensures the ~/.local/bin PATH line. The regexp form is required: live-machine testing showed hand-maintained full-path mise lines, and an exact-line lineinfile appended a duplicate after the atuin line, breaking the atuin-last invariant.
**Outcome:** assumed
**Ref:** (pending)

## Q3 — interactive/omz-role-move — gate-resolution

**Question:** Is zsh-autosuggestions redundant now that the modern CLI stack (atuin, fzf-tab, zoxide, starship) is in place?
**Options considered:** drop it (one less widget-wrapping plugin) / keep it (only inline ghost-text provider)
**Chosen:** Keep it. Nothing else in the stack draws as-you-type ghost text, and `atuin init zsh` registers `_zsh_autosuggest_strategy_atuin`, so atuin's history database powers the suggestions — the plugins are integrated, not overlapping.
**Decided-by:** human
**Justification:** User confirmed keeping it after reviewing the analysis (verified live: atuin's init injects its autosuggest strategy; no manual ZSH_AUTOSUGGEST_STRATEGY in ~/.zshrc).
**Outcome:** applied
**Ref:** a54c4c5

## Q4 — interactive/playwright-lock-failure — deviation

**Question:** The playwright role failed with "An active lockfile is found at … __dirlock", and Playwright's own error text tells you to `rm -rf` that lock. Should the role delete a contended lock, or avoid taking it?
**Options considered:** remove `__dirlock` before installing (as the error suggests) / remove it only when it looks stale (mtime age, no live `playwright install` process) / never remove it, and instead skip the install entirely when the browsers are already present
**Chosen:** Never remove the lock. Gate the install on an `INSTALLATION_COMPLETE` check driven by `playwright install chromium --dry-run`, which takes no lock, and retry (2 attempts) only when an install is genuinely needed.
**Decided-by:** agent
**Justification:** Reading playwright-core's bundled registry (`coreBundle.js`) settles it two ways. First, `install()` takes the lock at its top, *before* the per-browser "already installed" check — so a converged machine contends for the lock with nothing to do, which is exactly how this failure happened (all three components, chromium-1234/headless-shell-1234/ffmpeg-1011, were already marked COMPLETE). Second, the lock is a proper-lockfile with the default `stale: 10s` and a 5s refresh, so Playwright *already* reclaims a crashed installer's lock unaided; a lock still standing after that has a live holder, and deleting it would let two installs unpack into the same directory at once. Both the "always delete" and "delete when stale" options are therefore either unsafe or dead code. Verified live: with a wedged third-party installer holding the lock, the role went from a 7m49s failure to a 1.9s skip.
**Outcome:** applied
**Ref:** 7b3380d
