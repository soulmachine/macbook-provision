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
**Ref:** (pending)

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
**Ref:** (pending)

## Q34 — interactive/tailscale-api-credential — deviation

**Question:** The ask was a credential swap only. The key-expiry `POST` was unconditional, so it reported CHANGED on every converged run. Fix that in the same change, or leave it?
**Options considered:** leave it, credential-only as asked / gate the POST on a `GET .../device/{id}?fields=all` read of `keyExpiryDisabled` / set `changed_when: false` to silence it
**Chosen:** Gate the POST on the read.
**Decided-by:** agent
**Justification:** Scope expansion, taken because the role was already being restructured around the same request and the repo's `ansible-idempotency-check` skill exercises exactly this path. `changed_when: false` was rejected as the inverse error — it would hide a real change rather than detect one. The read is what the repo's "diff state, don't grep output" rule prescribes: the POST returns 200 whether or not it altered anything, so its response cannot distinguish the two. Verified live on this host — the POST now reports `skipping` and the role runs `changed=0`, where before it was CHANGED every run. `?fields=all` is load-bearing; the default field set omits `keyExpiryDisabled`. Cheap to reverse: one `when:` and one task.
**Outcome:** applied
**Ref:** (pending)
