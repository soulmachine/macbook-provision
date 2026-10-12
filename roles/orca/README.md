# orca role

[Orca](https://onorca.dev) is an IDE that runs coding agents across worktrees. The role splits on
`mac_is_always_on` like `paseo` (DECISIONS Q243). A MacBook gets the desktop app. An always-on Mac
gets the desktop app and the Orca server.

## Every Mac keeps the cask

Orca has no separate server package. The `orca` CLI and `orca serve` ship inside Orca.app, and the
`stablyai/orca/orca` cask links that CLI to `/opt/homebrew/bin/orca`. So an always-on Mac keeps the
cask, where paseo removes it. The cask is `auto_updates true`, so the role installs it `present`
with `--adopt` and lets the app update itself. Adopting matters on hosts that installed the DMG by
hand. The app's own "Install CLI" button writes a root-owned `/usr/local/bin/orca` that comes after
Homebrew's on PATH. On Franks-Mac-mini-M2 that link is dead ("Unable to determine Orca.app path"),
and the role leaves it alone.

## The server on always-on Macs

The role does not write its own LaunchAgent. It runs upstream's `orca serve service install --port
6768`, which writes and loads a LaunchAgent that runs `orca serve --supervise --no-pairing`. The
supervisor restarts the server with growing delays. It waits while an update replaces the app or
while the desktop app is serving the same profile. After 6 failures in 15 minutes it gives up.
`orca serve service install` is also what clears a supervisor that gave up.

- **It installs only when `orca serve service status --json` is not `live`.** A reinstall restarts
  the server and kills its sessions. So a converged host is never touched, and a change of flags
  (port, PATH) needs a manual `orca serve service install --port 6768`.
- **Port 6768 is fixed,** so paired clients keep their address across restarts.
- **It runs through `zsh -lc`.** The LaunchAgent pins the PATH it was installed with, and the agent
  CLIs the server spawns live on mise's shims.
- **A loaded agent is not a live server.** After installing, the role polls the status for up to 60
  s. If the server is not `live`, it sets `orca_serve_down`, and a `main.yml` post_task tagged
  `agent-multiplexer` fails the play after the other roles have run.
- **Orca 1.4.224 has no `serve service`.** The subcommand and `--supervise` landed upstream on
  2026-10-12 (stablyai/orca #27716, #27744), after the latest release. Until the app updates itself
  to a release that has them, the CLI answers `invalid_argument`, and the role skips the server with
  a message instead of failing.

## By hand

- **Pairing.** The service never prints a pairing link. Pair from the desktop app (Settings → Remote
  Orca Servers), or stop the service and run `orca serve --port 6768 --pairing-address <tailscale-ip>`
  in a terminal. Then paste the link into **Add Server** on the client. Do not run both at once.
- **Agent accounts and skills** on the server: `orca account add --agent claude|codex` and
  `orca skills install`.
