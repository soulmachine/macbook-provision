# orca role

[Orca](https://onorca.dev) is an IDE that runs coding agents across worktrees. The role splits on
`mac_is_always_on` like `paseo` (DECISIONS Q243). A MacBook gets the desktop app. An always-on Mac
gets the desktop app and the Orca server.

## Every Mac keeps the cask

Orca has no separate server package. The `orca` CLI and `orca serve` ship inside Orca.app, and the
`stablyai/orca/orca` cask links that CLI to `/opt/homebrew/bin/orca`. So an always-on Mac keeps the
cask, where paseo removes it. The cask is `auto_updates true`, so the role installs it `present`
with `--adopt` and lets the app update itself. Adopting matters on hosts that installed the DMG by
hand.

The app's own "Install CLI" button writes `/usr/local/bin/orca` as a root-owned symlink with mode
0700. A user cannot readlink it, so the CLI fails with "Unable to determine Orca.app path from
symlink". On macbook-pro-nickel that link comes before Homebrew's on PATH, so a plain `orca` broke
there. The role removes any symlink at that path, and calls the cask's link,
`/opt/homebrew/bin/orca`, by full path.

Settings → General → Orca CLI already shows the CLI as registered. On macOS the app takes the first
`orca` on the login shell's PATH, and the cask's link comes first and points at the app's
launcher. So the role registers nothing more, and the old "Install CLI" button is not needed.

## The server on always-on Macs

The role does not write its own LaunchAgent. It runs upstream's `orca serve service install --port
6768`, which writes and loads a LaunchAgent that runs `orca serve --supervise --no-pairing`. The
supervisor restarts the server with growing delays. It waits while an update replaces the app or
while the desktop app is serving the same profile. After 6 failures in 15 minutes it gives up.
`orca serve service install` is also what clears a supervisor that gave up.

- **It installs only when `orca serve service status --json` is not `live`.** A reinstall restarts
  the server and kills its sessions. So a converged host is never touched, and a change of flags
  (port, address, PATH) needs a manual `orca serve service install --port 6768 --command
  /opt/homebrew/bin/orca --pairing-address <tailscale-ip>`.
- **Port 6768 is fixed,** so paired clients keep their address across restarts.
- **It advertises the host's Tailscale IPv4** (`tailscale ip -4`) with `--pairing-address`, so a
  pairing offer names an address that macbook-pro-m3 reaches. It is an IP, not a MagicDNS name,
  because one fleet host answers `*.ts.net` from a fake-IP resolver. Without Tailscale, the role
  leaves the flag out.
- **`--command /opt/homebrew/bin/orca`** pins the cask's link in the LaunchAgent.
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

- **Pairing.** The service never prints a pairing link. When the desktop app is open on the server,
  pair from it: Settings → Remote Orca Servers → Advertise this app as a server → **New Link**,
  pick the `100.x.y.z` address, then **Generate Access Link**. Otherwise, on the server:
  1. `orca serve service uninstall`, which frees the profile.
  2. `orca serve --port 6768 --pairing-address <tailscale-ip>` in a terminal. It prints a pairing link.
  3. On the client, paste the link into **Add Server**, or run
     `orca environment add --name <host> --pairing-code '<link>'`.
  4. Ctrl+C the server, then `orca serve service install --port 6768 --command
     /opt/homebrew/bin/orca --pairing-address <tailscale-ip>`.

  The link is a secret: do not paste it into a file or a chat. Do not run step 2 while the app
  serves the same profile, because `orca serve` then exits with code 3. Each client gets its own
  grant: revoke one in the server's app under **Shared Server Access**. A new link replaces the
  last unused one. If the client shows the server as Disconnected, click **Connect**.
- **Agent accounts and skills** must be set up in the server's own shell, because a paired client
  disables Add account, and remote sessions use the server's PATH, home and logins:
  `orca account add --agent claude|codex`. The role installs the `orca-cli` skill on every run
  (`orca skills install --skill orca-cli`), which also updates it when Orca ships a newer copy. Add
  others by hand, such as `orca skills install --skill orchestration`.

Source for the steps: <https://www.onorca.dev/docs/remote-servers>.
