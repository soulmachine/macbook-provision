#!/usr/bin/env python3
"""cliproxy-tier-host — per-host half of cliproxy-tier. Runs ON the target host.

Optional tier (Claude Code, Codex, kimi): native login is the default, the gateway is
opt-in via claude-gw / codex-gw / kimi-gw (backpass-gw for backpass's Claude passes). Mandatory tier (pi, omp, hermes, opencode):
gateway only, vendor logins removed. Omarchy's other agents, on every host where they are installed
(coding-agent Q374, Q401): copilot-gw and gemini-gw wrappers (Gemini keeps a native Google login where
one exists, except on GATEWAY_ONLY hosts), built-in config for grok, crush and openclaw, and OpenClaw's
one-time onboarding. Cursor CLI and Muse Code have no route and stay native. Idempotent: every step checks before it writes,
backs up to <file>.bak-<ts> (mode 600) and prints one status line at the end.
The key comes from this host's own environment (CLIPROXY_API_KEY), never over the wire.
"""
import json, os, pwd, re, shutil, subprocess, sys, time, tomllib
from pathlib import Path

H = Path.home()
TS = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
KEY = os.environ.get("CLIPROXY_API_KEY")
BASE = os.environ.get("CLIPROXY_BASE_URL", "http://127.0.0.1:8317")
if not KEY:
    sys.exit("CLIPROXY_API_KEY not in environment; refusing to run")
status, changed, backups = {}, [], []
HOST = os.uname().nodename.split(".")[0]
# No native vendor login by design (coding-agent Q352): every agent there goes through the gateway.
GATEWAY_ONLY = HOST in {"mac-mini-2018-omarchy"}
# The gateway models every CLI below lists (macbook-provision Q261): (id, name, context, max output,
# reasoning, images). They must be listed: the gateway's /v1/models disguises the non-Claude ids for
# Anthropic-format clients. Nickel limits are vLLM's max_model_len; the rest match what the CLIs used.
GW_MODELS = [
    ("claude-opus-5-5", "Claude Opus 5.5", 200000, 32000, True, True),
    ("claude-sonnet-5-5", "Claude Sonnet 5.5", 200000, 32000, True, True),
    ("claude-haiku-5-5", "Claude Haiku 5.5", 200000, 16000, True, True),
    ("claude-fable-5-1", "Claude Fable 5.1", 200000, 32000, True, True),
    ("gpt-6-astra", "GPT-6 Astra", 272000, 32000, True, True),
    ("gpt-6.1-sol", "GPT-6.1 Sol", 272000, 32000, True, True),
    ("gpt-6-luna", "GPT-6 Luna", 272000, 32000, True, True),
    ("glm-5.3-flash", "GLM-5.3 Flash", 1048576, 32000, False, False),
    ("qwen3.8-flash-next", "Qwen3.8 Flash Next", 262144, 32000, False, False),
    ("deepseek-v4.1-flash", "DeepSeek V4.1 Flash", 1048576, 32000, False, False),
]


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
# The wrapper header follows the LOGIN shell, not the presence of a zsh binary: dev-server-frank
# keeps zsh installed but logs in to bash since 2026-10-11, and its keys live in ~/.bashrc.
LOGIN_ZSH = pwd.getpwuid(os.getuid()).pw_shell.endswith("zsh")
which = lambda c: shutil.which(c)


def installed(cmd):
    """A real install, not Omarchy's ~/.local/bin stub that installs the tool through mise on first run."""
    w = which(cmd)
    if not w:
        return False
    if Path(w).parent == H / ".local/bin" and b"mise use -g" in Path(w).read_bytes()[:600]:
        return (H / ".local/share/mise/shims" / cmd).exists()
    return True

# ---------- wrappers ----------
bindir = H / ".local/bin"; bindir.mkdir(parents=True, exist_ok=True)
if ZSH and LOGIN_ZSH:
    hdr = "#!/bin/zsh\n# zsh sources ~/.zshenv even for scripts, so CLIPROXY_* is always here.\n"
else:
    hdr = '#!/bin/bash\n[ -n "${CLIPROXY_API_KEY:-}" ] || . "$HOME/.bashrc"\n'
wrappers = {
    "claude-gw": hdr + ': "${CLIPROXY_API_KEY:?}" "${CLIPROXY_BASE_URL:?}"\n'
                 '# Plugin hooks call bare `node`, which non-interactive shells may lack (macbook-air).\n'
                 '# Appended, so a host\'s own node and tools still come first.\n'
                 'command -v node >/dev/null 2>&1 || export PATH="$PATH:$HOME/.local/share/mise/shims"\n'
                 '# Marks each session as a gateway one. Herdr saves only the session id and restores with a bare\n'
                 '# `claude --resume <id>`; the herdr role\'s `claude` shell function sends marked ids back here.\n'
                 '# modelPicker adds the gateway\'s GPT (Codex account) and nickel-3ed models to /model, which\n'
                 '# lists only Claude models; "model" starts every session on Opus 5.5 unless --model says otherwise.\n'
                 'gw_settings=\'{"model":"claude-opus-5-5","hooks":{"SessionStart":[{"hooks":[{"type":"command","command":"mkdir -p ~/.local/state/claude-gw && touch ~/.local/state/claude-gw/$CLAUDE_CODE_SESSION_ID"}]}]},'
                 '"modelPicker":{"options":[' + ','.join(
                     f'{{"model":"{m}","label":"{l}","description":"{d}, through the gateway"}}'
                     for m, l, d in [("gpt-6-astra", "GPT-6 Astra", "OpenAI"), ("gpt-6.1-sol", "GPT-6.1 Sol", "OpenAI"),
                                     ("gpt-6-luna", "GPT-6 Luna", "OpenAI"), ("glm-5.3-flash", "GLM-5.3 Flash", "Nickel 3ed vLLM"),
                                     ("qwen3.8-flash-next", "Qwen3.8 Flash Next", "Nickel 3ed vLLM"),
                                     ("deepseek-v4.1-flash", "DeepSeek V4.1 Flash", "Nickel 3ed vLLM")]) + ']}}\'\n'
                 'exec env ANTHROPIC_BASE_URL="$CLIPROXY_BASE_URL" ANTHROPIC_AUTH_TOKEN="$CLIPROXY_API_KEY" claude --dangerously-skip-permissions --effort medium --settings "$gw_settings" "$@"\n',
    "codex-gw": hdr + ': "${CLIPROXY_API_KEY:?}"\n'
                '# codex may live only in mise shims (dev-server-frank), which non-interactive shells lack.\n'
                'command -v codex >/dev/null 2>&1 || export PATH="$HOME/.local/share/mise/shims:$PATH"\n'
                '# Adds the gateway\'s Claude models to /model; cliproxy-tier writes the catalog.\n'
                'cat="$HOME/.codex/cliproxy-models.json"\n'
                '[ -f "$cat" ] && set -- -c "model_catalog_json=$cat" "$@"\n'
                '# -p before the subcommand: `codex-gw --yolo exec …` still works.\nexec codex -p cliproxy --yolo -c model_reasoning_effort=medium "$@"\n',
    # backpass cannot route its acpx Claude passes itself; the agent pins live in ~/.config/backpass/config.json.
    "backpass-gw": hdr + ': "${CLIPROXY_API_KEY:?}" "${CLIPROXY_BASE_URL:?}"\n'
                   'exec env ANTHROPIC_BASE_URL="$CLIPROXY_BASE_URL" ANTHROPIC_AUTH_TOKEN="$CLIPROXY_API_KEY" backpass "$@"\n',
}
kimi_bin = which("kimi") or (str(H / ".kimi-code/bin/kimi") if (H / ".kimi-code/bin/kimi").exists() else None)
if kimi_bin:
    wrappers["kimi-gw"] = hdr + (
        '# kimi rejects --yolo together with -p/--prompt ("Cannot combine"); one-shot mode\n'
        '# already runs unattended, so drop --yolo only then.\n'
        'yolo=--yolo\nfor a in "$@"; do case "$a" in -p|--prompt|-p=*|--prompt=*) yolo=;; esac; done\n'
        f'exec "{kimi_bin}" -m cliproxy/opus5.5 ${{yolo:+"$yolo"}} "$@"\n')
elif (bindir / "kimi-gw").exists():  # kimi was uninstalled: drop the wrapper that still points at it
    backup(bindir / "kimi-gw"); (bindir / "kimi-gw").unlink(); changed.append(str(bindir / "kimi-gw"))
if installed("copilot"):
    # BYOK through env vars only. Copilot refuses a classic PAT in GITHUB_TOKEN even in BYOK mode,
    # and its catalog spells models with dots (limits, prompting); the wire model is the gateway's name.
    # BYOK serves one model per session, so `--model <gateway id>` picks it at launch. Copilot knows the
    # Claude limits; the others get theirs from GW_MODELS.
    arms = "".join(f'    {m}) wire={m} id={re.sub(r"^(claude-[a-z]+-[0-9]+)-([0-9]+)$", r"\1.\2", m)} '
                   + ("ctx= out=" if m.startswith("claude-") else f"ctx={c - o} out={o}") + ";;\n"
                   for m, _, c, o, _, _ in GW_MODELS)
    wrappers["copilot-gw"] = hdr + (
        ': "${CLIPROXY_API_KEY:?}" "${CLIPROXY_BASE_URL:?}"\n'
        'command -v copilot >/dev/null 2>&1 || export PATH="$HOME/.local/share/mise/shims:$PATH"\n'
        'wire=claude-opus-5-5 id=claude-opus-5.5 ctx= out=\n'
        'set -- "$@" --gw-end  # rotate the arguments once, taking out a --model naming a gateway model\n'
        'while [ "$1" != --gw-end ]; do\n'
        '  a=$1; shift\n'
        '  case "$a" in\n'
        '    --model=*) m=${a#--model=} ;;\n'
        '    --model) [ "$1" = --gw-end ] && { set -- "$@" "$a"; continue; }; m=$1; shift ;;\n'
        '    *) set -- "$@" "$a"; continue ;;\n'
        '  esac\n'
        '  case "$m" in\n' + arms +
        '    *) set -- "$@" --model "$m" ;;\n'
        '  esac\n'
        'done\nshift\n'
        'exec env -u GITHUB_TOKEN -u GH_TOKEN -u COPILOT_GITHUB_TOKEN COPILOT_PROVIDER_TYPE=anthropic \\\n'
        '  COPILOT_PROVIDER_BASE_URL="$CLIPROXY_BASE_URL" COPILOT_PROVIDER_API_KEY="$CLIPROXY_API_KEY" \\\n'
        '  COPILOT_PROVIDER_MODEL_ID="$id" COPILOT_PROVIDER_WIRE_MODEL="$wire" \\\n'
        '  ${ctx:+"COPILOT_PROVIDER_MAX_PROMPT_TOKENS=$ctx"} ${out:+"COPILOT_PROVIDER_MAX_OUTPUT_TOKENS=$out"} copilot --allow-all "$@"\n')
GEMINI_SETTINGS = H / ".gemini/settings.json"


def gemini_native():
    """A Google login of the host's own: its OAuth file, or an auth type other than the gateway's api key."""
    if GATEWAY_ONLY:
        return False
    try:
        sel = json.loads(GEMINI_SETTINGS.read_text()).get("security", {}).get("auth", {}).get("selectedType")
    except (OSError, ValueError):
        sel = None
    return (H / ".gemini/oauth_creds.json").exists() or sel not in (None, "gemini-api-key")


if installed("gemini") and not gemini_native():
    # ~/.gemini/settings.json (below) pins the api-key auth type and the models; the env vars alone
    # select an auth type gemini-cli then rejects (#27550). Headless runs refuse an untrusted folder.
    wrappers["gemini-gw"] = hdr + (
        ': "${CLIPROXY_API_KEY:?}" "${CLIPROXY_BASE_URL:?}"\n'
        'command -v gemini >/dev/null 2>&1 || export PATH="$HOME/.local/share/mise/shims:$PATH"\n'
        'exec env GOOGLE_GEMINI_BASE_URL="$CLIPROXY_BASE_URL" GEMINI_API_KEY="$CLIPROXY_API_KEY" gemini --yolo --skip-trust "$@"\n')
for name, body in wrappers.items():
    p = bindir / name
    if not p.exists() or p.read_text() != body:
        write(p, body, 0o755)  # backs up a copy that differs, e.g. a hand edit
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
    # Default model is the Codex account's gpt-6-astra. Only the old Claude defaults are replaced, so a
    # model picked with /model and saved to this profile survives later runs.
    cand = re.sub(r'^model\s*=\s*"claude-opus-5(-5)?"', 'model = "gpt-6-astra"', cand, count=1, flags=re.M)
    if "model" not in tomllib.loads(cand):
        cand = re.sub(r'^(model_provider\s*=.*\n)', r'\1model = "gpt-6-astra"\n', cand, count=1, flags=re.M)
    if cand != ptext:
        assert tomllib.loads(cand)["model_provider"] == "cliproxy", "codex profile candidate invalid"
        write(prof, cand)
    # Codex's /model lists only its OpenAI catalog. codex-gw passes this copy, which adds the gateway's
    # Claude and nickel-3ed models cloned from gpt-5.5. Rebuilt each run so new OpenAI models still show up.
    try:
        cdx = which("codex") or str(H / ".local/share/mise/shims/codex")
        cat = json.loads(subprocess.run([cdx, "debug", "models"], capture_output=True, text=True, timeout=60).stdout)
        # A native login's catalog has no gpt-5.5; terra is in both. Pin terra's newer modes to gpt-5.5's,
        # the shape tested through the gateway.
        base = {**next(m for s in ("gpt-5.5", "gpt-5.6-terra") for m in cat["models"] if m["slug"] == s),
                "tool_mode": None, "use_responses_lite": False, "multi_agent_version": None,
                "include_skills_usage_instructions": True, "max_context_window": 272000}
    except Exception as e:  # keep the last good catalog; codex-gw skips the flag when there is none
        print(f"  codex catalog: skipped ({type(e).__name__})")
    else:
        nickel = "Nickel 3ed vLLM, through the gateway"
        for i, (slug, name, desc) in enumerate([
                ("claude-fable-5-1", "Claude Fable 5.1", "Anthropic Fable 5.1, through the gateway"),
                ("claude-opus-5-5", "Claude Opus 5.5", "Anthropic Opus 5.5, through the gateway"),
                ("claude-sonnet-5-5", "Claude Sonnet 5.5", "Anthropic Sonnet 5.5, through the gateway"),
                ("claude-haiku-5-5", "Claude Haiku 5.5", "Anthropic Haiku 5.5, through the gateway"),
                ("glm-5.3-flash", "GLM-5.3 Flash", nickel), ("qwen3.8-flash-next", "Qwen3.8 Flash Next", nickel),
                ("deepseek-v4.1-flash", "DeepSeek V4.1 Flash", nickel)]):
            cat["models"].append({**base, "slug": slug, "display_name": name, "priority": 20 + i, "description": desc,
                                  "service_tiers": [], "additional_speed_tiers": [], "availability_nux": None, "upgrade": None})
        cp, body = H / ".codex/cliproxy-models.json", json.dumps(cat, indent=1) + "\n"
        if not cp.exists() or cp.read_text() != body:  # generated, so no .bak copy
            cp.with_name(cp.name + ".tmp").write_text(body); os.replace(cp.with_name(cp.name + ".tmp"), cp); changed.append(str(cp))
    status["codex"] = "native" if (H / ".codex/auth.json").exists() else "gw-only(no-login)"

# ---------- kimi: native default only where a login exists ----------
p = H / ".kimi-code/config.toml"
if p.exists():
    text = p.read_text()
    # gateway model entries for `kimi -m cliproxy/<alias>`; inserted above the managed provider block
    KIMI_GW = {"opus5.5": "claude-opus-5-5", "sonnet5.5": "claude-sonnet-5-5", "fable5.1": "claude-fable-5-1"}
    # The rest of GW_MODELS: alias "haiku5.5" for Claude, the gateway id for the others.
    KIMI_NEW = {re.sub(r"^claude-([a-z]+)-([0-9]+)-([0-9]+)$", r"\1\2.\3", row[0]): row
                for row in GW_MODELS if row[0] not in KIMI_GW.values()}
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
        blocks += "".join(f'[models."cliproxy/{a}"]\nprovider = "cliproxy"\nmodel = "{m}"\nmax_context_size = {c}\n'
                          f'max_output_size = {o}\ncapabilities = {json.dumps(["tool_use"] + ["thinking"] * r + ["image_in"] * i)}\n\n'
                          for a, (m, _, c, o, r, i) in KIMI_NEW.items() if f'[models."cliproxy/{a}"]' not in cand)
        if blocks:
            mark = "# --- cliproxyapi (managed) ---"
            cand = cand.replace(mark, blocks + mark, 1) if mark in cand else cand.rstrip("\n") + "\n\n" + blocks
        if cand != text:
            models = tomllib.loads(cand)["models"]
            assert all(models[f"cliproxy/{a}"].get("max_output_size") == 128000 for a in KIMI_GW), "kimi candidate invalid"
            assert all(models[f"cliproxy/{a}"]["model"] == row[0] for a, row in KIMI_NEW.items()), "kimi candidate invalid"
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
if not omp.exists():  # Omarchy: a bash stub in ~/.local/bin that runs omp through mise
    omp = Path(which("omp") or omp)
# omp is a `#!/usr/bin/env bun` JS shim on some hosts (bun is not on PATH there) and a
# compiled Mach-O binary on others; pick the invocation by looking at the shebang.
OMP = [str(omp)]
shebang = omp.resolve().read_bytes().split(b"\n", 1)[0] if omp.exists() else b""
if shebang.startswith(b"#!") and shebang.endswith(b"bun"):
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
    # GW_MODELS as a `cliproxy` provider: omp's anthropic catalog has only the Claude ids. The key is the
    # .env variable's name. A file omp cannot validate disables every custom provider, so it lists them back.
    p = H / ".omp/agent/models.yml"
    y = ("providers:\n  cliproxy:\n    baseUrl: " + BASE + "\n    apiKey: ANTHROPIC_API_KEY\n    api: anthropic-messages\n    models:\n"
         + "".join(f"      - {{id: {json.dumps(m)}, name: {json.dumps(n)}, reasoning: {str(r).lower()}, "
                   f"input: {json.dumps(['text'] + ['image'] * i)}, contextWindow: {c}, maxTokens: {o}}}\n"
                   for m, n, c, o, r, i in GW_MODELS))
    if not p.exists() or p.read_text() != y:
        old = p.read_text() if p.exists() else None
        write(p, y, 0o600)
        if f"cliproxy ({len(GW_MODELS)})" not in run(*OMP, "models", "cliproxy").stdout:
            p.write_text(old) if old is not None else p.unlink()
            changed.remove(str(p)); outs.append("models.yml:REVERTED")
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
    # The /model picker lists providers.cliproxy.models; without discover_models: false it probes
    # /v1/models instead. `hermes config set` takes no maps, so a text edit that hermes then reads back.
    m = re.search(r"^providers:\n(?:[ \t].*\n)*?  cliproxy:\n((?:    .*\n)*)", text, flags=re.M)
    if m and on_gw(text):
        body = re.sub(r"^    discover_models:.*\n", "", m.group(1), flags=re.M)
        body = re.sub(r"^    models:\n(?:      .*\n)*", "", body, flags=re.M)
        body += "    discover_models: false\n    models:\n" + "".join(
            f'      "{i}":\n        context_length: {c}\n' for i, _, c, *_ in GW_MODELS)
        cand = text[:m.start(1)] + body + text[m.end(1):]
        if cand != text:
            write(p, cand)
            r = run(which("hermes") or str(H / ".local/bin/hermes"), "config", "get", "providers.cliproxy.discover_models")
            if r.returncode or r.stdout.strip().lower() != "false":
                p.write_text(text); changed.remove(str(p))
                print(f"  hermes models: reverted, hermes read back {r.stdout.strip()[:80]!r}")
            else:
                text = cand
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
    a = prov.setdefault("anthropic", {})
    a.setdefault("options", {}).update({"baseURL": f"{BASE}/v1", "apiKey": "{env:CLIPROXY_API_KEY}"})
    # opencode's own catalog has claude-haiku-5-5; drop the haiku-4-5 pin this script used to add (coding-agent Q385).
    if a.get("models", {}).get("claude-haiku-4-5") == {"id": "claude-haiku-4-5-20251001"}:
        del a["models"]["claude-haiku-4-5"]
        if not a["models"]:
            del a["models"]
    # opencode's catalog has the Claude ids; the gateway's other models go on the same provider.
    for i, name, c, o, r, img in GW_MODELS:
        if not i.startswith("claude-"):
            a.setdefault("models", {})[i] = {"name": name, "reasoning": r, "tool_call": True, "attachment": img,
                                             "limit": {"context": c, "output": o}}
    enabled = ["anthropic"] + (["google"] if "google" in prov else [])
    new = dict(d, enabled_providers=enabled, model="anthropic/claude-opus-5-5",
               small_model="anthropic/claude-haiku-5-5")
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

# ---------- Omarchy's other agents, every host (coding-agent Q374, Q401) ----------
# Each is configured only once really installed. Cursor CLI and Muse Code have no gateway route.
MANAGED = re.compile(r"^# --- cliproxyapi \(managed\) ---\n.*?^# --- end cliproxyapi ---\n", flags=re.M | re.S)


def managed_block(p: Path, block: str, check):
    """Replace the managed block in p, or append it; check(candidate) must pass before the write."""
    text = p.read_text() if p.exists() else ""
    m = MANAGED.search(text)
    cand = text[: m.start()] + block + text[m.end():] if m else text + ("\n" if text and not text.endswith("\n") else "") + block
    if cand != text:
        check(cand)
        p.parent.mkdir(parents=True, exist_ok=True)
        write(p, cand)


def subset(have, want):
    if isinstance(want, dict):
        return isinstance(have, dict) and all(k in have and subset(have[k], v) for k, v in want.items())
    if isinstance(want, list):
        return isinstance(have, list) and len(have) == len(want) and all(subset(h, w) for h, w in zip(have, want))
    return have == want


for name in ("copilot-gw", "gemini-gw"):
    if installed(name[:-3]):
        status[name[:-3]] = "gw" if (bindir / name).exists() else "NOT-gw"
if installed("gemini") and gemini_native():
    status["gemini"] = "native"

# Gemini: its helper tasks (classifier, summarizers, web fetch, loop detection, compression) call
# Gemini model names the gateway does not serve; overrides swap only the model, keeping each config.
p = GEMINI_SETTINGS
if installed("gemini") and not gemini_native():
    flash = ["flash-lite", "flash", "gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-3.1-flash-lite-preview",
             "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
    pro = ["pro", "gemini-3-pro-preview", "gemini-3.1-pro-preview", "gemini-3.1-pro-preview-customtools", "gemini-2.5-pro"]
    d = json.loads(p.read_text()) if p.exists() else {}
    new = json.loads(json.dumps(d))
    new.setdefault("security", {}).setdefault("auth", {})["selectedType"] = "gemini-api-key"
    name = new.setdefault("model", {}).get("name", "")
    if not name or name.startswith(("gemini", "gemma")) or name in ("auto", "pro", "flash", "flash-lite"):
        new["model"]["name"] = "claude-opus-5-5"  # a gateway model the user picked stays
    new.setdefault("privacy", {})["usageStatisticsEnabled"] = False
    new.setdefault("general", {})["enableAutoUpdate"] = False
    new.setdefault("modelConfigs", {})["customOverrides"] = (
        [{"match": {"model": m}, "modelConfig": {"model": "claude-haiku-5-5"}} for m in flash] +
        [{"match": {"model": m}, "modelConfig": {"model": "claude-sonnet-5-5"}} for m in pro])
    # /model lists modelDefinitions (under Manual) only with this experimental flag on.
    new.setdefault("experimental", {})["dynamicModelConfiguration"] = True
    new["modelConfigs"].setdefault("modelDefinitions", {}).update(
        {i: {"tier": "custom", "isPreview": False, "isVisible": True, "displayName": name,
             "dialogDescription": "Through the gateway", "features": {"thinking": r, "multimodalToolUse": False}}
         for i, name, _, _, r, _ in GW_MODELS})
    if new != d:
        p.parent.mkdir(parents=True, exist_ok=True)
        write(p, json.dumps(new, indent=2) + "\n")

# grok: custom models read the key from the environment; no xAI login, catalog fetch or telemetry.
# grok rewrites config.toml itself and appends its own tables at the end, so this checks the parsed
# file and rewrites only when a gateway setting is missing: grok's tables and a gateway model the
# user picked as default survive a rerun.
p = H / ".grok/config.toml"
if installed("grok"):
    # Non-Claude models on chat_completions: through the gateway, grok's responses parser trips on a
    # `response.metadata` event and its messages parser on Nickel's unsigned thinking blocks.
    gw_models = {m: ("messages" if m.startswith("claude-") else "chat_completions", c, img) for m, _, c, _, _, img in GW_MODELS}
    roles = ("session_summary", "image_description", "prompt_suggestion")

    def grok_on_gw(doc):
        models, defs, feats = doc.get("models", {}), doc.get("model", {}), doc.get("features", {})
        return (all(subset(defs.get(m), {"model": m, "base_url": f"{BASE}/v1", "api_backend": api, "env_key": "CLIPROXY_API_KEY",
                                         "context_window": c, "vision": img})
                    for m, (api, c, img) in gw_models.items())
                and all(models.get(k) in gw_models for k in ("default",) + roles)
                and all(feats.get(k) is False for k in ("telemetry", "feedback", "remote_fetch")))
    text = p.read_text() if p.exists() else ""
    try:
        on_gw = grok_on_gw(tomllib.loads(text))
    except tomllib.TOMLDecodeError:
        on_gw = None
    if on_gw is False:
        block = ("# cliproxyapi (managed by cliproxy-tier, coding-agent Q374): every model goes through CLIProxyAPI.\n"
                 '[models]\ndefault = "claude-opus-5-5"\n' +
                 "".join(f'{k} = "claude-haiku-5-5"\n' for k in roles) +
                 "".join(f'\n[model."{m}"]\nmodel = "{m}"\nbase_url = "{BASE}/v1"\napi_backend = "{api}"\nenv_key = "CLIPROXY_API_KEY"\n'
                         f'context_window = {c}\nvision = {str(img).lower()}\n'
                         for m, (api, c, img) in gw_models.items()) +
                 "\n[features]\ntelemetry = false\nfeedback = false\nremote_fetch = false\n")
        # Drop the managed tables (and an earlier block's comment lines) from the rest, keep the others.
        # Compared without quotes: grok rewrites [model."x"] as [model.x].
        managed = {"[models]", "[features]"} | {f"[model.{m}]" for m in gw_models}
        keep, skip = [], False
        for ln in text.splitlines(keepends=True):
            if re.match(r"^\s*\[", ln):
                skip = ln.strip().replace('"', "") in managed
            if not skip and not re.match(r"^# (cliproxyapi|--- (end )?cliproxyapi)", ln):
                keep.append(ln)
        rest = "".join(keep).strip("\n")
        cand = block + ("\n" + rest + "\n" if rest else "")
        try:
            ok = grok_on_gw(tomllib.loads(cand))
        except tomllib.TOMLDecodeError:  # e.g. managed keys set as dotted keys or inline tables elsewhere
            ok = False
        if ok:
            p.parent.mkdir(parents=True, exist_ok=True)
            write(p, cand)
            on_gw = True
    status["grok"] = "gw" if on_gw else "NOT-gw(conflict)"

# crush: a provider id outside the Catwalk catalog (crush #3504, #2649); no /v1 on an anthropic URL.
p = H / ".config/crush/crushrc"
if installed("crush"):
    block = ("# --- cliproxyapi (managed) ---\n"
             "# Every model goes through CLIProxyAPI (coding-agent Q374). The key stays in the environment.\n"
             "# No /v1 on an anthropic base URL: the SDK adds /v1/messages.\n"
             "option default-providers false\noption metrics false\n"
             f'provider add cliproxy --name CLIProxyAPI --type anthropic \\\n  --base-url "{BASE}" \\\n'
             '  --api-key "${CLIPROXY_API_KEY:?set CLIPROXY_API_KEY}"\n'
             + "".join(f'model add cliproxy/{m} --name "{name}" --context-window {c} --default-max-tokens {o}'
                       + " --can-reason true" * (r and m != "claude-haiku-5-5") + " --supports-images true" * img + "\n"
                       for m, name, c, o, r, img in GW_MODELS) +
             "model large cliproxy/claude-opus-5-5\nmodel small cliproxy/claude-haiku-5-5\n# --- end cliproxyapi ---\n")

    def crush_ok(cand):
        tmp = p.with_name("crushrc.cand"); tmp.parent.mkdir(parents=True, exist_ok=True); tmp.write_text(cand)
        ok = run("bash", "-n", str(tmp)).returncode == 0; tmp.unlink()
        assert ok, "crushrc candidate fails bash -n"
    managed_block(p, block, crush_ok)
    status["crush"] = "gw"

# openclaw: its gateway daemon (launchd or a systemd user unit) makes the model calls and never sees
# the session environment, so the key sits in ~/.openclaw/.env, read at daemon start. A host where
# OpenClaw is installed but not yet onboarded gets the non-interactive onboarding first; it needs
# the gateway up, since it sends a test request. Its output can carry the daemon's token, so it
# goes to a mode-600 log instead of stdout.
p = H / ".openclaw/openclaw.json"
if which("openclaw"):
    if not p.exists():
        log = H / ".cache/cliproxy-tier/openclaw-onboard.log"; log.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["openclaw", "onboard", "--non-interactive", "--accept-risk", "--mode", "local", "--flow", "quickstart",
               "--auth-choice", "custom-api-key", "--custom-compatibility", "anthropic", "--custom-base-url", BASE,
               "--custom-model-id", "claude-opus-5-5", "--custom-provider-id", "cliproxy", "--custom-image-input",
               "--secret-input-mode", "ref", "--gateway-bind", "loopback", "--install-daemon", "--skip-channels",
               "--skip-search", "--skip-skills", "--skip-hooks", "--skip-ui", "--skip-health"]
        try:
            r = subprocess.run(cmd, env=dict(os.environ, CUSTOM_API_KEY=KEY), stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, errors="replace", timeout=600)
            out, rc = r.stdout + r.stderr, r.returncode
        except subprocess.TimeoutExpired as e:
            out, rc = f"{e.stdout or ''}{e.stderr or ''}\ntimed out after 600 s", "timeout"
        log.write_text(out if isinstance(out, str) else out.decode(errors="replace")); os.chmod(log, 0o600)
        if p.exists():  # only an onboarding that reached the gateway writes the config
            changed.append(str(p))
        else:
            status["openclaw"] = f"NOT-onboarded(rc={rc}, see {log})"
    if p.exists():
        before = len(changed)
        upsert_env(H / ".openclaw/.env", {"CLIPROXY_API_KEY": KEY})
        free = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}
        want = {"models": {"providers": {"cliproxy": {
                    "baseUrl": BASE, "api": "anthropic-messages",
                    "apiKey": {"source": "env", "provider": "default", "id": "CLIPROXY_API_KEY"},
                    "models": [dict(id=m, name=name, contextWindow=c, maxTokens=o, input=["text"] + ["image"] * img,
                                    reasoning=r and m != "claude-haiku-5-5", cost=free)
                               for m, name, c, o, r, img in GW_MODELS]}}},
                "agents": {"defaults": {"models": {f"cliproxy/{m}": {} for m, *_ in GW_MODELS}}}}
        try:
            d = json.loads(p.read_text())
        except ValueError:  # hand-edited JSON5: leave it to `openclaw config`
            d = None
        # A gateway model the user picked as primary or utility model stays.
        dflt = (d or {}).get("agents", {}).get("defaults", {})
        if not str(dflt.get("model", {}).get("primary", "")).startswith("cliproxy/"):
            want["agents"]["defaults"]["model"] = {"primary": "cliproxy/claude-opus-5-5"}
        if not str(dflt.get("utilityModel", "")).startswith("cliproxy/"):
            want["agents"]["defaults"]["utilityModel"] = "cliproxy/claude-haiku-5-5"
        if d is not None and not subset(d, want):
            backup(p)
            r = subprocess.run(["openclaw", "config", "patch", "--stdin"], input=json.dumps(want),
                               capture_output=True, text=True, errors="replace")
            assert r.returncode == 0, f"openclaw config patch failed: {r.stderr[-300:]}"
            changed.append(str(p)); d = json.loads(p.read_text())
        if len(changed) > before:
            run("openclaw", "gateway", "restart")
        status["openclaw"] = "NOT-parsed" if d is None else ("gw" if subset(d, want) else "NOT-gw")

# ---------- pi: converged by Ansible + cliproxy-assert-pi; just assert here ----------
p = H / ".pi/agent/settings.json"
if p.exists():
    sd = json.loads(p.read_text())
    dm = f"{sd.get('defaultProvider')}/{sd.get('defaultModel')}"
    auth = H / ".pi/agent/auth.json"
    au = json.loads(auth.read_text()) if auth.exists() else {}
    status["pi"] = ("gw" if dm == "cliproxy/deepseek-v4.1-flash" else f"DEFAULT={dm}") + (f" AUTH={list(au)}" if au else "")

print(f"{os.uname().nodename.split('.')[0]}: " + " ".join(f"{k}={v}" for k, v in status.items()))
print("  changed: " + (", ".join(changed) or "nothing"))
if backups:
    print("  backups: " + ", ".join(backups))
