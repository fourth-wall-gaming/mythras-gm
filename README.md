# alhazen-skill-mythras

**A Claude-powered Gamesmaster for Mythras Imperative, with persistent campaigns in TypeDB.**

Tell Claude *"run my Veilwrack campaign"* and it becomes your GM: narrating
scenes, playing NPCs, and resolving every skill check and combat exchange
through a deterministic rules engine — while every character, wound, faction,
and journal entry persists in a TypeDB knowledge graph so the game can be
picked up at any time, in any future session, with zero context loss.

Built as a skill + agent for the [Skillful-Alhazen](https://github.com/GullyBurns/skillful-alhazen)
agent OS, but the CLI and engine run standalone against any TypeDB 3.x server.

## What's in the box

```
skills/mythras-gm/
  SKILL.md                  GM operating manual (how Claude runs the table)
  mythras_engine.py         Pure rules engine -- no I/O, fully unit-testable
  mythras_gm.py             CLI: 25 commands over TypeDB (JSON in/out)
  schema.tql                TypeDB myth- namespace
  campaign_io.py            Campaign publishing: export/import file trees
  rules/
    core-mechanics.md       Distilled SRD: checks, grades, opposed rolls, fatigue, healing
    combat.md               Distilled SRD: initiative, action points, special effects, wounds
    magic.md                Distilled SRD: Magic & Superpowers frameworks
agents/gamemaster/
  AGENT.md                  The Gamesmaster persona for Claude
```

Campaign settings live in their own repos and load with `import-campaign`.
The reference campaign is **[The Veilwrack: The Stilling](https://github.com/fourth-wall-gaming/veilwrack-campaign)** —
a full worldbook (46 lore entries), characters, factions, locations,
templates, and seed scripts.

## The rules engine

Implements Mythras Imperative mechanics faithfully:

- d100 skill checks with criticals (skill/10), fumbles, and the 01-05 / 96-00 rules
- Difficulty grades (Very Easy through Herculean)
- Opposed and differential rolls, including the over-100% skill adjustment
- Damage modifiers, hit-location tables (humanoid, **winged avianoid**, winged quadruped)
- Full attack resolution in one CLI call: differential roll, special-effect
  count, damage + modifier, hit location, parry size reduction, armor, wound level
- Action-point economy and initiative (with armor penalties) per encounter
- Character generation: rolled or assigned characteristics, derived attributes,
  auto-computed base skills, fatigue track, luck points, passions

## The setting: THE VEILWRACK

An original sky realm. No ground — an endless sky above the toxic **Undermist**.
The winged **Alar** peoples live on **Spires**: floating calcified husks of the
dead sky-leviathans whose marrow still holds living wind. The threat is the
**Stilling** — spreading zones of dead air where flight fails, sound dies,
spires sink, and the **Hushed** walk back out changed. The wind itself is
dying, and somebody, a thousand years ago, is to blame.

Three kindreds (Vael couriers, Roak archivists, Ossuin death-priests), five
factions, a five-act campaign arc, and a bestiary — published in full at
[fourth-wall-gaming/veilwrack-campaign](https://github.com/fourth-wall-gaming/veilwrack-campaign)
and loadable into TypeDB with one command.

## Install as Claude Code Plugin

The fastest way to play. Requires [Claude Code](https://claude.ai/code)
v1.0.33+, Docker, and [uv](https://docs.astral.sh/uv/).

### Step 1: Install the alhazen-core infrastructure plugin

mythras-gm stores all game state in TypeDB. The `alhazen-core` plugin
handles TypeDB startup and provides the base schema that mythras-gm extends.

```
/plugin marketplace add sciknow-io/alhazen-skill-examples
/plugin install alhazen-core@alhazen-skills
/alhazen-core:init
```

### Step 2: Install mythras-gm

```
/plugin marketplace add fourth-wall-gaming/mythras-gm
/plugin install mythras-gm
```

The plugin's SessionStart hook auto-loads the myth- namespace schema
into TypeDB on every new session.

### Step 3 (optional): Load a campaign setting

```bash
git clone https://github.com/fourth-wall-gaming/veilwrack-campaign
```

Then tell Claude: *"Import the Veilwrack campaign from ~/veilwrack-campaign"*

Or create a fresh campaign: just say *"Create a new Mythras campaign"*
and the GM will walk you through worldbuilding and character creation.

## Quick start (standalone)

For use without Claude Code. Prereqs: Python 3.11+, `typedb-driver>=3.8.0`,
a running TypeDB 3.x server with the
[alhazen-core](https://github.com/sciknow-io/alhazen-skill-examples/tree/main/skills/core/alhazen-core)
base schema loaded.

```bash
# environment (defaults shown)
export TYPEDB_HOST=localhost TYPEDB_PORT=1729 TYPEDB_DATABASE=alhazen_notebook

# 1. load the myth- namespace schema
python - <<'PY'
from typedb.driver import TypeDB, TransactionType, Credentials, DriverOptions
driver = TypeDB.driver("localhost:1729", Credentials("admin","password"),
                       DriverOptions(is_tls_enabled=False))
with driver.transaction("alhazen_notebook", TransactionType.SCHEMA) as tx:
    tx.query(open("skills/mythras-gm/schema.tql").read()).resolve()
    tx.commit()
PY

# 2. load the Veilwrack campaign
git clone https://github.com/fourth-wall-gaming/veilwrack-campaign
uv run --project skills/mythras-gm python skills/mythras-gm/mythras_gm.py \
  import-campaign --path veilwrack-campaign --new-ids

# 3. make a character and play
uv run --project skills/mythras-gm python skills/mythras-gm/mythras_gm.py \
  create-character --campaign <id> --name "Kithrel of the Moult" --roll --type pc
uv run --project skills/mythras-gm python skills/mythras-gm/mythras_gm.py \
  get-context --campaign <id>
```

Or, inside Skillful-Alhazen, register in `skills-registry.yaml` and say
*"run my Veilwrack campaign"*.

## Using with Skillful-Alhazen

```yaml
# skills-registry.yaml
- name: mythras-gm
  git: https://github.com/fourth-wall-gaming/mythras-gm
  ref: main
  subdir: skills/mythras-gm
# ...and under schema_map.namespaces:
    myth:
      skill: mythras-gm
      schema: local_skills/mythras-gm/schema.tql
      depends_on: []
```

```yaml
# agents-registry.yaml
- name: gamemaster
  git: https://github.com/fourth-wall-gaming/mythras-gm
  ref: main
  subdir: agents/gamemaster
```

## Licensing

- **Code** (the engine, CLI, and rules distillations): MIT License (see
  LICENSE). The Veilwrack setting content lives in
  [veilwrack-campaign](https://github.com/fourth-wall-gaming/veilwrack-campaign)
  under the same terms.
- **Game mechanics** are based on the *Mythras Imperative* SRD and are used
  under the **ORC License**. ORC Notice:

> This product is based on *Mythras Imperative*, Written by Pete Nash and
> Lawrence Whitaker, and published by The Design Mechanism, Copyright 2023.
> *Mythras* and *Mythras Imperative* are Reserved Material of The Design
> Mechanism. The SRD text consulted is maintained at
> [raleel/mythras-srd](https://github.com/raleel/mythras-srd).

The Veilwrack setting (names, lore, story arcs, distinctive characters) is
Reserved Material of this repository's authors under the ORC framework, and
simultaneously released under MIT — use it freely with attribution.
