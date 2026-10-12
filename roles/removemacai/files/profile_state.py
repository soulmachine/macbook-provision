#!/usr/bin/env python3
"""Print whether the installed profile matches a .mobileconfig: current, stale or missing.

Needs root: `profiles show` lists system-scope profiles only for root. The profile's own
PayloadUUID can't tell versions apart (RemoveMacAI 1.1.0 exports the same UUID for every tweak
set), so this compares the payloads themselves.
"""
import plistlib
import subprocess
import sys


def payloads(items):
    out = {}
    for p in items:
        # A restrictions payload in a .mobileconfig keeps its keys at the top level; the
        # installed copy moves them into PayloadContent. Preferences payloads get wrapped once
        # more, in PayloadContentManagedPreferences.
        c = p.get("PayloadContent") or {k: v for k, v in p.items() if not k.startswith("Payload")}
        out[p["PayloadIdentifier"]] = c.get("PayloadContentManagedPreferences", c)
    return out


want = plistlib.load(open(sys.argv[1], "rb"))
xml = subprocess.run(
    ["profiles", "show", "-type", "configuration", "-output", "stdout-xml"],
    capture_output=True, check=True,
).stdout
have = [p for p in plistlib.loads(xml).get("_computerlevel", [])
        if p["ProfileIdentifier"] == want["PayloadIdentifier"]]
if not have:
    print("missing")
elif payloads(have[0]["ProfileItems"]) == payloads(want["PayloadContent"]):
    print("current")
else:
    print("stale")
