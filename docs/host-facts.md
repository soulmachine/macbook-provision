# host-facts and the always-on gate

`host-facts` is the first role in `main.yml`. It sets `mac_family`, `mac_is_vm` and
`mac_is_always_on`.

`hermes` runs a long-lived local service (its agent process, its own checkout, Chromium and
messaging gateways), which earns its keep only on a Mac that stays up. So it installs only where
`mac_is_always_on` is true, and so does the half of `ponytail` that installs into Hermes; the rest of
`ponytail` is ungated. `paseo` branches on the gate instead of skipping; see
`roles/paseo/README.md`.

## The rule: a MacBook blacklist, fail-open

`host-facts` reads `machine_name` from `system_profiler -json SPHardwareDataType` into `mac_family`
and sets `mac_is_always_on` to `mac_is_vm or not mac_family.startswith('MacBook')`. A VM is
always-on, a MacBook (plain, Air or Pro) is not, and every other family is, including families
nobody has seen yet. `sysctl -n hw.model` cannot do this job: every Apple Silicon Mac reports the
family-less `MacN,M` form (Mac mini M2 is `Mac14,3`, MacBook Air M4 is `Mac16,12`); only the Intel
Macs spell out the family (`Macmini8,1`).

Fail-open is deliberate (DECISIONS Q171, 2026-10-04). The rule replaced an ioreg `BatteryInstalled`
gate (Q25–Q27) that installed only where the hardware reported no battery, which withheld the roles
from the Intel 2018 mini because Intel Macs publish no battery node at all. The VM branch is
redundant today (the lume VM's family is `Apple Virtual Machine 1`) and stays because the rule was
asked for in that shape.

## Easy to get wrong

- **A `set_fact` cannot reference a key defined in the same task.** Ansible fails the play with
  `Error while resolving value for 'x': 'y' is undefined` (verified). So the classification takes two
  `set_fact` tasks, and `mac_is_vm` re-parses the `system_profiler` JSON instead of reading
  `mac_family`.
- **The probe needs `check_mode: false`.** It is read-only, so running it in a dry run is safe, and
  it is what makes the gates mean anything there.
- **Every gate casts with `| bool`.** `-e mac_is_always_on=true` arrives as the string `"true"`, and
  every non-empty string is truthy, `"false"` included. Recent ansible-core also rejects a
  non-boolean conditional (`Conditionals must have a boolean result`), but only on the branch that
  meets it.
- **The gate lives inside each role, not as a `when:` on the role in `main.yml`.** It must hold for a
  single-role run, and for `ponytail`, which depends on `hermes`. The role's `tasks/main.yml` is the
  gate plus a dynamic `include_tasks: install.yml`, so a skipped host logs one line. A role-level
  `when:` would also be inherited by the role's dependencies and would skip `host-facts` with it.
- **The facts come from the `host-facts` role, not from `pre_tasks`.** `pre_tasks` run only in a full
  play, so a single-role run aborted with `'mac_is_always_on' is undefined`, which broke the
  `ansible-idempotency-check` skill. Ansible does run a role's `meta/main.yml` dependencies for an
  ad-hoc `include_role`, and a parameterless role de-duplicates, so `host-facts` runs once per play
  however many roles pull it in. To check the dedup, assert on a real run: `--list-tasks` prints the
  un-deduplicated graph, where `host-facts` appears five times.

## Single-role runs

```bash
ansible localhost -m include_role -a name=hermes
```

This needs no extra vars: the `host-facts` dependency classifies the machine.
`-e mac_is_always_on=true` (or `=false`) still works as an override.

A role that gates on `mac_is_always_on` must list `host-facts` in its `meta/main.yml`. Without it
the full play still works, because the fact is already set by then, but a single-role run aborts on
the undefined variable. That loud failure is intended: the gate carries no default, and the
`ansible-idempotency-check` skill runs every changed role standalone, so it catches the omission.
