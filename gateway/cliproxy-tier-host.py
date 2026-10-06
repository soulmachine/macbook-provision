#!/usr/bin/env python3
"""cliproxy-tier-host — per-host half of cliproxy-tier. Runs ON the target host.

Optional tier (Claude Code, Codex, kimi): native login is the default, the gateway is
opt-in via claude-gw / codex-gw / kimi-gw. Mandatory tier (pi, omp, hermes, opencode):
gateway only, vendor logins removed. Idempotent: every step checks before it writes,
backs up to <file>.bak-<ts> (mode 600) and prints one status line at the end.
The key comes from this host's own environment (CLIPROXY_API_KEY), never over the wire.
"""
import json, os, re, shutil, subprocess, sys, time, tomllib
from pathlib import Path

H = Path.home()
TS = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
KEY = os.environ.get("CLIPROXY_API_KEY")
BASE = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8317")
if not KEY:
    sys.exit("CLIPROXY_API_KEY not in environment; refusing to run")
status, changed, backups = {}, [], []


def backup(p: Path):
    b = p.with_name(p.name + f".bak-{TS}")
    if b.exists():  # a second write this run: keep the pre-run original
        return
    shutil.copy2(p, b); os.chmod(b, 0o600); backups.append(str(b))


def write(p: Path, text: str, mode=None):
    """candidate -> backup -> atomic replace."""
    if p.exists():
        backup(p)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text)
    os.chmod(tmp, mode if mode is not None else (p.stat().st_mode & 0o777 if p.exists() else 0o644))
    os.replace(tmp, p); changed.append(str(p))


def upsert_env(p: Path, kv: dict):
    lines = p.read_text().splitlines() if p.exists() else []
    out, seen = [], set()
    for ln in lines:
        k = ln.split("=", 1)[0]
        if k in kv:
            if k not in seen:
                out.append(f"{k}={kv[k]}"); seen.add(k)
            continue
        out.append(ln)
    for k, v in kv.items():
        if k not in seen:
            out.append(f"{k}={v}")
    text = "\n".join(out) + "\n"
    if not p.exists() or p.read_text() != text:
        p.parent.mkdir(parents=True, exist_ok=True)
        write(p, text, 0o600)
    os.chmod(p, 0o600)


def run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace")


ZSH = shutil.which("zsh")
which = lambda c: shutil.which(c)

# ---------- wrappers ----------
bindir = H / ".local/bin"; bindir.mkdir(parents=True, exist_ok=True)
if ZSH:
    hdr = "#!/bin/zsh\n# zsh sources ~/.zshenv even for scripts, so CLIPROXY_* is always here.\n"
else:
    hdr = '#!/bin/bash\n[ -n "${CLIPROXY_API_KEY:-}" ] || . "$HOME/.bashrc"\n'
wrappers = {
    "claude-gw": hdr + ': "${CLIPROXY_API_KEY:?}" "${CLIPROXY_BASE_URL:?}"\n'
                 'exec env ANTHROPIC_BASE_URL="$CLIPROXY_BASE_URL" ANTHROPIC_AUTH_TOKEN="$CLIPROXY_API_KEY" claude --dangerously-skip-permissions --effort xhigh "$@"\n',
    "codex-gw": hdr + ': "${CLIPROXY_API_KEY:?}"\n'
                '# codex may live only in mise shims (dev-server-frank), which non-interactive shells lack.\n'
                'command -v codex >/dev/null 2>&1 || export PATH="$HOME/.local/share/mise/shims:$PATH"\n'
                '# -p before the subcommand: `codex-gw --yolo exec …` still works.\nexec codex -p cliproxy --yolo -c model_reasoning_effort=xhigh "$@"\n',
}
kimi_bin = which("kimi") or (str(H / ".kimi-code/bin/kimi") if (H / ".kimi-code/bin/kimi").exists() else None)
if kimi_bin:
    wrappers["kimi-gw"] = hdr + (
        '# kimi rejects --yolo together with -p/--prompt ("Cannot combine"); one-shot mode\n'
        '# already runs unattended, so drop --yolo only then.\n'
        'yolo=--yolo\nfor a in "$@"; do case "$a" in -p|--prompt|-p=*|--prompt=*) yolo=;; esac; done\n'
        f'exec "{kimi_bin}" -m cliproxy/opus5.5 ${{yolo:+"$yolo"}} "$@"\n')
for name, body in wrappers.items():
    p = bindir / name
    if not p.exists() or p.read_text() != body:
        p.write_text(body); changed.append(str(p))
    os.chmod(p, 0o755)

# ---------- Claude Code: native default ----------
p = H / ".claude/settings.json"
if p.exists():
    d = json.loads(p.read_text())  # re-read right before writing; Claude Code rewrites this file whole
    env = d.get("env", {})
    if any(k in env for k in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")):
        env.pop("ANTHROPIC_AUTH_TOKEN", None); env.pop("ANTHROPIC_BASE_URL", None)
        write(p, json.dumps(d, indent=2) + "\n")
    os.chmod(p, 0o600)
    status["claude"] = "native"

# ---------- Codex: native default, `-p cliproxy` opts in ----------
p = H / ".codex/config.toml"
if p.exists():
    text = p.read_text()
    head, sep, tail = text.partition("\n[")
    new_head = re.sub(r'^model_provider\s*=\s*"cliproxy"[ \t]*\n?', "", head, count=1, flags=re.M)
    if new_head != head:
        cand = new_head + sep + tail
        doc = tomllib.loads(cand)
        assert "model_provider" not in doc and "cliproxy" in doc.get("model_providers", {}), "codex candidate invalid"
        write(p, cand)
    prof = H / ".codex/cliproxy.config.toml"
    # codex also keeps model/effort/project-trust keys here; assert only model_provider
    ptext = prof.read_text() if prof.exists() else ""
    cand = ptext
    if tomllib.loads(cand).get("model_provider") != "cliproxy":
        cand = 'model_provider = "cliproxy"\n' + re.sub(r'^model_provider\s*=.*\n?', "", cand, flags=re.M)
    cand = re.sub(r'^model\s*=\s*"claude-opus-5"', 'model = "claude-opus-5-5"', cand, count=1, flags=re.M)
    if cand != ptext:
        assert tomllib.loads(cand)["model_provider"] == "cliproxy", "codex profile candidate invalid"
        write(prof, cand)
    status["codex"] = "native" if (H / ".codex/auth.json").exists() else "gw-only(no-login)"

# ---------- kimi: native default only where a login exists ----------
p = H / ".kimi-code/config.toml"
if p.exists():
    text = p.read_text()
    # gateway model entries for `kimi -m cliproxy/<alias>`; inserted above the managed provider block
    KIMI_GW = {"opus5.5": "claude-opus-5-5", "sonnet5.5": "claude-sonnet-5-5", "fable5.1": "claude-fable-5-1"}
    # Where kimi supports api_key_env (2.1.1 does) the key stays in the environment, so a rotation leaves
    # no stale copy. Older builds (0.29-0.38 seen) ignore it and fail with "provider cliproxy has no
    # credential configured", so they keep a literal key, rewritten to the current one every run.
    env_ok = kimi_bin is not None and b"api_key_env" in Path(kimi_bin).resolve().read_bytes()
    cred = 'api_key_env = "CLIPROXY_API_KEY"' if env_ok else f'api_key = "{KEY}"'
    if kimi_bin and "[providers.cliproxy]" not in text:
        # kimi with no gateway provider yet (mac-mini-m6): add the managed block the other hosts carry
        cand = (text.rstrip("\n") + "\n\n" if text.strip() else "") + (
            '# --- cliproxyapi (managed) ---\n[providers.cliproxy]\ntype = "anthropic"\n'
            f'base_url = "{BASE}"\n{cred}\n\n# --- end cliproxyapi ---\n')
        assert tomllib.loads(cand)["providers"]["cliproxy"]["base_url"] == BASE, "kimi provider candidate invalid"
        write(p, cand); text = cand
    # kimi rejects api_key and api_key_env together, so swap whichever one is there
    cand = re.sub(r'(\[providers\.cliproxy\]\n(?:(?!\[)[^\n]*\n)*?)api_key(?:_env)? = "[^"]*"\n',
                  lambda m: m.group(1) + cred + "\n", text, count=1)
    if cand != text:
        prov = tomllib.loads(cand)["providers"]["cliproxy"]
        want = {"api_key_env": "CLIPROXY_API_KEY"} if env_ok else {"api_key": KEY}
        assert {k: prov.get(k) for k in ("api_key", "api_key_env") if k in prov} == want, "kimi key candidate invalid"
        write(p, cand); text = cand
    if "[providers.cliproxy]" in text:
        # kimi sends max_tokens = max_output_size, else max_context_size; the 5-5 models cap output at 128K
        blk = lambda a, m, out="": (f'[models."cliproxy/{a}"]\nprovider = "cliproxy"\nmodel = "{m}"\nmax_context_size = 262144\n'
                                    f'{out}capabilities = [ "tool_use", "thinking", "image_in" ]\n')
        cand = text
        for a, m in KIMI_GW.items():  # upgrade blocks from the first 2026-10-06 rollout, which lacked the cap
            cand = cand.replace(blk(a, m), blk(a, m, "max_output_size = 128000\n"))
        blocks = "".join(blk(a, m, "max_output_size = 128000\n") + "\n"
                         for a, m in KIMI_GW.items() if f'[models."cliproxy/{a}"]' not in cand)
        if blocks:
            mark = "# --- cliproxyapi (managed) ---"
            cand = cand.replace(mark, blocks + mark, 1) if mark in cand else cand.rstrip("\n") + "\n\n" + blocks
        if cand != text:
            models = tomllib.loads(cand)["models"]
            assert all(models[f"cliproxy/{a}"].get("max_output_size") == 128000 for a in KIMI_GW), "kimi candidate invalid"
            write(p, cand); text = cand
    if '[models."kimi-code/k3"]' in text:
        cand = re.sub(r'^default_model\s*=\s*"[^"]*"', 'default_model = "kimi-code/k3"', text, count=1, flags=re.M)
        if cand != text:
            assert tomllib.loads(cand)["default_model"] == "kimi-code/k3"
            write(p, cand)
        status["kimi"] = "native"
    else:
        cand = re.sub(r'^default_model\s*=\s*"cliproxy/opus5"', 'default_model = "cliproxy/opus5.5"', text, count=1, flags=re.M)
        if "default_model" not in tomllib.loads(cand) and "[providers.cliproxy]" in cand:
            cand = 'default_model = "cliproxy/opus5.5"\n' + cand  # top-level key: must precede every table
        if cand != text:
            assert tomllib.loads(cand)["default_model"] == "cliproxy/opus5.5"
            write(p, cand)
        status["kimi"] = "gw-default(no-login)"
    os.chmod(p, 0o600)

# ---------- omp: gateway only, vault purged ----------
omp = H / ".bun/bin/omp"; bun = H / ".bun/bin/bun"
# omp is a `#!/usr/bin/env bun` JS shim on some hosts (bun is not on PATH there) and a
# compiled Mach-O binary on others; pick the invocation by looking at the first bytes.
OMP = [str(omp)]
if omp.exists() and omp.resolve().read_bytes()[:2] == b"#!":
    OMP = [str(bun), str(omp)]
if (H / ".omp/agent/agent.db").exists() and omp.exists() and (OMP[0] != str(bun) or bun.exists()):
    upsert_env(H / ".omp/agent/.env", {"ANTHROPIC_BASE_URL": BASE, "ANTHROPIC_API_KEY": KEY})
    # the vault purge is the one hard-to-undo step: back the .db up once, not on every
    # re-run (omp is not running under this ssh session)
    if not list((H / ".omp/agent").glob("agent.db.bak-*")):
        for suf in ("", "-wal", "-shm"):
            db = H / f".omp/agent/agent.db{suf}"
            if db.exists():
                backup(db)
    outs = []
    for prov in ("kimi-code", "openai-codex", "anthropic"):
        r = run(*OMP, "auth-broker", "logout", prov)
        outs.append(f"{prov}:{r.returncode}")
    r = run(*OMP, "config", "set", "disabledProviders", '["kimi-code","openai-codex"]'); outs.append(f"cfg:{r.returncode}")
    # the cached catalog predates new gateway models; refresh so the default below resolves
    r = run(*OMP, "models", "refresh"); outs.append(f"refresh:{r.returncode}")
    try:
        roles = json.loads(run(*OMP, "config", "get", "modelRoles").stdout or "{}")
    except ValueError:
        roles = {}
    if roles.get("default") != "anthropic/claude-opus-5-5":
        roles["default"] = "anthropic/claude-opus-5-5"
        r = run(*OMP, "config", "set", "modelRoles", json.dumps(roles)); outs.append(f"role:{r.returncode}")
    status["omp"] = "gw " + " ".join(outs)
    # drop the interactive-only omp() shell wrapper; the dotenv replaces it
    rc = H / ".zshrc"
    if rc.exists():
        text = rc.read_text()
        m = re.search(r"^# --- cliproxyapi \(managed\) ---\n.*?^# --- end cliproxyapi ---\n", text, flags=re.M | re.S)
        if m and "omp()" in m.group(0):
            cand = text[: m.start()] + text[m.end():]
            tmp = rc.with_name(".zshrc.cand"); tmp.write_text(cand)
            ok = run(ZSH, "-n", str(tmp)).returncode == 0; tmp.unlink()
            assert ok, ".zshrc candidate fails zsh -n"
            write(rc, cand)

# ---------- hermes: key via $HERMES_HOME/.env (daemon-safe) ----------
if (H / ".hermes/config.yaml").exists():
    upsert_env(H / ".hermes/.env", {"CLIPROXY_API_KEY": KEY})
    p = H / ".hermes/config.yaml"; text = p.read_text()
    on_gw = lambda t: re.search(r'^  provider: "?custom:cliproxy"?$', t, flags=re.M)
    if on_gw(text):
        cand = re.sub(r"^(model:\n  default: )claude-opus-5$", r"\1claude-opus-5-5", text, count=1, flags=re.M)
        if cand != text:
            write(p, cand)
    else:
        # mandatory tier: move hermes (e.g. the untouched example config, provider "auto") onto the gateway.
        # `hermes config set` keeps the file's comments; a regex rewrite of a 120 KB example would not.
        hermes = which("hermes") or str(H / ".local/bin/hermes")
        backup(p)
        for k, v in (("model.provider", "custom:cliproxy"), ("model.default", "claude-opus-5-5"),
                     ("providers.cliproxy.base_url", BASE), ("providers.cliproxy.key_env", "CLIPROXY_API_KEY"),
                     ("providers.cliproxy.transport", "anthropic_messages")):
            run(hermes, "config", "set", k, v)
        run(hermes, "config", "unset", "model.base_url")  # the example's OpenRouter URL would win over the provider's
        changed.append(str(p)); text = p.read_text()
    pool = {}
    a = H / ".hermes/auth.json"
    if a.exists():
        pool = {k: len(v) for k, v in json.loads(a.read_text()).get("credential_pool", {}).items() if v}
    status["hermes"] = ("gw" if on_gw(text) else "NOT-gw") + (f" POOL={pool}" if pool else "")

# ---------- opencode: built-in anthropic provider pointed at the gateway ----------
p = H / ".config/opencode/opencode.json"
if p.exists():
    d = json.loads(p.read_text())
    prov = d.setdefault("provider", {})
    want = {"options": {"baseURL": f"{BASE}/v1", "apiKey": "{env:CLIPROXY_API_KEY}"},
            "models": {"claude-haiku-4-5": {"id": "claude-haiku-4-5-20251001"}}}
    a = prov.setdefault("anthropic", {})
    a.setdefault("options", {}).update(want["options"])
    a.setdefault("models", {}).update(want["models"])
    enabled = ["anthropic"] + (["google"] if "google" in prov else [])
    new = dict(d, enabled_providers=enabled, model="anthropic/claude-opus-5-5",
               small_model="anthropic/claude-haiku-4-5-20251001")
    if new != json.loads(p.read_text()):
        write(p, json.dumps(new, indent=2) + "\n")
    auth = H / ".local/share/opencode/auth.json"
    if auth.exists():
        ad = json.loads(auth.read_text())
        if "anthropic" in ad:
            ad.pop("anthropic"); write(auth, json.dumps(ad, indent=2) + "\n", 0o600)
    status["opencode"] = "gw"

# ---------- claude-mem: refresh the gateway key its observer reads ----------
# The claude-mem role writes this file too, but only at the host's next play, and dev-server-frank
# runs no playbook. claude-mem strips ANTHROPIC_* from its env, so a literal copy is the only option.
p = H / ".claude-mem/.env"
if p.exists() and re.search(rf"^ANTHROPIC_BASE_URL={re.escape(BASE)}/?$", p.read_text(), flags=re.M):
    upsert_env(p, {"ANTHROPIC_API_KEY": KEY})
    status["claude-mem"] = "gw"

# ---------- pi: converged by Ansible + cliproxy-assert-pi; just assert here ----------
p = H / ".pi/agent/settings.json"
if p.exists():
    dm = json.loads(p.read_text()).get("defaultModel")
    auth = H / ".pi/agent/auth.json"
    au = json.loads(auth.read_text()) if auth.exists() else {}
    status["pi"] = ("gw" if dm == "cliproxy/claude-opus-5-5" else f"DEFAULT={dm}") + (f" AUTH={list(au)}" if au else "")

print(f"{os.uname().nodename.split('.')[0]}: " + " ".join(f"{k}={v}" for k, v in status.items()))
print("  changed: " + (", ".join(changed) or "nothing"))
if backups:
    print("  backups: " + ", ".join(backups))
