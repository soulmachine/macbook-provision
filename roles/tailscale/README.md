# tailscale role

**Scope:** Tailscale is only a network layer here (private mesh + MagicDNS). The role does not enable
Tailscale SSH; standard OpenSSH handles remote shells. That is why there is no `--ssh` flag, no
`tag:server`/`tag:laptop` advertisement, no ACL `tagOwners` management, no Full Disk Access prompt for
`/Applications/Tailscale.app`, and no laptop-vs-server branching. If you turn Tailscale SSH back on,
reintroduce the FDA grant (so SSH child shells inherit working TCC) and, for per-machine ACL gating,
`--advertise-tags` plus the API-driven `tagOwners` update.

- **It installs the standalone Tailscale.app** through the `tailscale-app` cask (the tailscale.com
  build, not the sandboxed App Store one). The cask is a `.pkg`, so brew calls `sudo`, which
  passwordless sudo lets run unattended. The cask ships the GUI app and the embedded `tailscaled`, but
  **not** the CLI: the `.pkg` installs only the app bundle (`pkgutil --files com.tailscale.ipn.macsys`),
  and nothing creates `/usr/local/bin/tailscale`. Per <https://tailscale.com/kb/1080/cli>, the
  standalone build installs that launcher only when the user clicks Settings → CLI integration →
  "Show me how" → Install Now and authenticates. A symlink to the app binary is no substitute (it
  stays in GUI mode and exits `Tailscale.CLIError error 3`), and on Apple Silicon `/usr/local/bin` may
  not exist. MagicDNS configures itself through the Network Extension; no `/etc/resolver/ts.net` is
  needed.
- **Two GUI-only steps are gated, and they fail the play rather than prompt.**
  `ansible.builtin.pause` on a non-interactive stdin only warns and continues, so the play used to run
  past the gate and die later on something unrelated-looking. Both gates fail at the point of
  detection with the remedy. Re-run the playbook after doing the step.
  - **Network Extension.** The role captures `systemextensionsctl list | grep -i tailscale` (not
    `grep -q`, so the failure message can quote the state) and gates on `[activated enabled]`. If it is
    absent (disabled, `activated waiting for user`, or no row because Tailscale.app never launched),
    the role runs `open -a Tailscale`, which registers the extension and makes the toggle appear, then
    fails, pointing at System Settings → General → Login Items & Extensions → Network Extensions →
    Tailscale ON. The "would like to add VPN configurations" dialog on first launch is part of the
    same flow. `systemextensionsctl` is the source of truth; there is no marker file.
  - **CLI launcher.** Gated on `stat /usr/local/bin/tailscale`, inside a block gated on
    `(auth key set) or (OAuth configured)`. Both credential paths need the CLI (`tailscale up` to
    enrol, `tailscale status --json` for the device ID), so either one arms the gate; with neither,
    the role converges on the cask install alone.
- **Auto-login when `TAILSCALE_AUTH_KEY` is set.** The role runs `tailscale up --accept-dns
  --accept-routes --operator=$USER --auth-key=...` under `become: true`, skipped when the node is
  already `BackendState: Running`. `tailscale up` rejects a call that drops a previously set
  non-default flag (it needs `--reset` or every non-default flag restated), so the role lists every
  non-default flag the daemon was last brought up with. `--accept-routes` is there for that reason and
  to receive subnet routes from other nodes.
- **Key-expiry disable takes an OAuth client and nothing else.** With `TAILSCALE_OAUTH_CLIENT_ID` and
  `TAILSCALE_OAUTH_CLIENT_SECRET` both set, the role form-`POST`s them to `/api/v2/oauth/token` (no
  `grant_type`; Tailscale's documented curl omits it), reads `Self.ID` from `tailscale status --json`,
  and `POST`s `keyExpiryDisabled: true` to `/api/v2/device/{id}/key`. The bearer token lives exactly
  one hour (`expires_in: 3600`, not configurable). The client needs only the `devices:core` scope,
  whose endpoint list names that POST.
  - **No personal access token.** A PAT carries no scopes (this repo's read back as
    `["all","all:read"]`) and expires after 90 days, which made this task a 401 on a timer. An OAuth
    client secret does not expire (`expires: null`), belongs to the tailnet, and is revocable alone.
  - **Half a pair fails the play.** The block is otherwise gated on a credential being present, so a
    half-configured host would silently skip key-expiry disable and drift back to expiring keys.
  - An OAuth client secret cannot be a bearer token directly, hence the exchange. It can go straight
    to `tailscale up --auth-key=`, but that needs the `auth_keys` scope and forces tag ownership on the
    node, so `TAILSCALE_AUTH_KEY` stays a separate credential. Clients are created in the console
    only: `GET /api/v2/tailnet/-/oauth-clients` and `.../oauth_clients` both return 404.
- **The two credentials gate different halves of the role, deliberately unchained.**
  `TAILSCALE_AUTH_KEY` enrols the node once; the OAuth client authenticates control-plane calls
  ongoing. The key-expiry block is gated on `tailscale_oauth_configured` alone, and all credentials
  load up front. (It once also required the auth key, by accident of layout, so blanking a spent key
  silently switched off key-expiry maintenance.)
  - The block reads `Self.ID` **first**, before minting a token, so an unenrolled host does not burn a
    credential, and it emits a `debug` no-op when there is no ID: an unenrolled machine is a legitimate
    mid-setup state. Every extraction step defaults (`stdout | default('{}', true)`,
    `.Self | default({}, true)`, `.ID | default('', true)`), because an unenrolled node yields an empty
    stdout, a null `Self`, or a `Self` without `ID`, depending on how far setup got. The read is a
    fresh `tailscale status`; the enrolment block's copy predates `tailscale up` on a first run.
- **The key-expiry POST is gated on a read.** `GET /api/v2/device/{id}?fields=all` returns
  `keyExpiryDisabled` (only with `?fields=all`), and the POST is skipped when it is already `true`. The
  POST returns 200 either way, so without the read the role reports a change on every run.
- **The OAuth and device-read `uri` tasks carry `check_mode: false`;** the final POST does not, so it
  stays skipped under `--check`. Minting a one-hour token changes no durable state.
