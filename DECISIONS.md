<!-- AI-maintained, append-only -->

## Q1 — interactive/omz-role-move — deviation

**Question:** When moving "enable uv plugin" from bootstrap.sh into the oh-my-zsh role, should the uv role keep its own `omz plugin enable uv` task?
**Options considered:** keep both (idempotent but duplicated) / delete the uv role's task and its oh-my-zsh meta dependency (single owner)
**Chosen:** Delete the uv role's enable task and `roles/uv/meta/main.yml`; the oh-my-zsh role's `omz plugin enable git uv zoxide …` call is now the single owner of the plugin set.
**Decided-by:** agent
**Justification:** The request ("move enable uv plugin … to the oh-my-zsh role") reads as consolidating ownership; keeping the duplicate would leave two roles converging the same .zshrc line. Least-surprising single-owner layout.
**Outcome:** assumed
**Ref:** 8d08037

## Q2 — interactive/omz-role-move — gate-resolution

**Question:** Does the oh-my-zsh role need to re-ensure the `mise activate zsh` line in .zshrc, even though bootstrap.sh (which owns mise) already appends it?
**Options considered:** leave it to bootstrap only / add a lineinfile in the role (exact line) / add a lineinfile in the role with a regexp matching any spelling
**Chosen:** Regexp-based lineinfile in the role, placed after the omz install task.
**Decided-by:** agent
**Justification:** With the omz installer now running from the playbook (after bootstrap), a fresh machine's installer replaces ~/.zshrc and drops bootstrap's appends, so the role must restore the line — same reason the role already re-ensures the ~/.local/bin PATH line. The regexp form is required: live-machine testing showed hand-maintained full-path mise lines, and an exact-line lineinfile appended a duplicate after the atuin line, breaking the atuin-last invariant.
**Outcome:** assumed
**Ref:** 8d08037

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
**Ref:** 8d08037

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

## Q18 — interactive/updater-version-diff — deviation

**Question:** The `uv` role was asked only to swap its negated sentinel for a version diff. Its update task also carried `ignore_errors: true`, which CLAUDE.md rules against. Change that too, or leave it as out of scope?
**Options considered:** leave `ignore_errors: true` alone as outside the literal ask / replace it with `failed_when: false` plus an `rc != 0` warn task, matching the `bun` role / drop error tolerance entirely and let a rate-limited check fail the play
**Chosen:** Replaced with `failed_when: false` and a warn task gated on `uv_self_update.rc != 0`, mirroring the `bun` role's shape.
**Decided-by:** agent
**Justification:** The restructure forced the question rather than merely inviting it: the version-diff shape moves `changed_when` off the update task entirely, so that task's error handling had to be re-stated either way, and re-stating a documented anti-pattern verbatim in a task being rewritten line-by-line is not a neutral act. uv's case is precisely the one CLAUDE.md describes — the check hits the GitHub releases API unauthenticated, and uv's own `--help` offers `--token` / `UV_GITHUB_TOKEN` to "reduce the chance of encountering rate limits" — so a spent limit is an expected outcome, and `ignore_errors` would print a red `fatal:` block and count it under `ignored=` on every such run, which is what trains a reader to skim past red and makes a genuine failure indistinguishable from routine noise. Dropping tolerance altogether was rejected because it would abort the play at role five over a transient 403. Verified the failure branch directly rather than assuming it, per Q17's lesson: with the command forced to `uv self update 99.99.99`, the updater exits 2, the play continues with `failed=0` and nothing under `ignored=`, the warn task fires quoting the rc, and the version diff correctly reports no change. Flagged to the user as a scope extension at the time it was made.
**Outcome:** applied
**Ref:** c163a46

## Q19 — interactive/updater-version-diff — deviation

**Question:** A converged full-playbook run surfaced one negated sentinel, in the `omp` role. Fix that instance, or sweep the repo for the whole class?
**Options considered:** convert `omp` alone, as the instance actually observed / grep the repo and convert every self-updater carrying the same defect / leave all of them, since Q6 had already declared the rule and these roles simply predate it
**Chosen:** Swept. Converted `omp`, `pi`, and `uv` to before/after version diffs; deliberately left six other negated matchers alone.
**Decided-by:** human
**Justification:** The user asked for the sweep after the `omp` fix was in. It was the right call: Q6 established the rule against three roles that happened to be the ones failing that day, and Q16 caught a fourth, so treating each new sighting as a one-off had already been shown to leave siblings behind — `pi` and `uv` were found by a single grep in seconds. The criterion for inclusion is narrower than "negated sentinel", though, and worth stating because a blind sweep would have churned five healthy roles: the defect requires a command that **exits 0 on every path**, which is what makes a missing phrase indistinguishable from success. That is true of `omp update`, `pi update`, and `uv self update` — all of which perform a network check that can fail silently — and not of `brew trust --tap` (multica-cli, moshi, cc-switch) or `omz plugin enable` (rust, direnv), which are local, deterministic, two-branch operations whose own role comments already explain the reasoning. Those five were left deliberately. **One case is genuinely unresolved rather than excluded:** `roles/claude-code/tasks/main.yml:80` matches `'already' not in claude_code_mp.stdout` on `claude plugin marketplace add`, which does reach the network — it fits the criterion and was not audited. The sweep also paid for itself beyond the phantom changes: converting `pi` exposed a latent `spawn bun ENOENT` failure that no converged run could reach (Q17).
**Outcome:** applied
**Ref:** f5bf16d, c163a46

## Q20 — interactive/updater-version-diff — gate-resolution

**Question:** Q19 left one case unresolved: `roles/claude-code/tasks/main.yml:80` matches `'already' not in claude_code_mp.stdout` on `claude plugin marketplace add`, a network operation. Is it an instance of the negated-sentinel defect?
**Options considered:** convert it to a state diff like `omp`/`pi`/`uv` / add `failed_when: false` and a positive gate / audit its exit codes first and only act if it actually fits the criterion
**Chosen:** Audited first, and left it as-is — it is not an instance of the defect.
**Decided-by:** agent
**Justification:** The criterion from Q19 is that the command **exits 0 on every path**, which is what makes a missing phrase indistinguishable from success. `claude plugin marketplace add` does not: measured directly, an already-added marketplace prints "✔ Marketplace 'claude-plugins-official' already on disk — declared in user settings" and exits **0**, while a failed fetch prints "✘ Failed to add marketplace: Failed to clone marketplace repository…" and exits **1**. The task carries no `failed_when: false`, so the failure branch aborts the play loudly rather than passing through the sentinel at all. That leaves the negated match responsible only for separating the two *success* branches — already-present versus newly-added — which it does correctly. The defect in `omp`/`pi`/`uv` was never "a negated match" per se; it was a negated match forced to carry a failure branch it could not see. Here the non-zero exit carries it. Verified the probe was non-destructive: the failed add left no marketplace entry and no clone directory under `~/.claude/plugins/marketplaces/`, and the configured count was unchanged at 10.
**Outcome:** applied
**Ref:** (none — audit only, no code change)
**Supersedes:** Q19 — resolves the case it flagged as unaudited.

## Q21 — interactive/always-on-only-roles — gate-resolution

**Question:** `openclaw` and `hermes` should install only on the Mac minis and the Mac Studio, not the MacBooks, because a MacBook is not run 24x7. What signal decides that at play time?
**Options considered:** a `Mac mini`/`Mac Studio` model-name allowlist from `system_profiler`'s `machine_name` / a `MacBook*` denylist over the same field / internal-battery presence (`InternalBattery` in `pmset -g batt`) / a hostname allowlist
**Chosen:** Battery presence. `main.yml` `pre_tasks` set `mac_is_portable` from whether `InternalBattery` appears in `pmset -g batt`, alongside `mac_family` from `system_profiler -json SPHardwareDataType` for skip messages only.
**Decided-by:** human
**Justification:** The agent had implemented a `MacBook` model-name denylist; the user redirected to the battery and supplied the `pre_tasks` wiring. It is the better signal for the reason given: it answers the stated question directly — can this machine be left running — rather than proxying it through a name, reads identically on Intel, Apple Silicon and VMs, and needs no maintenance, since a MacBook bought next year classifies as portable with no list to edit and a headless VM lands in "always-on" for free. An allowlist inverts the failure mode into a silent skip of any desktop nobody remembered to add. `sysctl -n hw.model` was rejected outright as unusable: every Apple Silicon Mac reports the family-less `MacN,M` form, verified live — the Mac mini M2 is `Mac14,3` and the MacBook Air M4 `Mac16,12`, while only the Intel box still spells it out (`Macmini8,1`). Both probes were verified against three real fleet hosts rather than assumed: `machine_name` reads "Mac mini"/"MacBook Air", and the `InternalBattery` line is present on franks-macbook-air and absent on both franks-mac-mini-m2 (Apple Silicon) and franks-mac-mini-2018 (Intel). A hostname allowlist was never seriously in play — it encodes nothing about the hardware and breaks on a rename.
**Outcome:** applied
**Ref:** c45c12f

## Q22 — interactive/always-on-only-roles — tradeoff

**Question:** Where does the gate live — a `when:` on each role in `main.yml`'s `roles:` list, or inside the roles themselves?
**Options considered:** `when:` on the two entries in the `roles:` list / wrap each role's tasks in a `block:` / split each role into `tasks/main.yml` (gate) + `tasks/install.yml` (work) joined by `include_tasks`
**Chosen:** Split each role into a gate `main.yml` and an `install.yml`, joined by `include_tasks`.
**Decided-by:** agent
**Justification:** A role-level `when:` in `main.yml` fails two ways. It is inherited by the role's dependencies, so gating `openclaw` would also take `nodejs` with it — and `nodejs` is wanted on laptops. It only survives here by accident, because `nodejs` happens to be listed earlier as a top-level role and de-duplicates; that is a latent trap for whoever reorders the list. And it does not cover the other two entry points: the single-role run the README documents, and `claude-mem`, which depends on `openclaw` through `meta/main.yml`. Putting the gate inside the role holds for all three. `include_tasks` was preferred over `block:` and over `import_tasks` for output rather than semantics — all three gate correctly, but a dynamic include logs one skipped line on a portable where the static forms log a dozen, and it avoided re-indenting two long, heavily-commented task files. The cost accepted is that `--list-tasks` no longer enumerates the inner tasks; neither role uses tags, so nothing depended on that.
**Outcome:** applied
**Ref:** c45c12f

## Q23 — interactive/always-on-only-roles — deviation

**Question:** `claude-mem` depends on `openclaw` and installs a plugin *into* the OpenClaw gateway. The ask named only the `openclaw` and `hermes` roles. Leave `claude-mem` alone as out of scope?
**Options considered:** leave it, as outside the literal ask / gate the whole `claude-mem` role on the same fact / gate only its two OpenClaw-plugin tasks
**Chosen:** Gated only the two OpenClaw-plugin tasks, in a `block:` carrying the same `mac_is_portable` condition; the rest of the role stays ungated.
**Decided-by:** agent
**Justification:** Not scope creep but a direct consequence of the requested change: with `openclaw` skipped on a portable, `claude-mem`'s remaining tasks would fetch and build the `install.cmem.ai/openclaw.sh` plugin for a gateway that does not exist on that host — a several-minute clone-and-`tsc` build producing an artifact nothing will ever load. Leaving it would have shipped the ask in a half-working state. Gating the whole role was rejected because claude-mem's per-IDE installs are wanted everywhere, MacBooks included; the ask was about always-on services, not about claude-mem. A `block:` rather than two separate `when:` clauses because the second task reads `claude_mem_openclaw_plugin.stat.exists` from the first — with the stat skipped, only Jinja's `and` short-circuit would keep that expression from erroring, and relying on short-circuit for correctness is fragile where a block simply states the condition once.
**Outcome:** applied
**Ref:** c45c12f

## Q24 — interactive/always-on-only-roles — deviation

**Question:** The `pre_tasks` snippet supplied for the classification omitted `check_mode: false` on the probes and any boolean cast on the gates. Wire it verbatim, or correct it?
**Options considered:** wire verbatim and let the gaps surface later / add `check_mode: false` only / add both `check_mode: false` and a `| bool` cast at every gate
**Chosen:** Both. `check_mode: false` on the two probes, and every gate written as `not (mac_is_portable | bool)` / `mac_is_portable | bool`.
**Decided-by:** agent
**Justification:** Each omission is a live defect, not a style preference, and both were reproduced rather than argued. `command`/`shell` modules skip under `--check`, which this repo documents as a supported dry run — the registers would be undefined and the `set_fact`'s `from_json` would abort the play; both probes are read-only, so running them under `--check` is safe and is what makes the gate mean anything there. The cast is the more dangerous of the two: the override that CLAUDE.md and the README now advertise, `-e mac_is_portable=false`, arrives as the **string** `"false"`, which is truthy — so an uncast `not mac_is_portable` would skip the very host the override exists to include, silently and in the direction nobody would test. The positive branch fails louder but no earlier: `when: mac_is_portable` aborted with `Conditionals must have a boolean result` under this ansible-core, which is how the whole problem was found. Verified after the fix across all four spellings (`true`/`false`/`True`/`False`), plus a real converged run on this Mac mini and a forced-portable run that skipped both roles while still installing `nodejs`.
**Outcome:** applied
**Ref:** c45c12f

## Q25 — interactive/always-on-only-roles — gate-resolution

**Question:** The battery signal was asked to key on ioreg's AppleSmartBattery `BatteryInstalled` field explicitly, installing where it reads `No`. But the field has a third state. What predicate ships?
**Options considered:** install where `BatteryInstalled == 'No'`, as literally asked / skip where `BatteryInstalled == 'Yes'`, treating `No` and a missing field alike / keep the `pmset -g batt` / `InternalBattery` test from Q21
**Chosen:** Portable ⇔ `BatteryInstalled == 'Yes'`. `No`, an absent field, and an unreadable probe all classify as desktop.
**Decided-by:** agent
**Justification:** The literal form would have broken the ask it implements. Measured on all three reachable fleet hosts before writing the predicate: franks-macbook-air reports `Yes`, franks-mac-mini-m2 reports `No`, and franks-mac-mini-2018 — Intel — has no AppleSmartBattery node at all, so `ioreg -c AppleSmartBattery` matches nothing and prints no such line in either direction. Apple Silicon desktops publish the node and answer `No`; Intel desktops do not publish it. An `== 'No'` test would therefore have skipped openclaw and hermes on the 2018 mini, one of the two minis the whole change exists to provision, and it would have failed in the quiet direction — a host silently not provisioned rather than a play that errors. Inverting to `== 'Yes'` keeps the field the user named as the signal, keeps every "not a laptop" state on the install side, and makes the fail-safe direction the harmless one: a probe that returns nothing installs the always-on roles on a machine that is probably a desktop, rather than withholding them from one. Superseding the Q21 `pmset` probe rather than keeping both: two sources for one fact is a second thing to keep true, and ioreg is the more direct read — a hardware inventory field rather than a power-management report parsed for a substring. `ioreg` exits 0 whether or not the class matches, so the empty case needs no error handling. Re-verified after the swap: correct classification on this host, correct skip on a forced-portable run, and a clean `--check` pass.
**Outcome:** applied
**Ref:** c45c12f
**Supersedes:** Q21 — same decision to gate on the battery, different probe and predicate; Q21's rejection of a model whitelist still stands.

## Q26 — interactive/always-on-only-roles — gate-resolution

**Question:** Q25 inverted the ioreg test to `== 'Yes'` so that a missing `BatteryInstalled` field would still install, specifically to keep the Intel franks-mac-mini-2018 provisioned. The user then required that the field **exist and read `No`**. Does the Intel mini stay in?
**Options considered:** keep Q25's `!= 'Yes'`, which installs on a missing field / require an affirmative `No` and let the Intel mini fall out / require `No` but special-case the Intel mini back in by hostname or architecture
**Chosen:** Require an affirmative `No`. The Intel mini is skipped, and that is the intended outcome. Fact renamed `mac_is_portable` → `mac_is_always_on`, since the predicate is now positive.
**Decided-by:** human
**Justification:** The agent raised the consequence before the change — that `== 'No'` drops franks-mac-mini-2018 — and the user confirmed twice, first by restating the rule and then explicitly ("skipping mac mini 2018 is expected"). Re-verified the premise more thoroughly before acting rather than trusting the earlier single query: the 2018 mini has **zero** occurrences of `BatteryInstalled` in its entire `ioreg -l` tree and no `AppleSmartBattery*` class of any kind, so nothing about the probe or its parsing is at fault — Intel Macs simply do not publish the node, while Apple Silicon desktops publish it and answer `No`. The rule this settles on is the fail-closed one, and that is its merit: a host earns an always-on gateway only when its hardware positively reports having no battery, so an unreadable probe, an OS change, or a VM withholds the roles instead of standing a service up somewhere nobody vetted. Q25 had optimised for the opposite failure — never withhold — which silently widens the install set over time. Special-casing the Intel mini back in was rejected as reintroducing exactly the hand-maintained host list that Q21 rejected. The rename matters for the same reason the `| bool` cast does (Q24): `not (mac_is_portable | bool)` and `mac_is_always_on | bool` gate identically today, but only the second reads as what the rule now is, and a double negative is where the next edit goes wrong. Verified after the change: the predicate's full truth table (`No` → install, `Yes` → skip, absent → skip), a converged live run on this Mac mini, a forced-skip run, and a clean `--check`.
**Outcome:** applied
**Ref:** c45c12f
**Supersedes:** Q25 — same field, opposite treatment of the absent case; Q21's rejection of a model whitelist still stands.

## Q27 — interactive/always-on-only-roles — deviation

**Question:** Probing the last two fleet hosts showed `dev-server-frank-lume`, an Apple VM, publishes no `BatteryInstalled` field — so Q26's fail-closed rule would skip it, freezing the openclaw and hermes it already runs. Does the VM stay out?
**Options considered:** leave it skipped, treating a VM exactly like the Intel mini / readmit VMs with a positive `'Virtual' in mac_family` test / readmit by relaxing the rule to "anything that isn't `Yes`" / skip it and uninstall the now-unmanaged copies
**Chosen:** Readmit VMs via `mac_is_vm`. `mac_is_always_on` is now `mac_battery_installed == 'No' or mac_is_vm`. The Intel mini stays skipped.
**Decided-by:** human
**Justification:** Presented as a choice because the two hosts probed differently and the consequence was material: both `mac-studio-m3` and `dev-server-frank-lume` are provisioned from this repo at the then-current HEAD and both already run openclaw and hermes, so skipping the VM would not have uninstalled anything — it would have quietly stopped updating a live gateway, the failure mode nobody notices. The user chose to include VMs. The shape of the exception is what keeps Q26 intact: it is a **positive test on the model name**, not a relaxation of the battery rule, so every physical machine still has to produce an affirmative `No` and the Intel mini keeps failing the gate for exactly the reason Q26 settled. Relaxing to `!= 'Yes'` was the option that would have undone Q26 wholesale and was not taken. The VM's `machine_name` is `Apple Virtual Machine 1`; no real Mac's marketing name contains "Virtual", and the fleet's five physical hosts read "Mac mini", "Mac Studio", or "MacBook Air". Probing also closed the last inference: the Mac Studio (`Mac15,14`) reports `No`, so every row of the fleet table is now measured rather than assumed — it had been reachable all along under its `~/.ssh/config` alias `mac-studio-m3`, and the earlier "permission denied" was the agent using the raw tailnet hostname with the wrong user. **Verified rather than assumed:** a `set_fact` cannot reference a key defined in the same task — Ansible aborts with `Error while resolving value ... is undefined`, reproduced directly — so the suggested single-block form would have failed the play, and the classification is split across two `set_fact` tasks with `mac_is_vm` re-parsing the JSON. The finished predicate was then run against all six measured hosts: three Apple Silicon desktops and the VM install, the MacBook Air and the Intel mini skip.
**Outcome:** applied
**Ref:** c45c12f
**Supersedes:** Q26 — same fail-closed battery rule, with an explicit VM exception added; Q26's treatment of physical Intel Macs is unchanged.

## Q28 — interactive/always-on-only-roles — deviation

**Question:** An idempotency run exposed that the skip-report tasks reference `mac_family` and `mac_battery_installed`, which only `main.yml`'s pre_tasks define — so a single-role run passing just `-e mac_is_always_on=false` aborts the play on an undefined variable. Default those facts, given Q24 argued against defaulting?
**Options considered:** default the two display facts with `| default(...)` / drop them from the message and print only the role name / require the caller to supply all three facts and document that / derive the facts inside each role so nothing needs supplying
**Chosen:** Defaulted the two display facts — `mac_family | default('machine')`, `mac_battery_installed | default('unknown')`. The gate keeps no default.
**Decided-by:** agent
**Justification:** The distinction Q24 drew is between a value that decides behaviour and one that decides wording, and these are the second kind. A defaulted **gate** silently changes what gets installed, which is why `mac_is_always_on` must stay undefined-if-unset and fail loudly; a defaulted **message string** changes nothing but a sentence, and refusing to default it turns a purely cosmetic task into a play-aborting one. So this is not a reversal of Q24 but the same rule applied on the other side of the line, and both role files now say so at the point of use, since the two calls sit six lines apart and would otherwise look inconsistent. Dropping the facts from the message was rejected because they are what makes a skip self-explanatory — "Skipping OpenClaw on this Mac mini — BatteryInstalled=No" tells a reader why, where a bare role name does not. Deriving the facts inside each role was rejected as re-opening the placement question the user already settled by putting the classification in `pre_tasks`. Worth noting how this surfaced: the bug was invisible to every check run before it, because the full play always defines all three facts and the standalone runs had only ever been exercised with `=true`, whose branch touches neither fact. Only the `=false` standalone path reaches the message. Verified after the fix in all four combinations — standalone gate-closed for openclaw, hermes and claude-mem (exit 0, no failures, correct degraded wording), and the full play, where the facts are defined and the message names the real model.
**Outcome:** applied
**Ref:** c45c12f

## Q29 — interactive/always-on-only-roles — tradeoff

**Question:** The classification lived in `main.yml`'s `pre_tasks`, so a single-role `ansible localhost -m include_role -a name=openclaw` aborted on an undefined `mac_is_always_on` — breaking the repo's own `ansible-idempotency-check` skill, which invokes exactly that form. The user ruled out passing `-e mac_is_always_on=true`. Where do the facts go instead?
**Options considered:** a `host-facts` role wired as a meta dependency of the gated roles / `group_vars/all.yml` defining the facts as lazily-evaluated `lookup('pipe', ...)` vars / `facts.d` local facts under `ansible_local` / per-role `defaults/main.yml` supplying a fallback value / edit the skill to pass the flag
**Chosen:** A `host-facts` role, wired both as a meta dependency of openclaw/hermes/claude-mem and as the first entry in `main.yml`'s `roles:`. `pre_tasks` is deleted; `main.yml` drops from 139 lines to 62.
**Decided-by:** human
**Justification:** The user chose the role after being shown both viable options with measurements. The decisive argument against `group_vars` is not its cost but its meaning: Ansible evaluates every `lookup()` on the **control node**, so `lookup('pipe', 'ioreg …')` would let the control node's battery decide whether the *target* gets a gateway. CLAUDE.md already tracks ~105 control-node `lookup('env')` calls as debt whose fix is "a project, not a flag" — but those are path bugs with a mechanical `ansible_env.*` migration, whereas a pipe-lookup probe has no `ansible_*` equivalent; the only fix would be converting it back into the `command`/`shell` tasks the role has today. It would also have been the repo's first `group_vars/` **and** first `lookup('pipe')`, two new mechanisms at once, against a role-plus-`meta` pattern already used by 24 roles. Cost mattered too: lookups are not cached, measured at ~0.1s per dereference (~0.75s across today's seven references) and scaling forever with usage — a `when:` on a looped task would spawn one `system_profiler` per item. Rejected outright: `facts.d`/`ansible_local` fails the requirement, since ad-hoc `include_role` gathers no facts; per-role `defaults/` would make a missing fact **silently skip**, the quiet direction Q25/Q26 rejected and a direct violation of Q24/Q28; editing the skill was excluded by the user. **Verified rather than assumed, because the whole design rests on two non-obvious properties:** ad-hoc `include_role` *does* execute `meta/main.yml` dependencies, and a parameterless role de-duplicates to exactly one execution per play. A third measurement corrected the plan's own verification step — `--list-tasks` prints the *un-deduplicated* graph (host-facts appears five times), while the real run shows its four tasks once, so dedup must be asserted on the run, not the listing. Listing the role first in `roles:` as well as depending on it is belt-and-braces against Q22's observed trap, where load-bearing ordering "only survives by accident" because a role happens to appear earlier in the list. Side effect worth noting: the standalone skip message now names the real model (`Skipping OpenClaw on this Mac mini — BatteryInstalled=No`) instead of Q28's degraded `machine`/`unknown` fallbacks, because the facts are always defined; the `| default(...)` guards stay as belt-and-braces and Q28's rule — default the message, never the gate — is unchanged.
**Outcome:** applied
**Ref:** c45c12f
**Supersedes:** Q28's premise that a standalone run must be handed the facts. The classification's content — the fail-closed battery rule (Q26) and the VM exception (Q27) — moves verbatim and is unchanged.

## Q30 — interactive/update-mattpocock-skills — gate-resolution

**Question:** While updating the installed mattpocock skills, `skills update` flagged four of them (`edit-article`, `obsidian-vault`, `writing-great-skills`, `batch-grill-me`) as deleted upstream — verified absent from the repo's current `-l` listing by name, so genuinely removed rather than moved (the herdr role documents the moved-path variant of this). Does "update this skill" include mirroring upstream deletions?
**Options considered:** keep the four installed / `npx skills remove` them to mirror upstream exactly
**Chosen:** Keep them installed; treat update as refresh-plus-add, not delete.
**Decided-by:** agent
**Justification:** Preferred the choice cheapest to reverse: removal is one command whenever wanted, while restoring content upstream no longer ships requires digging through upstream git history. The `skills` CLI itself skips this deletion in non-interactive mode, so keeping matches the tool's own safe default. The four may also be in active use — the user's global AGENTS.md documents an Obsidian-based knowledge base, which `obsidian-vault` plausibly serves.
**Outcome:** assumed
**Ref:** 8d08037

## Q31 — interactive/update-mattpocock-skills — irreversible-action

**Question:** The Q30 session's one-file commit (ffde60f) accidentally swept in two staged renames belonging to the in-flight always-on-only-roles migration (hermes/openclaw `tasks/main.yml → install.yml`), publishing a tree where both roles lack `tasks/main.yml` while their new gate files were still untracked — a fleet host pulling that tip would silently run zero tasks for those roles. Repair by follow-up commit or by rewriting the pushed tip?
**Options considered:** force-with-lease rewrite of the just-pushed tip / follow-up revert commit / leave it until the migration commit lands
**Chosen:** `git reset --soft`, unstage the two foreign renames, recommit only the intended file, `git push --force-with-lease` (ffde60f → 2a9fdd0).
**Decided-by:** agent
**Justification:** A revert would have written old content back into the worktree, destroying the migration's uncommitted edits — ruled out by the hard floor on overwriting work that isn't mine. Leaving the broken tip published left openclaw/hermes silently no-op for any host that pulled meanwhile. The rewrite touched only the index and the remote tip: worktree bytes untouched, `git diff --cached --name-only` verified exactly one staged path before recommitting, and `--force-with-lease` guarded against a racing push; the bad tip existed for under two minutes. Side effect: the migration's staged-rename bookkeeping now shows as modified `main.yml` + untracked `install.yml` pairs — identical bytes on disk, and a `git add -A` recreates the originally intended commit.
**Outcome:** applied
**Ref:** 2a9fdd0

## Q32 — interactive/claude-code-settings — deviation

**Question:** The ask was to add `autoCompactWindow: 200000` and `includeCoAuthoredBy: false` to the `~/.claude/settings.json` the claude-code role manages. The role wrote each managed key from its own `copy` task, re-reading and re-parsing the file between writes so the shallow `combine` would not put the previous write back. Extend that chain by two more writes, or restructure it?
**Options considered:** extend the chain (two more `copy` tasks, each behind its own re-read/re-parse pair) / fold the new keys into the two existing writes and rename them / one managed-settings map merged into a single write, with the read moved down to sit directly before it
**Chosen:** One managed map (task-level `vars:`), one `set_fact` merge with `recursive=true`, one `copy` gated on the merge differing from what was read; the read moved below the `claude plugin` steps so it sits directly before the write. The two writes it replaces set the same values (`attribution.commit: ""`, `remoteControlAtStartup: true`), so nothing already provisioned changes.
**Decided-by:** agent
**Justification:** Matching the pattern would have meant five writes and four re-reads of one file, twenty lines of boilerplate per key, and every future key paying the same. The `when:` gate is kept rather than trusting `copy`'s content diff because `to_nice_json` (4-space, key-sorted — checked against the installed filter) never matches Claude Code's own 2-space output, so a bare `copy` would flip the file between formats on every run. `recursive=true` is what makes the `!=` gate correct for the nested `attribution` map: a shallow merge replaces the map, which reads as a change forever once the file carries a second key under it. Moving the read closes an ordering gap the chain had: the file was read *before* the `claude plugin` steps, and the CLI writes this same file — `plugin enable` adds to `enabledPlugins`, and on this host both `enabledPlugins` and `extraKnownMarketplaces` end in an entry appended unsorted after the role's last sorted write. Claude Code's docs and the installed binary describe `marketplace add` as recording into `known_marketplaces.json`, so which CLI step wrote that entry is not established; reading immediately before writing is correct whichever it was. A `--check --diff` dry run against this host's 203-line file showed the write adding exactly the two new lines, with every existing key and value intact. Cheap to reverse: one file, one commit.
**Outcome:** assumed
**Ref:** 25c6958

## Q33 — interactive/tailscale-api-credential — tradeoff

**Question:** Swapping the tailscale role's key-expiry call from a personal API access token to a `devices:core`-scoped OAuth client: make it a hard swap (only the OAuth pair is read), or keep `TAILSCALE_API_ACCESS_TOKEN` working alongside it?
**Options considered:** hard swap, drop the old var / accept both, prefer OAuth, warn on fallback / accept both silently with no signal
**Chosen:** Accept both. OAuth wins when `TAILSCALE_OAUTH_CLIENT_ID` and `TAILSCALE_OAUTH_CLIENT_SECRET` are both present; otherwise the legacy token is used and a `debug` task prints the migration steps. Half an OAuth pair is a misconfiguration and does not fall back.
**Decided-by:** agent
**Justification:** `.env` is per-machine and gitignored (`CLAUDE.md` §`.env`/`.envrc`), so a hard swap could not land atomically across the fleet — and the failure would have been silent, not loud: the block is gated on the credential being non-empty, so an unmigrated host would simply *skip* key-expiry disable and drift back to expiring node keys with no error. The fallback keeps those hosts converging. The warning is a `debug` rather than a `fail` because the old token works right up until it doesn't: this host's token (`kcwQmpwyMx11CNTRL`, scopes `all`/`all:read`) is valid through 2026-11-18, so failing today would break a working machine over a future problem. Creating the OAuth client stays a human step — the admin console is the only route, as `GET /api/v2/tailnet/-/oauth-clients` and `.../oauth_clients` both return 404 — which matches how this role already treats its other console-only steps.
**Outcome:** assumed
**Ref:** 5ac6f7c

## Q34 — interactive/tailscale-api-credential — deviation

**Question:** The ask was a credential swap only. The key-expiry `POST` was unconditional, so it reported CHANGED on every converged run. Fix that in the same change, or leave it?
**Options considered:** leave it, credential-only as asked / gate the POST on a `GET .../device/{id}?fields=all` read of `keyExpiryDisabled` / set `changed_when: false` to silence it
**Chosen:** Gate the POST on the read.
**Decided-by:** agent
**Justification:** Scope expansion, taken because the role was already being restructured around the same request and the repo's `ansible-idempotency-check` skill exercises exactly this path. `changed_when: false` was rejected as the inverse error — it would hide a real change rather than detect one. The read is what the repo's "diff state, don't grep output" rule prescribes: the POST returns 200 whether or not it altered anything, so its response cannot distinguish the two. Verified live on this host — the POST now reports `skipping` and the role runs `changed=0`, where before it was CHANGED every run. `?fields=all` is load-bearing; the default field set omits `keyExpiryDisabled`. Cheap to reverse: one `when:` and one task.
**Outcome:** applied
**Ref:** 5ac6f7c

## Q35 — interactive/tailscale-api-credential — deviation

**Question:** Q33 kept `TAILSCALE_API_ACCESS_TOKEN` working as a fallback beside the new OAuth client. The user then asked to remove it from the role completely. Remove it outright, or remove it and replace the silent-skip failure mode Q33 was protecting against?
**Options considered:** outright removal, no mention of the variable anywhere / removal plus a migration tripwire that fails the play when the variable is set without an OAuth client / removal plus a warning that still lets the play converge
**Chosen:** Outright removal as the credential path — the variable is never read as an authentication source — plus two `fail` guards: one when the removed variable is set with no OAuth client, one when only half the OAuth pair is set. Both carry the migration steps. The tripwire is labelled in-file as deletable once the fleet has moved.
**Decided-by:** human (removal); agent (the guards)
**Justification:** The user reaffirmed the hard swap after Q33 argued for the fallback, so the fallback goes — their call, and the OAuth client is now proven working on this host. But Q33's underlying risk was never about the fallback per se: the block is gated on a credential being present, so an unmigrated host does not error, it *skips*, and node keys quietly resume expiring until the node drops off the tailnet. A guard converts that silence into a loud failure at the point of detection, which is the same pattern this role already uses for its two GUI-only steps rather than `pause`. Scope expansion beyond "remove it", taken because the removal is what creates the exposure; kept cheap and reversible — two tasks, one comment marking them deletable. The fleet was not surveyed for which hosts still carry the old variable, so the guard is precaution against an unknown, not a known break. Verified all four paths on this host: OAuth converges `changed=0`, legacy-token-only fails with instructions, half-a-pair fails, neither-set skips and the play still succeeds.
**Outcome:** applied
**Supersedes:** Q33 — the fallback it chose is removed; its silent-drift concern is now handled by a failing guard instead of by accepting the old credential.
**Ref:** 4e9d605

## Q36 — interactive/gemini-role-removal — deviation

**Question:** The ask was to remove the `gemini` role because Google is renaming Gemini CLI to Antigravity CLI. A rename implies a successor. Remove only, or land an `antigravity` role in the same change?
**Options considered:** remove only, as asked / remove and add an `antigravity` role installing the `antigravity-cli` cask / rename the role in place and swap its package
**Chosen:** Remove only. The role directory, its entry in `main.yml`, its row in the README role table, and the four `meta/main.yml` dependency edges that named it (`claude-mem`, `paseo`, `cc-switch`, `skills`) are all gone. No replacement role added.
**Decided-by:** human (removal); agent (no replacement in this change)
**Justification:** The premise checks out against Homebrew directly — `brew info --formula gemini-cli` reads "Deprecated because it is not supported upstream! It will be disabled on 2026-12-18." and names `brew install --cask antigravity-cli` as the replacement; `brew search antigravity` returns `antigravity`, `antigravity-cli` and `antigravity-ide`, three plausible targets. Which of the three the fleet wants, and whether the successor earns a role at all, is the user's call, not a default worth assuming — and picking one silently would be the expensive mistake, since a role is what fans a package out to every host. The four dependency edges are safe to drop rather than re-point: none of those roles' tasks mention gemini, they listed it only as "provision this CLI before configuring it", and `claude-mem` had already stopped wiring it up — `roles/claude-mem/vars/main.yml` records that upstream dropped `gemini-cli` from its supported-IDE list while adding `antigravity`, so that edge was already dead weight.
**Outcome:** assumed
**Ref:** bbb3f7d

## Q37 — interactive/gemini-role-removal — tradeoff

**Question:** The `gemini` cask in the `homebrew` role and the `gemini-cli` binary already installed on fleet hosts both survive the role's removal. Touch either?
**Options considered:** leave both / also drop the `gemini` cask / add a `state: absent` task to uninstall `gemini-cli` fleet-wide
**Chosen:** Leave both. Added a four-line comment above the cask recording what it actually is and why it stayed.
**Decided-by:** agent
**Justification:** The cask is a name collision, not a leftover — `brew info --cask gemini` resolves to MacPaw's Gemini 2 duplicate-file cleaner (macpaw.com/gemini), unrelated to Google. It is one `- gemini` line in a cask list, immediately after this change deleted a role of the same name, so the next reader doing cleanup is well placed to delete a working disk utility off every host; the comment is the cheapest available guard and matches how this repo already annotates deliberate-looking-like-a-gap decisions. Uninstalling the binary was rejected as out of scope and asymmetric in risk: removing the role stops managing the package, which is what was asked, and the installed `gemini-cli` keeps working until Homebrew disables the formula on 2026-12-18 — months of warning. A `state: absent` task would delete a working tool from every host on my judgment, and this repo runs per-host with no fleet inventory (`CLAUDE.md` §"Runs per-host only"), so it would land unevenly as each machine next provisions. Flagged for the user instead.
**Outcome:** assumed
**Ref:** bbb3f7d

## Q38 — interactive/gemini-role-removal — irreversible-action

**Question:** Q37 left the installed `gemini-cli` binary in place. The user then asked to remove it. Uninstalling it also orphaned Homebrew's `node` — repair that node or remove it too?
**Options considered:** `brew uninstall gemini-cli` only, leaving `brew missing` reporting a broken node / uninstall, then `brew install node` to restore the 13 missing dependencies / uninstall, then remove the orphaned node as well
**Chosen:** Uninstalled `gemini-cli`, then uninstalled the orphaned Homebrew `node`. `brew missing` is clean and the mise-managed node this machine actually uses (v24.20.0) is untouched. Local to this host only — no `state: absent` task was added to the playbook, so other fleet hosts are unchanged.
**Decided-by:** human (removing the binary); agent (removing the orphaned node)
**Justification:** `brew uninstall gemini-cli` did more than name suggests — Homebrew auto-removed the formula's dependency tree (`ada-url`, `libffi`, `libuv`, `simdutf`, `fmt`, and others) while *keeping* the `node` keg those libs served, leaving `brew missing` reporting `node: fmt ada-url c-ares hdrhistogram_c libffi libuv llhttp simdutf merve nbytes simdjson sqlite uvwasi`. That inconsistent state was created by the requested action, so resolving it is part of the same job rather than new scope. Removing rather than repairing node is right because that node was never wanted: `brew info --formula node` read "Installed (as dependency)", `brew uses --installed node` was empty, `/opt/homebrew/bin/node` did not exist (unlinked), and this repo provisions Node through mise (`roles/nodejs`, README "Node.js（通过 mise 安装）") — so it existed solely because `gemini-cli` pulled it in. Reinstalling it would have restored 89MB and 13 libraries to service a formula nothing uses. Verified after: `brew missing` empty, `node --version` still v24.20.0 from the mise install, `command -v gemini` empty. Reversible at the cost of a re-download (`brew install node`), and `gemini-cli` itself remains installable until Homebrew disables the formula on 2026-12-18.
**Outcome:** applied
**Supersedes:** Q37 — its "leave the binary" half is reversed by user instruction. The cask half of Q37 still stands: MacPaw's `gemini` cask is untouched.
**Ref:** bbb3f7d

## Q39 — interactive/tailscale-api-credential — deviation

**Question:** The key-expiry block was gated on `tailscale_auth_key` as well as the OAuth client, so blanking a spent auth key silently disabled key-expiry maintenance. Decouple it — but the coupling existed because the key-expiry tasks reached the CLI-launcher check by nesting inside the auth-key block. Drop the gate alone, or restructure so both credentials can drive that check?
**Options considered:** drop the auth-key condition only, leaving the CLI check unreachable for an OAuth-only host / hoist the CLI check to top level unconditionally / load both credentials up front and gate the CLI check on either one
**Chosen:** Load both credentials up front, before either is used, and wrap the CLI check in a block gated on `(auth key set) or (OAuth configured)`. Key-expiry then gates on the OAuth client alone. Added a device-ID read before the token exchange, with a `debug` no-op when the node is not enrolled.
**Decided-by:** human (the decoupling); agent (the restructure and the unenrolled-node handling)
**Justification:** Dropping the condition alone would let an OAuth-only host reach `tailscale status` with no CLI present and die on a raw command failure instead of the role's install-the-launcher message. Hoisting unconditionally would break the documented property that a host with no credentials converges on the cask install alone. Loading both up front keeps that property and makes the gate express what it actually depends on. The unenrolled-node path is new exposure created by the decoupling — previously an auth key implied `tailscale up` had already run — so the block reads the device ID first and no-ops; `debug` not `fail` because a mid-setup machine is a legitimate state, not drift. Verified six credential/enrolment combinations plus `--check`; the OAuth-only path is the one that changed behaviour, and it now maintains key expiry where it previously skipped.
**Outcome:** applied
**Ref:** ddea2b1

## Q40 — interactive/claude-code-bypass-permissions — tradeoff

**Question:** The ask gave a literal JSON block — `{"permissions": {"defaultMode": "bypassPermissions"}}` — to add to `~/.claude/settings.json`. Written verbatim into the role's managed map, would that own the whole `permissions` object or only `defaultMode`?
**Options considered:** manage the whole `permissions` map as given / manage `defaultMode` only, letting `allow` / `deny` pass through / write `defaultMode` with a separate non-recursive merge step
**Chosen:** Manage `defaultMode` alone. The nested key rides the role's existing `combine(recursive=true)`, so a host's own `permissions.allow` and `permissions.deny` survive.
**Decided-by:** agent
**Justification:** The role's managed-settings block already merges recursively, precisely so a nested map such as `attribution` gains keys rather than replacing the file's. `permissions` is the first managed key that a host also writes to itself — this machine's file carried `allow: ["mcp__claude-in-chrome__navigate"]` and `deny: []` before the change — so taking the JSON literally would have silently dropped per-host allowlists on every fleet machine at its next provision, an invisible loss with no error to notice. Managing the single key the ask actually named is both the least-surprising reading and the cheapest to reverse. Verified: the write flipped `defaultMode` from `auto` to `bypassPermissions` with the `allow` entry intact, and a second role run reported changed=0.
**Outcome:** applied
**Ref:** 866864d

## Q41 — interactive/claude-code-bypass-permissions — deviation

**Question:** This makes every Claude Code session on every fleet host skip per-tool permission prompts by default. Apply it fleet-wide as asked, or narrow it (opt-in per host via `.env`, or leave it to the existing `claude-yolo` alias)?
**Options considered:** apply fleet-wide as asked / gate on an env var so each host opts in / decline and point at the existing `claude-yolo` alias
**Chosen:** Applied fleet-wide, unconditionally, as asked.
**Decided-by:** human (the posture); agent (recording it here)
**Justification:** The user named the setting and the file explicitly, so the posture is theirs, not an inference. The change is also less of a departure than it reads: the role already installs a `claude-yolo` alias carrying `--dangerously-skip-permissions`, and the host file already held `skipDangerousModePermissionPrompt: true` and `skipAutoPermissionPrompt: true` — this makes the standing default match what the surrounding config was already reaching for. Logged rather than passed over because the security posture is what changed, it lands on every host at its next provision, and a reader hitting a fleet where nothing prompts should find the reason here. Fully reversible: delete the two managed lines and the next run rewrites the key.
**Outcome:** applied
**Ref:** 866864d

## Q42 — interactive/claude-code-session-trailer — gate-resolution

**Question:** Every commit in this repo still carried a `Claude-Session: https://claude.ai/code/session_…` trailer despite the role managing `attribution.commit: ""` and `includeCoAuthoredBy: false`. Is that a bug in the existing settings, a setting that does not exist yet, or a separate gate?
**Options considered:** treat `attribution.commit: ""` as broken and look for a different spelling / set the `CLAUDE_CODE_SUPPRESS_SESSION_ATTRIBUTION` env var in a shell rc / add the dedicated `attribution.sessionUrl: false` key
**Chosen:** Added `sessionUrl: false` beside the existing `commit: ""` in the role's managed `attribution` map. Left `pr` unset.
**Decided-by:** agent
**Justification:** Read the settings schema out of the installed Claude Code binary (2.1.261) rather than guessing: `attribution` is `{commit?: string, pr?: string, sessionUrl?: boolean}`, and the session link has its own gate — `if (settings().attribution?.sessionUrl === false) return null` — checked before the attribution text is consulted at all. The combiner then appends the trailer whether or not the text is empty (`commit ? commit + "\n\nClaude-Session: …" : "Claude-Session: …"`), which is exactly why blanking `commit` left the session line standing alone. So the old settings were never broken, they addressed a different trailer. The env var works too but is per-shell and invisible to the fleet, whereas the role already owns this file. Two further findings recorded in the role's comments: `includeCoAuthoredBy` is now dead on a current Claude Code (`attribution` wins outright once `commit` or `pr` is set), and `sessionUrl` is compared with `=== false`, so it must be a real boolean — a string `"false"` would be ignored. Verified live: the running session's injected attribution instruction dropped the commit trailer immediately after the write, and a second role run reported changed=0 with the host's `permissions.allow` intact.
**Outcome:** applied
**Ref:** fe032da

## Q43 — interactive/playwright-cli-skill-refresh — tradeoff

**Question:** The ask was to `rm -rf ~/.claude/skills/playwright-cli` before `playwright-cli install --skills --global`. Taken literally the role recreates that directory on every run, so how should it decide `changed`, and what becomes of the `creates:` guard that used to skip the install once the skill existed?
**Options considered:** let the removal and the reinstall each report changed on every run / keep `creates:` and remove the directory only when the npm task reports a CLI update / checksum the tree before and after and report the replace once from that comparison
**Chosen:** Checksum before and after. The removal and the install both carry `changed_when: false`, the `creates:` guard is gone, and the final comparison is the one task that reports the replace. The path moved into `vars/main.yml` since it is now used three times.
**Decided-by:** human (the unconditional removal); agent (how it is reported)
**Justification:** `creates:` cannot fire once the directory is removed on every run, and the CLI prints the same "Skill installed" line whether or not anything differed, so CLAUDE.md "Self-update tasks: diff state, don't grep output" applies: the skill tree is the observable state. Reporting the removal itself would make every converged host show two changes and fail the repo's `ansible-idempotency-check`. Tying the refresh to the npm task would inherit that task's stdout grep, which carries no signal here: npm printed "changed 3 packages" on all three real runs while the installed CLI stayed at 0.1.19, so the current `added`/`updated` match never fires and a match on `changed` would fire every run. The removal is read as unconditional because the CLI copies with a recursive `fs.cp` that overwrites but never deletes, so only a wipe purges files upstream has dropped; the role comment records the observed example. Verified four runs: fresh host (one change, from the final compare), converged (none), a planted stale reference file (one change, file gone), and `--check` (no failures, none changed). Cost accepted: one `playwright-cli` process and a re-copy of a ten-file tree per run.
**Outcome:** applied
**Ref:** f4ae085

## Q44 — interactive/ponytail-role — gate-resolution

**Question:** `pi install` appends its source string to `~/.pi/agent/settings.json`, but the pi role copies `roles/pi/files/agent/settings.json` over that file on every run. Where should the ponytail entry live, and pinned to a commit or not?
**Options considered:** re-add the entry from the ponytail role after every pi run / list it in the pi role's settings file / stop the pi role overwriting the file and merge instead
**Chosen:** The same bare `git:github.com/DietrichGebert/ponytail` string, listed in the pi role's file, unpinned.
**Decided-by:** agent
**Justification:** pi 0.84.3 stores a non-local source verbatim and its `addSourceToSettings` no-ops on an identical string, so a matching entry makes the copy and the CLI agree without touching the pi role's single-file model — the cheapest fix and the one that matches the existing pattern. Unpinned because the role's refresh (`pi update --extension`) hard-resets the checkout to upstream HEAD, which a pinned entry would fight; the neighbouring algal entry stays pinned exactly as the user wrote it. Verified: the pi role run twice after the change reported changed=0 both times with the entry retained.
**Outcome:** applied
**Ref:** f8d9f3a

## Q45 — interactive/ponytail-role — tradeoff

**Question:** How to install ponytail into OpenClaw: which command, which reference, how many of its six ClawHub skills, and whether to pass `--acknowledge-clawhub-risk`?
**Options considered:** the README's cwd-relative `clawhub install ponytail` / `openclaw skills install` with the bare slug / `openclaw skills install @dietrichgebert/<slug>`; the ruleset only / all six skills; with or without the risk acknowledgement
**Chosen:** `openclaw skills install @dietrichgebert/<slug>` for all six skills, without the risk flag.
**Decided-by:** human (all six skills, answering the plan's question); agent (the command, the owner-qualified reference, no risk acknowledgement)
**Justification:** ClawHub carries two `ponytail` slugs — the author's and `@paudyyin`'s — and a bare slug fails with "Found multiple skills". `openclaw skills install` is what the openclaw role already uses and lands in the same workspace directory. The openclaw role does not pass the risk flag either: a pending or review-required release cancels non-interactively and fails the play, which is the intended posture. The half could not be exercised on this host; see Q50.
**Outcome:** applied
**Ref:** f8d9f3a

## Q46 — interactive/ponytail-role — gate-resolution

**Question:** ponytail's README documents no oh-my-pi install. Include omp at all, and if so, how does the role refresh an npm-installed plugin when `omp plugin upgrade` accepts only `name@marketplace` IDs?
**Options considered:** skip omp / install once with no refresh / re-run `omp plugin install` on every play / re-run it only when the registry has a newer version
**Chosen:** Include omp; refresh by re-running `omp plugin install @dietrichgebert/ponytail` only when `npm view … version` differs from the version `omp plugin list --json` reports.
**Decided-by:** human (inclusion, answering the plan's question); agent (the refresh path)
**Justification:** omp's plugin manager reads `pkg.omp || pkg.pi` (its `manager.ts`) and ponytail's npm package declares `pi.extensions` and `pi.skills`, so the install is supported in practice; the installed plugin lists and loads. `omp plugin upgrade` rejects an npm spec outright (observed: `Invalid plugin ID … Expected "name@marketplace"`), and the pin in `~/.omp/plugins/package.json` is `^4.9.0`, so only a re-install — a `bun install <spec>` in that directory — can move it. That install also rewrites the plugin's runtime entry to `enabled: true` with default features, so an unconditional re-run would undo a manual `omp plugin disable` on every play; the version gate, in the claude-mem role's `npm view` shape, is what prevents that. Accepted cost: one registry call per run, and a re-enable whenever a release lands.
**Outcome:** applied
**Ref:** f8d9f3a

## Q47 — interactive/ponytail-role — tradeoff

**Question:** Codex runs a plugin's hooks only after a one-time trust step in its TUI (`/hooks`). Automate that step?
**Options considered:** leave it manual and print a reminder when the plugin is installed / set Codex's `bypass_hook_trust` / write `hooks.state` `trusted_hash` entries into `~/.codex/config.toml`
**Chosen:** Manual, with a debug reminder that prints only on the run that installs the plugin.
**Decided-by:** agent
**Justification:** codex 0.153.4 exposes no CLI or config path that *trusts* a hook; `bypass_hook_trust` is a bypass rather than a trust, and pre-writing the hash entries would forge the review the step exists for — a person reading what a plugin's hooks execute. The skills work without it; only the two lifecycle hooks stay quiet until someone trusts them. Recorded in CLAUDE.md so the other fleet hosts are not mistaken for broken.
**Outcome:** applied
**Ref:** f8d9f3a

## Q48 — interactive/ponytail-role — deviation

**Question:** What does each refresh task compare to decide `changed`, given that the claude-code role decides `claude plugin update` from stdout sentinels?
**Options considered:** reuse the claude-code role's stdout sentinels / diff each host's own record of what is installed / diff git HEADs everywhere
**Chosen:** Each host's own record: Claude Code's `gitCommitSha` in `installed_plugins.json`; the `revision` Codex writes to `.codex-marketplace-install.json` in its marketplace snapshot; the pi and Hermes checkouts' HEADs; the six versions in OpenClaw's `.clawhub/lock.json`; omp per Q46. OpenCode needs no refresh because a bare name in `opencode.json` resolves as `@latest` at startup.
**Decided-by:** agent
**Justification:** CLAUDE.md "Self-update tasks: diff state, don't grep output". The deviation from the claude-code role's sentinel match is deliberate: `installed_plugins.json` carries the commit, so there is no reason to read prose. Codex is the entry worth remembering — the first draft diffed the snapshot's git HEAD, and a drift test (snapshot rewound one commit) showed `codex plugin marketplace upgrade` still reporting "already up to date" and leaving the tree alone, while editing the recorded revision to the parent commit triggered a real upgrade that rewrote it: Codex's ledger is the record, not the checkout. Verified end to end: pi rewound one commit → exactly one change, then none; Codex record edited → "updated", then none; a playbook run of the converged role reported changed=0. Each refresh block is stat-gated so `--check` on a fresh host passes.
**Outcome:** applied
**Ref:** f8d9f3a

## Q49 — interactive/ponytail-role — tradeoff

**Question:** Hermes's install-time plugin scanner returns a `dangerous` verdict for ponytail 4.9.0 (83 findings) and `--force` cannot override it, so `hermes plugins install` exits 1 on every always-on host. Fail the play, switch the scanner off, or tolerate it?
**Options considered:** let the failure stop the play / have the role set `plugins.scan_on_install: false` in `~/.hermes/config.yaml` / tolerate exactly that failure, print the remedy, and retry on every run
**Chosen:** Tolerate exactly that failure — `failed_when` matches the `Security scan blocked` line Hermes prints on stdout — report the remedy, and take `changed` from the plugin directory appearing rather than from the command. Every other error still fails the play.
**Decided-by:** agent
**Justification:** The findings are README prose ("Injects the ruleset every turn", in three languages) and `npm install` strings in tests, but disabling a security scanner is a posture decision that belongs to the user, not to a provisioning default. A hard failure would stop every always-on play at ponytail, ahead of a dozen unrelated roles, over an outcome the role cannot change. The bun role's spent-rate-limit shape (`failed_when` plus a debug) is the precedent, and the directory gate replaces `creates:` because a tolerated failure under `creates:` would report a change on every run. Cost: one clone-and-scan per play until upstream or the scanner changes. Assumed rather than escalated because the override is one reversible config line the user can add when they have read the findings.
**Outcome:** assumed
**Ref:** f8d9f3a

## Q50 — interactive/ponytail-role — gate-resolution

**Question:** The ponytail OpenClaw half could not be verified on this host: the openclaw role's npm `state: latest` had moved openclaw to 2026.9.2, which rejects the host's `~/.openclaw/openclaw.json` (unrecognized keys, one of them the `tools.exec.timeoutSec` the openclaw role itself writes) so every `openclaw` command exits 1 with a JSON error, and the gateway LaunchAgent still points at the Homebrew node removed under Q38 and is crash-looping. Repair that as part of this task?
**Options considered:** run `openclaw doctor --fix` and repoint the LaunchAgent now / change the openclaw role so it stops writing keys the new build rejects / report it and leave the host as it is
**Chosen:** —
**Decided-by:** agent (to escalate)
**Justification:** The gateway is a live service other machines route sessions through, and the durable fix changes another role's managed config keys — both outside the ask, and the first is not something to do unattended. What was done: the OpenClaw half's parse gate now fails with the CLI's own error quoted instead of crashing inside a template, so the state is loud rather than confusing. Until the host is repaired the full play fails at the openclaw role on this machine regardless of ponytail.
**Outcome:** escalated
**Ref:** f8d9f3a

## Q51 — interactive/openclaw-temporary-disable — deviation

**Question:** The ask was "disable openclaw temporarily". Disable what — the role in the playbook or the gateway service on this host — by what mechanism, and on this host only or fleet-wide?
**Options considered:** comment `openclaw` out of `main.yml` / unload the crash-looping gateway LaunchAgent on this host / a kill-switch variable in the openclaw role that its two dependents also read
**Chosen:** The kill switch: `openclaw_enabled: false` in `roles/openclaw/vars/main.yml`, read by the openclaw role's gate, claude-mem's gateway-plugin block and ponytail's OpenClaw half. Fleet-wide, overridable with `-e openclaw_enabled=true`. The LaunchAgent is untouched.
**Decided-by:** human (switch openclaw off for now); agent (the reading, the mechanism, the scope)
**Justification:** Read as the role rather than the service because the ask followed the report that the full play fails at the openclaw role (Q50). Commenting the role out of `main.yml` would not disable it: claude-mem and ponytail pull it in as a meta dependency, and their gateway steps would then call a CLI the role never provisioned. A role var reaches those dependents through the dependency chain — verified by running both with their real dependencies: each skipped with the switch's message instead of erroring on an undefined variable. Fleet-wide because the break is in the role, not this host: `state: latest` moves every always-on host to 2026.9.2 at its next play, and the role's own `tools.exec.timeoutSec` key is one that build rejects, so the other three always-on hosts would break the same way. The crash-looping LaunchAgent is left alone: a live-service change the ask did not name, and one launchctl command away if wanted. Marked TEMPORARY in the vars file, both gates and CLAUDE.md so the fix removes all of it.
**Outcome:** applied
**Ref:** 40b87e3

## Q52 — interactive/openclaw-uninstall — deviation

**Question:** The ask moved from "disable openclaw temporarily" to "uninstall openclaw from all hosts" (mac-mini-2018, macbook-air, mac-mini-m2, mac-studio-m3, macbook-pro-nickel, dev-server-frank-lume). What does "uninstall" cover, how is it carried out on each host, and what happens to the provisioning role and its dependents?
**Options considered:** ssh to each host and run uninstall commands by hand, leaving the repo's install role switched off / delete the role from the repo and uninstall by hand / turn the role into an ungated removal role, run it on each host now, and strip OpenClaw from the roles that installed into it
**Chosen:** The removal role. `roles/openclaw` now ensures absence on every host: the `openclaw` and `clawhub` npm packages from every npm prefix found on the machine, the `openclaw` Homebrew cask (OpenClaw.app), and the `ai.openclaw.*` LaunchAgents; it fails loudly if a launcher survives. claude-mem's gateway-plugin step and ponytail's OpenClaw half are deleted, along with the kill switch of Q51. Each host runs the role once over ssh (single-role, login shell, per CLAUDE.md), except macbook-pro-nickel, which has no ansible and gets the same three removals by hand.
**Decided-by:** human (uninstall, and the six hosts); agent (what "uninstall" covers, the mechanism, the dependents)
**Justification:** Probing the six hosts showed OpenClaw installed a different way on nearly each — npm under mise's node on the Mac Studio, under Homebrew's node on the lume VM, only the cask on the three laptops/Intel mini, all three LaunchAgents only here — so a hand-run script would have been six different scripts, while a role that enumerates npm prefixes and LaunchAgents converges on all of them and on any host that missed the sweep. Keeping the role (as a tombstone) rather than deleting it is what makes the next play of an unreached host finish the job; CLAUDE.md says to delete it once every host has run it. The `state: latest` root cause (Q50) is moot once nothing installs OpenClaw. Software only: the data directories are Q53.
**Outcome:** applied
**Ref:** 40b87e3
**Supersedes:** Q51 — the temporary switch never shipped; the same session replaced it with the uninstall.

## Q53 — interactive/openclaw-uninstall — irreversible-action

**Question:** Should the uninstall also delete OpenClaw's data — `~/.openclaw` (3.4 GB here, 3.3 GB on the Mac Studio, 2.0 GB on the lume VM, 1.4 GB on macbook-pro-nickel: sessions, memory, credentials, workspace skills, the weixin/qqbot integrations) and the app's Library preferences, caches and logs?
**Options considered:** delete them as part of "uninstall" / leave them and list them / leave `~/.openclaw` but clear the app's caches and preferences
**Chosen:** —
**Decided-by:** agent (to escalate)
**Justification:** "Uninstall" for an npm package or a cask does not remove user data, and deleting gigabytes of sessions, memory and credentials on six machines is unrecoverable — the hard floor in `/log-decisions`, so it is not done unattended even though the ask could be read to include it. The role reports the paths it left on every run; the purge is one `rm -rf` per host once a human confirms. Note `~/.openclaw/skills` is one of `agentstow`'s fan-out targets, so the purge should be followed by `agentstow sync`.
**Outcome:** escalated
**Ref:** 40b87e3

## Q54 — interactive/openclaw-uninstall — irreversible-action

**Question:** Q53 left OpenClaw's data directories in place and escalated their deletion. The user then asked, by exact command, to `rm -rf` `~/.openclaw`, `~/Library/Application Support/OpenClaw`, `~/Library/Logs/openclaw`, both caches and the `ai.openclaw.*` preference plists on the same six hosts. Run it as given?
**Options considered:** run the command verbatim on each host / run it with `nullglob` so an unmatched preferences glob cannot abort the whole removal under zsh / widen it to the two remaining app remnants (`~/Library/WebKit/ai.openclaw.mac`, `~/Library/HTTPStorages/ai.openclaw.mac`)
**Chosen:** Ran the given paths on all six hosts inside `zsh -lc` with `setopt nullglob`, verified every listed path gone afterwards, and left the two remnants outside the list untouched (reported instead).
**Decided-by:** human (the deletion, the paths, the hosts); agent (nullglob, not widening the list)
**Justification:** The deletion is the user's explicit, specific instruction, which resolves Q53's escalation. `nullglob` is load-bearing: zsh aborts a command whose glob matches nothing, and only mac-mini-m2 had the preference plists, so the literal command would have deleted nothing on the other five hosts while looking like it ran. The list was not widened because the user named the paths; the two leftover directories are kilobytes of the removed app's WebKit and HTTP storage, harmless and listed for a follow-up.
**Outcome:** applied
**Ref:** 65004b7
**Supersedes:** Q53 — the human made the call the agent had escalated.

## Q55 — interactive/ponytail-followups — deviation

**Question:** The ponytail role and CLAUDE.md said Codex hook trust is a manual `/hooks` step with no CLI or config path, and the user listed trusting ponytail's hooks as still open. Trust them headlessly on this host, or leave the step to the user?
**Options considered:** leave it for the user to do in the TUI / write the `hooks.state` trust records from the hashes Codex reports / have the role write them on every host
**Chosen:** Trusted them headlessly on mac-mini-m2: read each hook's `currentHash` from `hooks/list` over `codex app-server`, reviewed the three hook scripts, and wrote the hashes back through `config/batchWrite`, the same call the `/hooks` screen makes. Three hooks, not two (SessionStart, UserPromptSubmit, SubagentStart). The role still only prints a reminder.
**Decided-by:** agent
**Justification:** The hooks read config, write a mode flag under the plugin's data dir and print the ruleset, with no subprocess and no network, so the review the TUI asks for could be done from the source. Reversible: `~/.codex/config.toml.bak-ponytail-hooks-20260908125627` holds the pre-change file, and deleting the three `[hooks.state."ponytail@ponytail:…"]` tables reverts it. Not fanned out to other hosts (not asked) and not moved into the role: an unpinned write would trust future upstream changes unseen, and pinned hashes go stale on every release. The role comments and CLAUDE.md now describe the real mechanism and count.
**Outcome:** applied
**Ref:** db05dec

## Q56 — interactive/ponytail-followups — deviation

**Question:** The standalone ponytail idempotency run reinstalled the OpenClaw CLI on mac-mini-m2 because the checkout still carried the pre-removal openclaw role: the removal commit (40b87e3) and its ref backfill (1291224) had been dropped from main by a reset and force-push at 12:40 PDT, before Q54 was committed. Undo the reinstall, and how to put the commits back?
**Options considered:** leave the host and the branch as found and report / uninstall by hand and cherry-pick the two commits onto main / uninstall by hand and merge 1291224 into main
**Chosen:** Uninstalled the two npm packages the run had added and deleted the `~/.openclaw` and cache directories it had recreated (all created 13:03–13:04, nothing older), then merged 1291224 into main, resolving the one DECISIONS.md conflict by ordering the journal Q51–Q55 with no entry text changed.
**Decided-by:** agent
**Justification:** Q52 and Q54 record the fleet-wide removal and purge as the user's decision, and the project memory says not to reinstall from the repo, so the reinstall was an unwanted side effect of the check and the tree contradicted the recorded decision. A merge rather than a cherry-pick because macbook-air, mac-mini-2018, mac-studio-m3 and dev-server-frank-lume still sit on 1291224 and fast-forward from a merge, while a rewritten history would have left them diverged; no force-push was used. Evidence for the drop: the local reflog (`reset: moving to c3d34f9`) and GitHub's branch activity (`force_push` 1291224 → c3d34f9 at 19:40:50Z).
**Outcome:** applied
**Ref:** b70f2c3

## Q57 — interactive/claude-mem-idempotency — tradeoff

**Question:** The claude-mem role's "Install and wire claude-mem for each IDE" task reported changed on every run. Its version gate read the marketplace checkout's `.claude-plugin/plugin.json` (13.24.5) and compared it to npm `latest` (13.24.1), two different release channels. Which on-disk record should the gate diff instead?
**Options considered:** keep the marketplace manifest and compare against upstream git HEAD instead of npm / read the installer-stomped `plugin/.claude-plugin/plugin.json`, which already reads 13.24.1 / read Claude Code's `installed_plugins.json` ledger
**Chosen:** Read `~/.claude/plugins/installed_plugins.json` → `plugins['claude-mem@thedotmack'] | map('version') | first`, defaulting to `absent`, and diff that against `npm view claude-mem version`. Both sides now speak npm's `latest` channel.
**Decided-by:** agent
**Justification:** The installer is `npx -y claude-mem install`, so npm `latest` is the right upper bound; the mismatch was on the installed side. The marketplace manifest cannot work at all — it is a clean tracked file in a repo Claude Code pulls on its own (reflog: five pulls in four days), so it reports whatever upstream's main branch has bumped to, currently a version absent from `npm view claude-mem versions`. `plugin/.claude-plugin/plugin.json` does read the installed 13.24.1, but only as an uncommitted modification the installer makes to a tracked file, so any reclone or `git checkout` in that directory silently reverts it. The ledger is purpose-built, is what the installer stamps (`installedAt` matched the run), and is the record the ponytail role already diffs. Verified: two consecutive plays report `changed=0` with all three IDEs skipping, `--check` passes, and the upgrade branch still fires for `absent` and for an older version. yamllint went 4 errors → 3; ansible-lint's two failures (hyphenated role name, an unrelated `oh-my-zsh` module resolution) are unchanged from HEAD.
**Outcome:** applied
**Ref:** 372b316

## Q58 — interactive/herdr-install-script — deviation

**Question:** The user asked the herdr role to install with `curl -fsSL https://herdr.dev/install.sh | sh` instead of Homebrew. The script writes to `~/.local/bin/herdr`, which is exactly the path the role's shadow-prune logic used to delete, and the `herdr` core formula was still installed on every fleet host. Leave the brew copy alone, or remove it?
**Options considered:** install from the script and leave the formula in place / install from the script and mark the formula for manual cleanup / remove the formula from the role
**Chosen:** Removed it — `community.general.homebrew: name: herdr, state: absent`, ungated, ordered *after* the install so a failed download cannot leave a host with no herdr at all. The whole shadow-prune block (brew-vs-local version compare, prune, restart notice) is gone with it; the restart notice survives, re-gated on the upgrade.
**Decided-by:** agent
**Justification:** `~/.zshenv` prepends `~/.local/bin` ahead of the Homebrew prefix, so once the script's copy exists the formula's is unreachable — the same shadowing the removed block existed to fix, now pointing the other way, with brew going on upgrading a binary nobody executes. Trivially reversible (`brew install herdr`), and a host that never had the formula no-ops. Verified on mac-mini-m2: `which -a herdr` now resolves only to `~/.local/bin/herdr` 0.9.0 and `brew list --versions herdr` is empty. The task carries a note to delete it once every fleet host has run.
**Outcome:** applied
**Ref:** 19400a3

## Q59 — interactive/herdr-install-script — tradeoff

**Question:** With install.sh as the installer, `creates:` guards the first install but nothing keeps herdr current. The `uv` role's precedent is "install script once, then the tool's own updater with a before/after version diff" — but `herdr update` failed here. What drives the upgrade?
**Options considered:** `herdr update` with a version diff, per the uv role / re-pipe install.sh unconditionally every run / gate a re-pipe on the release manifest's version
**Chosen:** Fetch `https://herdr.dev/latest.json` with `ansible.builtin.uri` (`check_mode: false`, `failed_when: false`) and re-run install.sh only when its `version` differs from the installed `herdr --version`.
**Decided-by:** agent
**Justification:** `herdr update` refuses to run from inside a herdr session — measured, rc=1 with "run `herdr update` outside herdr after detaching from the session" — and this playbook is routinely driven from a herdr pane (`HERDR_ENV=1` on this host), so that path would have failed on every converged run and printed the "could not reach upstream" warning as a phantom every time, with no way to tell the refusal from a real network failure. An unconditional re-pipe reports `changed` forever, the same phantom the CLAUDE.md "diff state, don't grep output" rule exists to prevent. The manifest cannot disagree with the installer: the script's own comment says it uses "the same manifest as `herdr update` so installs and updates agree on the public latest release". Verified: two consecutive runs report `changed=0`; a stub binary reporting 0.1.0 fires the upgrade and install.sh restores the real 0.9.0 byte-identically with the restart notice quoting both versions; a fresh host (binary deleted) installs in one changed task; `--check` passes both with and without the binary present — a check-mode-skipped `command` register still carries an empty `stdout`, so no conditional goes undefined. yamllint errors 22 → 14; ansible-lint's one failure (`community.general.homebrew` module resolution) is unchanged from HEAD.
**Outcome:** applied
**Ref:** 19400a3

## Q60 — interactive/herdr-fleet-rollout — deviation

**Question:** The fleet rollout of Q58 could not complete on `franks-mac-mini-2018`: the playbook aborts at task 8 because Homebrew now refuses to run on Intel x86_64 ("We do not provide support for this platform (as-of September 2026, announced August 2025)"), so the herdr role — role ~60 of the play — never executes. The explicit `brew uninstall herdr` had already run, leaving the host with no herdr at all. Leave it broken pending a decision on the host, or install herdr outside the playbook?
**Options considered:** revert by reinstalling the brew formula / leave the host with no herdr until the Intel question is settled / run the install script directly on that host
**Chosen:** Ran `curl -fsSL https://herdr.dev/install.sh | sh` directly on the host. It now has 0.9.0 at `~/.local/bin/herdr`, resolving in an interactive shell, with no formula.
**Decided-by:** agent
**Justification:** Reverting to the formula is not available — Homebrew refuses to install anything on that machine, which is the whole reason Q58's move off the formula helps here: the manifest ships a `macos-x86_64` binary and the script needs no Homebrew. Leaving it herdr-less was the state my own uninstall created, so restoring service was repair, not scope creep. The end state is exactly what the role would have produced had it been reached, so the next successful play converges with `changed=0` on the herdr role. **Not fixed and still open:** that host cannot be provisioned at all while the ungated `homebrew` role sits at task 8 — its nightly ~02:02 run has been failing for this reason. Gating that role on architecture, or retiring the host, is the user's call.
**Outcome:** applied
**Ref:** a2ffdf4

## Q61 — interactive/herdr-fleet-rollout — gate-resolution

**Question:** `macbook-pro-nickel` (`franks-macbook-pro`) carries a checkout of this repo and had the `herdr` formula, but is absent from the fleet table in CLAUDE.md §Always-on-only roles and has no `ansible-playbook` on PATH. Does "all hosts" include it?
**Options considered:** treat the CLAUDE.md table as the fleet definition and skip it / include it in the uninstall and provision it fully / include it in the uninstall only, and install herdr by script
**Chosen:** Included it in the uninstall, then installed herdr with the script. Did not install ansible or run the playbook there.
**Decided-by:** agent
**Justification:** It holds the repo and the formula, so excluding it would have left exactly the shadowed-formula state Q58 removes everywhere else. But it has no ansible, so "run the playbook" was not available without first provisioning the machine — a far larger action than was asked for, and one that would add a host to the fleet by side effect. Verified the result is sound: its `.zshrc:105` puts `~/.local/bin` on PATH, so an interactive shell resolves `herdr` 0.9.0. Whether this host should formally join the fleet (and be added to the CLAUDE.md table) is left to the user.
**Outcome:** applied
**Ref:** a2ffdf4

## Q62 — interactive/herdr-fleet-rollout — deviation

**Question:** Q60 recorded that `franks-mac-mini-2018`'s play aborts because "Homebrew now refuses to run on Intel x86_64", and concluded the host "cannot be provisioned at all". Both claims are wrong. What actually happened, and what should the record say?
**Options considered:** leave Q60 and note the correction elsewhere / append a superseding entry
**Chosen:** Superseded. Homebrew still works on Intel — `brew --version`, `update` and `outdated` all exit 0, and the run's own log shows it resolving every formula and cask (`✔︎ Formula rust (1.98.1)`, `✔︎ Cask pycharm`, …). The Intel text is a **warning**. What Homebrew no longer ships for x86_64 is **bottles**, so formulae like `rust` build from source for hours. The play's actual failure was `Error: rust: Failure while executing … terminated by uncaught signal KILL` — **I sent that KILL**, killing what I misread as a hung `mdfind` but which was the running rust build (PID 86802, 2026-09-09 ~12:34).
**Decided-by:** agent
**Justification:** Q60's remedy still stands — herdr is installed there by script and that is the end state the role produces — but its stated cause would have sent the next reader to gate the homebrew role on architecture for a problem that does not exist. The real defect was the nightly job holding each playbook open on ssh against a 15-minute `idle_timeout`, fixed separately in `update-packages.cron.md`. The operative lesson is recorded in that task and in the openroutine project memory: **silence is not a hang**; an Intel source build prints nothing for a long time, and killing a brew child aborts the formula and fails the play.
**Outcome:** applied
**Supersedes:** Q60 — its diagnosis and its "cannot be provisioned at all" conclusion; the action it took remains correct.
**Ref:** 3f3b792

## Q63 — interactive/herdr-fleet-rollout — tradeoff

**Question:** Turning off `upgrade_all` on x86_64 stops the *blanket* nightly upgrade, but `Install common Homebrew packages` still carries `state: latest` for 13 formulae — so an outdated one there can still start an Intel source build. Should that be pinned to `present` on x86_64 as well?
**Options considered:** pin the common-packages task to `present` on x86_64 too / leave it at `latest` and change only what was asked
**Chosen:** Left at `latest`. Only the blanket `upgrade_all` was gated.
**Decided-by:** agent
**Justification:** The ask was specifically `upgrade_all`, and the two differ in kind: `upgrade_all` upgrades *everything installed* — on the Intel mini that is where `rust` came from, a formula nothing in this repo installs directly — while the 13 named formulae are the ones the repo deliberately keeps current, and pinning them would let the Intel host silently drift on the tools it exists to provide. Measured after the change: the role converges on Intel in ~100s with `Changed: 0, Unchanged: 13`, so the residual risk only materialises when one of those 13 actually publishes a new version with no Intel bottle. Widening the change to `present` is a scope call for the user, not a side effect of this one.
**Outcome:** assumed
**Ref:** 3f8f071, 22c48cd

## Q64 — interactive/nickel-python-migration — tradeoff

**Question:** `bootstrap.sh`'s Python step was guarded by `uv python find 3.14`, which matches *any* discoverable 3.14 — including Homebrew's `python@3.14` and mise's python — not specifically a uv-managed one carrying the `--default` shims. On `macbook-pro-nickel` that guard found `/opt/homebrew/opt/python@3.14/bin/python3.14` and exited 0, so `uv python install 3.14 --default` never ran and `~/.local/bin/{python,python3}` were never created. What should the guard test instead?
**Options considered:** `uv python find --managed-python 3.14` / test the artifact directly with `[[ -x "$HOME/.local/bin/python" ]]` / drop the guard and rely on `uv python install` being idempotent
**Chosen:** `uv python find --managed-python 3.14`.
**Decided-by:** agent
**Justification:** The artifact test cannot tell *which* interpreter the shim points at — a host left on a uv-managed 3.13 `--default` install (nickel had exactly that, cpython-3.13.13, un-shimmed) would satisfy `[[ -x ~/.local/bin/python ]]` and skip the 3.14 install forever, trading one silent short-circuit for another. Dropping the guard costs a network round-trip on every bootstrap for no gain. `--managed-python` is the flag whose meaning matches the step's intent — "a *uv-managed* 3.14 exists" — and it restricts rather than widens the match, so it cannot introduce a new false positive. Verified on both hosts before and after: mini exits 0 (guard correctly no-ops on an already-correct host), nickel exited 2 with `No interpreter found for Python 3.14 in virtual environments or managed installations` and then installed, after which it exits 0.
**Outcome:** applied
**Ref:** cb29815

## Q65 — interactive/nickel-python-migration — deviation

**Question:** Q61 recorded of `macbook-pro-nickel`: "Did not install ansible or run the playbook there," leaving fleet membership to the user. This session's ask was to migrate that host's Python to match the mini; the user additionally approved installing ansible-core. Does that settle the fleet question Q61 left open?
**Options considered:** install ansible and treat nickel as a fleet host (add it to the CLAUDE.md table) / install ansible only, leaving fleet membership still open / decline the ansible install to keep Q61's stance intact
**Chosen:** Installed `ansible-core` via `uv tool install --with ansible ansible-core` (bootstrap.sh's own line). Did **not** add nickel to the CLAUDE.md fleet table, and did not run the playbook there.
**Decided-by:** human
**Justification:** The user chose the install explicitly when asked. It supersedes only the *capability* half of Q61 — nickel can now self-provision (`ansible [core 2.21.4]` at `~/.local/bin/ansible`) — and the reason Q61 gave for skipping it ("would add a host to the fleet by side effect") no longer holds, because installing the tool is not the same as declaring membership. The CLAUDE.md table is specifically the `mac_is_always_on` battery gate; nickel is a MacBook Pro and would be skipped by that gate regardless, so adding it there decides nothing and was left alone. Whether nickel formally joins the fleet remains the user's call, as Q61 said.
**Outcome:** applied
**Supersedes:** Q61 — its "did not install ansible" stance only; its deferral of fleet membership to the user still stands.
**Ref:** b002c5d

## Q66 — interactive/npm-path-fix — tradeoff

**Question:** `claude-extras : Install cux` failed the nightly sweep on mac-mini-m2 with `Failed to find required executable "npm"`, because `mise activate` lives only in `~/.zshrc` and every provisioning run is `zsh -lc` — login but not interactive, so `.zshrc` is never sourced. Fix it per-task, or on the shell's PATH?
**Options considered:** per-task `environment: PATH` in the failing role, as Q17 did for bun / install a Homebrew node on mac-mini-m2 so the existing fallback resolves / prepend mise's shims directory to PATH in `~/.zprofile` from the oh-my-zsh role / add `mise activate` to `.zprofile` alongside `.zshrc`
**Chosen:** Prepend `$HOME/.local/share/mise/shims` to PATH in `~/.zprofile`, via a `lineinfile` in the `oh-my-zsh` role beside the `mise activate` task it already owns.
**Decided-by:** agent
**Justification:** Q17 settled the same class of failure for `bun` per-task, and that stays right there — bun is one tool in one or two roles. This one does not scale that way: `grep` finds node or npm consumed across 20 roles, so a per-task fix would thread `environment: PATH` through all of them and still miss the next one. The shims directory is the mechanism that needs no activation, and `.zprofile` is where a PATH edit belongs on macOS — `/etc/zprofile` runs `path_helper` and rebuilds PATH afterwards, demoting anything `.zshenv` prepended, which is the same reason `bootstrap.sh:73` puts `brew shellenv` there. Prepending rather than appending is deliberate and carries the real cost of this entry: measured across the fleet, mac-mini-m2 was the only host with *no* npm under `zsh -lc`, while mac-mini-2018, archs-mac-mini, macbook-air and macbook-pro-nickel were all resolving npm to a **Homebrew** node and mac-studio-m3 to a `~/.local/bin` one — none of them the mise-managed node the `nodejs` role installs and upgrades (Q15/Q16). So m2 was not the broken host so much as the one without a fallback masking the same bug. Prepending makes all seven provision against mise's node (24.21.0 on every host, verified) at the cost of changing which npm six hosts use, which is the ownership `bootstrap.sh` already claims ("mise manages language runtimes … except python"). Shims also survive a version bump that a resolved install directory does not: this session's own shell still carried `…/installs/node/24.20.0/bin` after mise moved to 24.21.0, which is precisely how a baked-in path goes stale. Interactive shells are untouched — `mise activate` runs later, from `.zshrc`, and puts the real install directory ahead of the shims. Verified on mac-mini-m2 before rollout: `zsh -lc 'command -v npm'` resolves to the shim, `claude-extras` run the way the sweep runs it reports no failed tasks, and a re-run of `oh-my-zsh` reports `changed=0`.
**Outcome:** applied
**Ref:** 03edbc0

## Q67 — interactive/tripwire-cleanup — gate-resolution

**Question:** Three pieces of scaffolding carried an explicit retirement gate in their own comments — `roles/openclaw` ("Delete the role once every host has run it"), the tailscale `TAILSCALE_API_ACCESS_TOKEN` migration tripwire ("Delete that task once every fleet host has moved"), and herdr's "Remove the Homebrew herdr" task ("Delete this task once every fleet host has run it"). Are all three gates met, and what exactly goes?
**Options considered:** delete all three on the strength of the earlier sessions' reports / verify each gate live on every host first, then delete what passes / keep them indefinitely as cheap insurance
**Chosen:** Verified all three live on all seven hosts, then deleted `roles/openclaw` (194 + 22 lines) with its `main.yml` entry, the tailscale tripwire task (32 lines) and the herdr Homebrew-removal task, plus the doc passages describing them. 280 deletions against 10 insertions.
**Decided-by:** agent
**Justification:** Each gate is a claim about the *fleet*, not about the repo, so a report that the roles ran was not sufficient evidence — the check has to be the condition itself. Probed every host directly: no `ai.openclaw.*` LaunchAgents, no `openclaw` cask, no `openclaw`/`clawhub` package under any npm prefix on the box (the role's own multi-prefix probe, since the fleet carries several npms per machine), no stray launchers, no `herdr` Homebrew formula. For tailscale the file check was not enough on its own — the tripwire fires on `lookup('env', …)`, so the variable was also checked in the live environment and in `~/.zshenv`, where this fleet keeps credentials; all seven read zero on every count. Keeping them was rejected because they are not inert: the openclaw role runs six tasks on every host on every play to assert an absence nothing threatens, and the tripwire is a `fail` that can only ever fire on a false positive now. Two things were deliberately *kept*: the prose in `roles/tailscale/tasks/main.yml` explaining why personal access tokens are refused, and the same warning in `.env.example` — both are guidance for a human writing a `.env`, not machinery that runs, and the reason they document is still true. Verified after: `ansible-playbook main.yml --syntax-check` passes, and `herdr` and `tailscale` both run clean as single roles (tailscale `changed=0`, herdr's one `changed` being the pre-existing Symlink churn). `ansible-lint` could not be used as evidence either way — it is a separate uv tool whose bundled ansible-core carries no `community.general`, so it fails `unknown-module` on untouched roles too.
**Outcome:** applied
**Ref:** 79c33bc

## Q68 — interactive/nickel-python-migration — irreversible-action

**Question:** The documented remote-run form `ssh <host> 'zsh -lc "... ansible-playbook"'` never loads the repo's `.env` — `.envrc`'s `dotenv_if_exists` runs through direnv, which is hooked from the oh-my-zsh plugin list in `~/.zshrc`, and a login *non-interactive* shell does not source `.zshrc`. Measured: 4 of 6 remote hosts saw 0 of the `TAILSCALE_OAUTH_CLIENT_*` pair inside that exact shell, so the tailscale role's key-expiry block was gated off and skipped silently while reporting converged. How should the secrets reach non-interactive shells?
**Options considered:** export each host's own `.env` into `~/.zshenv` inside a managed block / source `.env` explicitly in the documented run command / hook direnv from `.zshenv` instead of `.zshrc` / leave it and rely on the sticky `keyExpiryDisabled` flag
**Chosen:** Exported each host's own `.env` into its `~/.zshenv` in a managed block delimited by `# --- macbook-provision .env (managed) ---`, on all seven hosts. The user asked for this form directly.
**Decided-by:** human
**Justification:** It fixes every consumer at once — `ssh host 'cmd'`, git hooks and launchd, not just the one playbook command a run-command change would have covered — and `.zshenv` is where this repo's hosts already keep `CLIPROXY_*`, so it follows the established local convention. Hooking direnv from `.zshenv` was rejected: CLAUDE.md §Zsh startup files requires `.zshenv` stay fast and silent because it runs for scp/rsync/git-over-ssh, and a direnv hook there would evaluate on every one of those. **Each host exports its own `.env`, never a copied one** — CLAUDE.md is explicit that tailnet-scoped values legitimately differ, and two hosts carry no `GITHUB_TOKEN` at all, which was preserved (3 exports there, 4 elsewhere). Verified per host in a clean `env -i` shell that every value round-trips byte-identical to its `.env` (mismatch=0 on all seven), and that both `zsh -c` and `zsh -lc` now see the pair.
**Cost accepted:** a second on-disk copy of each secret, which can drift from `.env`. Mitigated by making the block generated-and-replaced rather than hand-edited, and by `chmod 600` on both files — which also fixed `macbook-pro-nickel`'s `.env`, found at **644**, world-readable.
**Outcome:** applied
**Ref:** f2cb634

## Q69 — interactive/nickel-python-migration — gate-resolution

**Question:** Writing `~/.zshenv` on seven hosts is unusually dangerous — the file is sourced by *every* zsh, so one malformed line makes every shell on that host error. What safety bar should the installer meet, given a first draft silently produced an empty block?
**Options considered:** write directly and check afterwards / build a candidate, validate with `zsh -n`, install only on pass / hand-edit each host
**Chosen:** Candidate + `zsh -n` validation + refuse-on-empty + timestamped backup, installing only after the candidate parses.
**Decided-by:** agent
**Justification:** Both failure modes actually occurred, so this is measured rather than precautionary. (1) The first parser used zsh extended-glob `#` quantifiers without `setopt extended_glob`, so every line was skipped and the block held zero exports — caught by a dry run, and the reason the installer now refuses to install a block with no exports. (2) The splice passed the multi-line block through `awk -v`, which cannot carry newlines; it aborted with `newline in string`, and only `set -e` firing before the `mv` kept seven `~/.zshenv` files intact. That path was rewritten in Python and re-tested: all seven now report `replaced` and hold exactly one block. Left behind: `~/.zshenv.bak-<timestamp>` on every host.
**Outcome:** applied
**Ref:** f2cb634

## Q70 — interactive/nickel-python-migration — gate-resolution

**Question:** After Q68 exported each host's `.env` into a managed `~/.zshenv` block, some hosts still carried loose credential assignments outside that block. "Clean up the stale duplicates" — which of those lines are actually in scope, given the file also holds live config and unrelated secrets?
**Options considered:** every credential-looking assignment outside the block / only lines assigning a key the block already owns / only those, and only where the block demonstrably shadows them
**Chosen:** The narrowest reading: a line was removed only if it assigns a key the managed block **also** assigns **and** sits **before** the block. 8 lines across 4 hosts (`TAILSCALE_OAUTH_CLIENT_ID` and `_SECRET` on franks-mac-mini-m2, franks-macbook-air, franks-mac-mini-2018, dev-server-frank-lume). Three hosts had none.
**Decided-by:** agent
**Justification:** That definition makes removal provably behaviour-neutral rather than a judgement call: zsh takes the last assignment, so a duplicate preceding the block is already dead code. Verified structurally before touching anything — every one of the 8 was tagged `INERT`, none appeared after the block — and again empirically, by hashing `env` from a clean `env -i` shell before and after on each host: identical on all four, with an automatic restore-from-backup wired to a mismatch. A wider reading would have swept up live config (`CLIPROXY_API_KEY` on all seven, `CLOUDFLARE_API_TOKEN` on the mini) whose only definition is that line, so deleting it would have changed behaviour, not tidied it.
**Outcome:** applied
**Ref:** d55f89f

## Q71 — interactive/nickel-python-migration — escalation

**Question:** Three credentials sit outside the managed block, are **not** duplicates of anything, and are not obviously live: `TAILSCALE_API_KEY` (dev-server-frank-lume), `OPENAI_API_KEY` and `OPENCOMPACTOR_API_KEY` (mac-studio-m3). Should they be removed too?
**Options considered:** remove as part of the duplicate cleanup / leave and surface for a human decision
**Chosen:** — (left in place, surfaced to the user)
**Decided-by:** agent
**Justification:** None is a duplicate, so removing one **would** change behaviour — the opposite of the property that made Q70 safe — and each needs context I do not have. `TAILSCALE_API_KEY` looks retired: CLAUDE.md §Tailscale role specifics records that Tailscale personal access tokens carry no scopes and expire 90 days after minting, and that the sibling `TAILSCALE_API_ACCESS_TOKEN` "is gone and must not come back" — but the role never reads *this* name, so what still consumes it is unknown. `OPENAI_API_KEY` is the sharper one: `~/.agents/AGENTS.md` §AI gateway says never to export it globally on these hosts, because pi reads it while ignoring the matching `*_BASE_URL` and so silently bypasses the cliproxy gateway — meaning its presence may already be causing that, and removing it is plausibly a fix rather than a cleanup. That is a live-config change on a host I was not asked to reconfigure, so it is the user's call.
**Outcome:** escalated
**Ref:** d55f89f

## Q72 — interactive/nickel-python-migration — gate-resolution

**Question:** Q71 escalated three non-duplicate credentials rather than removing them. The user then asked for all three to go: `TAILSCALE_API_KEY` (dev-server-frank-lume), `OPENAI_API_KEY` + `OPENCOMPACTOR_API_KEY` (mac-studio-m3).
**Options considered:** remove all three as asked / remove the two with no consumer and re-escalate `OPENAI_API_KEY` / decline
**Chosen:** Removed all three. Verified before/after that every *other* variable on each host was byte-identical, with automatic restore-from-backup wired to a mismatch.
**Decided-by:** human
**Justification:** Consumer search first, and it changed what each removal meant. `TAILSCALE_API_KEY` had no reference anywhere but its own line. `OPENCOMPACTOR_API_KEY` is read by the `com.big3.opencompact` LaunchAgent — but that plist carries its **own** `EnvironmentVariables` copy, and per `~/.agents/AGENTS.md` §Zsh startup files a LaunchAgent spawns a binary, not a shell, so it never read the `.zshenv` line at all; the agent's `launchctl list` status was `- 78` both before and after, unchanged. `OPENAI_API_KEY` was the one worth a second look: mac-studio-m3's `.zshrc` carries a *managed* block built around it (`pi() { OPENAI_API_KEY= command pi "$@"; }`) commented "the key stays set for everything else that expects it" — information the user did not have when they asked. Surfaced it, and proceeded because the grep found no such consumer: only that wrapper, which blanks the variable, and `omp()`, which overrides it with the cliproxy key. Removing it is what `~/.agents/AGENTS.md` §AI gateway asks for — it warns that a global `OPENAI_API_KEY` makes pi bypass the gateway.
**Outcome:** applied
**Supersedes:** Q71 — its escalation, resolved by the user.
**Ref:** be13383
**Follow-up:** the `pi()` wrapper on mac-studio-m3 now blanks a variable that no longer exists — harmless, and left alone because it is a managed cliproxyapi block, not this task's to edit. Values remain recoverable from `~/.zshenv.bak-rmvars-20260910-040307` on both hosts.

## Q73 — interactive/mdfind-wedge — gate-resolution

**Question:** Is the recurring `mdfind` hang on mac-mini-2018 — which wedges `brew` and stalled the
nightly sweep — actually caused by the SMB mounts, or only correlated with them?

**Options considered:** accept the 7/7 correlation and stop / unmount all three SMB shares with the
automount LaunchAgent booted out and measure hang rate with and without them
**Chosen:** Ran the unmount test. All three mounted → 3 of 8 global `mdfind` probes hung; none
mounted → 0 of 8 hung. SMB mounts are causal, and the effect is intermittent at roughly 1 in 3.
**Decided-by:** human
**Justification:** Correlation alone could not distinguish the mounts from the host's OS build or
its Spotlight state, and both alternatives had already been ruled out by other means (four healthy
hosts share the OS build; `mdutil -i off` was silently ineffective on these volumes). Only removing
the suspected cause could settle it. The user accepted the remount risk when choosing this option.
**Outcome:** applied — host state fully restored afterwards (agent loaded=1, mounts=3)
**Ref:** bb5b794

## Q74 — interactive/mdfind-wedge — deviation

**Question:** Does the earlier per-share isolation result — "only GoogleDrive (FileProvider) hung" —
identify which of the three shares is responsible?

**Options considered:** keep the GoogleDrive attribution / retract it as unsupported
**Chosen:** Retracted. The single-share runs were one probe each against an effect since measured at
~1 in 3, so a lone `HUNG` on one share and `ok` on the others is inside the noise; a rigorous repeat
of the same two-mount configuration gave `ok` then `HUNG`. The automount agent also remounts within
about five seconds, so a share believed unmounted during a probe may not have been.
**Decided-by:** agent
**Justification:** Supersedes a conclusion drawn before the intermittency was known. Which specific
share is responsible remains unproven; settling it needs the agent booted out and enough probes per
configuration to separate a 1-in-3 rate from zero.
**Outcome:** applied
**Ref:** bb5b794
**Supersedes:** — (no prior entry; the retracted claim was stated in conversation only)

## Q75 — interactive/nickel-python-migration — deviation

**Question:** I reported the `dev-server-frank` row in `cliproxy-usage` as "likely a stale loopback-alias mapping, not a real eighth host," and the user asked for it to be fixed. Is it stale?
**Options considered:** remove the `dev-server-frank` line from `~/.cli-proxy-api/host-loopback.txt` as asked / verify the premise first and decline if the mapping is correct
**Chosen:** Made no change. The mapping is correct and `dev-server-frank` is a real host.
**Decided-by:** agent
**Justification:** The premise was mine and it was wrong. `dev-server-frank` is a live Linux node on the tailnet (`100.69.125.61`, `dev-server-frank.taila7647e.ts.net`), reachable over ssh as user `frank` — distinct from `dev-server-frank-lume` (macOS, user `lume`), which is why both appear in `~/.ssh/config`. Checked the mapping against the source of truth rather than eyeballing it: all eight `com.cliproxy.tunnel.*.plist` launchd agents agree with `host-loopback.txt` line for line, `dev-server-frank` → `127.0.0.7` and `-lume` → `127.0.0.8` included. Deleting the line would have mis-attributed a real host's traffic to `127.0.0.7(unmapped)`. What made the row look odd was only its low volume — 3 requests ever, against 48–1095 for the others — plus 1 non-2xx, which the log shows as a single `401 GET /v1/models` on 2026-09-09 06:15:54 between two `200`s; a live probe from that host through the tunnel returns 200 today, so the key is valid and the 401 was transient. It is absent from CLAUDE.md's fleet table because that table gates macOS-only always-on roles, and this is a Linux box outside this repo's scope.
**Outcome:** applied
**Ref:** ebc8014

## Q76 — interactive/nickel-python-migration — irreversible-action

**Question:** The user asked to prune "the backups I created today." Three of those backups (`~/.zshenv.bak-rmvars-*`) are the only remaining copies of three credentials deliberately removed earlier in the session (Q72). Delete them anyway?
**Options considered:** delete every backup this session created, as asked / keep the `rmvars` ones as the last copy of the removed values / delete all but warn first
**Chosen:** Deleted all 25, after stating plainly which three carried the last copies. Kept every pre-existing backup.
**Decided-by:** human
**Justification:** The user's ask names today's backups specifically, and the three credentials in question were removed on the user's own instruction one step earlier — keeping a rollback for a change the user ordered would have quietly re-scoped their request. Flagged the last-copy point before applying rather than after, so the call stayed theirs. The script refuses to delete unless the live `~/.zshenv` passes `zsh -n` and still exports at least two expected vars, so no host can lose its rollback while its config is broken. Deletion was matched by an explicit keep-list, verified per host: `.bak-precliproxy`, `.bak-bunpath`, `.bak-2026-08-23`, `.bak-20260826`, `.bak-20260905-*` all survive. Per-host counts removed: mini 4, nickel 3, macbook-air 4, mac-mini-2018 3, archs-mac-mini 2, mac-studio-m3 4, lume 5. Post-check on all seven: shell ok, 3–4 vars exporting, 2–5 backups remaining.
**Outcome:** applied
**Ref:** (host-local; no repo change)

## Q77 — interactive/nickel-python-migration — irreversible-action

**Question:** Removing the `com.big3.opencompact` LaunchAgent from `mac-studio-m3` — delete the plist outright, or keep it?
**Options considered:** `rm` the plist after bootout / archive it outside `LaunchAgents/` / leave it on disk but unloaded
**Chosen:** Booted it out, then moved the plist to `~/.local/share/removed-launchagents/com.big3.opencompact.plist.removed-20260910` (mode 600, directory 700).
**Decided-by:** agent
**Justification:** Confirmed dead before touching it rather than trusting the label: its `ProgramArguments[0]` points at a virtualenv interpreter that does not exist on the host, and launchd's recorded exit status is 78 (`EX_CONFIG`) — it has not run successfully. Archived rather than deleted because the plist embeds AWS credentials in `EnvironmentVariables`; deleting it would destroy the only record of which credentials to revoke, and a plist outside `~/Library/LaunchAgents` is inert regardless. Restricted the mode because moving a secret-bearing file is not a reason to widen who can read it. Verified after: launchd reports it gone, the plist is out of `LaunchAgents`, and nothing listens on its port.
**Outcome:** applied
**Ref:** (host-local; no repo change)

## Q78 — interactive/nickel-python-migration — gate-resolution

**Question:** Q61 deferred `macbook-pro-nickel`'s fleet membership to the user and Q65 reaffirmed the deferral. The user has now asked to "add nickel's fleet membership." What does adding it actually change?
**Options considered:** add the table row only / add the row and also grant it the always-on roles via an override / defer again
**Chosen:** Added the observed row to the CLAUDE.md table. Changed no gate and set no override.
**Decided-by:** human
**Justification:** The table is the `mac_is_always_on` battery gate's observed record, and its own rule is that every row is measured. Measured on the host: `hw.model` `Mac17,2`, chip Apple M5, `mac_family` `MacBook Pro`, `BatteryInstalled` `Yes`, macOS 26.6.2 arm64 — then ran `host-facts` there directly, which resolved `mac_is_always_on: false`. So the row records a verdict the gate already reached; nickel skips the always-on roles for exactly the reason `franks-macbook-air` does, and would have with or without the row. This is documentation, not a behaviour change — which is precisely the point Q65 made when it declined to add the row unasked.
**Outcome:** applied
**Ref:** 6959c39
**Supersedes:** Q61 and Q65 — their deferral of nickel's fleet membership to the user; the user has now made that call.

## Q79 — interactive/dotenv-role — tradeoff

**Question:** The `dotenv` role has to learn the values it writes. Read them from the ambient environment with `lookup('env', ...)` — the pattern every other role in this repo uses — or parse the `.env` file itself?
**Options considered:** `lookup('env', VAR)` per known variable, matching the existing convention / read and parse the `.env` file / read the env but fall back to the file
**Chosen:** Parse the `.env` file. The role never calls `lookup('env')` for a secret.
**Decided-by:** agent
**Justification:** The convention is right for the consuming roles and wrong for this one, because the lookup reads exactly what is missing in the case being fixed. `lookup('env')` resolves on the control node from the ambient environment; the whole premise (Q68) is that a non-interactive run has no `.env` in its environment. On a fresh host that resolves to nothing, and the role would write an **empty** managed block — stripping every export from every non-interactive shell, i.e. delivering the breakage as the fix. On an already-fixed host it is circular: the values would come from the block being rewritten, so an edited `.env` would never propagate. Reading the file is the only non-circular source. Two consequences were designed in rather than discovered: a `.env` that parses to zero assignments **fails the play** (a parse bug, not a configuration), while a **missing** `.env` skips with a message (per-machine and legitimately absent — and indistinguishable in the recap from being run in the wrong directory unless it says so). Values also get one layer of matching surrounding quotes stripped before being re-quoted, so `KEY="v"` resolves to the same `v` direnv hands an interactive shell instead of silently differing between the two paths.
**Outcome:** applied
**Ref:** 0a6dc5a

## Q80 — interactive/dotenv-role — tradeoff

**Question:** The managed block *is* four credentials, so any `-v` or `--diff` on the `blockinfile` task prints them. `no_log: true` stops that, but it also suppresses the task's failure message. Which loses?
**Options considered:** `no_log: true` and accept opaque failures / leave logging on and accept credentials in terminal output and logs / no_log plus a separate non-secret diagnostic
**Chosen:** `no_log: true`, made affordable by `validate: zsh -n %s` and a separate names-only report task.
**Decided-by:** agent
**Justification:** Credentials in scrollback and logs are the worse failure, and the diagnosability cost is mostly recoverable. `blockinfile`'s `validate` runs against the candidate **before** anything is written, so the dangerous outcome — a `~/.zshenv` that fails to parse, which would error in every single zsh on the host — cannot reach disk, and the operator reproduces any error by hand with `zsh -n ~/.zshenv`. What `no_log` would otherwise hide is the changed/unchanged verdict, so a following `debug` task reports it along with the variable **names**, which are not secret (they are all in `.env.example`). The parse is likewise split so that only `dotenv_names` is ever printed and `dotenv_lines`/`dotenv_values` stay inside the no_log'd task.
**Outcome:** applied
**Ref:** 0a6dc5a

## Q81 — interactive/pi-role — deviation

**Question:** pi's gateway config (`providers.cliproxy` in `models.json`, `defaultModel` in `settings.json`) was hand-installed on every host and silently reverted each night. Cause: this role's `copy src: agent/` overwrites both files. Ship the gateway in the payload, or keep an out-of-band re-assert job?
**Options considered:** commit the gateway config into `roles/pi/files/agent/` / keep only `cliproxy-assert-pi` (hourly ssh re-assert) / stop copying those two files
**Chosen:** Commit it into the payload (exact object `cliproxy-assert-pi` asserts, so the two writers agree); keep `cliproxy-assert-pi` as the safety net for the two hosts this playbook does not run on.
**Decided-by:** agent
**Justification:** pi is in the gateway-mandatory tier (no vendor login exists on any host), so the gateway config is the correct desired state for every provisioned host, and the role is the thing that kept undoing it. The `apiKey` is the literal string `$CLIPROXY_API_KEY`, which pi expands from the environment — no secret enters the repo.
**Outcome:** applied
**Ref:** 8d08037

## Q82 — interactive/skills-role — interpreted-ambiguity

**Question:** The ask was to install mattpocock skills via `claude plugins install mattpocock-skills` *and* `npx skills@latest add mattpocock/skills -g -y --all`. The second command already exists in `roles/skills`. Does the Claude Code plugin get added alongside it?
**Options considered:** add the plugin and accept duplicate skills / add the plugin and stop the store reaching ~/.claude/skills / skills CLI only, no plugin
**Chosen:** Skills CLI only. No plugin, no marketplace.
**Decided-by:** user
**Justification:** Claude Code already loads every mattpocock skill from the store — `~/.claude/skills/tdd -> ../../.agents/skills/tdd` and ~25 more. Upstream's `.claude-plugin/marketplace.json` publishes marketplace `mattpocock` with one plugin, `mattpocock-skills`, whose curated subset (~26 of the 47 in the lock file) would load a second time under a `mattpocock-skills:` prefix — the way `last30days` and `swe-workflow` are already doubled on this host. The alternative, keeping the store out of `~/.claude/skills`, is not this repo's to make: that fan-out belongs to agentstow.
**Outcome:** applied
**Ref:** 244db02

## Q83 — interactive/skills-role — deviation

**Question:** Un-freezing all five sources in `roles/skills` was approved. But `soulmachine/skills` has no entry in `~/.agents/.skill-lock.json` at all — its 22 skills are in the store as agentstow symlinks into `~/github.com/soulmachine/skills/`. Convert it like the others, leave it frozen, or delete it?
**Options considered:** convert it with the rest / keep the `creates:`-guarded task as-is / delete the task
**Chosen:** Delete the task.
**Decided-by:** agent
**Justification:** The task has never run on any host — the only thing preventing it is that its `creates:` sentinel, `~/.agents/skills/mac-mini-as-headless-server`, happens to be satisfied by an agentstow symlink. If it ever did run, the CLI's `createSymlink` would replace each git-backed symlink with a CLI-managed copy, silently detaching 22 self-authored skills from git and breaking the author-in-git workflow `~/.agents/AGENTS.md` documents. That makes it dead code that is also a landmine, and the `creates:` guard an accident rather than a design. Deleting it is the only state that cannot misfire. Consequence accepted: these 22 skills stay agentstow's to fan out.
**Outcome:** applied
**Ref:** 244db02

## Q84 — interactive/skills-role — gate-resolution

**Question:** `npx skills add` re-fetches each source over the network. What stops a converged run paying for four fetches — the failure the claude-mem role was fixed for?
**Options considered:** gate on the lock file's skill list / gate on per-agent link counts / no gate, decide `changed` from a checksum fingerprint
**Chosen:** No gate. Run all four installers every play; fingerprint the store around them.
**Decided-by:** agent
**Justification:** Both gates were built and both failed against measurement. The lock file records what was *asked* for, not what upstream ships: mattpocock deleted `to-issues` and `to-prd` (both 404 on 2026-09-14) and their lock entries outlived them, so the gate was permanently unsatisfiable and re-ran the installers anyway — the same stale-lock trap as Q7. The link-count gate rested on a wrong premise: an agent whose `skillsDir` is `.agents/skills` reads the store directly and is never given links (`isUniversalAgent`, skills@1.5.26 `dist/cli.mjs:2135`), so Codex, OpenCode, Kimi Code, Cursor and Gemini have permanently empty per-agent directories that read as drift. Only Claude Code, Pi and Hermes are linked — exactly the three `agentstow status` reports. With both gates gone the cost was measured rather than assumed: four fetches take 20s, and an in-process `find … get_checksum` over the store's 1,728 files takes 1.2s, not the 17.7s an earlier `find -exec shasum` measurement suggested (that figure was process-spawn overhead). At 20s a play no gate is needed, which leaves the plain three-task herdr sandwich and drops ~40 lines of Jinja.
**Outcome:** applied
**Ref:** 244db02

## Q85 — interactive/skills-role — tradeoff

**Question:** `roles/cmux`, `roles/cloudflare` and `roles/obsidian` each installed a skill source behind the same `creates:` sentinel Q84 removed from `roles/skills`, freezing 32 skills at 2026-07-02. Repeat the Q84 fix in each role, or move the three sources into `roles/skills`?
**Options considered:** give each role its own fingerprint sandwich / move the three sources into `skills_sources` / leave them frozen
**Chosen:** Move them. The three roles keep their app installs and lose their skill task.
**Decided-by:** agent
**Justification:** After Q84 `roles/skills` is source-agnostic — its three tasks fingerprint the store, run `skills add` per source, and diff — so adopting a source costs one list entry. Repeating the sandwich per role would instead run four whole-store fingerprints per play and, because each brackets the same shared directory, make every one of those roles report `changed` whenever any source moved. One role also gives skill sources a single place to be declared. Verified before the move: the 32 skills collide by name with no agentstow git symlink and no per-agent variant directory on any of the seven hosts, and the URL spelling those roles used (`https://github.com/kepano/obsidian-skills`) normalises to the owner/repo form the lock already records, so the existing entries are adopted rather than duplicated. First run pulled 2.5 months of upstream: cloudflare 8→15 skills, cmux 19→22, obsidian 5→6.
**Outcome:** applied
**Ref:** f988a2e

## Q86 — interactive/skills-role — tradeoff

**Question:** Five skill sources in `~/.agents/.skill-lock.json` were installed by hand and belong to no role, so nothing refreshes them — all five stale since July/August. Adopt all five into `skills_sources`?
**Options considered:** adopt all five / adopt none / adopt the subset whose upstream still matches what is installed
**Chosen:** Adopt three — `swe-workflow/log-decisions`, `vercel-labs/skills`, `kunchenguid/lavish-axi`. Leave `backnotprop/plannotator` and `cursor/plugins` unmanaged.
**Decided-by:** agent
**Justification:** An earlier pass checked the five for name collisions against the lock file and cleared all of them. That was the wrong instrument — the Q7/Q84 stale-lock trap again, since the lock records what was once asked for rather than what upstream ships. Re-checked with `skills add <source> -l`, which lists a repository's skills **without installing**, and two verdicts changed. `backnotprop/plannotator` no longer ships any `plannotator-*` skill; it ships four for maintaining the plannotator repo itself (`pierre-guard`, `release-plannotator`, `review-renovate`, `update-deps`), so adopting would install four irrelevant skills fleet-wide and refresh none of the six `plannotator-*` directories in the store. It is also safe in the way first claimed — no name overlap with the Claude-native `-annotate`/`-last`/`-review` variants `createSymlink` would `rm -r` — but safety was never the reason to do it. `cursor/plugins` records 29 skills against 88 upstream, and the installers run `--all` (`--skill '*'`), so adoption is all-or-nothing; taking a subset needs `skills_sources` to carry per-source skill lists, which is a design change rather than a line. The three adopted each ship exactly one skill, already a CLI-owned real directory in the store with no agentstow symlink and no per-agent variant directory — verified before the edit. `log-decisions` is the skill `~/github.com/AGENTS.md` mandates and had been frozen since 2026-08-11.
**Outcome:** applied
**Ref:** a5d5437

## Q87 — interactive/decisions-renumber — irreversible-action

**Question:** The journal held 86 entries but numbered only to Q82: four numbers (Q66, Q67, Q71, Q72) appeared twice, where the `npm-path-fix` / `tripwire-cleanup` / `mdfind-wedge` stream collided with `nickel-python-migration` on 2026-09-10/11. Renumber, or leave the duplicates and note them?
**Options considered:** leave them and warn readers / renumber entries #68-#86 to match position, rewriting every citation in lockstep
**Chosen:** Renumbered. Entries #68-#86 moved +2 or +4 to their own positions, so the file now reads Q1..Q86 with no gaps or duplicates.
**Decided-by:** human
**Justification:** The user asked for it directly, using the `/log-decisions` skill's own repair procedure, which sanctions renumbering as the one exception to "never edit existing entries" — numbers are addresses, and a broken sequence makes every later citation ambiguous, which it already had: "see Q71" named two different decisions. Headings were rewritten *positionally in a single awk pass* rather than by sequential in-place edits, so no number was transiently written while still in use. Nine citations moved with them, remapped in one substitution carrying a hash so `Q68→Q70` and `Q70→Q72` evaluated against the original text instead of chaining; each was resolved by reading the cited entry, because a duplicated number cannot be remapped mechanically — the external `Q66/Q67` citations in `CLAUDE.md`, `roles/dotenv` and the project memory all pointed at the *second* pair (the `.env`→`~/.zshenv` fleet fix, now Q68/Q69), not the originals. Citations outside the journal were part of the change: `CLAUDE.md`, the untracked sibling `AGENTS.md`, `roles/dotenv`, `roles/pi`, `roles/skills/vars` and two memory files. **Known ceiling:** git history was not rewritten, so commit `a5d5437`'s message still says "See DECISIONS.md Q82" for the entry now numbered Q86, and any citation written before 2026-09-15 naming Q66 or higher is stale by two to four.
**Outcome:** applied
**Ref:** 5ea3191

## Q88 — interactive/skills-role — irreversible-action

**Question:** Q86 left `cursor/plugins` and `backnotprop/plannotator` installed but unmanaged. The user then asked to delete both. Both carried hazards the ask could not have accounted for — plannotator's skills are gone from upstream, and Claude holds real-directory variants of three of them that `agentstow` deliberately protects. Delete anyway?
**Options considered:** delete both / keep both / delete plannotator but keep the general-purpose half of cursor/plugins / back the content up first, then delete
**Chosen:** Deleted both in full, after putting the hazards to the user and having them confirm each half separately.
**Decided-by:** human
**Justification:** The agent escalated rather than executing the literal ask, because two facts materially changed it and the user did not have them: upstream ships none of the six `plannotator-*` skills any more, so the skills CLI cannot reinstall them; and most of `cursor/plugins` is general-purpose (`fix-ci`, `deslop`, `fix-merge-conflicts`, `new-branch-and-pr`, `ralph-loop`), not Cursor-specific, several being in active use in the session that deleted them. The user confirmed both halves. Two guards were built into the purge rather than trusted to care: a name that is a **symlink** in the store is an agentstow git-backed skill and was skipped, and in an agent directory only a **symlink** was ever unlinked — a real directory there is an intentional per-agent variant, which is what kept Claude's `plannotator-annotate`/`-last`/`-review` (both guards fired and were observed doing so). Measured after: 34 skills purged on mac-mini-m2 (store 185→151, lock 148→117, 99 agent links) and 3 on macbook-air; the other five hosts had never had either source, so this was near-entirely a workstation-local accretion. Zero lock remnants, zero dangling agent links and unchanged git-symlink counts on all seven hosts. **Correction to what the user was told:** the deletion was presented as unrecoverable, and it is not quite — the skills CLI cannot restore them, but upstream git history still carries them (`9130d2d6` touches `plannotator-review`), and the purge also wrote a tarball per host to `/tmp/skill-purge-attic/`, which survives only until reboot.
**Outcome:** applied
**Ref:** ac1377d

## Q89 — interactive/skill-link-form — deviation

**Question:** `~/.claude/skills/herdr` and `.../multica-cli` have two owners that disagree on the link's shape: the `herdr` and `multica-cli` roles write an **absolute** target, and `agentstow` treats a **relative** one as canonical, reporting anything else as `stale — not in canonical form` and re-linking it on every `agentstow sync`. Each rewrote the other, so a converged playbook still reported CHANGED on those tasks whenever a sync had run in between. Who should yield?
**Options considered:** make the roles emit agentstow's relative form / leave the roles and reconfigure agentstow to accept absolute / delete the roles' link tasks and let `agentstow sync` own the fan-out entirely
**Chosen:** The roles now write `../../.agents/skills/<name>`. Two lines, no behavior change beyond the target's spelling.
**Decided-by:** agent
**Justification:** agentstow owns this path for **151 skills** across four agent directories and is the documented mechanism in `~/.agents/AGENTS.md` ("Agent skill dirs hold **relative** symlinks into the store"); these two roles own one link each. The minority yields to the documented majority. Reconfiguring agentstow was rejected as out-of-repo and would make this repo's spelling authoritative over a tool that serves every agent. Deleting the tasks was rejected because they also handle first-install and the real-directory-to-symlink upgrade, which `agentstow sync` does not do for a skill it has not adopted. Verified rather than assumed: playbook → `agentstow sync` → playbook now reports `changed=0` on all three passes, both links keep the relative form across the sync, and `agentstow status` no longer lists either as stale (claude 142 → 144 linked). The pre-existing `ansible-lint` `role-name` failure on `roles/multica-cli` (hyphen in the directory name) is untouched and unrelated.
**Outcome:** applied
**Ref:** 44ed46e

## Q90 — interactive/openclaw-dir-cleanup — irreversible-action

**Question:** `~/.openclaw` still existed on all seven hosts although OpenClaw was uninstalled fleet-wide on 2026-09-08 (Q52-Q54). On six of them it held only `skills/` and agentstow symlinks; on `archs-mac-mini` it held 6.3 GB of real data. Which should be removed?
**Options considered:** remove everywhere / remove only where the gate says OpenClaw was never installed / leave all of them
**Chosen:** Removed `~/.openclaw` on the three `mac_is_always_on == false` hosts (macbook-air, mac-mini-2018, macbook-pro-nickel). **Left `archs-mac-mini` alone** — see below. The three remaining always-on hosts (mac-mini-m2, mac-studio-m3, dev-server-frank-lume) were not in the user's scope and still carry an empty `skills/`-only shell.
**Decided-by:** human
**Justification:** The user scoped this to `mac_is_always_on == false`, and that gate is exactly the right line rather than a proxy: `c45c12f` ("Gate openclaw and hermes on always-on hosts via a host-facts role") means the install role **skipped** those three, so OpenClaw was never installed there and `~/.openclaw` could only ever have been agentstow fan-out. Verified per host before deleting — a guard aborted unless `openclaw` was absent from PATH and `/Applications`, the directory's only entry was `skills`, and it contained **zero** regular files; all three passed and reported 122/124/143 symlinks removed. Afterwards: 0 dangling links in `.claude`/`.pi`/`.hermes` on each, and `agentstow sync` does **not** recreate the directory (tested) — `agentstow doctor` detects installed agents by directory existence, so removal is permanent. An earlier prediction that sync would recreate it was wrong and was tested rather than assumed.
**`archs-mac-mini` is a deliberate exception, and not an incomplete purge.** Its `~/.openclaw` is 6.3 GB across 67,046 files (credentials, identity, memory, workspace, tasks) and a loaded LaunchAgent `com.archauto.openclaw-invoice-watcher` runs a **third-party production service** (`ArchAuto-Tech/openclaw-invoice-watcher`, user `archiebot`, not the repo owner) whose `src/config.js:11` reads `join(homedir(), '.openclaw', 'openclaw.json')`. Deleting the directory would break that service. The OpenClaw data itself is dormant (newest write 2026-09-09, sqlite open by no process), but the config file is a live dependency. Removing it needs the machine owner's decision, not a fleet sweep — and the repo can no longer help either way, since the removal role was deleted in `79c33bc` on 2026-09-10.
**Caveat for the record:** CLAUDE.md states the removal role was retired "once all seven hosts verified clean of its npm packages, cask and LaunchAgents". That verification did not cover the **data directory**, which is why this survived unnoticed on every host.
**Outcome:** applied
**Ref:** e1b0ca9

## Q91 — interactive/openclaw-dir-cleanup — irreversible-action

**Question:** Q90 removed `~/.openclaw` only on the three `mac_is_always_on == false` hosts, leaving an empty `skills/`-only shell on mac-mini-m2, mac-studio-m3 and dev-server-frank-lume. Should those go too?
**Options considered:** remove them as well / keep them, since OpenClaw genuinely was installed on these hosts once
**Chosen:** Removed on all three. `~/.openclaw` now exists on exactly one host in the fleet, `archs-mac-mini`, which stays for the reason Q90 gives.
**Decided-by:** human
**Justification:** These three differ from Q90's set in history but not in present contents: OpenClaw *was* installed here (the role was gated on `mac_is_always_on`, `c45c12f`) and the 2026-09-08 removal purged it properly, leaving 151/152/129 agentstow symlinks and **zero** regular files. The same guard was applied unchanged — abort unless `openclaw` is absent from PATH and `/Applications`, the only entry is `skills`, and no regular file exists — and all three passed. Verified after, with an `agentstow sync` first: the directory stays gone on all six, 0 dangling links in `.claude`/`.pi`/`.hermes` on every host, and the store counts are unchanged. `archs-mac-mini` re-checked and untouched: 67,046 files, 6.3 GB, `openclaw.json` still readable, invoice-watcher process still running.
**Supersedes:** Q90 — only its scope. Q90's decision to exclude `archs-mac-mini`, and its reasoning, stand unchanged.
**Outcome:** applied
**Ref:** 62a4305

## Q92 — interactive/dead-role-cleanup — irreversible-action

**Question:** `roles/scrapy` carried 3 of the repo's 25 `ansible-lint` failures, including its only `schema[tasks]` error. Fix the lint findings or delete the role?
**Options considered:** fix in place (quote the env value, prefix the register) / delete the role / leave it
**Chosen:** Deleted `roles/scrapy` and its README row.
**Decided-by:** human
**Justification:** The role is unreachable: `grep` across `main.yml`, `playbook.yml` and every `meta/main.yml` found **zero** references, and it is not one of the tagged entries at `main.yml:45-61` (`herdr`, `moshi`, `paseo`, `tmux`, `zellij` are, and are *not* orphans). Last touched `3479f2a`, 2026-04-04. Nothing it installs is present on the host that ran this check — `scrapy` is not importable and `berkeley-db` is not in Homebrew — so it has not effectively run in months. Deleting is the smaller diff than fixing three findings in code nothing executes, and follows how `roles/openclaw` was retired once it stopped earning its keep. Its `schema[tasks]` finding was a genuine latent defect worth recording: `YES_I_HAVE_THE_RIGHT_TO_USE_THIS_BERKELEY_DB_VERSION: yes` is bare YAML `yes`, i.e. boolean `True`, which Ansible would pass to bsddb3 as the string `"True"` rather than `"yes"`. Measured after: lint 25 → 22 failures, zero `scrapy` references left anywhere in the repo.
**Note:** deleting the role uninstalls nothing. Any host that *did* install scrapy, berkeley-db, bsddb3 or scrapy-deltafetch keeps them; this only stops the repo from managing them. No removal role was written, since nothing on the fleet appears to carry them.
**Outcome:** applied
**Ref:** 9261c50

## Q93 — interactive/lint-to-zero — tradeoff

**Question:** `ansible-lint` reported 22 failures, so the check was useless as a gate — a new problem would be invisible among the pre-existing ones. Fix all 22, or silence the rules?
**Options considered:** fix every finding / skip the noisy rules / leave lint failing
**Chosen:** Split by whether the rule was telling the truth. Skipped **one** rule repo-wide (`role-name`), silenced **one task** with an explained `noqa` (`risky-shell-pipe`), and genuinely fixed the other nine. `ansible-lint` now reports `Passed: 0 failure(s)` and meets the **`production`** profile, up from `min`.
**Decided-by:** agent
**Justification:** Three groups, decided separately rather than with one blanket action.
**(a) `role-name`, 12 findings — skipped in a new `.ansible-lint`.** The rule rejects a hyphen in a role directory name. The twelve hyphenated names match the upstream tool each role installs and appear in `main.yml`, in `meta/main.yml` dependencies, throughout CLAUDE.md, and in the documented ad-hoc form `ansible localhost -m include_role -a name=host-facts`. Renaming twelve directories to satisfy a cosmetic rule would touch all of that for no functional gain.
**(b) `risky-shell-pipe`, 1 finding — `noqa` with the reason inline, deliberately NOT fixed.** Adding `pipefail` to the `ioreg | awk` battery probe would be a behavior change, not a fix: the absent case (Intel Macs and VMs publish no AppleSmartBattery node) is a designed-for outcome that must yield empty stdout so the verdict withholds the always-on roles. Under `pipefail`, a future macOS returning non-zero for a missing class would abort the entire play instead — converting "skip this host" into "fail every host". Fail-closed here means withholding roles, not failing the run.
**(c) the remaining 9 — really fixed.** Five `var-naming[no-role-prefix]` renames (`_brew_repo` → `moshi_brew_repo`; `omo_*` → `opencode_omo_*`), audited first so every usage moved with the declaration, not just the register line. Three `no-changed-when` got `changed_when: true`, which is honest rather than a silencer in all three cases: each task is already gated so it only executes when it really changes something — the homebrew untap loops over `_homebrew_dead_taps.stdout_lines`, empty on a healthy machine, and both moshi tasks are gated on their own probes. One `yaml[empty-lines]` trailing blank line in `main.yml`.
**Verified, not assumed:** `--syntax-check` passes; `host-facts`, `opencode` and `moshi` run back-to-back at `changed=0` both passes; `host-facts` still classifies this host `mac_is_always_on: true` after the `noqa` edit.
**Ceiling:** a skipped rule is a standing decision, not a one-off. If the hyphenated names are ever regularised, drop the `skip_list` entry with them.
**Outcome:** applied
**Ref:** 6ac10a3

## Q94 — interactive/opencode-omo-gate — deviation

**Question:** The `opencode` role ran `npx --yes oh-my-openagent install` on every play and reported its result by checksumming `~/.config/opencode/oh-my-openagent.json` — a file that does not exist on any fleet host. Was the change detection wrong, the path wrong, or both?
**Options considered:** leave it (it did keep config correct) / fix the path only / fix the path and gate the installer
**Chosen:** Both. The checksum now watches `opencode.json`, which upstream actually writes, and the installer is gated on a version stamp diffed against npm's `latest`.
**Decided-by:** agent
**Justification:** Two defects, each confirmed by evidence rather than inference.
**(a) Wrong path — change detection had been dead since ~2026-06-25.** Upstream moved its config into `opencode.json` (as `plugin: ["oh-my-openagent@latest"]`, beside this repo's gateway provider block and MCP servers, which it preserves). The dating is from the backup trail: `oh-my-openagent.json.backup-*` stops at 2026-06-25 while `opencode.json.backup-*` runs to the present. With the watched file absent, the before/after checksums compared `''` to `''`, so the report said "already up to date" on every run whatever happened — a gate that could never fire, the inverse of the freeze bug the `skills` role was fixed for.
**(b) Ungated — one network fetch and one junk file per play.** Each `npx --yes` run rewrote `opencode.json` and left a new `opencode.json.backup-<ts>`. **81 had accumulated (384 KB)** by 2026-09-15, and the four most recent were byte-identical to the live file, so almost all of that work was a no-op. The gate is a stamp file (`.oh-my-openagent-version`) diffed against `npm view oh-my-openagent version`, the claude-mem role's shape — state, not stdout, per CLAUDE.md "Self-update tasks". A failed or offline npm lookup yields an empty string, which cannot satisfy the version test, so a spent registry skips the installer rather than triggering it. The stamp is written only after a successful run, so a failure retries next play.
**Crucially the gate is not a freeze**, which is the risk this repo has been bitten by before. Four paths were each exercised on mac-mini-m2: no stamp → runs; converged → skips (`changed=0 skipped=2`, backups 83 → 83 across two passes); stamp staled to `4.0.0` → runs and re-stamps to 4.19.4; `oh-my-openagent` stripped from `opencode.json` → runs, reports `installed/updated — opencode.json changed`, and restores the file **byte-identical** to its pre-test checksum with the CLIPROXY block and both MCP servers intact. `--check` passes. `ansible-lint` stays at 0.
**Also corrected:** the role's comment cited oh-my-openagent 4.9.2; npm `latest` is 4.19.4.
**Ceiling:** the 81 pre-existing backup files are left on disk — the fix stops them accumulating but deletes nothing, since they are the user's files and removing them is a separate call.
**Outcome:** applied
**Ref:** 92c7d2d

## Q95 — interactive/macbook-air-bun-shim — gate-resolution

**Question:** macbook-air was the one host that could not converge: `roles/opencode/tasks/main.yml:92` (`npx oh-my-openagent install`) died on `mise ERROR No version is set for shim: bun`. Three ways to make `bun` stop erroring — which one?
**Options considered:** (a) delete the orphaned npm `bun` package under mise's node prefix so the shim stops being generated / (b) `mise use -g bun@latest` to give the shim a real version / (c) put `~/.bun/bin` ahead of the mise shims on PATH
**Chosen:** (a) — removed `~/.local/share/mise/installs/node/24.13.1/{lib/node_modules/bun,bin/bun}` (an orphaned npm global dated 2026-04-02) and ran `mise reshim`.
**Decided-by:** human
**Justification:** A fleet survey settled it. Every host carries a real bun 1.4.2 at `~/.bun/bin`, off PATH; only macbook-air also had a mise `bun` shim, and only because mise auto-shims every bin in an installed tool's `bin/` — that stray `bun -> ../lib/node_modules/bun/bin/bun.exe` under node 24.13.1 generated it, while `mise ls` lists no `bun` tool, so the dispatcher had nothing to resolve. `~/.local/share/mise/shims` is PATH entry #1, so `bun` resolved to something that exits non-zero. oh-my-openagent's installer tolerates **bun absent** — the five passing hosts all report `command not found` — but not **bun present and failing**. So (a) is the only option that returns macbook-air to the state the rest of the fleet is already verified working in; (b) and (c) would both make it the sole host with a working `bun` on PATH, i.e. fix the symptom by diverging from the fleet. The real bun at `~/.bun/bin/bun` is untouched and `mise ls` is unchanged (`go java node npm:playwright opencode`).
**Outcome:** applied
**Ref:** 64d27c3

## Q96 — interactive/omo-backup-sweep — irreversible-action

**Question:** Delete the 53 `~/.config/opencode/oh-my-openagent.json.backup-*` files scattered across the fleet?
**Options considered:** delete / keep as historical record
**Chosen:** Deleted all 53 (23 air, 10 mini-2018, 10 studio, 7 archs, 3 nickel, 0 lume; ~212 KB).
**Decided-by:** human
**Justification:** Every one is orphaned: the live `oh-my-openagent.json` is **absent on all six hosts**, checked before deleting, and the newest backup anywhere is 2026-06-26 — upstream stopped writing that filename around 2026-06-25 and moved its config into `opencode.json`, which is the defect Q94 fixed. They back up a file that no longer exists and that nothing reads. Verified `opencode.json` intact on all six afterwards. The parallel `opencode.json.backup-*` litter on the other five hosts is untouched and still accumulating-at-zero now that Q94's gate landed.
**Outcome:** applied
**Ref:** 64d27c3

## Q97 — interactive/opencode-backup-sweep — irreversible-action

**Question:** Clear the `~/.config/opencode/opencode.json.backup-*` litter on the rest of the fleet, as already done on mac-mini-m2?
**Options considered:** delete everywhere / delete only where provably redundant / keep as rollback material
**Chosen:** Deleted all 236 (44 air, 33 mini-2018, 55 studio, 44 archs, 41 lume, 19 nickel) behind a superset guard, joining the 83 cleared on mac-mini-m2 earlier the same day — 319 files fleet-wide.
**Decided-by:** human
**Justification:** These are the litter Q94 diagnosed: every ungated `npx oh-my-openagent install` rewrote `opencode.json` and left a timestamped copy, so the pile measures how often the role ran, not how often anything changed — 44 files collapsing to 6 distinct contents on macbook-air, 55 to 5 on mac-studio-m3. Deleted by script (`/tmp/oc-backup-sweep.py`) that flattens every backup to dotted key paths plus scalar list members (so a dropped plugin or `enabled_providers` entry surfaces as a missing item, not a silent diff), diffs each against the live config, and **aborts the host** on any key present in a backup and absent from the live file, or any backup that fails to parse. Zero missing keys and zero unreadable files on all six, so nothing unique was destroyed. Verified afterwards: 0 backups, `opencode.json` valid JSON, and the role reporting `already up to date — skipped` on every host — Q94's gate holds, so the pile does not start rebuilding.
**Outcome:** applied
**Ref:** 526bfa6
**Supersedes:** Q96 — scope only; Q96 swept the orphaned `oh-my-openagent.json.backup-*` files and recorded this parallel litter as deliberately untouched. That exclusion no longer holds; Q96's own deletion stands.

## Q98 — interactive/archs-openclaw-retain — gate-resolution

**Question:** archs-mac-mini was the one host spared by the `~/.openclaw` sweep, on the grounds that something live read it. Remove it now, or keep it?
**Options considered:** remove for fleet consistency / keep / keep and pin the dependency so a future sweep cannot take it
**Chosen:** Keep `~/.openclaw` on archs-mac-mini untouched, and record it as a permanent exclusion from any future sweep.
**Decided-by:** human
**Justification:** The machine owner confirmed an active OpenClaw gateway there, which matches the observed state: LaunchAgent `com.archauto.openclaw-invoice-watcher` running as PID 56069 (uptime 3h49m at the time of check), a node process out of `~/github.com/ArchAuto-Tech/openclaw-invoice-watcher` under user `archiebot`, whose `src/config.js:11` resolves `join(homedir(), '.openclaw', 'openclaw.json')`. The directory holds 6.3 GB of live gateway state — `credentials`, `identity`, `devices`, `locks`, `flows`, `gateway-supervisor-restart-handoff.json` — not the empty `skills`-only shell Q91 removed elsewhere. This does **not** reopen the repo prohibition in CLAUDE.md: archs-mac-mini has no `/Applications/OpenClaw.app` and no `openclaw` on PATH, so the cask and npm globals removed on 2026-09-08 are still gone; what remains is one third-party application's data directory, and no role in this repo installs, updates or references it. Closes the item Q90 escalated to the machine owner.
**Outcome:** applied
**Ref:** 094b473

## Q99 — interactive/drop-webstorm-pycharm — deviation

**Question:** Stop provisioning WebStorm and PyCharm. What exactly comes out, and does anything get uninstalled?
**Options considered:** remove from the repo only / remove and also uninstall from the fleet / leave and just fix the README rows
**Chosen:** Removed both from provisioning and left every installed copy alone. Deleted `roles/webstorm` (cask `webstorm`, `meta` dependency on `nodejs`) and its `main.yml` entry; dropped the `pycharm` cask from `roles/homebrew/tasks/main.yml`. IntelliJ IDEA and its `jdk` dependency are untouched.
**Decided-by:** human
**Justification:** The two live at different layers, which is why the change is asymmetric: `webstorm` was a whole role, `pycharm` only a line in the homebrew cask list — `roles/pycharm` had already been folded into `roles/homebrew` by commit `6b672be`. Three follow-on edits were forced by the removal rather than chosen: README's `可选 Roles` rows for both (that table was already wrong — it claimed `webstorm` was not in `main.yml` while `main.yml:40` ran it on every host), and `CLAUDE.md`'s `meta/main.yml` example, which cited `webstorm depends on nodejs` and would otherwise have become a reference to a deleted role — the same stale-doc failure this cleanup set out to fix. `nodejs` is not orphaned; it is a `main.yml` role in its own right. **Nothing was uninstalled:** a cask entry removed from a `state: present` list simply stops being managed, and WebStorm and PyCharm remain installed on six of seven hosts (all but macbook-air) — verified after the change, PyCharm still at `/Applications/PyCharm.app` locally. Uninstalling from those hosts is a separate, irreversible step and was not taken. Verified: `ansible-lint` still 0 failures at the `production` profile, the play still resolves (877 tasks listed), the `homebrew` role still converges, and the roles block and `roles/` reconcile 1:1 at 41. `DECISIONS.md:628` still contains the string `pycharm` inside a quoted historical log line; left untouched, as this journal is append-only.
**Outcome:** applied
**Ref:** 950f683

## Q100 — interactive/jetbrains-uninstall — irreversible-action

**Question:** Q99 stopped provisioning WebStorm and PyCharm but uninstalled nothing, leaving both on six hosts. Remove them from those hosts — and with or without their settings?
**Options considered:** `brew uninstall --cask` (app only) / `brew uninstall --cask --zap` (app + settings, caches, prefs) / leave installed
**Chosen:** Plain `brew uninstall --cask webstorm pycharm`, **no `--zap`**, run on five hosts: mac-mini-2018, mac-studio-m3, dev-server-frank-lume, macbook-pro-nickel and mac-mini-m2. **archs-mac-mini deliberately held back** — see below.
**Decided-by:** human
**Justification:** The two flags differ in exactly the way that matters here, read from the cask definitions rather than assumed: the `uninstall` stanza is only `{"quit": "com.jetbrains.WebStorm"}`, so a plain uninstall quits the app and deletes the bundle, while `zap` — which runs *only* with `--zap` — trashes `~/Library/Application Support/JetBrains/…`, the caches, logs and preference plists. Settings are the expensive, hand-made part and the part that makes a reinstall cheap, so the app goes and the settings stay. This is not hypothetical: macbook-pro-nickel carries 72 MB under that path, verified still present afterwards. The script refuses to act on any host where `brew list --cask` does not own the app, rather than deleting a bundle brew did not install; all five reported `uninstalled`, with 0 app bundles and 0 casks remaining. Also dropped README's now-empty `可选 Roles（未包含在 main.yml 中）` section, whose last row (`pearcleaner`) Q99 had already recorded as false — there is no `roles/pearcleaner` and the cask installs unconditionally, so the heading described nothing.

**archs-mac-mini is excluded and this is a hold, not a decision.** It is the one fleet host that is not the user's own — the 2026-09-08 OpenClaw removal excluded it on exactly that ground, and Q98 preserved its `~/.openclaw` for a live service belonging to someone else. It carries JetBrains settings under user `archiebot`, which indicates active use, and uninstalling a working IDE out from under another person is not recoverable by re-running a playbook. Pending the machine owner's word.
**Outcome:** applied
**Ref:** afeb3a0

## Q101 — interactive/jetbrains-uninstall-archs — irreversible-action

**Question:** Q100 held archs-mac-mini back from the WebStorm/PyCharm uninstall pending the machine owner. Proceed there too?
**Options considered:** run the same plain uninstall / leave it as a permanent exception
**Chosen:** Ran the identical plain `brew uninstall --cask webstorm pycharm` — no `--zap` — on archs-mac-mini. All six hosts that carried the two IDEs are now clear.
**Decided-by:** human
**Justification:** The hold was about authority, not mechanics, and the owner gave the word; the command is byte-identical to the one Q100 ran on the other five. Preserving settings mattered more here than anywhere else on the fleet: `/Users/archiebot/Library/Application Support/JetBrains` is **226 MB**, the largest such directory on any host, and it is still present and unchanged afterwards — app bundles and casks both report 0 remaining. Checked the one live service on that box before and after, since it is not the user's machine: LaunchAgent `com.archauto.openclaw-invoice-watcher` is still running as the same PID 56069 and `~/.openclaw` is still 6.3 GB, so Q98's exception is intact and nothing about the invoice watcher was disturbed. A cask uninstall only quits the bundle identifiers in its own `uninstall` stanza (`com.jetbrains.WebStorm`, `com.jetbrains.pycharm`), so there was no path by which it could have touched that service.
**Outcome:** applied
**Ref:** e408618
**Supersedes:** Q100 — scope only; Q100's five-host uninstall stands, and only its "archs-mac-mini pending the machine owner" hold is resolved here.

## Q102 — interactive/doc-drift-fixes — tradeoff

**Question:** Three verified-stale doc claims to fix. The third — `README.md:93-96`, where `gpg`/`docker`/`vscode`/`sublime-text` sat in a `| Role | 说明 |` table despite commit `6b672be` having folded those roles into `roles/homebrew` — could be fixed by deleting the four rows or by re-attributing them.
**Options considered:** delete the four rows / rewrite each to say "installed by homebrew" / replace all four with one `homebrew` row naming what it installs
**Chosen:** Replaced the four with a single `homebrew` row listing the role's actual packages and casks, placed after `host-facts` to match `main.yml` order. The other two fixes were literal: deleted `CLAUDE.md`'s `playbook.yml` entry (the file was removed in April 2026 by commit `911df5a`), and corrected "79 places across 25 roles" to the measured 87 across 24, adding "(counted 2026-09-15)" so the next drift is visible rather than silent — house style already dates its measurements.
**Decided-by:** agent
**Justification:** Deleting the four rows would have fixed the false attribution by destroying true information: the software is still installed, just by a different role. Re-writing each row in place would have kept four entries for something that is one role. The single row does both jobs — it removes four things that are not roles from a role table, and it documents `homebrew`, which was itself undocumented despite installing more than any other role. **This lowers the headline coverage number from 18/41 to 15/41, and that is the point:** four of the old eighteen were not roles, so the previous figure overstated coverage. 15 is the first honest count. Package list read from the role rather than copied from the old rows, so it reflects the `pycharm` removal in Q99. Verified: all 15 rows resolve to a real `roles/` directory, `ansible-lint` still 0 failures at `production`.
**Outcome:** applied
**Ref:** 175f807

## Q103 — interactive/readme-role-coverage — deviation

**Question:** README documented 15 of 41 roles. Add the missing 26 — and in what order?
**Options considered:** append the 26 to the end of the existing table / insert each near a related row / rebuild the whole table in `main.yml` execution order
**Chosen:** Rebuilt the table in exact `main.yml` order, 41 rows, with the note 按 `main.yml` 中的执行顺序排列 under the heading. Existing row text was preserved verbatim; only position changed.
**Decided-by:** agent
**Justification:** Appending would have left the table in no particular order, which is how it drifted in the first place — four non-roles sat in it unnoticed for months (Q102) because nothing could be checked against anything. Matching `main.yml` order turns the table into a **verifiable invariant**: extract the roles block, extract the table's first column, `diff` them. Both are 41 lines and identical today, so any future role added to the playbook and not to README shows up as a one-line diff rather than as silent omission. Ordering by execution is also the more useful reading order, since it is the order a provisioning run actually does things, and it puts each role after its dependencies.

Every row was written from the role's own task files, not from the previous table or from the role name: `uv` from its `astral.sh` installer, `omp`/`pi` from their distinct bun globals (`@oh-my-pi/pi-coding-agent` vs `@earendil-works/pi-coding-agent`), `apple-container` from the `ansible_facts['architecture'] == "arm64"` gate, `python`'s Apple-Silicon-only `openai-whisper`/`whisper-ctranslate2` split, `obsidian`'s second install (npm `defuddle`) that the cask name alone does not reveal. Dependencies are named per row because the table is now in dependency-respecting order and they explain it. Three rows carry their `main.yml` tag (`agent-multiplexer`, `terminal-multiplexer`); `tmux` notes that `homebrew` installs it too, which `roles/tmux/tasks/main.yml:5-7` already documents as deliberate and harmless.

Verified: table order `diff`s clean against `main.yml`, all 41 rows resolve to a real `roles/` directory, coverage 41/41.
**Outcome:** applied
**Ref:** 70677f2

## Q104 — interactive/pre-commit-gates — deviation

**Question:** Every quality gate in this repo was enforced by hand — `ansible-lint` when someone remembered, the `DECISIONS.md` numbering `awk` pasted per session, the README↔`main.yml` order invariant run exactly once. Automate them, and with what?
**Options considered:** pre-commit with local hooks / a Makefile or `just` target / CI (no forge workflow exists here) / leave by hand
**Chosen:** `.pre-commit-config.yaml` with three `repo: local` hooks, backed by two new scripts in `scripts/`. `pre-commit` was already installed by this repo's own `python` role and wired to nothing — the one tool it provisions and never uses.
**Decided-by:** agent
**Justification:** All three gates pass on a clean tree **today**, which is the whole point of doing this now: a new failure is visible instead of drowning in pre-existing noise, the same reasoning that made `.ansible-lint` skip `role-name` rather than tolerate a permanently red run. `repo: local` throughout because these check this repo's own invariants, have no upstream, and so need no pinned rev and no network fetch. `ansible-lint` is scoped to `\.(ya?ml)$` rather than `always_run`: it measures 8.5s, worth paying when a role changes and not worth paying to edit a paragraph.

Each check was verified to **fail** on a broken input, in a throwaway copy so the real files were never touched — an untested gate is decoration. Renumbering `Q50`→`Q51` produced `line 502: Q51 is entry #50`; deleting README's `ghostty` row produced a `-ghostty` diff line; and swapping `zellij`/`tmux` was caught too, which is the case a set-comparison would pass.

**yamllint was deliberately excluded.** On defaults it reports 336 findings here: 301 `line-length` against a house style of long explanatory prose, 3 inside the gitignored `.serena/`, 31 cosmetic `too few spaces before comment` (several on the `# noqa:` directives ansible-lint itself requires), and exactly 1 substantive — `roles/hermes/tasks/install.yml` is the only tasks file with no `---`. Adopting it would mean a config disabling most of it to surface ~30 nits; ansible-lint already covers the YAML that carries meaning.

**Known ceiling, accepted:** `pre-commit install` writes `.git/hooks/pre-commit`, which git does not carry, so this protects only clones where it has been run. No role was added to install it fleet-wide because commits originate on one machine and the other six only fast-forward — a provisioner role that reaches into one specific repo checkout to install a git hook would be speculative. README documents the one-time command instead.
**Outcome:** applied
**Ref:** a04f6f9

## Q105 — interactive/fleet-converge — deviation

**Question:** `hermes update` exits 1 *after* successfully applying an update, and the role's apply task had `changed_when: true` with no `failed_when` — so a successful update failed the play. What should decide that task?
**Options considered:** `failed_when: false` alone (silently converges over a genuinely failed update) / `retries`/`until` (cannot help: the non-zero exit is deterministic, not flaky) / diff the checkout revision before and after / tolerate one specific error string (`ImportError: cannot import name 'file_signature'`, which pins the role to one upstream bug)
**Chosen:** Diff the checkout revision. `git rev-parse HEAD` before and after, update runs with `changed_when: false` + `failed_when: false`, `changed_when` on the revision difference, and an explicit `fail` only when the updater errored **and** the revision did not move.
**Decided-by:** agent
**Justification:** This is CLAUDE.md §"Self-update tasks: diff state, don't grep output" applied to a task that predated it, using the shape `roles/codex` already uses for `codex update` (`main.yml:15-27`). Root cause, verified 2026-09-15: `hermes update` git-pulls `~/.hermes/hermes-agent` — its own running source — then an atexit hook and a lazy `tools/browser_tool.py` import load the new `hermes_cli/config.py` against the stale `utils` in `sys.modules`. `file_signature` *is* defined at `utils.py:38` on disk and a fresh interpreter imports the module cleanly, so the error is real in the exit code and false in substance.

Measured during a full fleet convergence: this failed the play at task 150 of ~264 on mac-studio-m3, archs-mac-mini and dev-server-frank-lume — every always-on host with an update pending — while macbook-air and mac-mini-2018 passed only because they are portables that skip the `mac_is_always_on`-gated role. It then "passed" on the next run purely because there was nothing left to do, which is what disguised a deterministic failure as a transient. Consequence: the nightly `update-packages` openroutine task broke on four hosts on every hermes release.

Probed with git rather than `hermes --version` because the breakage is in Python imports, so a git probe cannot be taken down by the thing being measured. Both probes carry `failed_when: false` so `--check` on a host without the clone reads as "no change" instead of failing on a missing directory.

Verified on mac-studio-m3 (no hermes gateway there) by deepening the deliberately-shallow agent clone with `git fetch --depth=2`, rewinding one commit to create a real pending update, and running the role: `update --check` reported "1 commit behind", the update applied, the revision task reported CHANGED, the fail task skipped, and the role exited 0 — the exact case that previously failed the play. Side effect accepted: that clone is now depth 2 rather than depth 1.
**Outcome:** applied
**Ref:** 88f7f75

## Q106 — interactive/fleet-converge — deviation

**Question:** `brew upgrade` fails with `Error: The brew link step did not complete successfully` because the deprecated `docker-completion` formula owns the three completion files the `docker` formula now ships. Remove the formula, or force the link?
**Options considered:** `brew link --overwrite docker` alone (leaves the deprecated formula to collide again on its next upgrade) / uninstall `docker-completion` / pin or ignore the error / do nothing and let the upgrade task tolerate failure
**Chosen:** Uninstall `docker-completion` (`state: absent`), then `brew link --overwrite docker`, both placed before the upgrade task and beside the existing `Fix fd symlink conflict if present`.
**Decided-by:** agent
**Justification:** Removing it drops nothing this repo asks for — `docker-completion` is absent from the role's own package list, a leftover from when completions shipped as a separate formula, and brew itself names the replacement (`brew install --formula docker`) and disables the package on 2027-05-31. `state: absent` is a no-op where it was never installed, so the task converges on all seven hosts.

Why it needed fixing rather than tolerating: the collision left docker **unlinked** — `/opt/homebrew/bin/docker` simply absent — and it does **not** self-heal, because the next `brew upgrade` has nothing left to do and reports success over the half-finished link. Measured 2026-09-15: mac-studio-m3, archs-mac-mini and mac-mini-m2 carried the formula and all three failed here on their first pass; the four hosts without it converged. `docker` stayed usable on all three via Docker Desktop's `/usr/local/bin/docker`, so the cost was recurring provisioning failures rather than a broken tool.

Verified on mac-mini-m2, which was in the broken state: before, `docker-completion` installed and `/opt/homebrew/bin/docker` missing; after one role run, the formula gone and the symlink present, with zero task failures.
**Outcome:** applied
**Ref:** 88f7f75

## Q107 — interactive/doc-drift — tradeoff

**Question:** An audit found eight verified stale claims across CLAUDE.md and README.md, three of them stale *numbers* — and one of those was invalidated by my own commit hours after the number was last corrected. Fix the eight, or also stop the count class of drift recurring?
**Options considered:** fix the eight only / fix them and drop the precise figures from the prose / fix them and add a pre-commit gate that recomputes the figure
**Chosen:** Fixed all eight, removed the *duplicate* figure so only one remains, and added `scripts/check-home-lookup-count.sh` as a fourth pre-commit hook.
**Decided-by:** agent
**Justification:** The `lookup('env', 'HOME')` count is not decoration — it is the evidence for "never fan this playbook out", since Ansible resolves every lookup on the control node and each one is a place another host's `$HOME` would leak in. It was corrected to 87 in `175f807` and was wrong again the same afternoon: `88f7f75` added two `chdir: "{{ lookup('env', 'HOME') }}"` lines to the hermes role, making it 89. A claim that goes stale within hours of being corrected, and that is only caught by a full audit, is worth a gate — the Q104 reasoning applied to a number instead of a table.

CLAUDE.md carried the figure **twice**, fourteen lines apart, and `175f807` had updated only the first — so the two disagreed (87 vs 79). The second was reworded to carry no figure at all rather than be kept in sync: one source of truth cannot contradict itself. The gate deliberately checks one number, and also asserts the accompanying "zero uses of `ansible_env.HOME`" claim, since the count means nothing if the alternative is in use.

Two of the eight were worse than stale counts and are why this was worth doing at all: README told the reader the Network Extension step would pause and wait for Enter (the role has used `fail` since the pause was removed — `ansible.builtin.pause` only warns on non-interactive stdin and lets the play run on to die somewhere unrelated), and it promised a migration tripwire on a leftover `TAILSCALE_API_ACCESS_TOKEN` that was retired 2026-09-10. One tells you to wait for a prompt that never comes; the other promises a safety net that does not exist.

Verified the gate fails before trusting it — an untested gate is decoration. It was wrong twice on the way: the claim-matching regex expected a character that is not there, and the counting pattern left its parens unescaped, which in ERE is a group and silently matched nothing, reporting "0 lookups" rather than erroring. Both found only by running it. It now passes on the real tree (89 across 24, matching the audit's independent count) and fails on a wrong figure, on an added lookup, and on an introduced `ansible_env.HOME` — each checked in a throwaway copy so the real files were never touched.
**Outcome:** applied
**Ref:** 397f7f8

## Q108 — interactive/fleet-coverage — gate-resolution

**Question:** The nightly `update-packages` openroutine sweep provisioned five of the seven fleet hosts, leaving `macbook-air` and `macbook-pro-nickel` to drift until someone ran the playbook by hand. Add them, and if so, how should an unreachable laptop be reported?
**Options considered:** add both best-effort (unreachable = skip) / add both strictly (unreachable = error) / record the exclusion as deliberate and leave the sweep at five
**Chosen:** Added both as a second, best-effort tier. Unreachable is a SKIP for those two and stays an ERROR for the five always-on hosts. A portable that answers is held to exactly the same standard as any other host.
**Decided-by:** human
**Justification:** The drift was measurable, not theoretical: in the 2026-09-15 fleet convergence nickel came in at `changed=12`, the largest on the fleet, against 0-6 on the five swept hosts. Q78 added nickel to the fleet's documented membership without changing any behaviour; this is the behaviour half, for both portables.

Two tiers rather than one because the sweep's value is that silence means success — it fires at 02:00 and only iMessages on error. Laptops are asleep, shut, or off-tailnet most nights, so treating them strictly would page on most mornings for the expected case, which trains the reader to ignore the alert that matters. Best-effort is scoped narrowly to *reachability at 02:00*: once a portable's ssh succeeds, a failed `git pull`, a failed launch, a non-zero `failed=`/`unreachable=` or a `STOPPED-NO-RECAP` is a real error and goes in the message.

Verified before trusting the prose: both hosts answer `ssh -o BatchMode=yes`, both do a non-interactive `git fetch origin main` (so the sweep's `git pull` will work — they hold their own deploy keys), and `ansible-playbook` resolves on each one's non-interactive PATH, which is what lets the task call it unqualified.

The task file lives outside this repo (`~/coworker/.openroutine/update-packages.cron.md`), so this entry is the only record in the repo whose playbook it runs. Its embedded restatement of the never-fan-out rule also carried the stale `79 places across 25 roles` figure and was corrected to `89 across 24` in the same edit; note that copy is not covered by `scripts/check-home-lookup-count.sh`, which only reads this repo's CLAUDE.md. `openroutine reload` was run so the daemon re-read the file; next tick 02:00.
**Outcome:** applied
**Ref:** 20f2ddb

## Q109 — interactive/fleet-coverage — deviation

**Question:** The nightly `update-packages` runbook prescribed a step-2 poll loop the agent cannot actually run: the harness blocks foreground `sleep`, and a single Monitor event carrying all seven hosts is truncated. The 2026-09-16 Run improvised around both and recorded the workaround as a memory. Fix the runbook, or leave the memory to carry it?
**Options considered:** leave it to the memory / rewrite step 2 to prescribe the shape that works / drop the polling requirement
**Chosen:** Rewrote step 2. The loop now goes to `/tmp/fleet-poll.sh` and runs under Monitor, emits one event line per host, drops hosts as they finish, and leaves a host after three consecutive ssh failures. Also bracketed the `pgrep` pattern to `[a]nsible-playbook main.yml`.
**Decided-by:** human
**Justification:** Memory recall is relevance-ranked and not guaranteed; the runbook is read every run, so the durable instruction belongs there. Dropping the polling was never open — it is what keeps the Run from reading as idle, and an idle Run is killed at `idle_timeout`, which is the entire reason step 1 detaches. Both branches were verified against the live fleet before committing: the happy path printed seven per-host lines and `ALL-DONE` in 3s against last night's recaps, and the unreachable path dropped a bogus host after exactly three strikes and terminated. The `pgrep` bracket is hardening, not a bug fix — the unbracketed form was measured NOT to self-match on either the remote or local branch, but only by an accident of when the shell execs, and the local branch runs concurrently with `ssh` processes that carry the pattern in their argv. `[a]nsible-playbook` matches the real process and cannot match a literal copy of itself.
**Outcome:** applied
**Ref:** 9f6196f

## Q110 — interactive/skills — deviation

**Question:** Four requests arrived to add one specific skill each — `eli5`, `show-me`, `skill-doctor`, `unslop`. Their sources ship 31, 5, 27 and 85 skills, and the role installs every source with `--all`. Add the sources as lines, or make the role able to take a subset?
**Options considered:** add four lines with `--all` (63+ unwanted skills) / add a second list carrying per-source skill names / install the four by hand outside the role
**Chosen:** Added `skills_sources_partial`, a list of `{source, skills}`, plus a second install task that names the skills instead of passing `--all`. `cursor/plugins` moved out of the exclusion list into it.
**Decided-by:** human
**Justification:** `vars/main.yml` already named this as the blocker — `cursor/plugins` was excluded *only* because "taking a subset needs skills_sources to carry per-source skill lists, which is a design change rather than a line." All four requests need that change, so the design note came due rather than being invented here. `--all` was never a shorthand worth keeping for these: `warpdotdev/common-skills` ships `complain`, which posts anonymously to Slack unprompted and is instructed never to mention having done so — not something to install fleet-wide as a side effect of wanting `skill-doctor`. Verified before and after: each source's inventory read with `skills add <source> -l` (installs nothing), then the role run took the store 153 → 156 adding exactly `eli5`, `skill-doctor`, `unslop` (`show-me` was already in from the hand test), removing nothing, with nine named siblings confirmed absent. Two further passes reported `changed=0` and `--check` was clean.
**Outcome:** applied
**Ref:** 2a74053
**Supersedes:** Q88 — narrowed, not reversed. Q88 deleted all 28 installed `cursor/plugins` skills because re-adding meant taking 85; `unslop` returns on its own and the other 84 stay out.

## Q111 — interactive/skills — deviation

**Question:** Adding `eli5` to the skill store left Claude Code with two copies — the store skill and the hand-installed `eli5@claude-community` plugin. Q110 kept both; the user asked to drop the plugin. Which copy goes, and how far does the removal reach?
**Options considered:** drop the plugin, keep the store skill / drop the store skill, keep the plugin / keep both
**Chosen:** Uninstalled the `eli5@claude-community` plugin and deregistered the `claude-community` marketplace it left orphaned. The store skill stays.
**Decided-by:** human
**Justification:** The store copy is strictly the more useful of the two — it reaches every agent, where the plugin reached only Claude Code. Surveyed before acting: the plugin existed on mac-mini-m2 alone, was hand-installed on 2026-08-28, appears in no role, and neither it nor its marketplace is referenced anywhere in this repo, so no role change was needed and no other host was touched. Removing it took the entry out of both `installed_plugins.json` and `settings.json`'s `enabledPlugins`, leaving the marketplace with zero plugins and a 3.8M clone Claude Code would have gone on pulling, so that was removed too. Verified after: marketplace deregistered, clone gone, the other 14 plugins untouched, and `~/.agents/skills/eli5/SKILL.md` still readable.
**Outcome:** applied
**Ref:** f1c5892
**Supersedes:** Q110 — only its decision to keep both copies of eli5. The rest of Q110, including `skills_sources_partial` and the eli5 store entry, stands.

## Q112 — interactive/skills — deviation

**Question:** Q110's partial-install task can fail in a way the `--all` task cannot — a pinned skill renamed or withdrawn upstream. It was shipped with no `failed_when`, so it failed the play with the CLI's own output. Is that failure good enough as it stands?
**Options considered:** leave it / make the failure legible, keeping the play-failing semantics / tolerate the failure and report it as a debug
**Chosen:** Kept the play failing, but moved the failure into an explicit `fail` task that names every source and skill that could not be installed and gives the remedy. `failed_when: false` on the install task defers rather than tolerates.
**Decided-by:** agent
**Justification:** The state was already safe — measured, a missing skill exits 1, installs nothing and leaves the store undamaged — so only the message was wrong, and it was wrong in the place it matters: the CLI prints `● Available skills:` and its inventory, which in the 02:00 iMessage reads as help text rather than an error and never names the broken pin. This preserves today's behaviour rather than choosing between failing and tolerating, so that question stays open and is still a one-line change. `failed_when: false` earns its place separately: without it the loop aborts on the first bad pin and hides the rest, so one run now reports every broken entry. Verified by injecting two broken pins at once — all four loop entries completed, then a single failure named both, with the remedy — then restoring the file and confirming a clean `changed=0` run.
**Outcome:** applied
**Ref:** fd55c2f

## Q113 — interactive/skills — deviation

**Question:** Q112 left open whether a pinned skill that vanishes upstream should fail the play. Failing is the only signal the nightly sweep can see, but `skills` is role 21 of 41, so failing there stops the 20 roles after it. Fail, tolerate, or something else?
**Options considered:** keep failing inside the role / tolerate and report via debug / record in the role and fail in `main.yml`'s post_tasks
**Chosen:** The third. The role records the broken pins as a fact and prints them; a new `post_tasks` block in `main.yml` fails the play on that fact after every role has run.
**Decided-by:** human
**Justification:** The choice only looked binary because the check sat at role 21. Failing there was disproportionate — a renamed skill would have halted `tailscale` (and its OAuth key-expiry maintenance), `hermes`, `ponytail` and 17 others, on all seven hosts, nightly, until someone edited one line. Tolerating was worse in the other direction and not merely risky but structurally invisible: the sweep's only success test is `failed=0` in the PLAY RECAP, so anything that does not fail the play cannot be seen by it, and the skill would leave the fleet silently. Upstream withdrawal is not hypothetical — this role already records three (mattpocock's `to-issues` and `to-prd` 404ing, `lavish-design` no longer shipped, `backnotprop/plannotator` dropping every `plannotator-*`). Deferring keeps the recap honest and drops the blast radius to zero. Verified on a harness mirroring `main.yml`'s shape: healthy pins pass with the post_task skipped; two broken pins let all four loop entries and the rest of the role run (reaching `ok=46` where the in-role failure reached `ok=43`), print the debug, then fail the play with `failed=1` naming both. `main.yml` passes `--syntax-check`, and `--list-tasks` shows the post_task last, after all 41 roles.
**Outcome:** applied
**Ref:** e9269cf
**Supersedes:** Q112 — only its placement of the failure inside the role. Its message, and the `failed_when: false` that lets one run report every broken pin, both stand.

## Q114 — interactive/claude-code — deviation

**Question:** The `claude-code` role decided `changed` for its six plugins from a NEGATED pair of stdout sentinels, the one shape CLAUDE.md rules out. Convert it to a state diff, and if so against what?
**Options considered:** leave it (it works today) / add a third sentinel as they appear / diff `gitCommitSha` from `installed_plugins.json`
**Chosen:** Diff `gitCommitSha` from `~/.claude/plugins/installed_plugins.json` around the update, the same ledger and the same shape the `ponytail` role already uses. The six plugin names moved to a new `roles/claude-code/vars/main.yml`, which also removes the triple duplication across the install, update and enable tasks, and the ledger path with them — the pre-existing `Check installed plugins` slurp now reads the same variable rather than respelling the path, so the role gained no net `lookup('env', 'HOME')` and `scripts/check-home-lookup-count.sh` still reads 89.
**Decided-by:** human
**Justification:** The old gate enumerated the two no-op phrasings known when it was written, so any third one — or a failure printing neither — reports a phantom change on all six, and a failed update reads as a change rather than an error. Only `gitCommitSha` is compared, never whole records: `lastUpdated` is rewritten on a no-op update (observed on planning-with-files), so a wholesale comparison would itself be the phantom. Proved the comparison against three fixtures — a moved sha reads changed, a `lastUpdated`-only difference reads unchanged, identical reads unchanged. Two further findings from testing: `claude plugin update` does not rewrite `gitCommitSha` on a no-op, so the gate is quiet on a converged host; and several records in this ledger carry no sha at all, which `default('')` keeps stable rather than treating as drift. Three consecutive runs reported `changed=0` and `--check` was clean.
**Outcome:** applied
**Ref:** 3cf0048

## Q115 — interactive/readme — tradeoff

**Question:** The README's agent-CLI roles had only one-line table rows. What prose belongs in README, given CLAUDE.md already documents several of the same roles in depth?
**Options considered:** translate CLAUDE.md's role sections into Chinese / write README prose only for what a human operator needs and leave agent-facing detail in CLAUDE.md / leave the table as-is
**Chosen:** A new `### Agent CLI 与技能` section covering six things the one-line rows actively mislead about — differing install channels, config files overwritten every run, the skills store and its fan-out, expected output that reads like errors, steps the roles cannot perform, and kimi-code never upgrading. Deliberately NOT a translation of CLAUDE.md.
**Decided-by:** human
**Justification:** The two files have different readers and different jobs: CLAUDE.md is agent-facing and explains why each task is shaped the way it is, README is operator-facing and answers "what will this do to my machine and what do I still have to do myself". Duplicating would create a second copy to keep in sync, and this repo has measured form on exactly that failure (Q102's ghost rows, and `scripts/check-home-lookup-count.sh` existing at all). The selection rule was: include it only if a human running the playbook would be surprised or misled without it. Highest-value entry is `~/.pi/agent/settings.json`, overwritten wholesale on every run with no gate, so an in-app `/settings` edit is silently lost.
**Outcome:** applied
**Ref:** a108480

## Q116 — interactive/skills — deviation

**Question:** `roles/skills/tasks/main.yml` justified running its installers ungated with "20s for all four, measured". The list now holds 14 sources. Restate the figure, or re-measure it?
**Options considered:** quote the existing figure in the README / drop the number from both / re-measure and correct both
**Chosen:** Re-measured the whole role on mac-mini-m2, 2026-09-16: **136s**, not 20s. Corrected the role comment and cited the new figure in the README.
**Decided-by:** agent
**Justification:** The old figure was written when `skills_sources` held four entries and survived every later addition because nothing re-measured it — the same doc-rot this repo builds checkers against. Restating it in user-facing docs would have propagated a number wrong by roughly 7x, and dropping it silently would have discarded the actual justification for having no gate. The cost is real and worth stating plainly: it buys the only mechanism that pulls upstream skill edits down. The comment now records the old figure and why it went stale, so the correction is not itself mistaken for drift later.
**Outcome:** applied
**Ref:** a108480

## Q117 — interactive/checkers — deviation

**Question:** `scripts/check-readme-roles.sh` walks `main.yml`'s `roles:` block with an exit rule that only fires at column 0. `roles:` is itself indented, so a sibling key — the `post_tasks:` added under Q113 — does not stop it and the walk continues to EOF. Fix, or leave it?
**Options considered:** leave it (harmless today) / filter the post_tasks lines explicitly / exit at a sibling key
**Chosen:** Added a second exit rule, `f && /^  [a-z_]+:/ { exit }`. Role entries are indented four spaces so they cannot match it, and the original column-0 rule stays for the top-level case.
**Decided-by:** human
**Justification:** It is currently harmless only by accident — every line in the post_tasks block fails the later `^[a-z][a-z0-9-]*$` filter. Demonstrated the latent failure rather than arguing it: with one bare lowercase token planted inside post_tasks, the old parser yields **42** role names and the new one 41, so the check would have demanded a README row for something that is not a role and blamed the table, which is the one part that was correct. This is a guard whose whole value is being trustworthy, and a guard that can fail confusingly is worse than one that fails loudly. Verified it still reports 41 roles and still passes.
**Outcome:** applied
**Ref:** 4eb3240

## Q118 — interactive/journal — gate-resolution

**Question:** Q50 is the only escalation in this journal never resolved or superseded. It asks whether to repair a crash-looping OpenClaw gateway and a config the openclaw role itself had invalidated. Is it still open?
**Options considered:** treat as open and act on it / edit Q50 in place / append a closing entry
**Chosen:** Moot, closed by an appended entry. Q50 is not edited.
**Decided-by:** agent
**Justification:** The question was overtaken rather than answered: Q52 deleted `roles/openclaw` and ponytail's OpenClaw half, and Q54 removed the data directories fleet-wide. Verified against the tree, not inferred — `roles/openclaw` is absent and `roles/ponytail/tasks/` has no `openclaw.yml`. There is no longer a role that could perform the repair Q50 asked about, and CLAUDE.md records that re-adding one needs a fresh decision. Closing it by appending preserves the append-only invariant; the alternative, editing Q50's `Outcome`, would rewrite history to claim a decision nobody made. Note one deliberate exception outside this: `archs-mac-mini` still runs a live OpenClaw gateway and its `~/.openclaw` is left alone (Q98).
**Outcome:** applied
**Ref:** 4eb3240

## Q119 — interactive/changed-gates — deviation

**Question:** Seven tasks across six roles still decided `changed` from a NEGATED stdout sentinel, the shape CLAUDE.md rules out — including `claude plugin marketplace add` in the very file whose plugin-update gate was converted under Q114. Convert them, and to what state?
**Options considered:** leave them (all quiet today) / convert only the claude-code one for consistency with Q114 / convert all seven to state diffs
**Chosen:** All seven, in three classes. `brew trust` (cc-switch, moshi, multica-cli) now reads the trust ledger `brew trust --json v1` prints and skips the call when the tap is listed. The oh-my-zsh plugin enables (direnv, rust) parse the `plugins=(...)` array out of `~/.zshrc`. The marketplace adds diff `~/.claude/plugins/known_marketplaces.json` — a key-set diff in `claude-code`, which adds five, and a presence check in `ponytail`, which adds one whose name it knows.
**Decided-by:** human
**Justification:** Each had real state available that nobody had looked for: `brew trust` documents its own state file and ships a `--json v1` reader, and the enabled zsh plugins simply *are* the `plugins=()` array. Severity was low and stated as such — all seven were quiet on all three hosts sampled, so this is fragility, not a live bug. Two traps were designed against rather than discovered later: the plugins array is parsed to a list, so `direnv-extra` cannot read as `direnv`; and only the marketplace *names* are compared, never the records, which carry per-fetch metadata that moves on its own — the same phantom `lastUpdated` would have caused in Q114. `known_marketplaces.json` is keyed by the marketplace's own manifest name, which is not derivable from `owner/repo` (`thedotmack/claude-mem` registers as `thedotmack`), which is why claude-code diffs the key set rather than looking each one up. Verified: zero negated gates remain; lint clean; two real passes and a `--check` over all seven roles with no gate reporting changed (the one `changed=1` in pass 2 was an unrelated genuine hermes update); each gate fixture-tested in both directions including absent and empty ledgers; no dangling references to the five deleted registers. The two zshrc reads raised the `lookup('env', 'HOME')` count to 91 across 25 roles, and CLAUDE.md was updated to match.
**Outcome:** applied
**Ref:** b47832f

## Q120 — interactive/claude-code-plugins — irreversible-action

**Question:** How far does "delete the planning-with-files Claude Code plugin from all hosts" reach — the ledger entry alone, or the marketplace registration and cached payload with it?
**Options considered:** uninstall the plugin only / uninstall + remove the marketplace / uninstall + remove the marketplace + delete the cached version snapshots
**Chosen:** All three. `claude plugin uninstall` then `claude plugin marketplace remove` on each of the seven hosts, followed by `rm -rf ~/.claude/plugins/cache/planning-with-files`.
**Decided-by:** human
**Justification:** The user asked for the plugin gone fleet-wide, so the destructive step was theirs to authorize, not mine to assume. Scope was settled by measuring what each command actually leaves behind rather than by reading its help: on the first host `uninstall` + `marketplace remove` together cleared `installed_plugins.json`, the `known_marketplaces.json` key, and both `enabledPlugins` and `extraKnownMarketplaces` in `settings.json` — but left `~/.claude/plugins/cache/<name>/`, which held 5-9 version snapshots per host, 790M across the fleet. Inspected before deleting: those directories hold copies of the upstream repo (README, CHANGELOG, tests, docs) and no user-authored content, and the plugin's own plan files live in the project trees it was used in, which were not touched. Also verified the two skills it ships (`i18n`, `planning-with-files`) had never reached `~/.agents/skills`, so there was no symlink fan-out to prune. Repo side: dropped the plugin from `claude_code_plugins` and `OthmanAdi/planning-with-files` from the marketplace loop, and corrected the three comment counts that named the old list sizes. Verified all seven hosts read clean afterwards, then re-ran the role standalone — `changed=0`, both verdict tasks reporting "already registered" / "already up to date", and nothing resurrected.
**Outcome:** applied
**Ref:** 07d7eb3

## Q121 — interactive/skills-orphans — tradeoff

**Question:** `skills add` never deletes, so store directories that leave the role's reach accumulate forever and diverge hosts. Should the role delete them, detect them, or leave the problem to a manual audit?
**Options considered:** delete orphans automatically / detect and report, deleting nothing / leave it to a manual audit each time
**Chosen:** Detect and report. A read-only task runs `roles/skills/files/find-orphans.py` and a `debug` prints the list when it is non-empty; nothing is removed.
**Decided-by:** human
**Justification:** Deleting is the catastrophic-irreversible case CLAUDE.md reserves for a human, and the list is not uniform junk — `soulmachine/skills` entries surface here as real directories, which is a git-backed skill shadowed by a CLI copy (Q82), not something to sweep. The rule is per-source because a single fleet-wide test cannot work: whole sources (`--all`) are judged on `updatedAt`, partial sources (`--skill`) on the configured name list, since only the named skills are fetched and a timestamp test flags every unnamed sibling — that error alone produced 102 candidates of which nearly all were false. The whole-source branch compares with a 300s tolerance rather than for equality: measured 2026-09-16, one run stamps a source's skills milliseconds apart (mattpocock's 37 spanning .511Z to .523Z), so an exact `updatedAt < max` called 43 of its 45 skills orphans while the real gap to an orphan is two months. Two no-false-positive properties are asserted rather than assumed — same-run siblings are never flagged, and a source that failed or was rate-limited has every entry at one older stamp and so yields nothing. Validated against ground truth before wiring in: `npx skills add <source> -l` confirmed `sandbox-sdk` is absent from the 14 cloudflare/skills ships, the mattpocock 8 match an earlier hand audit, and `lavish-design` is the orphan `roles/skills/vars/main.yml` already documents. Fleet-wide the report ranges 2 (dev-server-frank-lume) to 24 (macbook-pro-nickel). `changed_when: false` throughout: an orphan persists until someone acts, so reporting it as a change would be a permanent phantom. Two passes gave `changed=1` then `changed=0` with the count stable at 11, and `--check` renders the report because the read is forced with `check_mode: false`.
**Outcome:** applied
**Ref:** e233cd5

## Q122 — interactive/mise-roles — deviation

**Question:** `go` and `jdk` both ran a bare `mise use` gated on `'installed' in stderr`, the shape `nodejs` was rescued from. Should both get the `nodejs` treatment — an added `mise upgrade` plus a state diff?
**Options considered:** give both roles the full nodejs pattern / give both the state diff but add `mise upgrade` only where measurement says it is needed / leave both alone since neither reports a phantom change
**Chosen:** State diff in both; `mise upgrade` added to `jdk` only. `go` keeps its single `mise use` deliberately.
**Decided-by:** agent
**Justification:** The premise that both were frozen was tested and half of it was wrong. mise's install history on mac-mini-m2, read 2026-09-16, shows `go` has upgraded eight times since March (1.26.1 Mar 30 through 1.27.1 Sep 7) with no `mise upgrade go` anywhere in this repo — so `@latest` re-resolves on every run, where `lts` is satisfied by any already-installed LTS release. Adding an upgrade step to `go` would be a command that never has work to do, so it is left out and the asymmetry is documented in both roles. `jdk` is the real gap: same `lts` request as `nodejs`, no upgrade step, and nothing installed since 2026-04-03. It is a mechanism fix and not a stale-version fix — java resolves to 25.0.2, which is the newest LTS, so nothing had drifted yet; `mise upgrade java` costs 0.04s and prints "All tools are up to date" when current. The stderr gate had to go regardless: once an upgrade task exists, a gate reading the *use* task's wording cannot see an upgrade at all. Gates proved in both directions rather than assumed — injected drift (go 1.27.0, java 17.0.2) made both report `changed`, state restored to `latest`/`lts` on the same run, and the following pass read `changed=0`. The `requested_version` half was proved separately by pinning `go = "1.27.1"`, the version the alias already resolves to: config-only drift with the resolved version unmoved still fired, which is exactly what a `mise current` or resolved-version-only diff would have missed.
**Outcome:** applied
**Ref:** 8d07bc1

## Q123 — interactive/npm-sentinel-gates — deviation

**Question:** Three roles decided `changed` from `'added'`/`'updated'` in `npm install -g` stdout. Is that the usual phantom-change problem, and what is the right state to diff?
**Options considered:** leave them, since none reports a phantom on a converged host / diff the installed version from `npm ls -g --json` / diff `npm view <pkg> version` against the installed one
**Chosen:** Diff `npm ls -g --depth=0 --json <pkg>` around the install, in `obsidian`, `playwright` and `playwright-cli`. The `playwright install chromium` gate became `changed_when: true`.
**Decided-by:** agent
**Justification:** It is not a phantom but its inverse, which is why it survived: measured 2026-09-16 on mac-mini-m2, a converged `npm install -g defuddle` prints `changed 27 packages in 542ms` and a genuine 0.19.2 → 0.19.3 upgrade prints `changed 27 packages in 550ms`. Neither says "added" or "updated" — that wording appears only on a first install — so the gates were permanently false and all three roles reported `ok` through every upgrade they actually performed. A missed change is invisible in a recap by construction, unlike a phantom, which is why no amount of two-pass checking would have surfaced it. `npm ls -g --json` was chosen over comparing against `npm view <pkg> version` because the latter is the two-channel mistake the `claude-mem` role was fixed for (Q-series on that role): it compares upstream's latest against local state and reads as a permanent difference whenever a publish is pending. Fresh-host behaviour was checked rather than assumed — an absent package prints `{"name": "lib"}` and exits 1, hence `failed_when: false` on the read, so a first install reads as a change. The chromium gate is a different case: it already runs only `when` the marker check found a missing component, so reaching it means work was genuinely needed, and the extra `'downloading' in stdout` test could only subtract — Playwright can unpack from its browser cache without printing that word. Gates proved in both directions: downgrading `defuddle` to 0.19.2 and `@playwright/cli` to 0.1.19 (the scoped-name case) each made the role report `changed` and restored the newer version in the same run, with the following pass reading `changed=0`; three consecutive converged runs and `--check` were clean.
**Outcome:** applied
**Ref:** 524e355

## Q124 — interactive/rust-component-gate — deviation

**Question:** `roles/rust` decided `changed` from `'installing'` in `rustup component add` output. Earlier triage called this merely wording-fragile but working. Is it?
**Options considered:** leave it, since the converged run correctly reports `ok` / diff `rustup component list --installed` around the loop / match a different phrase in rustup's output
**Chosen:** Diff `rustup component list --installed` before and after the loop, reporting one `changed` for both components rather than one each.
**Decided-by:** agent
**Justification:** The earlier "it works" verdict was wrong because only the converged direction had been tested — the exact mistake the npm note in Q123 warns about. Measured 2026-09-16 on mac-mini-m2 by removing and re-adding both looped components: a genuine install prints exactly `info: downloading component rust-src` and nothing else, so `'installing'` never matches and the role had been installing components while reporting `ok`. This is the same missed-change class as Q123, not the fragility it was first triaged as. Confirmed structurally as well as empirically: the only `installing component` string in the rustup 1.29.1 binary is the hardcoded literal `installing component rust` on the legacy-manifest path, not a template for a named component — so the gate was written against an older wording upstream has dropped. `component list --installed` was chosen over per-component name matching because the listing spells components inconsistently (`rust-analyzer-aarch64-apple-darwin` carries the target triple, `rust-src` does not), and comparing the whole listing needs to know neither. Only the "before" read takes `failed_when: false`, so an empty stdout differs from a real "after" and reports `changed` rather than failing; the "after" read stays strict so a broken rustup still fails the play. Proved in both directions: converged run `changed=0`, then removing `rust-src` made the run report `changed=1` from the comparison task (the loop itself stayed `SUCCESS` under `changed_when: false`) and restored the component, and the pass straight after read `changed=0`. The word `installing` appears nowhere in that drift run's log, which is direct evidence the old gate would have called a real install `ok`. The two `oh-my-zsh` gates triaged alongside this one were tested the same way and genuinely do work, including the mixed case where five plugins are already enabled and one is not, so they were deliberately left alone.
**Outcome:** applied
**Ref:** d1600e8

## Q125 — interactive/stale-skill-directories — irreversible-action

**Question:** A retired skill, `deploy-kimi-k26-blackwell`, was still resident as a real directory in the skill store on macbook-pro-nickel three months after being renamed. Delete it, or leave it?
**Options considered:** delete directory and lock entry / delete the directory but leave the lock entry / leave both and only report
**Chosen:** Delete both, after archiving the directory on the host and backing up the lock.
**Decided-by:** human
**Justification:** Escalated rather than decided, per the detection-not-deletion rule set in Q121 and the hard floor on deleting work that is not mine; the user approved this specific directory on this specific host. Materiality was established before asking: the successor `deploy-kimi-k26-on-rtx-pro-6000` differs by 253 diff lines of SKILL.md and ships 11 scripts against the stale copy's 4, having moved to containerised serving with a systemd unit, so an agent on that host could follow a three-month-old GPU deployment path — and both names were resident at once, so it could pick either. Recoverability was verified before deleting, not asserted: the two files unique to the stale copy (`scripts/apply_sm120_fixes.sh`, `scripts/serve.sh`) are both present in `soulmachine/skills` git history, which matters because the store is the only copy of anything authored in place. The lock entry was dropped alongside the directory so the skills CLI does not keep treating a deleted skill as managed (128 -> 127 entries, JSON re-validated); `agentstow sync` then pruned the four agent-dir links. A tarball was left at `~/stale-skill-<name>-<stamp>.tar.gz` on the host and the lock backed up beside it, so the step is reversible without reaching for git at all. Four sibling directories that this decision would also have covered vanished between two surveys an hour apart, by an actor never identified — openroutine, `agentstow sync`, my own commands and host schedulers were each ruled out — so the scope shrank from five directories on four hosts to one before the deletion ran. That the store is mutated by something outside this repo is itself the argument for the detector staying report-only.
**Outcome:** applied
**Ref:** 48c2c09

## Q126 — interactive/mise-role — gate-resolution

**Question:** Nothing in the repo ever updated mise after bootstrap.sh installed it, so the fleet had drifted to four versions spanning six months. Add a role, catch up by hand, or pin deliberately?
**Options considered:** a new `mise` role using `mise self-update` / a one-off manual catch-up with no role / pin deliberately and document why
**Chosen:** A new `mise` role running `mise self-update --yes --no-plugins`, placed immediately before `go` in main.yml, deciding `changed` from `mise --version` before and after.
**Decided-by:** human
**Justification:** Escalated rather than decided, because jumping a host six months of mise changes sits underneath `go`, `jdk` and `nodejs` fleet-wide and deserved an attended first run; the user chose the role. Measured 2026-09-16: mac-mini-2018 on 2026.3.17, mac-mini-m2 on 2026.4.3, macbook-pro-nickel on 2026.5.2, dev-server-frank-lume on 2026.8.8 — each frozen at whenever that host was bootstrapped, because bootstrap.sh runs on a fresh Mac and not after. mise was itself printing "mise version 2026.9.10 available" on every invocation, with nothing acting on it. `self-update` is the correct updater precisely because the install is standalone: its help states the command is unavailable when mise comes from a package manager, and no fleet host has it from brew (`brew list --formula | grep -x mise` finds nothing), so a host that ever switches will fail loudly rather than no-op — the warning task names that case. `--no-plugins` is deliberate and is the Q123/Q124 lesson applied forward: self-update also updates plugins by default, which `mise --version` does not report, so a plugin-only update would be a real change reported as `ok`. No host has any plugin today (`mise plugins ls` empty; go/java/node use built-in backends), so it narrows nothing now and keeps the gate honest later. The GitHub rate-limit borrow follows the `bun` role, with one difference that matters: mise reads `GITHUB_API_TOKEN`, not the `GITHUB_TOKEN` bun reads. Bare `mise` rather than an absolute path matches what `go`, `jdk` and `nodejs` already do and added no `lookup('env', 'HOME')`, so CLAUDE.md's counted figure stays at 93. Proved on this host, which was five months stale: the role took it 2026.4.3 -> 2026.9.10 reporting `changed=1`, the re-run read `changed=0`, and the three dependent roles were re-run under the new mise and all reported `changed=0 failed=0` with `mise ls --current <tool> --json` still carrying the `version` and `requested_version` fields their gates compare.
**Outcome:** applied
**Ref:** aaf35ea

## Q127 — interactive/ansible-core-drift — tradeoff

**Question:** `ansible-core` was the last thing bootstrap.sh installs that nothing ever updates. Add it to the `python` role's `python_cli_tools` list, upgrade it outside the play, or leave it frozen?
**Options considered:** add `ansible-core` to `python_cli_tools` (two lines, matches the existing `@latest` pattern) / upgrade it in the openroutine nightly sweep, before `ansible-playbook` starts / leave it frozen and document why
**Chosen:** Upgrade it outside the play — `{ uv tool upgrade ansible-core || true; }` inserted into the per-host launch line of `~/coworker/.openroutine/update-packages.cron.md`, between `git pull` and `nohup ansible-playbook`. `mac-studio-m3` reconciled from the `ansible` bundle onto `ansible-core` so one tool name works fleet-wide.
**Decided-by:** human
**Justification:** The in-repo option is the obvious one and is unsafe twice over. (1) It would rewrite the running interpreter's own libraries mid-play: the `python` role is 7th of ~44, leaving ~37 roles still lazily importing ansible modules out of a directory `uv tool install` had just replaced — the shape `mem:hermes-update-exits-1-when-it-succeeds` records for `hermes update`. Not tested, and deliberately not tested against the live fleet. (2) `mac-studio-m3` carried the **`ansible` bundle v14.3.1** as its uv tool, not `ansible-core` — an undocumented divergence from bootstrap.sh's `uv tool install --with ansible ansible-core`, invisible because both yield a working `ansible-playbook`. Installing `ansible-core` beside it would contend for `~/.local/bin/ansible`, trip uv's `Executable already exists`, and the `python` role's existing `--force` heal path — written for pip3 leftovers — would have silently hijacked the executables. The nightly sweep is the right home because it already runs `uv tool upgrade graphifyy` and, crucially, runs *before* ansible starts, so the mid-run hazard cannot arise by construction. The tradeoff accepted: a nightly unattended ansible-core upgrade can in principle break all seven hosts at once (a deprecation becoming an error, as CLAUDE.md's `Conditionals must have a boolean result` note shows). Accepted because the fleet is already exposed to exactly this class — the play tracks latest for brew, npm globals, bun, mise, uv, claude and codex unattended every night — so pinning ansible alone would be inconsistent, and the sweep reports per-host `failed=N` loudly. `|| true` rather than `&&` so a spent PyPI or a network blip cannot cost a host its whole provisioning run. Measured 2026-09-16: six of seven hosts on core 2.21.3 installed 2026-08-14 (the uniformity is a fleet bootstrap that day, not an updater — `bootstrap.sh:132` guards on `command -v ansible` and never re-runs), macbook-pro-nickel on 2.21.4 only because it was bootstrapped 09-10, against a PyPI latest of 2.21.4; meanwhile `ansible-lint`, which the `python` role does reinstall at `@latest` every run, reported `using ansible-core:2.21.4` on every host — the lint gate validating against a core the fleet did not run. All seven are now on 2.21.4 with the playbook syntax-checking clean, rolled attended rather than letting the 02:00 sweep be the first run on an unverified ansible. `uv tool upgrade ansible-core` also carries the `--with ansible` bundle (14.3.1 -> 14.4.0), verified, so one command covers both.
**Outcome:** applied
**Ref:** 8688179

## Q128 — interactive/thermo-nuclear-skill — interpreted-ambiguity

**Question:** The user linked one upstream SKILL.md — `cursor-team-kit/skills/thermo-nuclear-code-quality-review` — and asked for it in the `skills` role. Upstream ships two near-identically named siblings beside it. Take the one named, or the family?
**Options considered:** add only `thermo-nuclear-code-quality-review` to the existing `cursor/plugins` partial entry / also take `thermo-nuclear-review` and `thermos`, which the linked skill's own family implies / re-open `cursor/plugins` to `--all`
**Chosen:** One line: `skills: [unslop, thermo-nuclear-code-quality-review]`. No role logic changed.
**Decided-by:** claude
**Justification:** The partial-source list added on 2026-09-16 exists for exactly this, so the change is data, not code — `cursor/plugins` was already an entry, so this narrows Q88 one more skill rather than reversing it. Taking the siblings was rejected on evidence, not taste: `thermos` is documented upstream as launching "both thermo-nuclear review subagents in parallel", and subagents live in the plugin's own tree, not in the skill directory — outside what `skills add` copies — so it would install a skill whose first action is to invoke two things the store does not have. `thermo-nuclear-review` is a different skill (branch security/correctness audit) that the user did not ask for. The one taken is a single self-contained SKILL.md — verified against the GitHub contents API, one file — carrying `disable-model-invocation: true`, so it only ever runs when named and cannot fire on its own in an unrelated session. Name verified with `npx skills@latest add cursor/plugins -l`, which lists without installing, per the vars comment's own rule about not trusting the lock file. Measured after: store directory and `~/.claude/skills` symlink both present, lock entry records `skillPath: cursor-team-kit/skills/thermo-nuclear-code-quality-review/SKILL.md`, role re-run reports 0 CHANGED, ansible-lint clean at production profile. The stale `not the other 84` comment was corrected to 83 in the same edit — a count that silently goes wrong on every future addition is the same class of rot as the `20s for all four` timing this role already carries a note about.
**Outcome:** applied
**Ref:** 9d1ef03

## Q129 — interactive/mattpocock-orphan-purge — catastrophic-action

**Question:** The `skills` role's orphan detector had been reporting stale `mattpocock/skills` store directories on every host, on every run. The user asked to clear them fleet-wide. Delete, and on what evidence?
**Options considered:** delete the reported directories on each host / delete only the subset that duplicates a currently-shipped skill under an old name / leave them and silence the report instead / teach the role to delete them itself
**Chosen:** Deleted the mattpocock orphans on the six hosts that had them, by hand, with a per-host tarball and lock backup first. dev-server-frank-lume had none. The role was **not** changed — it stays detection-only.
**Decided-by:** human (asked for), claude (scope and safety checks)
**Justification:** Authorised explicitly, so the Q121/Q125 escalation rule was satisfied; what remained was proving the deletion safe, which was done before anything was removed rather than asserted after. Three preconditions were measured per host: (1) **none was a symlink** — an `agentstow`/`soulmachine/skills` entry shows up in this report as a real directory and must never be swept (Q82), and the purge script refuses one rather than trusting the survey; (2) **no file was newer than its own lock `updatedAt`**, so nothing had been authored or edited in place — the specific hazard Q125 found, where the store is the only copy; (3) **upstream git history still carries every path** (`skills/deprecated/qa`, `skills/engineering/diagnose`, `skills/engineering/to-prd`, `skills/productivity/write-a-skill` all return commits from the GitHub API), so the tarball is a convenience, not the last copy. Materiality was not assumed from the word "orphan": most of these are **renames, not withdrawals** — upstream now ships `diagnosing-bugs` where the stale copy says `diagnose`, and `writing-for-agents` where it says `write-a-skill`/`writing-great-skills`. Both spellings were resident at once on five hosts, so an agent could load either, which is Q125's argument exactly. The per-host counts prove the drift the detector was added for: 11 on macbook-pro-nickel, 9 on archs-mac-mini, 8 here, 4, 4, 2, and 0 on dev-server-frank-lume — 38 directories in total, from a source that ships 38 skills. Lock entries were dropped with the directories (the JSON re-parsed after each write) so the CLI stops treating deleted skills as managed, and `agentstow sync` then pruned 8/16/16/36/44 per-agent links. Scope was held to `mattpocock/skills`: `cloudflare/skills sandbox-sdk`, `kunchenguid/lavish-axi lavish-design` and two `jimliu/baoyu-skills` entries still report, untouched, because they were not asked about. Verified after: all seven hosts read `mattpocock-live=38, orphans=none, ghost-dirs=none, dangling=none`, and the role's own `find-orphans.py` prints no mattpocock line anywhere. **Side finding, not fixed:** `agentstow` is absent on mac-mini-m2 while all six other hosts carry it at `~/.cargo/bin/agentstow`, and no role installs it — the local link pruning had to be done directly. `~/.openclaw/skills` also still exists on this host and held links, eight months after Q52-Q54 removed OpenClaw.
**Outcome:** applied
**Ref:** 4895f3f

## Q130 — interactive/agent-sync-migration — hard-to-undo

**Question:** `agentstow` looked absent on mac-mini-m2 and present on the six others. The user corrected the reading: the tool was renamed to `agent-sync`, repo `agent-sync-sh/agent-sync`, and asked to uninstall the old binary and install the new one everywhere.
**Options considered:** migrate all six laggards to `agent-sync` and drop `agentstow` / install `agentstow` on mac-mini-m2 to match the majority / add a role so the install is reproducible
**Chosen:** Migrated the six to `agent-sync 1.0.1` via the Homebrew tap and removed `agentstow`. No role added — flagged instead.
**Decided-by:** human
**Justification:** The majority was the stale side, which is why "make the odd host match the other six" was the wrong instinct and needed the user's correction — mac-mini-m2 was not missing the tool, it was the only host already on the new name, via brew rather than cargo. Installed per upstream's own README: tapped **by URL** because the tap lives inside the main repo rather than a `homebrew-*` one, with `brew trust agent-sync-sh/tap` between tap and install — Homebrew 6 refuses an untrusted third-party tap, the constraint `mem:homebrew-tap-trust-required` already records and which upstream documents in the same snippet. The trust step is guarded on `brew trust --json v1` so a re-run is a no-op. Landed at `/opt/homebrew/bin` on the five Apple Silicon hosts and `/usr/local/bin` on the Intel mini, which is the expected split and confirms each host's own shellenv decided. **A scripting trap cost one round:** the migration was first piped as `ssh host 'zsh -l -s' < script`, and `brew install` read from the same stdin, swallowing the rest of the script — the tap/trust/install ran, everything after was consumed, and one line surfaced as literal echoed text rather than as an error. Re-run by `scp`ing the script and executing it as a file, with `exec </dev/null` at the top so nothing downstream can eat it. Not a role, deliberately: this was an unattended fleet mutation done once, and a role would need the same tap/trust/install shape plus an `agentstow` removal step that is dead weight the moment it converges. That leaves a real gap — nothing in this repo installs `agent-sync`, so a rebuilt host loses it, the same class as Q127's ansible-core finding — recorded here and raised rather than silently fixed.
**Outcome:** applied
**Ref:** 37d41d1

## Q131 — interactive/orphan-purge-round-2 — catastrophic-action

**Question:** After Q129 cleared the mattpocock orphans, four renamed-away skills remained on 6 hosts and 13 hand-installed firecrawl skills sat on mac-studio-m3 alone. The user approved deleting both.
**Options considered:** delete both sets / delete only the renamed ones and adopt firecrawl into `skills_sources_partial` so all hosts get it fresh / leave and silence the report
**Chosen:** Deleted 17 names across 5 sources on the hosts carrying them — `sandbox-sdk`, `baoyu-imagine`, `baoyu-image-cards`, `lavish-design`, and the 13 firecrawl skills. `gpt-researcher` on macbook-air was **not** touched.
**Decided-by:** human (asked for), claude (evidence and scope)
**Justification:** Same three gates as Q129, and this time **two of them fired and both were false positives that had to be disproved rather than waved through.** The mtime heuristic ("any file newer than the lock's `updatedAt` means locally authored") flagged `sandbox-sdk` on macbook-air and `firecrawl` on mac-studio-m3. In both, every file shared an mtime to the **millisecond** — the signature of a bulk re-fetch, not of a human editing three files — so the heuristic was measuring a refresh that never bumped `updatedAt`. Settled on content, not on timestamps: macbook-air's `sandbox-sdk/SKILL.md` is **byte-identical** to `cloudflare/skills@30553f8` (5771 bytes, sha256 `0f3501e65109` on both sides), so nothing was lost. `firecrawl` needed a full-history search rather than an API spot-check — the GitHub API's `commits?path=` returns the commit that **deleted** the path, where the blob is already gone, which is why the first two fetches came back as 14-byte `404: Not Found` and looked like a missing upstream. Cloning both repos and matching every file by `git hash-object` put 14 of 15 files in history (`firecrawl/cli` for the CLI docs and `rules/`, `firecrawl/skills` for the four `build-*.md`), leaving only `SKILL.md` in neither — and that one is **generated by `firecrawl init`**, which the file says of itself and which its embedded `firecrawl cli v1.8.0` banner confirms, so it is machine output and regenerable, not authored work. Scope was held to what was asked: `gpt-researcher` on macbook-air is the one remaining orphan fleet-wide and was left because the user named firecrawl only. Two live consequences are raised rather than acted on: the **firecrawl CLI is still installed** at `/opt/homebrew/bin/firecrawl` on mac-studio-m3, so `firecrawl init` would restore all 13 skills, and the deletion is therefore not durable until that is decided; and upstream still ships every firecrawl skill, so re-adoption is `npx skills add firecrawl/cli` rather than a restore. The four renamed ones all had live successors resident at the same time (`sandbox-next`/`sandbox-stable`/`sandbox-migrate-to-next`, `baoyu-image-gen`, `baoyu-xhs-images`, `lavish`) — the same two-spellings hazard that motivated Q129, and worst for `sandbox-sdk`, where upstream ships an explicit migration skill, meaning the API moved under it. Verified after: the role's own `find-orphans.py` reports zero orphans on six hosts and only `gpt-researcher` on the seventh, with zero dangling links anywhere; `agent-sync sync` pruned 8/8/12/56/12/12 links, exactly 4 per deleted skill. Per-host tarballs and lock backups were written first, as in Q129.
**Outcome:** applied
**Ref:** 37d41d1

## Q132 — interactive/firecrawl-cli-removal — catastrophic-action

**Question:** Q131 deleted the 13 firecrawl skills but left the CLI that generates them, so `firecrawl init` would restore them. The user asked to remove the CLI, then — mid-run — `~/.firecrawl` as well.
**Options considered:** remove the CLI only / remove the CLI and its data directory / leave the data and say so
**Chosen:** Removed the CLI, left `~/.firecrawl` until asked, then removed it too with a tarball first.
**Decided-by:** human
**Justification:** The CLI was not what it looked like twice over, and both mattered. `brew info firecrawl` reports **no such formula** even though the binary sits at `/opt/homebrew/bin/firecrawl` — it is an **npm global** (`firecrawl-cli 1.16.2`) symlinked from `/opt/homebrew/lib/node_modules`, installed by a Homebrew node that is no longer the active one: this host's node is mise-managed (`~/.local/share/mise/installs/node/24.21.0`) and its `npm ls -g` does not list firecrawl at all. So `npm uninstall -g` under the active npm would have been a silent no-op, and the removal had to go through `/opt/homebrew/bin/npm` (55 packages removed) rather than brew or the default npm. Second, `~/.firecrawl` was **not config** — 13 JSON files, 284K, of scraped output (`reddit-claude-code.json`, `hn-ai-tools.json`, `post-*.json`, dated May 13-25), which is work product rather than tool state. That is why it was deliberately left standing when the CLI went, and reported instead: "delete the CLI" does not imply "delete what it produced", and the asymmetry is the whole point — a tool is reinstallable, a scrape result is not. It was removed only after the user asked in a second, explicit instruction, with a `~/firecrawl-data-<stamp>.tar.gz` written first and its path reported so the user can bin that too.
**Outcome:** applied
**Ref:** 02f0c5f

## Q133 — interactive/agent-sync-role — gate-resolution

**Question:** Q130 migrated the fleet to `agent-sync` by hand and flagged that nothing in this repo installs it, so a rebuilt host would lose it. Add a role, and what about the stale `agentstow` naming in `~/.agents/AGENTS.md`?
**Options considered:** a role mirroring the `moshi` tap/trust/install shape / leave it manual and rely on the DECISIONS entry / add the install to the `homebrew` role
**Chosen:** A new `roles/agent-sync`, placed immediately before `skills` in main.yml, plus a 1:1 rename of `agentstow` to `agent-sync` in `~/.agents/AGENTS.md` on all seven hosts.
**Decided-by:** human
**Justification:** Not the `homebrew` role, for the reason `mem:homebrew-tap-trust-required` already records: that role runs early and auto-taps, hitting the untrusted-tap wall *before* any owning role's trust step, which is exactly why 62485a1 moved `multica` and `cc-switch` out of it. Placed before `skills` because it is the tool that maintains that role's per-agent symlink farms. **One gate is non-obvious and would have produced a permanent phantom change:** `brew trust --json v1` records a URL-tapped tap by its **URL** (`https://github.com/agent-sync-sh/agent-sync`), not by its name — there is no `agent-sync-sh/tap` entry anywhere in the ledger — so the `moshi`-style gate on the tap name would never match and the trust command would re-run and re-report `changed` on every play forever. Verified against the live ledger and commented in the role. The role carries **no** `cargo uninstall agentstow` step: the fleet is already migrated, and a host rebuilt from this repo never had the cargo binary, so it would be dead weight from the moment it converged. Crucially the install path was **tested by tearing it down**, not merely by re-running on converged hosts where every task is a no-op by construction: `agent-sync` was uninstalled and the tap removed on dev-server-frank-lume, the role rebuilt it from nothing (tap -> trust -> install, 0 failures, 1.0.1 restored), and the second pass read 0 changed. All seven hosts then converged at 0 changed; ansible-lint clean at production profile; the README row was added in the same commit because a pre-commit hook checks the table against main.yml. For the docs, the six remote hosts were fixed by applying the same **transformation** rather than copying this host's file: five shared one version but macbook-pro-nickel's `~/.agents/AGENTS.md` diverges by 115 diff lines of genuinely host-specific content (a nickel.ai repository-layout section, a local-Chrome-only rule, an X-timeline section), so an overwrite would have destroyed it. `sync`, `adopt` and `status` were confirmed to exist on the new CLI before renaming, so the rename is safe rather than assumed. One `agentstow` mention is left on purpose in each file — the line recording the old name.
**Outcome:** applied
**Ref:** 02f0c5f

## Q134 — interactive/commons-hygiene — gate-resolution

**Question:** Three things surfaced after the agent-sync migration: a duplicate `agentstow` reappeared on mac-mini-m2, `agent-sync` was still fanning skills into a dead OpenClaw, and 11 per-agent directories were byte-identical copies rather than links. Act on which?
**Options considered:** all three / leave the duplicate if it was installed deliberately / OpenClaw cleanup only
**Chosen:** All three. Uninstalled `agentstow`, removed `~/.openclaw` on six hosts (archs-mac-mini excluded), and re-linked all 11 `variant-identical` directories.
**Decided-by:** human
**Justification:** The duplicate needed a real check before removal, because the naive reading was alarming and wrong: the tap's **deprecated** `agentstow` formula is at **2.0.6** while its replacement `agent-sync` is at **1.0.1**, which looks like the fleet was migrated backwards. Upstream releases say otherwise — **the version line reset at the rename**: `v2.0.6` published 2026-09-17T01:34, then `agent-sync-v1.0.0` at 11:10 and `v1.0.1` at 20:45. 1.0.1 is the newest build despite the lower number, so the migration was correct and only the duplicate was wrong. It arrived by `brew install` at 23:56:24 the same night, `installed_on_request: true`, with no match in shell history and not from any command in this session — attribution unresolved, which is the second sighting of an unidentified actor mutating this host's agent state (`mem:soulmachine-skills-cli-copies-shadow-git` records the first). It mattered rather than being cosmetic: the 2.0.6 binary drives the **same** `~/.agents` Commons, so any script or habit using the old name silently ran a pre-rename build against it. The user confirmed it was not deliberate before it was removed. **OpenClaw**: the binary has been absent fleet-wide since Q52-Q54, yet `~/.openclaw/` survived on all seven hosts and `agent-sync` counted it as an installed target, re-creating 123-149 symlinks per host on every sync — dead weight that also meant this session's skill deletions were pruning links in a dead agent's tree. Verified safe before deleting rather than assumed: the directory held **only symlinks**, `0B`, zero regular files and zero real subdirectories on every host, so nothing authored was inside; the removal script re-checks that and refuses otherwise. archs-mac-mini was excluded throughout because Q98 retains its copy as live gateway state, and the user re-confirmed that mid-run. `agent-sync sync` was then re-run on all six to prove the directory is not resurrected — it is not, and the tool now reports three targets instead of four. **Re-links**: `sync` does not fix these (it leaves real directories alone by design), `adopt` does, and the distinction the tool draws is load-bearing — `variant-identical` means a byte-identical copy that should be a link, while a bare `variant` is a deliberate per-agent divergence. Only the former was touched, verified by `--dry-run` first ("would remove … identical to the Commons copy, would leave a link"); mac-mini-m2's genuine `playwright-cli` variant and Claude's `plannotator-*` set were left exactly as they were. Ended at `variant-identical=0` on all seven hosts with the one genuine variant still standing.
**Outcome:** applied
**Ref:** 301a32d

## Q135 — interactive/agents-md-reconcile — interpreted-ambiguity

**Question:** The user asked to sync `~/.agents/AGENTS.md` across all hosts. macbook-pro-nickel's copy diverged by 115 lines. Overwrite it, or preserve what it held?
**Options considered:** copy mac-mini-m2's file to every host / reconcile section by section, moving host-specific content to `AGENTS.local.md` / leave nickel out of the sync
**Chosen:** Reconciled. Nickel's host-specific sections were moved into `~/.agents/AGENTS.local.md` (35 lines) and its shared file replaced with the canonical one. All seven hosts now hold an identical `AGENTS.md`.
**Decided-by:** claude
**Justification:** A plain overwrite was the literal request and would have destroyed three things, so the file was compared section by section rather than by checksum. Two were genuinely host-specific and belong in a local file: a `## Repository layout` section describing nickel.ai's `~/ghe.com/` checkouts, and a `## Reading the X (Twitter) home timeline` section — which this host already keeps in `AGENTS.local.md`, so nickel was simply holding it in the wrong file. That split is not an invention: `AGENTS.local.md` already existed on five of seven hosts, and both `~/.agents/AGENTS.md` and `~/github.com/AGENTS.md` document the sibling-file convention explicitly. The third difference was the dangerous one and is the reason this needed evidence rather than judgement: nickel's `## AI gateway` section described **shared fleet infrastructure differently** — "four OAuth accounts — 3 Claude + 1 Codex Plus" and "every agent CLI reaches models through the gateway" against canonical's three accounts and two-tier optional/mandatory split. One had to be stale, and syncing the wrong direction would have propagated it fleet-wide. Settled by measurement, not by recency: `~/.cli-proxy-api/` holds exactly **three** credential files (2 Claude, 1 Codex Plus), matching canonical and contradicting nickel; canonical also spans loopback aliases `127.0.0.2-.9` where nickel stops at `.8`, consistent with a fleet that has grown since. So canonical won on evidence and nickel's copy was stale documentation, not a local customisation worth keeping. **One preserved item is flagged rather than silently corrected:** nickel's local-Chrome safety rule names the browser to use as `chrome-on-mac-mini-m2` — on macbook-pro-nickel that instruction points at *another machine's* Chrome, which is the exact failure the rule exists to prevent. It was copied verbatim into that host's `AGENTS.local.md` and raised with the user, because silently rewriting a safety rule is worse than an obviously wrong one, and deleting it would remove the only guard there. Backups of both files were written on nickel first. `agent-sync sync` was re-run there so the agent surfaces pick it up; two pre-existing `conflict` lines (opencode and gemini instruction files owned by claude-mem) are unrelated to this change and were left alone. **This is a one-time reconcile, not automation** — nothing syncs `~/.agents/AGENTS.md`, so theseven copies will drift again; the openroutine `sync-agentsmd` task covers only `~/github.com/AGENTS.md`. Raised, not built, since it lives outside this repo.
**Outcome:** applied
**Ref:** 9c70b34

## Q136 — interactive/sync-agentsmd-host-gap — deviation

**Question:** The user asked to extend the openroutine `sync-agentsmd` task to cover `~/.agents/AGENTS.md`, on my statement that it synced only `~/github.com/AGENTS.md`. Extend it how?
**Options considered:** add the path to `PATHS` as asked / find out why the file drifted despite the task, and fix that / leave it manual
**Chosen:** Neither as asked nor as framed. **`.agents/AGENTS.md` was already in `PATHS`** — my premise was wrong. The real gap was that `macbook-pro-nickel` was absent from `HOSTS`, so it was added there instead.
**Decided-by:** claude
**Justification:** Reading the task before editing it is what caught this: `PATHS=(github.com/AGENTS.md github.com/CLAUDE.md .claude/CLAUDE.md .agents/AGENTS.md)`, with the frontmatter description naming all four and a comment dating both dotfile paths to 2026-08-25. Adding the path as literally requested would have been a no-op at best and a duplicate entry at worst, and would have left the actual cause untouched. That cause is simply absence: `macbook-pro-nickel` appears **zero** times in the file, so the task had never looked at that host — it was not the content gate skipping a diverged copy, which is the failure mode the comments are all about. Distinguishing the two mattered, because the documented remedy for a *gated* host (reconcile, then it adopts) is different from the remedy for an *absent* one (add it to the list), and the fix for one does nothing for the other. The first run was predicted before it was allowed to happen, using the task's own probe logic rather than a `-f` test, because the task treats a missing **directory** as `FAILED` and exits 1 — adding a host whose `~/github.com` did not exist would have turned an hourly job permanently red. Nickel returned `__NOFILE__` for both `github.com` paths (directory present, file absent), so the prediction was COPIED, not FAILED. The run matched exactly: `copied=2 updated=0 in-sync=21 skipped-diverged=1 failed=0`, exit 0. `~/.agents/AGENTS.md` landed as **in sync** rather than skipped, which is the payoff from reconciling it by hand first (Q135) — had that not been done, the content gate would have skipped it forever and the "extension" would have appeared to do nothing. `~/.claude/CLAUDE.md` on nickel is SKIPPED as diverged, correctly and by design, and is left for the same `.local.md` treatment; it is called out in the new comment rather than quietly reconciled, since nobody asked for that file. Only the two forward-looking "five" references were changed to "six" — the three historical ones (describing the 2026-08-25 migration that renamed five keys) are statements about the past and were left alone. `bash -n` run against the body before the task was executed, and the file backed up beside itself; `~/coworker` is not a git repo, so that backup is the only history it has.
**Outcome:** applied
**Ref:** 5415207

## Q137 — interactive/claude-mem-symlink-writethrough — gate-resolution

**Question:** `agent-sync` reports 1-3 `conflict` lines on six hosts: opencode's and gemini's instruction files are owned by claude-mem, so those agents never receive the shared Commons instructions. mac-mini-m2 has zero conflicts and symlinks all three. Fan that arrangement out?
**Options considered:** replace the claude-mem files with Commons symlinks, matching mac-mini-m2 / leave the conflicts and let those agents read claude-mem's file / something else once the mechanism is understood
**Chosen:** **Do not fan it out.** The symlink arrangement is unsafe, and the investigation inverted the finding: mac-mini-m2 is not the template to copy, it is the host carrying a latent fleet-wide hazard.
**Decided-by:** claude
**Justification:** The blocking files look free to replace — their entire content is claude-mem's placeholder, verbatim "*No context yet. Complete your first session and context will appear here.*", and macbook-air's `~/.codex/AGENTS.md` is literally 0 bytes — so the obvious move is to symlink them at the Commons as this host does. Reading the writer first is what stopped it. `setupGeminiMdContextSection` (AntigravityCliHooksInstaller.ts:250) reads the target, returns early only if a `<claude-mem-context>` tag is already present, otherwise appends its block and calls `writeFileSync` — and the shared `src/utils/context-injection.ts` writer does the same with no `lstat`, `realpath` or `unlink` anywhere. **`writeFileSync` follows a symlink.** So on a host where those paths point at `~/.agents/AGENTS.md`, the next run reads the 177-line Commons, finds no tag, and writes 177 lines plus a claude-mem block back *through the link into the Commons itself*. That file then differs from the sync source, and `sync-agentsmd`'s content gate skips that host permanently — exactly the drift Q135 and Q136 just cleared. **The hazard is live on mac-mini-m2 specifically, which is the worst host for it:** `~/.gemini/GEMINI.md`, `~/.config/opencode/AGENTS.md` and `~/.codex/AGENTS.md` are all symlinks into the Commons here, `~/.gemini/` exists, the Commons currently has zero `claude-mem-context` blocks, and the installer's entry guard checks only for its worker-service path — it never checks whether Gemini is actually installed, so "gemini is absent on this host" is not protection. This host is also the **source** the hourly task pushes from, so a single claude-mem write here would propagate the polluted file to all six hosts as `UPDATED` on the next run. The trigger is dated and predictable rather than hypothetical: the `claude-mem` role runs `npx -y claude-mem install` whenever the installed version differs from npm's, so the next claude-mem release fires it. Nothing was changed, because the right remedy is a design choice the user has to make — the `import-line` mechanic that `~/.claude/CLAUDE.md` already uses (`@~/.agents/AGENTS.md` on line 9) coexists with claude-mem safely, since claude-mem appends to a real file while the import still pulls the Commons in, but agent-sync picks the mechanic per agent and chose symlink for these two, so forcing it is not a one-liner. Raised with evidence instead.
**Outcome:** raised
**Ref:** 64a8696

## Q138 — interactive/nickel-reconcile-finish — gate-resolution

**Question:** After Q136, nickel's `~/.claude/CLAUDE.md` was still SKIPPED as diverged, and its preserved local-Chrome rule named another machine's browser. Fix how?
**Options considered:** split host-specific parts into `CLAUDE.local.md` as Q135 did for AGENTS.md / delete the far copy and let the task re-seed it / guess nickel's Chrome name
**Chosen:** Deleted nickel's `~/.claude/CLAUDE.md` so the task copied the source, and rewrote the Chrome rule without any hardcoded browser name.
**Decided-by:** claude
**Justification:** The `.local.md` split was the expected fix and turned out to be unnecessary, which only the diff showed: nickel's copy was a strict **subset** of the source — the diff carried `<` lines only, no `>` line anywhere, missing the `## graphify` section and some blank lines. So it held nothing host-specific and nothing to preserve, making the task's own cheapest documented remedy the correct one: "an absent file is COPIED, not skipped". Backed up, deleted, and the next run copied it; the fleet now reports `skipped-diverged=0` across all four paths and six hosts, 23 in sync plus that one copy. For the Chrome rule, **the name was removed rather than guessed.** No `chrome-on-*` identifier is recorded anywhere on nickel, and inventing one is worse than leaving the wrong one: a name that matches no paired browser could let an agent fall through to any browser at all, which is the failure the rule exists to prevent, whereas the invariant itself ("only the Chrome on this machine, never another machine's, ask the user to confirm through the in-Chrome Connect prompt when the list is ambiguous") is enforceable without naming anything. The stale `chrome-on-mac-mini-m2` instruction is gone, a dated TODO records what was removed and why so the fact is not silently lost, and the file picked up the header convention macbook-air's local file already uses. The X-timeline section was carried across verbatim rather than re-typed.
**Outcome:** applied
**Ref:** 64a8696

## Q139 — interactive/agent-instruction-mechanics — deviation

**Question:** Q137 raised the claude-mem symlink write-through hazard and named the import-line mechanic as the safe shape. The user said to use it: "use the import-line mechanic `~/.claude/CLAUDE.md` already uses too". Apply it to codex, opencode and gemini?
**Options considered:** write `@~/.agents/AGENTS.md` into all three instruction files as asked / change agent-sync's `registry.rs` to assign `ImportLine` to those agents / verify each agent actually parses an import line first, then pick per agent
**Chosen:** Verified first — and **none of the three can consume an import line**, so the requested mechanic was not applied anywhere. The hazard was removed by making the two written-to files real, and opencode was given the Commons through its own `instructions` config key instead. Codex was left on its symlink, which is both safe and its only working mechanism.
**Decided-by:** claude
**Justification:** Q137's own recommendation was wrong and would have failed silently — an unparsed `@path` line leaves the agent with **no instructions at all**, which looks identical to working. agent-sync's rationale comment is about ownership, not capability ("Claude users keep their own content in CLAUDE.md"), so it could not settle this; each agent was measured. **Codex 0.155.0: no.** `codex debug prompt-input` renders the model-visible prompt as JSON — a temp `AGENTS.md` holding a sentinel plus `@/tmp/import-probe.md` put the host file's own sentinel in the prompt (1 match) and the *imported* sentinel nowhere (0 matches), with the `@` line arriving verbatim ahead of `</INSTRUCTIONS>`. Upstream tracks it as openai/codex#6038 and #17401, so re-test after a Codex upgrade. **OpenCode 1.18.31: no** `@` syntax at all, but its schema carries `instructions` — "Additional instruction files or patterns to include" — which is the same effect by a supported route. **Gemini: parses imports and refuses this one.** The bundle does ship the processor (`processImports` ×11, `circular import` ×3), which is exactly why reading further mattered: `validateImportPath` is `path.resolve(basePath, importPath)` tested against `[projectRoot || '']`, with **no `~` expansion anywhere in that path** — the one `homedir()` tilde-expansion in the bundle belongs to sandbox-denial handling. Memory discovery passes `projectRoot = undefined`, so it falls back to `findProjectRoot(dirname(file), ['.git'])`, which walks up and — finding no marker — **returns the start directory itself**. For `~/.gemini/GEMINI.md` the allowed set is therefore `[~/.gemini]`, and any home-level target renders `<!-- Import failed: … - Path traversal attempt -->`. No fleet host has `~/.git` (checked on all seven), and a relative `@../.agents/AGENTS.md` fails the same test, so Gemini has no route to the Commons short of duplicating it — it is left as it already was on five hosts. **The hazard is not uniform either, which changed what needed fixing:** `~/.config/opencode/AGENTS.md` goes through `injectContextIntoMarkdownFile`, which writes **unconditionally on every call** (replaces the block if the tag is there, appends if not) — one write per session, the hot path; `~/.gemini/GEMINI.md` writes **once** behind an `includes(contextTag)` early return; and `~/.codex/AGENTS.md` is **strip-only** — `readAndStripContextTags` returns early unless *both* tags are present, because Codex moved to native hooks, so a Commons symlink there is never written and Q137's worry about that third path does not hold. Actual state was also not what Q137 assumed: the opencode symlink existed on mac-mini-m2 **only**, gemini's on two hosts (mac-mini-m2 and dev-server-frank-lume), and macbook-air's `~/.codex/AGENTS.md` was a 0-byte **real** file — so that host's Codex was getting nothing, and it was converted to the symlink the other six already had. Replacement placeholders were generated and checked against the fleet's own files by md5 before any host was touched (`2623bad4…` 241 bytes, `2f612b00…` 156 bytes), the script is idempotent (re-run on two hosts: all four steps report "already"), opencode.json was backed up per host and round-tripped through `json` so the gateway provider, three plugins and both MCP servers survived, and `opencode debug config` confirms the key in the **resolved** configuration rather than merely in the schema. The Commons reads 177 lines with zero `claude-mem-context` blocks on all seven hosts afterwards. Two consequences are accepted rather than fixed: `agent-sync` will keep reporting `conflict` on those two paths on all seven hosts, because its compiled-in registry wants symlinks there and that is now the correct state; and nothing in this repo provisions any of it, so a rebuilt host returns to the old arrangement. Changing `registry.rs` upstream is the durable fix and was not attempted — it is a third-party tool needing a rebuild and a fleet reinstall.
**Outcome:** applied
**Ref:** REFPLACEHOLDER139

## Q140 — interactive/nickel-chrome-rule-removal — interpreted-ambiguity

**Question:** The user asked to "remove the local the Chrome rule on all hosts". Q138 had just written that rule into macbook-pro-nickel's `AGENTS.local.md` with a dated TODO. Which rule, and on which hosts?
**Options considered:** remove the shared `## Browser automation (claude-in-chrome)` section from `~/.agents/AGENTS.md` fleet-wide / remove the host-local `**Local Chrome only**` rule wherever it exists / remove both
**Chosen:** Removed the **host-local** rule only — the `## Browser automation — this machine` section in nickel's `~/.agents/AGENTS.local.md`. The shared fleet-wide Chrome section in `~/.agents/AGENTS.md` was left untouched on every host.
**Decided-by:** claude
**Justification:** "the local … Chrome rule" distinguishes it from the shared one, and the two are different rules with different jobs: the shared section says to reuse a running Chrome and not close the user's tabs, while the local one was the never-drive-another-machine's-browser guard. Deleting the shared section would have been a fleet-wide behaviour change nobody asked for. "On all hosts" was taken literally rather than assumed to mean nickel: every instruction file that could plausibly carry it was grepped for the rule's own text across all seven hosts — `~/.agents/AGENTS.{md,local.md}`, `~/.claude/CLAUDE.{md,local.md}`, `~/github.com/{AGENTS,CLAUDE}.local.md` and the three agent files — and **exactly one** match existed, nickel's. So the request is satisfied fleet-wide by a single edit, which is worth recording because it differs from what the phrasing implies. Cut by an anchored `perl` range from the heading to the next `## `, not by line numbers, with a dated backup beside the file; the section's trailing blank line and the whole TODO block went with it, `grep -ci chrome` on the result is 0, and the surrounding `## Repository layout` and `## Reading the X (Twitter) home timeline` sections are intact. This retires Q138's open TODO by deletion rather than by supplying nickel's paired browser name, which is still unknown — so the guard Q138 deliberately preserved is now gone, and only the shared reuse-the-running-instance rule applies there.
**Outcome:** applied
**Ref:** REFPLACEHOLDER140

## Q141 — interactive/typesafe-ai-skill-pin — interpreted-ambiguity

**Question:** The user asked to add `npx skills add typesafe-ai/skills --skill typesafe-ai -g -y` to the skills role. `skills_sources` installs with `--all`; `skills_sources_partial` names individual skills. Which list?
**Options considered:** `skills_sources` (`--all`), since the source ships exactly one skill and the two are equivalent today / `skills_sources_partial`, pinning the one skill as the user's command spells it
**Chosen:** `skills_sources_partial`, with the pin.
**Decided-by:** claude
**Justification:** Checked upstream before pinning, the way this file's own comments require — `npx skills@latest add typesafe-ai/skills -l` lists without installing and reports **"Found 1 skill"**, named `typesafe-ai`. That makes the two lists behave identically right now, and the repo's precedent cuts the other way: `swe-workflow/log-decisions` and two others sit in `skills_sources` under the note "Each ships exactly one skill upstream". The pin was still chosen for what it does *later*: a one-skill source that grows would hand `--all` the additions unreviewed, and this file already documents why that matters — `warpdotdev/common-skills` ships a `complain` skill that "posts anonymously to Slack unprompted and is instructed never to mention having done so", which is why that source is pinned rather than taken whole. It is also the form the user actually wrote. `-g -y` needed no handling: the partial task already supplies `-g -y --agent '*'` and builds repeated `--skill` flags, so the entry is two lines and no task changed. Verified by running the role standalone: the store gained `~/.agents/skills/typesafe-ai` (SKILL.md + LICENSE), the lock recorded `typesafe-ai/skills` → `skills/typesafe-ai/SKILL.md`, and it fanned out to all three symlink-farm agents (`~/.claude/skills`, `~/.pi/agent/skills`, `~/.hermes/skills`). Not rolled out to the fleet — the nightly sweep will carry it, as with Q128.
**Outcome:** applied
**Ref:** REFPLACEHOLDER141
