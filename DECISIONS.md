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

## Q5 — interactive/claude-extras-role — deviation

**Question:** The new `claude-extras` role was asked to run `uv tool install claude-swap`, but the python role already installs claude-swap via `python_cli_tools`. Should the python role keep its entry?
**Options considered:** keep both (each is idempotent, but the tool is provisioned twice) / drop it from `python_cli_tools` so `claude-extras` is the single owner
**Chosen:** Drop `claude-swap` from `roles/python/vars/main.yml`; `claude-extras` is now the only role that installs it.
**Decided-by:** agent
**Justification:** Same single-owner reasoning as Q1. The request to put claude-swap in a Claude-Code-specific role reads as relocating it, not duplicating it — claude-swap is a Claude Code account switcher that merely happens to ship as a Python package, so `python_cli_tools` (generic language-runtime CLIs) was always the weaker home. Leaving both would have two roles converging the same `uv tool` state, and a future version pin or removal would have to be applied in two places. The literal ask (a claude-extras role that installs it) is satisfied either way, so this is a deviation only in what it removes.
**Outcome:** applied
**Ref:** 81955ec

## Q6 — interactive/self-update-idempotency — deviation

**Question:** Three self-update tasks (`claude update`, `codex update`, `npx skills update herdr`) reported `changed` on a converged machine. Each already had a `changed_when` that matched an "up to date" phrase in the tool's output. Harden the phrases, or stop reading output altogether?
**Options considered:** widen each regex to cover the other no-op phrasings / match a positive "did update" sentinel instead of a negated one / drop output matching and diff observable state (version, checksum) measured before and after the call
**Chosen:** Diff state. Record `claude --version` / `brew list --cask --versions codex` / an `ansible.builtin.find` checksum of `~/.agents/skills/herdr` before the updater, run the updater with `changed_when: false`, then re-measure and set `changed_when` on the difference.
**Decided-by:** agent
**Justification:** Phrase matching cannot be made correct here, because all three updaters exit 0 on every path — so a missing phrase is indistinguishable from success — and each has no-op branches that print no phrase at all. Read from the `skills` CLI bundle (`dist/cli.mjs`, the `update` flow): it stays silent about being current when a source is skipped, when there is nothing global to check, and when the check itself throws (`✗ Failed to check skills from …`). That last branch is routine, not exotic — the unauthenticated GitHub API allows 60 calls an hour and was measured at `remaining: 0` during this session, which is what pushed the run onto the git-clone fallback. Verified against on-disk evidence: at the reported run the codex cask (0.148.0, Aug 19 02:02) and the herdr `SKILL.md` (Aug 10) had not moved, so both were phantom changes, while `claude` genuinely installed 2.1.238 — the sentinel was right by luck, not by construction. After the change, two consecutive runs of all three roles report `changed=0`, and a synthetic test confirms the detectors still fire on a content edit, a new file, and a version bump. `agent-reach` is left alone: it has no version to compare, so its **positive**-sentinel match stays the right call.
**Outcome:** applied
**Ref:** 44a79ab

## Q7 — interactive/self-update-idempotency — gate-resolution

**Question:** While fixing the above, found that the herdr skill can never actually update: upstream moved the file to `skills/herdr/SKILL.md`, but `~/.agents/.skill-lock.json` still records `skillPath: "SKILL.md"`, so `skills update` looks at the repo root, finds nothing, and reports the skill "deleted upstream". The role's install task is guarded by `creates:`, so it never re-runs and never repairs the path. Fix it in this pass?
**Options considered:** re-add the skill now so the lock records the new path / point the role at the new path and force a reinstall / leave the state alone and report it
**Chosen:** Leave it. Report the finding and let the user decide.
**Decided-by:** agent
**Justification:** Out of the requested scope, which was idempotency, and repairing it means mutating `~/.agents/skills` — a tree that fans out by symlink to every installed agent runtime, per `~/.agents/AGENTS.md §Skills management`. Took the least-surprising, cheapest-to-reverse option. The idempotency fix is correct either way: the task now honestly reports no change instead of a phantom one. Note the skill content is frozen at its 2026-07-02 version until this is repaired. Both repo paths are live and resolve to the same HEAD (`ogulcancelik/herdr` was renamed to `herdrdev/herdr`), so the source is fine — only the recorded path is stale.
**Outcome:** assumed
**Ref:** 44a79ab

## Q8 — interactive/self-update-idempotency — deviation

**Question:** Q7 left the stale herdr skill path alone as out of scope. The user then asked for it to be fixed. Repair only this machine's lock, or also change the role so it can repair itself?
**Options considered:** re-add the skill by hand and leave the role untouched / re-add and also drop the role's `creates:` guard so `add` runs every time / re-add and add a task that re-runs `add` only when the CLI reports the skill deleted upstream
**Chosen:** Both — repaired the lock on this machine, and added a conditional re-add to the role gated on the `deleted upstream` warning.
**Decided-by:** human
**Justification:** A hand fix alone teaches the repo nothing and lives only in dotfiles; the machine would drift again with no record. Dropping the `creates:` guard would re-clone the repo on every run to converge something that almost never changes. The conditional keeps the cheap path cheap. Matching a phrase here is not the mistake Q6 removed: this is a positive sentinel on exactly one branch, and a miss leaves a stale skill rather than inventing a change — the same reasoning that keeps `agent-reach` on a positive match. Note the role was already correct for a fresh machine (`skills add` finds the new path unaided); the drift was historical, from a June install. Verified in both directions: with the lock re-staled the task fires and reports `changed`, and the lock comes back repaired; converged, it skips and the run is `changed=0`. All 52 agent symlinks still resolve and now serve the newer SKILL.md (10140 → 10553 bytes), and the lock still holds 141 skills, so no duplicate entry was created.
**Outcome:** applied
**Ref:** 44a79ab
**Supersedes:** Q7 — user asked for the fix, so the assumption it recorded no longer holds.
