# Secrets, `.env` and GitHub tokens

## `.env`

`.env` and `.envrc` are optional, gitignored and per-machine. `.env.example` lists every variable.
Values legitimately differ across the fleet: a Tailscale auth key is tailnet-scoped, so hosts on
different tailnets carry different keys. That divergence is correct, not drift to reconcile.

- The `tailscale` role reads `TAILSCALE_AUTH_KEY` (to run `tailscale up`) and, optionally, a
  `devices:core` OAuth client as `TAILSCALE_OAUTH_CLIENT_ID` + `TAILSCALE_OAUTH_CLIENT_SECRET` (to
  disable node-key expiry). See `roles/tailscale/README.md`.
- The `typesafe` role reads `TYPESAFE_API_KEY`. `GITHUB_SSH_KEY` is optional and unset across the
  fleet.
- **`GITHUB_TOKEN` is not in `.env` on any host** (since 2026-10-03). `~/.local/bin/gh-token-fleet`
  owns the PAT and exports it in `~/.zshenv` below the `dotenv` managed block. A copy in `.env` made
  the two overwrite each other. See `~/.agents/docs/github-auth.md`. The `github`, `bun` and `mise`
  roles read it from the environment, with a `gh auth token` fallback.

## The `dotenv` role

direnv loads `.env` only in an interactive shell: `.envrc` runs `dotenv_if_exists .env`, and direnv
is hooked from `~/.zshrc`. Every other shell sees none of it: `ssh host 'cmd'`, git hooks, launchd,
and the `zsh -lc "… ansible-playbook …"` form in AGENTS.md, which is a login shell but not an
interactive one. Roles that gate on `lookup('env', VAR) | length > 0` then skip silently. So the
role exports `.env` into `~/.zshenv`, the one startup file every zsh reads, inside a managed block
(DECISIONS Q68/Q69).

Four things are load-bearing:

- **It reads the `.env` file, never `lookup('env', ...)`.** The lookup reads the ambient environment,
  which is exactly what is missing. On a fresh host it would write an empty block; on a host whose
  `.env` changed it would write back the stale values from the old block.
- **An empty parse fails the play.** `blockinfile` would write a block with no exports and strip
  every variable from every non-interactive shell. A `.env` that yields no assignment is a parse bug,
  so an `assert` stops it. A missing `.env` is legitimate (the file is per-machine): that path skips
  and says so, because "no `.env` here" and "run from the wrong directory" look the same in the recap.
- **`no_log: true` is affordable only because of `validate: zsh -n %s`.** The block is the
  credentials, so without `no_log` any `-v` or `--diff` prints them, but `no_log` also hides a failure
  message. `validate` checks the candidate before anything is written, so a bad parse leaves the live
  file untouched, and `zsh -n ~/.zshenv` reproduces the error. A broken `~/.zshenv` breaks every zsh
  on the host.
- **`{% set %}` inside the `block:` template renders as empty.** Ansible's inline templating does not
  carry the binding out, which once turned the whole block into `export =''` four times. So the names
  and values are built as two parallel lists in `vars/main.yml`, and the template only indexes them.

The markers are asymmetric (`# --- macbook-provision .env (managed) ---` /
`# --- end macbook-provision .env ---`) because they match the hand-written blocks that were already
on the hosts, so the role adopted those in place. That is why `marker_begin` and `marker_end` are set
separately instead of one `{mark}`.

## Borrowing gh's token for GitHub API rate limits

The unauthenticated GitHub API allows 60 calls an hour per IP, shared by every tool on the box, so
the allowance is often spent before a play runs. `bun upgrade` feels it most: it resolves the newest
release from `api.github.com/repos/Jarred-Sumner/bun-releases-for-updater/releases/latest` and, on a
403, exits non-zero with `Bun upgrade failed with error: HTTPForbidden` even when bun is current. An
authenticated call gets 5000 an hour. bun reads `GITHUB_TOKEN` / `GITHUB_ACCESS_TOKEN`, so the
fleet's exported PAT reaches it with no plumbing. The bun role's `gh auth token` lookup is only the
fallback for a host with no exported token.

**Blank both `GH_TOKEN` and `GITHUB_TOKEN` when you shell out to `gh auth token`.** gh resolves
`GH_TOKEN`, then `GITHUB_TOKEN`, then the keyring, so either variable makes the command echo back the
value the fallback exists to replace. With a stale PAT the request then fails 401 instead of 403,
which reads as an unrelated bug. Set `environment: {GH_TOKEN: "", GITHUB_TOKEN: ""}` on the lookup
task to force the keyring credential. A spent rate limit is an expected outcome, so that task uses
`failed_when: false` (see [writing-roles.md](writing-roles.md)).
