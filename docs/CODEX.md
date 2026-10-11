# Running mythras-gm in Codex

There is no separate Codex build of this plugin, and there is no sync job. Codex
reads this repository's Claude manifests directly:

| What | File | How Codex treats it |
| --- | --- | --- |
| Marketplace catalogue | `.claude-plugin/marketplace.json` | a "legacy-compatible marketplace", read alongside `.agents/plugins/marketplace.json` |
| Plugin manifest | `.claude-plugin/plugin.json` | a recognised compatibility manifest; `.codex-plugin/plugin.json` is optional |
| Hooks | `hooks/hooks.json` | discovered by default; `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA` are set for hook commands, for compatibility |
| Skills | `skills/*/SKILL.md` | the same format both hosts use (agentskills.io) |

What keeps that true over time is `tests/test_portability.py`, which runs in the
ordinary `tests` workflow and fails if a Claude-only construct comes back.

## Install

In a Codex CLI session:

```text
/plugins
```

Add this repository as a marketplace, install `mythras-gm`, then **start a new
session** — bundled skills only become available in a session started after the
install. The non-interactive equivalent is
`codex plugin marketplace add https://github.com/fourth-wall-gaming/mythras-gm.git`.

## Two things to do once, or the game cannot come up

**1. Trust the hook.** Installing or enabling a plugin does not trust its hooks:
Codex skips plugin-bundled hooks until you review and trust the current hook
definition. Until you do, the session-start preflight never runs — so TypeDB is
never started, the schema is never loaded, and the skills have no engine path.
This looks exactly like a broken database and is not one.

**2. Let the sandbox install the server.** `init-db` downloads a ~25MB native
TypeDB server on first run and installs it outside the workspace (`~/.typedb`).
Under `workspace-write` both the write and the download are blocked, so in
`~/.codex/config.toml`:

```toml
[sandbox_workspace_write]
network_access = true
writable_roots = ["~/.typedb"]
```

Trusting the project (`[projects."/path/to/your/campaign"] trust_level =
"trusted"`) is the blunter alternative.

Diagnose either failure with the `mythras-setup` skill, which runs `doctor` and
reads back every `false` check.

## What differs from Claude Code

- **No slash commands.** Codex has no commands component — skills, MCP servers
  and hooks only. `/mythras-gm:play` is a Claude Code entry point; in Codex,
  invoke the skill (`$mythras-play`, or just ask to play) and Codex loads the
  same instructions the command delegates to.
- **`agents/*.md` are not ported.** The three lookup subagents are in Claude
  Code's format. Codex has subagents, but they are configured differently;
  nothing here depends on them, and play is unaffected.
- **The canon loads from `AGENTS.md`.** Codex reads `AGENTS.md`; Claude Code
  reads `CLAUDE.md`, which imports it. One file, both hosts.

## Checking a machine where it will not start

One command. It installs nothing, downloads nothing, and changes nothing:

```bash
curl -fsSL https://raw.githubusercontent.com/fourth-wall-gaming/mythras-gm/main/scripts/verify-install.sh | bash
```

It reports the host, the engine, `uv`, whether the save location is writable,
outbound network, the database verdict, and — if a campaign plugin is installed
— whether that campaign can find the engine. For anything that fails it prints
the remedy as an action to take, and exits non-zero. Nothing it reports requires
reading this document first.

**A second machine tells you something this repository's own machine cannot.**
A campaign plugin finds the engine by searching, and one of its probes is
`$HOME/mythras-gm` — so on a development machine with a checkout there, the
lookup always succeeds no matter which host is running. A clean machine is the
only place that probe can be observed failing.

**If you would rather not run a script**, ask the agent why the game will not
start. The `mythras-setup` skill runs the same checks, says what is wrong in
plain language, and offers to make the config change for you rather than handing
you a file to edit.
