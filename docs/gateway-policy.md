# Gateway policy for coding CLIs

This is the target policy for how each coding CLI uses CLIProxyAPI, the gateway on mac-mini-m2.
`gateway/cliproxy-tier-host.py` applies it on every host, and `gateway/cliproxy-assert-pi`
re-asserts pi. Frank set it on 2026-10-20 (Q268 in `DECISIONS.md`).

## Class 1: CLIs with their own vendor login

claude, codex, gemini, grok (Grok Build), kimi, copilot.

- The plain command stays as the vendor ships it: its own login, model and effort. The policy does
  not touch it.
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
  the user picked a different gateway model, the script keeps that model.

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
