# Gateway policy for coding CLIs

This is the target policy for how each coding CLI uses CLIProxyAPI, the gateway on mac-mini-m2.
`gateway/cliproxy-tier-host.py` applies it on every host. For pi, the `pi` role sets the default model.
Frank set it on 2026-10-20 (Q268 in `DECISIONS.md`).

## Class 1: CLIs with their own vendor login

claude, codex, gemini, grok (Grok Build), kimi, copilot.

- The plain command stays as the vendor ships it: its own login, model and effort. The policy does
  not change how it behaves. The script still edits two native files, see below.
- A separate `<cli>-gw` wrapper in `~/.local/bin` sends the CLI through CLIProxyAPI.
- Each `-gw` wrapper starts on `deepseek-v4.1-flash`, with two exceptions:
  - `claude-gw` starts on `claude-opus-5-5`.
  - `codex-gw` starts on `gpt-6-astra`.

## Class 2: CLIs without a vendor login

pi, omp, hermes, crush, openclaw, opencode.

- No wrapper. The CLI's own config uses CLIProxyAPI as its provider and `deepseek-v4.1-flash` as
  its model.
- opencode is in this class even though it has the opencode Go plan. It gets no `opencode-gw`.

## Rules for both classes

- **Effort is always high** on every gateway path, with no exceptions. This includes `claude-gw`
  and `codex-gw`.
- **No per-host logic.** Every host gets the same model and effort.
- A default is only a starting point. When the script finds the old default, it replaces it. When
  the user picked a different gateway model, the script keeps that model. Effort is set back to high
  either way. For crush, the models live in its data-dir state, `~/.local/share/crush/crush.json`,
  where crush saves a pick. A `model large` line in `crushrc` would outrank that pick on every start.
  For pi, the `pi` role keeps a pick.

## How the script keeps class 1 native

`claude-gw` and `copilot-gw` pass the gateway on the command line and in environment variables.
`codex-gw` does too, but it also needs files in the native `~/.codex`: a `[model_providers.cliproxy]`
table in `config.toml`, the `cliproxy.config.toml` profile it selects with `-p cliproxy`, and
`cliproxy-models.json`, its model catalog. Plain `codex` ignores all three. The script also removes
gateway keys from the native files, so that the plain commands stay native: `ANTHROPIC_AUTH_TOKEN`
and `ANTHROPIC_BASE_URL` from `~/.claude/settings.json`, and a top-level
`model_provider = "cliproxy"` from `~/.codex/config.toml`.

kimi, gemini and grok need a gateway default in a config file, so each `-gw` wrapper gets its own
home: `KIMI_CODE_HOME=~/.kimi-code-gw`, `GEMINI_CLI_HOME=~/.gemini-gw` and `GROK_HOME=~/.grok-gw`. On
its first run after the change, the script removed the gateway settings it used to write into the
native `~/.kimi-code`, `~/.gemini` and `~/.grok`.

Each run also mirrors the native home's tools into the `-gw` home, and only reads the native home:
- kimi: the `[[hooks]]` tables and `mcp.json`, and a `hooks` link.
- gemini: `mcpServers`, `hooks`, `hooksConfig` and `context`, links for `extensions`, `commands`, `skills`
  and `GEMINI.md`, and `~/.gemini-gw/.agents` linked to `~/.agents` (`context.fileName` paths are
  relative to the home).
- grok: the `[mcp_servers.*]` tables, and `skills` and `hooks` links.

So a role or a hand edit that adds an MCP server or hook to the native home reaches the `-gw` wrapper at
the next `cliproxy-tier` run.

## Known gaps

- **opencode's oh-my-openagent plugin** pins its own agents (Sisyphus and the rest) to
  `anthropic/claude-*` models, and its Sisyphus agent wins even over `--agent build`. Those models
  go through the gateway, but they are not `deepseek-v4.1-flash`. Frank will fix the plugin's
  model pins later.
- **gemini-gw on Nickel models** (deepseek, qwen, glm) prints `Model stream ended without a finish
  reason`, and deepseek repeats its answer. Claude models are fine. The cause is the gateway's
  Gemini-format translation, not the thinking setting.

## Out of scope: Cursor CLI

`cursor-agent` has no option for a custom endpoint. Its `--endpoint` flag and `CURSOR_API_ENDPOINT`
only choose which Cursor backend it logs in to, and every request after login uses Cursor's
private RPC protocol. So no one can build a working `cursor-gw`, and the scripts leave Cursor CLI
alone. Check again if Cursor ships a custom-endpoint option for the CLI.
Sources: [Cursor CLI parameters](https://cursor.com/docs/cli/reference/parameters),
[LiteLLM's Cursor guide](https://docs.litellm.ai/docs/tutorials/cursor_integration).

## Adding a CLI

Ask one question: does the CLI have its own vendor login? If yes, it is class 1: leave the plain
command alone and add a `<cli>-gw` wrapper. If no, it is class 2: point its own config at the
gateway. If it cannot reach a custom endpoint at all, it is out of scope, like Cursor CLI.
