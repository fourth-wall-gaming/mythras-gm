@AGENTS.md

## Why this file is two lines

The canon lives in `AGENTS.md` so that one file serves both hosts. Codex reads
`AGENTS.md` directly; Claude Code reads it **only** when no `CLAUDE.md` sits at
or above the working directory — and this repository has one, so without the
import above, Claude Code would read this file and silently ignore the canon.

Keep the canon in `AGENTS.md`. Add Claude-Code-specific instructions below this
line, never above it, and never a second copy of anything in `AGENTS.md`.
