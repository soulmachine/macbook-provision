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
