Ansible playbook that provisions each Mac in Frank's fleet with Homebrew, mise, npm and agent
installers. Every host runs it on itself.

## Commands

Run them from the repo root: `.env` and the single-role form both resolve against it.

```bash
./bootstrap.sh                                        # fresh Mac: Xcode CLT, Homebrew, mise, Ansible, passwordless sudo
ansible-playbook main.yml --limit 127.0.0.1           # provision this machine
ansible-playbook main.yml --limit 127.0.0.1 --check   # dry run
ansible localhost -m include_role -a name=<role>      # one role; host-facts classifies the machine itself

# another fleet host: over ssh in a login shell, because only ~/.zprofile puts brew on PATH
ssh -o BatchMode=yes -o ConnectTimeout=15 <host> \
  'zsh -lc "cd ~/github.com/soulmachine/macbook-provision && git pull && ansible-playbook main.yml --limit 127.0.0.1"'
```

## Every task

- **Runs per-host only.** `inventory` holds only `127.0.0.1 ansible_connection=local`, so each host
  provisions itself. Keep it that way, and reach other hosts with the ssh command above. The roles read
  `lookup('env', 'HOME')` in 99 places across 27 roles (`scripts/check-home-lookup-count.sh` checks
  this), with zero uses of `ansible_env.HOME`. Ansible evaluates every `lookup()` on the control node,
  so a fan-out writes one host's `$HOME` and `.env` secrets onto every target. The nightly sweep
  (`update-packages` on mac-mini-m6) therefore runs the playbook on each host over ssh.
- **Self-update tasks: diff state, don't grep output.** A task that runs a tool's own updater measures
  a version, checksum or ledger before and after the call, and sets `changed_when` on the difference.
- **`gateway/` is live on mac-mini-m2.** m2's `~/.local/bin/cliproxy-*` are symlinks into this
  checkout, so an edit takes effect there at once. The playbook never runs them.

## Read before you act

| Before you… | Read |
|---|---|
| add a role, or write or change any role's tasks | [docs/writing-roles.md](docs/writing-roles.md) |
| gate a role on `mac_is_always_on`, or touch `host-facts` | [docs/host-facts.md](docs/host-facts.md) |
| touch `.env`, a secret, `GITHUB_TOKEN`, or the `dotenv` or `bun` role | [docs/secrets.md](docs/secrets.md) |
| change agent-reach, paseo, ponytail, tailscale or typesafe | that role's `roles/<name>/README.md` |
