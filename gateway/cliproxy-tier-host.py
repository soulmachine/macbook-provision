#!/usr/bin/env python3
"""cliproxy-tier-host — per-host half of cliproxy-tier. Runs ON the target host.

The policy is docs/gateway-policy.md. A CLI with its own vendor login (Claude Code, Codex, kimi, gemini,
copilot, grok) keeps that login as the plain command, untouched, and gets a <cli>-gw wrapper onto the
gateway. Each -gw starts on deepseek-v4.1-flash, except claude-gw (claude-opus-5-5) and codex-gw
(gpt-6-astra). The others (pi, omp, hermes, crush, openclaw, opencode) use the gateway by default, on
deepseek-v4.1-flash. Effort is high on every gateway route. backpass-gw routes backpass's Claude passes.
Idempotent: every step checks before it writes,
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
GW_DEFAULT = "deepseek-v4.1-flash"  # every gateway default except claude-gw and codex-gw (Q268)
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
    ("deepseek-v4.1-flash", "DeepSeek V4.1 Flash", 1048576, 32000, True, False),
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


def link(dst: Path, src: Path):
    """dst -> src, so a -gw home shares a native folder; a real file or folder at dst is left alone."""
    if not src.exists() or (dst.exists() and not dst.is_symlink()) or (dst.is_symlink() and dst.resolve() == src.resolve()):
        return
    if dst.is_symlink():
        dst.unlink()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.symlink_to(src); changed.append(str(dst))


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
                 'exec env ANTHROPIC_BASE_URL="$CLIPROXY_BASE_URL" ANTHROPIC_AUTH_TOKEN="$CLIPROXY_API_KEY" claude --dangerously-skip-permissions --effort high --settings "$gw_settings" "$@"\n',
    "codex-gw": hdr + ': "${CLIPROXY_API_KEY:?}"\n'
                '# codex may live only in mise shims (dev-server-frank), which non-interactive shells lack.\n'
                'command -v codex >/dev/null 2>&1 || export PATH="$HOME/.local/share/mise/shims:$PATH"\n'
                '# Adds the gateway\'s Claude models to /model; cliproxy-tier writes the catalog.\n'
                'cat="$HOME/.codex/cliproxy-models.json"\n'
                '[ -f "$cat" ] && set -- -c "model_catalog_json=$cat" "$@"\n'
                '# -p before the subcommand: `codex-gw --yolo exec …` still works.\nexec codex -p cliproxy --yolo -c model_reasoning_effort=high "$@"\n',
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
        '# Its own KIMI_CODE_HOME holds the gateway config and default model; ~/.kimi-code stays native.\n'
        f'exec env KIMI_CODE_HOME="$HOME/.kimi-code-gw" KIMI_MODEL_THINKING_EFFORT=high "{kimi_bin}" ${{yolo:+"$yolo"}} "$@"\n')
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
    dctx, dout = next((c, o) for m, _, c, o, _, _ in GW_MODELS if m == GW_DEFAULT)
    wrappers["copilot-gw"] = hdr + (
        ': "${CLIPROXY_API_KEY:?}" "${CLIPROXY_BASE_URL:?}"\n'
        'command -v copilot >/dev/null 2>&1 || export PATH="$HOME/.local/share/mise/shims:$PATH"\n'
        f'wire={GW_DEFAULT} id={GW_DEFAULT} ctx={dctx - dout} out={dout}\n'
        '# copilot rejects a repeated flag, so add the effort only when the caller gave none\n'
        'case " $* " in *" --reasoning-effort"*|*" --effort"*) ;; *) set -- --reasoning-effort high "$@" ;; esac\n'
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
GEMINI_GW_HOME = H / ".gemini-gw"  # GEMINI_CLI_HOME: gemini reads $GEMINI_CLI_HOME/.gemini/settings.json
GEMINI_GW_SETTINGS = GEMINI_GW_HOME / ".gemini/settings.json"
if installed("gemini"):
    # Its own home, so ~/.gemini keeps the Google login. The settings there (below) pin the api-key auth type
    # and the models, which the env vars alone cannot (#27550); system settings would need a root-owned
    # folder. Headless runs refuse an untrusted folder.
    wrappers["gemini-gw"] = hdr + (
        ': "${CLIPROXY_API_KEY:?}" "${CLIPROXY_BASE_URL:?}"\n'
        'command -v gemini >/dev/null 2>&1 || export PATH="$HOME/.local/share/mise/shims:$PATH"\n'
        f'exec env GEMINI_CLI_HOME="$HOME/{GEMINI_GW_HOME.name}" '
        'GOOGLE_GEMINI_BASE_URL="$CLIPROXY_BASE_URL" GEMINI_API_KEY="$CLIPROXY_API_KEY" gemini --yolo --skip-trust "$@"\n')
if (bindir / "opencode-gw").exists():  # opencode is gateway-default again (Q268): drop the old wrapper
    backup(bindir / "opencode-gw"); (bindir / "opencode-gw").unlink(); changed.append(str(bindir / "opencode-gw"))
if installed("grok"):
    # A separate GROK_HOME: grok's GROK_CONFIG_PATH overlay accepts no model keys, and ~/.grok keeps the xAI login.
    wrappers["grok-gw"] = hdr + (
        ': "${CLIPROXY_API_KEY:?}"\n'
        'command -v grok >/dev/null 2>&1 || export PATH="$HOME/.local/share/mise/shims:$PATH"\n'
        'exec env GROK_HOME="$HOME/.grok-gw" grok "$@"\n')
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

# ---------- kimi: native stays native; kimi-gw has its own KIMI_CODE_HOME (Q268) ----------
# kimi needs default_model in config.toml even with -m, so the gateway gets a config of its own.
KIMI_GW_HOME = H / ".kimi-code-gw"
if kimi_bin:
    # `kimi -m cliproxy/<alias>`: the 5-5 Claude models by short alias, haiku as "haiku5.5", the rest by gateway id
    KIMI_ALIAS = {"claude-opus-5-5": "opus5.5", "claude-sonnet-5-5": "sonnet5.5", "claude-fable-5-1": "fable5.1"}
    kimi_alias = lambda m: KIMI_ALIAS.get(m, re.sub(r"^claude-([a-z]+)-([0-9]+)-([0-9]+)$", r"\1\2.\3", m))
    # Where kimi supports api_key_env (2.1.1 does) the key stays in the environment, so a rotation leaves
    # no stale copy. Older builds (0.29-0.38 seen) ignore it and fail with "provider cliproxy has no
    # credential configured", so they keep a literal key, rewritten to the current one every run.
    env_ok = b"api_key_env" in Path(kimi_bin).resolve().read_bytes()
    cred = 'api_key_env = "CLIPROXY_API_KEY"' if env_ok else f'api_key = "{KEY}"'
    # kimi sends max_tokens = max_output_size, else max_context_size; the 5-5 models cap output at 128K.
    # Effort is high no matter what: every reasoning model defaults to it.
    body = (f'default_model = "cliproxy/{GW_DEFAULT}"\n\n[thinking]\nenabled = true\neffort = "high"\n\n'
            f'[providers.cliproxy]\ntype = "anthropic"\nbase_url = "{BASE}"\n{cred}\n' +
            "".join(f'\n[models."cliproxy/{kimi_alias(m)}"]\n'
                    f'provider = "cliproxy"\nmodel = "{m}"\n'
                    + (f"max_context_size = 262144\nmax_output_size = 128000\n" if m in KIMI_ALIAS else f"max_context_size = {c}\nmax_output_size = {o}\n")
                    + f'capabilities = {json.dumps(["tool_use"] + ["thinking"] * r + ["image_in"] * i)}\n'
                    + ('support_efforts = ["low", "medium", "high"]\ndefault_effort = "high"\n' if r else "")
                    for m, _, c, o, r, i in GW_MODELS))
    # Mirror the native hooks and MCP servers (context-mode, browseros-neo, herdr ...), so kimi-gw runs
    # with the same tools. The native home is only read.
    native = H / ".kimi-code/config.toml"
    ntext = native.read_text() if native.exists() else ""
    body += "".join("\n" + b for b in re.findall(r"^\[\[hooks\]\]\n(?:(?!\[)[^\n]*\S[^\n]*\n)*", ntext, flags=re.M))
    gp = KIMI_GW_HOME / "config.toml"
    # A gateway model picked in kimi-gw stays as the default (Q268).
    try:
        picked = tomllib.loads(gp.read_text()).get("default_model") if gp.exists() else None
    except tomllib.TOMLDecodeError:
        picked = None
    if picked and picked in tomllib.loads(body)["models"]:
        body = body.replace(f'default_model = "cliproxy/{GW_DEFAULT}"', f'default_model = "{picked}"', 1)
    if not gp.exists() or gp.read_text() != body:
        doc = tomllib.loads(body)
        assert doc["default_model"] in doc["models"], "kimi-gw candidate invalid"
        assert len(doc.get("hooks", [])) == len(tomllib.loads(ntext).get("hooks", [])) if ntext else True, "kimi-gw hooks invalid"
        gp.parent.mkdir(parents=True, exist_ok=True)
        write(gp, body, 0o600)
    nm, gm = H / ".kimi-code/mcp.json", KIMI_GW_HOME / "mcp.json"
    if nm.exists() and (not gm.exists() or gm.read_text() != nm.read_text()):
        write(gm, nm.read_text(), 0o600)
    elif not nm.exists() and gm.exists():
        backup(gm); gm.unlink(); changed.append(str(gm))
    link(KIMI_GW_HOME / "hooks", H / ".kimi-code/hooks")
p = H / ".kimi-code/config.toml"
if p.exists():
    # Undo what this script used to write into the native config: the gateway default_model, the managed
    # provider block and the cliproxy model blocks. Anything else is the user's.
    text = p.read_text()
    cand = re.sub(r'^default_model\s*=\s*"cliproxy/[^"]*"[ \t]*\n', "", text, count=1, flags=re.M)
    cand = re.sub(r"^# --- cliproxyapi \(managed\) ---\n.*?^# --- end cliproxyapi ---\n", "", cand, flags=re.M | re.S)
    cand = re.sub(r'^\[models\."cliproxy/[^"]*"\]\n(?:(?!\[)[^\n]*\n)*', "", cand, flags=re.M)
    if cand != text:
        doc = tomllib.loads(cand)
        assert "cliproxy" not in doc.get("providers", {}) and not any(k.startswith("cliproxy/") for k in doc.get("models", {})), \
            "kimi native candidate invalid"
        write(p, cand); text = cand
    status["kimi"] = "native+gw" if '[models."kimi-code/k3"]' in text else "native(no-login)+gw"
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
    # Only the old default is replaced, so a model picked later survives (Q268).
    if roles.get("default") in (None, "anthropic/claude-opus-5-5"):
        roles["default"] = f"cliproxy/{GW_DEFAULT}"
        r = run(*OMP, "config", "set", "modelRoles", json.dumps(roles)); outs.append(f"role:{r.returncode}")
    if run(*OMP, "config", "get", "defaultThinkingLevel").stdout.strip().strip('"') != "high":
        r = run(*OMP, "config", "set", "defaultThinkingLevel", "high"); outs.append(f"think:{r.returncode}")
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
hermes = which("hermes") or str(H / ".local/bin/hermes")
# Every step below goes through `hermes config`, so a config left behind by an uninstalled hermes is skipped.
if (H / ".hermes/config.yaml").exists() and Path(hermes).exists():
    upsert_env(H / ".hermes/.env", {"CLIPROXY_API_KEY": KEY})
    p = H / ".hermes/config.yaml"; text = p.read_text()
    on_gw = lambda t: re.search(r'^  provider: "?custom:cliproxy"?$', t, flags=re.M)
    if on_gw(text):
        # Only the old defaults are replaced, so a model picked later survives (Q268). `hermes config set`
        # keeps the file's comments, which sit between `model:` and `default:` in the example config.
        if run(hermes, "config", "get", "model.default").stdout.strip().strip("\"'") in ("claude-opus-5", "claude-opus-5-5"):
            backup(p); run(hermes, "config", "set", "model.default", GW_DEFAULT); changed.append(str(p)); text = p.read_text()
    else:
        # mandatory tier: move hermes (e.g. the untouched example config, provider "auto") onto the gateway.
        # `hermes config set` keeps the file's comments; a regex rewrite of a 120 KB example would not.
        backup(p)
        for k, v in (("model.provider", "custom:cliproxy"), ("model.default", GW_DEFAULT),
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
            r = run(hermes, "config", "get", "providers.cliproxy.discover_models")
            if r.returncode or r.stdout.strip().lower() != "false":
                p.write_text(text); changed.remove(str(p))
                print(f"  hermes models: reverted, hermes read back {r.stdout.strip()[:80]!r}")
            else:
                text = cand
    # Effort is high no matter what (Q268); hermes' example config ships medium.
    if run(hermes, "config", "get", "agent.reasoning_effort").stdout.strip().strip("\"'") != "high":
        backup(p); run(hermes, "config", "set", "agent.reasoning_effort", "high"); changed.append(str(p)); text = p.read_text()
    pool = {}
    a = H / ".hermes/auth.json"
    if a.exists():
        pool = {k: len(v) for k, v in json.loads(a.read_text()).get("credential_pool", {}).items() if v}
    status["hermes"] = ("gw" if on_gw(text) else "NOT-gw") + (f" POOL={pool}" if pool else "")

# ---------- opencode: built-in anthropic provider pointed at the gateway ----------
# opencode counts as a CLI without its own login (Q268), Go plan or not. The built-in anthropic provider
# keeps the oh-my-openagent plugin's anthropic/claude-* agent pins working through the gateway.
p = H / ".config/opencode/opencode.json"
if p.exists():
    d = json.loads(p.read_text())
    new = json.loads(json.dumps(d))
    prov = new.setdefault("provider", {})
    a = prov.setdefault("anthropic", {})
    a.setdefault("options", {}).update({"baseURL": f"{BASE}/v1", "apiKey": "{env:CLIPROXY_API_KEY}"})
    # opencode's own catalog has claude-haiku-5-5; drop the haiku-4-5 pin this script used to add (coding-agent Q385).
    if a.get("models", {}).get("claude-haiku-4-5") == {"id": "claude-haiku-4-5-20251001"}:
        del a["models"]["claude-haiku-4-5"]
    # opencode's catalog has the Claude ids; the gateway's other models go on the same provider. A reasoning
    # model gets a "high" variant, which the agents below select: effort is high no matter what (Q268).
    for i, name, c, o, r, img in GW_MODELS:
        if not i.startswith("claude-"):
            a.setdefault("models", {})[i] = {"name": name, "reasoning": r, "tool_call": True, "attachment": img,
                                             "limit": {"context": c, "output": o}} | (
                {"variants": {"high": {"thinking": {"type": "enabled", "budgetTokens": 16000}}}} if r else {})
    if not a.get("models"):
        a.pop("models", None)
    for ag in ("build", "plan"):
        new.setdefault("agent", {}).setdefault(ag, {})["variant"] = "high"
    new["enabled_providers"] = ["anthropic"] + (["google"] if "google" in prov else [])
    # Only the old default is replaced, so a model picked later survives (Q268).
    if new.get("model") in (None, "anthropic/claude-opus-5-5"):
        new["model"] = f"anthropic/{GW_DEFAULT}"
    new["small_model"] = "anthropic/claude-haiku-5-5"
    if new != d:
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
# Each is configured only once really installed.
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


for name in ("copilot-gw", "gemini-gw", "grok-gw"):
    if installed(name[:-3]):
        status[name[:-3]] = "native+gw" if (bindir / name).exists() else "NOT-gw"

# Gemini: gemini-gw reads GEMINI_GW_SETTINGS in its own home; the native settings.json is the user's.
# Its helper tasks (classifier, summarizers, web fetch, loop detection, compression) call Gemini model
# names the gateway does not serve; overrides swap only the model, keeping each config.
GW_IDS = {m for m, *_ in GW_MODELS}
if installed("gemini"):
    flash = ["flash-lite", "flash", "gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-3.1-flash-lite-preview",
             "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
    pro = ["pro", "gemini-3-pro-preview", "gemini-3.1-pro-preview", "gemini-3.1-pro-preview-customtools", "gemini-2.5-pro"]
    gw = {"security": {"auth": {"selectedType": "gemini-api-key"}}, "model": {"name": GW_DEFAULT},
          "privacy": {"usageStatisticsEnabled": False}, "general": {"enableAutoUpdate": False},
          # /model lists modelDefinitions (under Manual) only with this experimental flag on.
          "experimental": {"dynamicModelConfiguration": True},
          "modelConfigs": {
              # Effort is high no matter what (Q268): every reasoning model thinks at HIGH.
              "customOverrides": [{"match": {"model": m}, "modelConfig": {"model": "claude-haiku-5-5"}} for m in flash] +
                                 [{"match": {"model": m}, "modelConfig": {"model": "claude-sonnet-5-5"}} for m in pro] +
                                 [{"match": {"model": m}, "modelConfig": {"generateContentConfig": {"thinkingConfig": {
                                     "thinkingLevel": "HIGH", "includeThoughts": True}}}} for m, _, _, _, r, _ in GW_MODELS if r],
              "modelDefinitions": {i: {"tier": "custom", "isPreview": False, "isVisible": True, "displayName": name,
                                       "dialogDescription": "Through the gateway", "features": {"thinking": r, "multimodalToolUse": False}}
                                   for i, name, _, _, r, _ in GW_MODELS}}}
    # gemini saves /model picks and its own state here, so merge: a gateway model the user picked stays.
    d = json.loads(GEMINI_GW_SETTINGS.read_text()) if GEMINI_GW_SETTINGS.exists() else {}
    new = json.loads(json.dumps(d))
    for k, v in gw.items():
        new[k] = {**new.get(k, {}), **v} if k != "modelConfigs" else v
    if d.get("model", {}).get("name") in GW_IDS - {"claude-opus-5-5"}:
        new["model"]["name"] = d["model"]["name"]
    # Mirror the native MCP servers, hooks and context files (context-mode, browseros-neo, orca ...); the
    # native home is only read. context.fileName paths are relative to the home, hence the .agents link.
    try:
        nd = json.loads(GEMINI_SETTINGS.read_text()) if GEMINI_SETTINGS.exists() else {}
    except ValueError:
        nd = {}
    for k in ("mcpServers", "hooks", "hooksConfig", "context"):
        if k in nd:
            new[k] = nd[k]
        else:
            new.pop(k, None)
    if new != d:
        GEMINI_GW_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        write(GEMINI_GW_SETTINGS, json.dumps(new, indent=2) + "\n")
    link(GEMINI_GW_HOME / ".agents", H / ".agents")
    for sub in ("extensions", "commands", "skills", "GEMINI.md"):
        link(GEMINI_GW_SETTINGS.parent / sub, H / ".gemini" / sub)
    # Undo what this script used to write into the native settings.json, recognised by its gateway model
    # definitions. The privacy and auto-update settings stay.
    p = GEMINI_SETTINGS
    d = json.loads(p.read_text()) if p.exists() else {}
    mc = d.get("modelConfigs", {})
    if any(v.get("dialogDescription") == "Through the gateway" for v in mc.get("modelDefinitions", {}).values()):
        new = json.loads(json.dumps(d)); mc = new["modelConfigs"]
        for i in GW_IDS:
            mc["modelDefinitions"].pop(i, None)
        if all(o.get("modelConfig", {}).get("model") in GW_IDS for o in mc.get("customOverrides", [])):
            mc.pop("customOverrides", None)
        for k in [k for k in mc if not mc[k]]:
            del mc[k]
        if not mc:
            del new["modelConfigs"]
        if new.get("model", {}).get("name") in GW_IDS:
            del new["model"]["name"]
        if new.get("security", {}).get("auth", {}).get("selectedType") == "gemini-api-key":
            del new["security"]["auth"]["selectedType"]
        new.get("experimental", {}).pop("dynamicModelConfiguration", None)
        if new.get("security", {}).get("auth") == {}:
            del new["security"]["auth"]
        for k in ("model", "security", "experimental"):
            if new.get(k) == {}:
                del new[k]
        write(p, json.dumps(new, indent=2) + "\n")

# grok: custom models read the key from the environment; no xAI login, catalog fetch or telemetry.
# grok rewrites config.toml itself and appends its own tables at the end, so this checks the parsed
# file and rewrites only when a gateway setting is missing: grok's tables and a gateway model the
# user picked as default survive a rerun. All of it lives in grok-gw's GROK_HOME (Q268); ~/.grok is native.
p = H / ".grok-gw/config.toml"
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
                and models.get("default_reasoning_effort") == "high"  # effort is high no matter what (Q268)
                and all(feats.get(k) is False for k in ("telemetry", "feedback", "remote_fetch")))
    # Compared without quotes: grok rewrites [model."x"] as [model.x].
    managed = {"[models]", "[features]"} | {f"[model.{m}]" for m in gw_models}

    def drop_managed(text, tables):
        """text without the given tables and without this script's earlier comment lines."""
        keep, skip = [], False
        for ln in text.splitlines(keepends=True):
            if re.match(r"^\s*\[", ln):
                skip = ln.strip().replace('"', "") in tables
            if not skip and not re.match(r"^# (cliproxyapi|--- (end )?cliproxyapi)", ln):
                keep.append(ln)
        return "".join(keep).strip("\n")
    # Undo the block this script used to write into the native ~/.grok/config.toml. [features] (telemetry off) stays.
    native = H / ".grok/config.toml"
    ntext = native.read_text() if native.exists() else ""
    try:
        ndoc = tomllib.loads(ntext)
    except tomllib.TOMLDecodeError:
        ndoc = None
    if ndoc and any(ndoc.get("model", {}).get(m, {}).get("base_url") == f"{BASE}/v1" for m in gw_models):
        tables = {f"[model.{m}]" for m in gw_models} | ({"[models]"} if ndoc.get("models", {}).get("default") in gw_models else set())
        cand = drop_managed(ntext, tables)
        cand = cand + "\n" if cand else ""
        assert not any(m in tomllib.loads(cand).get("model", {}) for m in gw_models), "grok native candidate invalid"
        write(native, cand)
    text = p.read_text() if p.exists() else ""
    try:
        on_gw = grok_on_gw(tomllib.loads(text))
    except tomllib.TOMLDecodeError:
        on_gw = None
    if on_gw is False:
        block = ("# cliproxyapi (managed by cliproxy-tier, Q268): every grok-gw model goes through CLIProxyAPI.\n"
                 f'[models]\ndefault = "{GW_DEFAULT}"\ndefault_reasoning_effort = "high"\n' +
                 "".join(f'{k} = "claude-haiku-5-5"\n' for k in roles) +
                 "".join(f'\n[model."{m}"]\nmodel = "{m}"\nbase_url = "{BASE}/v1"\napi_backend = "{api}"\nenv_key = "CLIPROXY_API_KEY"\n'
                         f'context_window = {c}\nvision = {str(img).lower()}\n'
                         for m, (api, c, img) in gw_models.items()) +
                 "\n[features]\ntelemetry = false\nfeedback = false\nremote_fetch = false\n")
        # Drop the managed tables (and an earlier block's comment lines) from the rest, keep the others.
        rest = drop_managed(text, managed)
        cand = block + ("\n" + rest + "\n" if rest else "")
        try:
            ok = grok_on_gw(tomllib.loads(cand))
        except tomllib.TOMLDecodeError:  # e.g. managed keys set as dotted keys or inline tables elsewhere
            ok = False
        if ok:
            p.parent.mkdir(parents=True, exist_ok=True)
            write(p, cand)
            on_gw = True
    if not on_gw:
        status["grok"] = "NOT-gw(conflict)"
    # Mirror the native MCP servers (browseros-neo ...) and share skills and hooks; the native home is only read.
    MCP_TBL = re.compile(r"^\[mcp_servers\.[^\n]*\]\n(?:(?!\[)[^\n]*\n)*", flags=re.M)
    ntext = native.read_text() if native.exists() else ""
    gtext = p.read_text() if p.exists() else ""
    try:
        want_mcp = tomllib.loads(ntext).get("mcp_servers", {})
        if on_gw and tomllib.loads(gtext).get("mcp_servers", {}) != want_mcp:
            cand = MCP_TBL.sub("", gtext).rstrip("\n") + "\n" + "".join("\n" + b.rstrip("\n") + "\n" for b in MCP_TBL.findall(ntext))
            assert tomllib.loads(cand).get("mcp_servers", {}) == want_mcp, "grok-gw mcp candidate invalid"
            write(p, cand)
    except (tomllib.TOMLDecodeError, AssertionError) as e:  # e.g. MCP servers set as an inline table: left as they are
        status["grok"] = f"native+gw(mcp-not-mirrored: {e})"[:120]
    for sub in ("skills", "hooks"):
        link(p.parent / sub, H / ".grok" / sub)

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
             "# --- end cliproxyapi ---\n")

    def crush_ok(cand):
        tmp = p.with_name("crushrc.cand"); tmp.parent.mkdir(parents=True, exist_ok=True); tmp.write_text(cand)
        ok = run("bash", "-n", str(tmp)).returncode == 0; tmp.unlink()
        assert ok, "crushrc candidate fails bash -n"
    managed_block(p, block, crush_ok)
    # The models go in crush's data-dir state, where a model picked in crush is saved: a `model large` line
    # in crushrc would outrank that pick on every start. Only a missing or old default is replaced (Q268),
    # and effort stays high whatever the model.
    sp = H / ".local/share/crush/crush.json"
    try:
        sd = json.loads(sp.read_text()) if sp.exists() else {}
    except ValueError:
        sd = None
    if sd is not None:
        new = json.loads(json.dumps(sd)); ms = new.setdefault("models", {})
        if ms.get("large", {}).get("model") in (None, "claude-opus-5-5"):
            ms["large"] = {"provider": "cliproxy", "model": GW_DEFAULT}
        ms["large"].update(think=True, reasoning_effort="high")
        ms.setdefault("small", {"provider": "cliproxy", "model": "claude-haiku-5-5"})
        if new != sd:
            sp.parent.mkdir(parents=True, exist_ok=True)
            write(sp, json.dumps(new, indent=2) + "\n")
    status["crush"] = "gw" if sd is not None else "gw(state-unparsed)"

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
               "--custom-model-id", GW_DEFAULT, "--custom-provider-id", "cliproxy", "--custom-image-input",
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
                "agents": {"defaults": {"models": {f"cliproxy/{m}": {} for m, *_ in GW_MODELS},
                                        "thinkingDefault": "high"}}}  # effort is high no matter what (Q268)
        try:
            d = json.loads(p.read_text())
        except ValueError:  # hand-edited JSON5: leave it to `openclaw config`
            d = None
        # A gateway model the user picked as primary or utility model stays; the old default does not (Q268).
        dflt = (d or {}).get("agents", {}).get("defaults", {})
        primary = str(dflt.get("model", {}).get("primary", ""))
        if not primary.startswith("cliproxy/") or primary == "cliproxy/claude-opus-5-5":
            want["agents"]["defaults"]["model"] = {"primary": f"cliproxy/{GW_DEFAULT}"}
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

# ---------- pi: converged by Ansible; just assert here ----------
p = H / ".pi/agent/settings.json"
if p.exists():
    sd = json.loads(p.read_text())
    dm = f"{sd.get('defaultProvider')}/{sd.get('defaultModel')}"
    auth = H / ".pi/agent/auth.json"
    au = json.loads(auth.read_text()) if auth.exists() else {}
    # Same rule as roles/pi's pi_keep: any bare cliproxy model but the old default is on the gateway.
    m = sd.get("defaultModel") or ""
    on_gw = sd.get("defaultProvider") == "cliproxy" and m and "/" not in m and m != "claude-opus-5-5"
    status["pi"] = ("gw" if on_gw else f"DEFAULT={dm}") + (f" AUTH={list(au)}" if au else "")

print(f"{os.uname().nodename.split('.')[0]}: " + " ".join(f"{k}={v}" for k, v in status.items()))
print("  changed: " + (", ".join(changed) or "nothing"))
if backups:
    print("  backups: " + ", ".join(backups))
