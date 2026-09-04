# CLAUDE.md — mythras-gm

Guidance for Claude Code working in this repository.

## What this is

**mythras-gm** is a standalone Claude Code plugin: a Gamesmaster system for
running persistent tabletop RPG campaigns (Mythras Imperative / Classic Fantasy)
with all game state in **TypeDB**. It is **self-contained** — it depends on no
other plugin and on no Alhazen infrastructure. It needs only **`uv`** and
**`docker`** (plus `pandoc` + `typst` for novelisation PDFs).

The player talks to you in natural language; you narrate, play the NPCs, and call
for rolls. The CLI is your dice tower and your save file.

## Layout

```
.claude-plugin/           plugin.json (manifest) + marketplace.json
hooks/hooks.json          SessionStart hook -> skills/mythras-gm/mythras_init.py
agents/gamemaster/        the Gamesmaster subagent
skills/mythras-gm/        the skill itself:
  SKILL.md                skill entry point (operating rules — read this to play)
  USAGE.md                full CLI reference (GM rules, chargen, combat, publishing)
  CHARACTER-SCORES.md     how to play NPCs from their stored character score
  WORLD-STATE.md          doing / knowledge / camera / canon between scenes
  NOVELIZATION.md         turning a campaign journal into a typeset PDF novel
  mythras_gm.py           the CLI (dice, combat, CRUD, rules graph, publishing)
  mythras_init.py         SessionStart provisioner (TypeDB + DB + rules)
  mythras_engine.py       deterministic rules engine (rolls, combat)
  schema.tql              the myth- schema
  base-schema.tql         the base types (own root types — no alh- dependency)
  db_copy.py              id-preserving DB copy (backup / clone / move servers)
  rules/ , rules-cfi/     the rules graph (Imperative core; CFI variant)
  styles/ , book_template/ novelisation assets
tests/                    pytest suite
```

## The database (own, standalone)

- Default database: **`mythras`** (`$TYPEDB_DATABASE`). This is the save file.
- The **SessionStart hook** runs `mythras_init.py`, which is idempotent:
  1. If a TypeDB server is already reachable at `$TYPEDB_HOST:$TYPEDB_PORT`
     (default `localhost:1729`) it is **adopted** — the existing `mythras`
     database is left untouched.
  2. Otherwise it starts — **creating it the first time** — its own container
     `$MYTHRAS_TYPEDB_CONTAINER` (default **`mythras-typedb`**, image
     `typedb/typedb:3.8.0`) with its own named data volume, then provisions the
     `mythras` DB from `base-schema.tql` + `schema.tql` and loads the rules graph.
- **Running alongside another TypeDB** (e.g. an Alhazen container already on
  1729): give this one its own port, `export TYPEDB_PORT=1730`, so the two
  coexist. `db_copy.py` (or the CLI's `export-campaign` / `import-campaign`)
  moves campaigns between them.

## Non-negotiables (how to run the game)

1. **Every roll goes through the CLI** — `roll-skill`, `roll-opposed`,
   `resolve-attack`, `apply-damage`. Never free-hand or narrate dice you did not
   roll through the engine.
2. **The database is the save.** Persist with `log-event`, `set-scene`,
   `update-character`, `add-lore`, etc. Never hand-edit a campaign's exported
   files to change game state.
3. **A published campaign's file tree is a snapshot, not the live game.** If you
   find yourself reading a campaign folder (it carries a `CLAUDE.md` saying so),
   drive play through this skill and its DB instead of GMing off the files.

To play, read `skills/mythras-gm/SKILL.md` — it is the operating entry point.

## CLI

```bash
GM="skills/mythras-gm"
uv run --project "$GM" python "$GM/mythras_gm.py" <command> [args] 2>/dev/null
```

`$TYPEDB_DATABASE` defaults to `mythras`; `--campaign` resolves from
`$MYTHRAS_CAMPAIGN` or the only campaign present. Start a play session with
`list-campaigns` then `get-context --campaign <id> --compact`.

## Context discipline

Every token loaded is re-sent each turn. Load the minimum: start with
`get-context --compact`; pull a full sheet only when you need it; fetch rules on
demand from the graph with `query-rules --facet ...` rather than reading
`rules/*.md` wholesale. See SKILL.md for the full discipline.

## Safety

- **Back up before anything destructive.** Before a schema reload or a risky
  change, snapshot with `export-campaign --campaign <id> --output <dir>` (or
  `db_copy.py copy --src mythras --dst mythras_backup`). Exports are read-only on
  the source.
- **TypeDB 3.8 gotchas:** never run a variable-free schema match
  (`match X sub Y;` with two concrete labels crashes the server — always bind a
  variable). Insert with UTF-8, not `\uXXXX` escapes (`ensure_ascii=False`).
- **Pin the driver** `typedb-driver>=3.8.0,<3.9`; the venv wants Python 3.11-3.13
  (3.14 segfaults the driver).

## Tests

`uv run --project skills/mythras-gm pytest tests/ -q` from the repo root.
