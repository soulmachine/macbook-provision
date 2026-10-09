# paseo role

`paseo` branches on `mac_is_always_on` instead of skipping. A MacBook gets the `paseo` cask
(Paseo.app, which bundles its own daemon). An always-on Mac, or a non-macOS host, gets upstream's
server install, `npm install -g @getpaseo/cli`, and has the cask **removed**, because nobody sits at
those boxes to use a desktop app. The npm install is diffed with `npm ls -g`, the same gate as
`obsidian` and `playwright-cli`. A hand-written `"npm:@getpaseo/cli" = "0.8.0"` pin in mise's global
config had been shadowing both installs on five hosts, and the role removes it everywhere.

Its `tags: [agent-multiplexer]` reaches `host-facts` with no `tags: always`, because a role's tags are
inherited by its meta dependencies.

## The daemon on always-on Macs

The role owns the `sh.paseo.daemon` LaunchAgent (DECISIONS Q176), so every such host runs the daemon.
It installs `files/sh.paseo.daemon.plist`, which runs `zsh -lc "exec paseo daemon run"`, and loads the
agent whenever launchd does not have it, including one someone unloaded on purpose. It also turns on
the relay (`daemon.relay.enabled`, off by default). The daemon listens on 127.0.0.1 only, so the relay
is the only way a paired device reaches it. `paseo daemon config set` only saves the file, so a change
goes through the same reload. Pairing (`paseo daemon pair`) stays manual, because the pairing link is
a per-host secret.

Five things are easy to get wrong:

- **0.10 removed `--foreground`.** The old hand-written agents survived only because the 0.8.0 pin won
  on PATH. Once the pin was gone they exited 1 in a loop every ThrottleInterval. The role's plist
  replaces that line.
- **`paseo` is launched by name, through a login shell, on purpose.** The nodejs role's
  `mise upgrade node` deletes the old Node version, and the npm global with it. The daemon's workers
  run on the full path of the Node they started on, so even a running daemon breaks. The paseo role
  then sees `@getpaseo/cli` go from absent to present, and the reload starts the daemon on the new
  Node. A mise pin would not help: a Node upgrade breaks it the same way, and with Paseo's version
  unchanged nothing would trigger a restart.
- **Every change leaves the daemon stopped or on deleted code.** The cask's uninstall stanza runs
  `paseo daemon stop --force`, an npm install replaces its files, and the pin removal prunes the tree
  it was launched from. `mise unuse` only edits the config, so `mise prune` follows it. So any change,
  or a new plist, reloads the agent.
- **Reload means bootout plus bootstrap, with a wait between them.** `kickstart -k` would restart the
  cached old command line. `bootout` returns before the daemon finishes its roughly 6 s graceful
  shutdown, and a `bootstrap` in that window fails with rc 5 and leaves the agent unloaded (measured
  2026-10-04). The task polls `launchctl print` until the service is gone.
- **A loaded agent is not a running daemon.** archs-mac-mini's daemon failed on every start for about
  a week (a stale, empty `~/.paseo/paseo.pid`) while `launchctl print` still found the agent. So after
  loading, the role asks `paseo daemon status --json` for up to 60 s. If the daemon is not `running`,
  it sets the host fact `paseo_daemon_down`, and a `main.yml` post_task fails the play on it, so the
  sweep's `failed=0` check sees it while the roles after paseo still run. On this ansible-core,
  `until` with `failed_when: false` does not fail the task when the retries run out (verified
  2026-10-04). The post_task is tagged `agent-multiplexer`, because untagged post_tasks are skipped in
  a tag-limited run.

## The paseo-bots plugin on always-on Macs

The role installs `npm:@oliexe/paseo-bots` (DECISIONS Q192). Paseo ships with its global
`pluginsEnabled` switch off, and an installed plugin stays `disabled` until it is on, so the role turns
it on first. That was the user's choice, made after reading Paseo's warning that plugins are
unsandboxed code. It applies the switch with `paseo reload`, not the launchd bounce, because a bounce
kills the daemon's running agents. Both steps wait for the daemon to be running. The role installs the
plugin only when `paseo plugin ls` lacks it and never runs `paseo plugin update`, because each update
trusts new code. Run that by hand.

`~/Library/LaunchAgents` is 700 on some hosts and 755 on others. The task that ensures the directory
exists uses `mode: u+rwx`, so it changes neither.
