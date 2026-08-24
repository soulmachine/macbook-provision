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

## Q9 — interactive/bun-upgrade-rate-limit — gate-resolution

**Question:** `bun upgrade` fails with `HTTPForbidden` whenever the unauthenticated GitHub API budget (60/hr per IP) is spent. Where should the role get a token to raise that ceiling?
**Options considered:** borrow gh's keyring credential at run time / mint a new PAT and add `GITHUB_TOKEN` to `.env` and `.env.example` / do not authenticate at all and only make the task tolerate the 403
**Chosen:** Borrow gh's stored credential — a task runs `gh auth token` and feeds the result to `bun upgrade` as `GITHUB_TOKEN`.
**Decided-by:** human
**Justification:** Surfaced the three options to the user, who picked this one. It adds no second secret to rotate and stays correct as long as gh is logged in, which the `github` role already requires. Two implementation details the option itself did not settle: bun reads `GITHUB_TOKEN` / `GITHUB_ACCESS_TOKEN` and never `GH_TOKEN` (confirmed against the binary's strings alongside `GITHUB_API_DOMAIN`), so the value must be copied across rather than reused in place; and `GH_TOKEN` outranks the keyring inside gh, so the lookup task sets `environment: {GH_TOKEN: ""}` — without it a stale PAT in `.env` is handed back and the request fails 401 instead of 403, presenting as an unrelated bug. Verified: with the dead `.env` PAT exported, the task still retrieves the 40-char keyring credential.
**Outcome:** applied
**Ref:** 7788e76

## Q10 — interactive/bun-upgrade-rate-limit — deviation

**Question:** The role masked the rate-limit failure with `ignore_errors: true`. Keep that, or change how the expected failure is reported?
**Options considered:** keep `ignore_errors: true` / `failed_when: false` plus a conditional warn task / let the task fail the play now that authentication makes 403 rare
**Chosen:** `failed_when: false` with a `when: rc != 0` debug task carrying the diagnosis.
**Decided-by:** agent
**Justification:** A spent rate limit is an expected outcome, not a failure. `ignore_errors` still prints a full red `fatal:` block and counts the task under `ignored=`, so a converged machine looked broken on every rate-limited run and a genuine bun failure would have been indistinguishable from that noise. Letting it fail outright was rejected because authentication raises the ceiling but does not remove it — gh can be logged out, and the shared per-IP budget can still be exhausted. `changed_when` moved to a `bun --version` diff under the existing rule in `CLAUDE.md §Self-update tasks`, so this needed no separate decision; see Q6. Both branches proven on this machine: authenticated the play is `changed=0` with the warning skipped, and with the API domain pointed at an unreachable host it is still `changed=0 failed=0 ignored=0` with the warning emitted.
**Outcome:** applied
**Ref:** 7788e76

## Q11 — interactive/bun-upgrade-rate-limit — gate-resolution

**Question:** `GH_TOKEN` in `.env` is an expired classic PAT that 401s, and because it outranks the keyring it makes gh's working account inactive machine-wide and sends the `github` role into its `rescue:` branch. Repair it as part of this change?
**Options considered:** remove the dead value from `.env` so gh falls back to the keyring / leave `.env` untouched and report only / mint a replacement PAT with the scopes the `github` role needs
**Chosen:** — (minting a replacement, pending the user)
**Decided-by:** human
**Justification:** Offered the three options; the user asked to be walked through minting a replacement rather than have `.env` edited. Only a human can create the PAT, so the repo stays as-is until they paste the new value in. Unblocking is not required for the bun fix — Q9's `GH_TOKEN: ""` blanking makes the bun role immune to the stale value either way. Note the dead value is a `ghp_` classic PAT while `.env.example` documents the fine-grained `github_pat_` form; it should be revoked whichever way it is replaced.
**Outcome:** escalated
**Ref:** (pending)

## Q12 — interactive/bun-upgrade-rate-limit — deviation

**Question:** The user asked to rename `GH_TOKEN` to `GITHUB_TOKEN` "in .env". Four other places read that name — rename only `.env`, or everywhere?
**Options considered:** `.env` only / `.env` plus every consumer (`.env.example`, `roles/github/tasks/main.yml`, `setup_github.sh`) / keep `GH_TOKEN` and add `GITHUB_TOKEN` as a second copy
**Chosen:** Renamed across every consumer.
**Decided-by:** agent
**Justification:** Renaming `.env` alone would have sent the `github` role down its "not set — skipping" path on the next run, silently disabling SSH key and git-signing setup — plainly not the intent. A second copy was rejected because it doubles the rotation burden on a value that had just gone stale. The rename is safe for the `github` role because gh resolves `GH_TOKEN`, then `GITHUB_TOKEN`, then the keyring, so the script authenticates unchanged; verified by running the role, which now converges (`rescued=0`) where it previously rescued. Also flipped the bun role so an ambient `GITHUB_TOKEN` outranks its `gh auth token` fallback, since the whole point of the new name is that bun reads it directly.
**Outcome:** applied
**Ref:** a935f63

## Q13 — interactive/bun-upgrade-rate-limit — gate-resolution

**Question:** After the rename, the bun role blanked only `GH_TOKEN` before calling `gh auth token`. Is that still enough to reach the keyring?
**Options considered:** leave the blanking as-is / blank `GITHUB_TOKEN` as well / drop the gh fallback entirely and rely on `.env`
**Chosen:** Blank both `GH_TOKEN` and `GITHUB_TOKEN` on the lookup task.
**Decided-by:** agent
**Justification:** Confirmed empirically that gh honours `GITHUB_TOKEN` as a second-priority source, not just its own `GH_TOKEN`: with `GH_TOKEN` cleared and `GITHUB_TOKEN` set to a bogus value, `gh auth status` reports "The token in GITHUB_TOKEN is invalid" and marks it the active account. So after the rename the old blanking would have made `gh auth token` hand back the very `.env` value the fallback exists to replace — reintroducing the Q9 bug under a new variable name. Dropping the fallback was rejected because it is what covers a machine with no `.env`.
**Outcome:** applied
**Ref:** a935f63

## Q14 — interactive/bun-upgrade-rate-limit — gate-resolution

**Question:** Q11 left the dead PAT unresolved pending a human. The user then minted a replacement and supplied it. Is it fit for purpose?
**Options considered:** write it in unverified / verify status and scopes before relying on it
**Chosen:** Wrote it to `.env` (mode 600 preserved) and verified before continuing.
**Decided-by:** human
**Justification:** `GET /user` returns HTTP 200 with `x-oauth-scopes: admin:public_key, admin:ssh_signing_key, read:user, user:email` — all four scopes `setup_github.sh` requires — and `x-ratelimit-limit: 5000`, which is the ceiling the bun fix was after. `gh auth status` now shows the account active and healthy rather than shadowed by a dead value. Confirmed read-only beforehand that both the signing and authentication keys were already on GitHub, so running the `github` role performed no writes to the account. The token was pasted into the session transcript, so it should be treated as exposed and rotated at the user's convenience.
**Outcome:** applied
**Ref:** a935f63
**Supersedes:** Q11 — the human minted the PAT, so the escalation is resolved.

## Q15 — interactive/nodejs-lts-drift — gate-resolution

**Question:** `mise use --global node@lts` left the machine on a stale LTS (24.14.1) that openclaw refuses to run, breaking the gateway LaunchAgent. How should the role force the newest LTS?
**Options considered:** pin an exact version in `config.toml` and bump it by hand / add `mise upgrade node` alongside the existing `mise use` / leave the role alone and repair drifted machines by hand
**Chosen:** Add `mise upgrade node` as its own task after `mise use --global node@lts`.
**Decided-by:** agent
**Justification:** `mise use --global node@lts` only guarantees *an* LTS is installed — the request "lts" is satisfied by any already-installed LTS release, so a box that already has one never pulls a newer one. That is exactly how this machine ended up running openclaw off 24.14.1: `mise ls node` shows three builds (24.13.1, 24.14.1, 24.19.0), and openclaw's `engines.node` is `>=22.22.3 <23 || >=24.15.0 <25 || >=25.9.0` — 24.14.1 falls in the gap between the first and second clauses and satisfies none of them, so every openclaw call failed while the role reported converged. `mise upgrade` was chosen over an exact pin because it moves to the newest release *inside the configured range*, which lets `config.toml` keep the readable `node = "lts"` rather than an exact version that then needs its own hand-maintained bump — the pin would trade a silent drift bug for a silent staleness bug. Repairing machines by hand was rejected as the failure recurs on every host. Verified live: the role moved a stale 24.13.1 to 24.19.0 and reported `changed`, and a converged re-run reports `ok=4 changed=0`.
**Outcome:** applied
**Ref:** 5f23643

## Q16 — interactive/nodejs-lts-drift — deviation

**Question:** Codex flagged (P2) that `mise use --global` can rewrite `config.toml` while the role's `changed_when` — a resolved-version diff over `mise current node` — reports no change. Widen the diff to also cover the config value, or replace the probe?
**Options considered:** keep `mise current node` and add a second probe over `mise config get tools.node` / replace the probe with `mise ls --current node --json`, which carries both dimensions in one payload / accept the gap as cosmetic
**Chosen:** Replace the probe with `mise ls --current node --json` for both the before and the after read.
**Decided-by:** agent
**Justification:** The finding is real and not cosmetic: these tasks move two independent pieces of state, and `mise current` sees only one. On a machine whose `config.toml` carries a hand-pinned `node = "24.19.0"`, `mise use` rewrites that line to `node = "lts"` while the resolved version stays 24.19.0 — a real edit to a file the role manages, reported as unchanged. The JSON form settles it in one comparison because it emits `requested_version` (what `config.toml` asks for) beside `version` (what that resolves to); confirmed live, the payload reads `"version": "24.19.0", "requested_version": "lts"`. The two-probe option was rejected on a measured difference in the unconfigured case, which is the fresh-machine path: `mise ls --current node --json` prints `[]` and exits 0, whereas `mise config get tools.node` exits 1 with `Key not found: tools.node`, so it would need its own `failed_when` and a null-vs-missing distinction to avoid a spurious first-run change. Same shape as Q6 — diff observable state, and pick the probe that already covers every dimension rather than bolting on a second one. Verified against all three scenarios: converged reports `changed=0`, Codex's pinned-version case now reports `changed=1` with an immediately idempotent re-run, and a stale-pin case (`node = "24.13.1"`) reports `changed=1` with both config and resolved runtime advancing. `ansible-lint roles/nodejs/` passes clean at the production profile.
**Outcome:** applied
**Ref:** 5f23643

## Q17 — interactive/updater-version-diff — gate-resolution

**Question:** Converting the `pi` role from a negated sentinel to a version diff, the drift test (downgrade to 0.84.1, re-run the role) failed with `Error: spawn bun ENOENT` — `pi update` shells out to `bun` to perform the install, and `bun` is not on Ansible's PATH. Is that a regression from the conversion, and how should it be fixed?
**Options considered:** revert the conversion as the cause / treat it as pre-existing and give the update task the same `environment: PATH` its own install task already carries / leave PATH alone and add `failed_when: false` so a missing `bun` cannot abort the play
**Chosen:** Pre-existing bug, not a regression. Added `environment: PATH` with `~/.bun/bin` prepended to the update task, matching pi's install task and the `omp` role.
**Decided-by:** agent
**Justification:** The conversion did not introduce this and reverting would not have fixed it: the pre-conversion task carried no `environment:` either, and `changed_when` does not suppress a non-zero rc, so the old role would have failed identically on the same input. What the conversion changed was only that the failure became reachable. It had stayed invisible because `pi update` spawns `bun` **only when it has an update to apply** — a current pi prints its "already up to date" line and exits 0 without spawning anything — so every converged run took the early-exit path, including two full playbook runs the same day that both reported `failed=0`. `failed_when: false` was rejected as actively harmful here: it would convert a real breakage (pi silently never updating) into a permanent no-op, and the version diff would then honestly report `changed=0` forever while pi rotted — the exact phantom-signal problem the conversion exists to remove, inverted. Verified: with the PATH set, the drifted 0.84.1 host updates to 0.84.3 and reports `changed=1`, and the immediate re-run reports `changed=0`. The transferable lesson is about verification method, not about pi: re-running a role to see `changed=0` exercises only the no-op branch, and every one of these updaters has a second branch that a converged machine never reaches. Drift the state and make the updater actually work before believing it does.
**Outcome:** applied
**Ref:** c163a46
