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

## The living world

NPCs are not scenery waiting to be visited. Every significant character and
faction holds an **agenda** -- a goal with a progress clock -- and each agenda
schedules **beats**: the concrete things it produces if nobody interferes,
placed in world time and given a location and a cast.

```bash
tick --campaign <id> --to "d-3/night"
```

`tick` advances the world clock and reports every beat that has come due,
flagged **onscreen** (a PC is at its location or in its cast -- play it) or
**offscreen** (it happens anyway, and becomes a fact they may later discover).
Staging is read from recorded presence, not chosen: move the party, and the
attack they would have interrupted becomes the one they hear about at dawn.

Clocks advance when the fiction earns it (`advance-agenda`), agendas can be
`thwarted` outright, new ones appear when player action creates new interests,
and `revise-beat` bends any plan that play has made stale. The structure keeps
the world moving consistently between sessions; it is not a rail.

## What each character knows

The world engine says what is happening; the fact graph says who is aware of it.

Situational truth lives in exactly one place -- a graph of **facts**, each one a
proposition with a status (`not-yet-true` -> `established`), a truth value, and
the moment it became true. What a character knows is a **projection** of that
graph through `myth-knows` edges carrying certainty, source and when they
learned it. There is no per-character state store, so two views cannot drift
apart.

```bash
character-view --campaign C --id <pc> --compact   # what they can act on
who-knows --campaign C --fact F                   # who could betray this
check-consistency --campaign C                    # reconcile it all
```

Because status and truth are independent, a **believed falsehood is a
first-class object** -- the rumour that sends a city hunting the wrong man is
data, not GM improvisation. And agendas can be gated on knowledge: a dormant
agenda whose holder learns its trigger fact is activated by `tick` itself, so
"the Baron acts the moment he sees that face" is computed rather than
remembered.

`check-consistency` catches a character knowing something that has not happened
yet, or learning it before it was true -- the class of error that otherwise
hides in prose until it contradicts play.

## Novelization

Turn a campaign's journal into a typeset PDF novel. Claude reads the event
journal and player-visible canon from TypeDB, drafts chapters in a chosen
author style (Hemingway, Tolkien, Moorcock, or any description you give it),
and `novelist.py` renders the manuscript with pandoc + Typst.

```bash
brew install pandoc typst    # one-time, for PDF builds
```

Then just ask: *"Novelize the Veilwrack campaign in Moorcock's style."*
Claude extracts the journal, proposes a chapter outline for your approval,
drafts the chapters, and builds the PDF. Manuscripts live in the campaign
repo under `novels/<slug>/` and are never imported back into game state --
keep as many parallel novelizations as you like.

## Install as Claude Code Plugin

The fastest way to play. Requires [Claude Code](https://claude.ai/code)
v1.0.33+ and [uv](https://docs.astral.sh/uv/). Nothing else -- the engine has
no plugin dependencies, and **no Docker.** TypeDB 3.x is a native binary with
no JVM, so `init-db` downloads a ~25MB self-contained server for your platform
on first run and manages it directly. Already have TypeDB running some other
way -- including via `docker-compose.yml`, still here for anyone who prefers
it? Pass `--docker`, or nothing changes: `init-db` checks for something already
listening before it manages anything at all.

### Want a game, not an engine?

Install a campaign and it brings the engine with it. The session-start hook
does the rest -- downloads the native server on first run, creates the
database, defines the schema, loads the rules graph -- so there is no separate
setup step:

```
/plugin marketplace add fourth-wall-gaming/mythras-gm
/plugin install purewater@fourth-wall-gaming
/purewater:start
```

### Just the engine

```
/plugin marketplace add fourth-wall-gaming/mythras-gm
/plugin install mythras-gm@fourth-wall-gaming
```

Start a session and the hook reports `mythras-gm ready`. `/mythras-gm:setup`
still exists for the rare case the hook could not manage it automatically --
no network for the first-run download, or a platform with no native build --
and for `--docker`, if you would rather run the old docker-compose.yml path.

If anything is wrong, one command tells you what:

```bash
GM="${CLAUDE_PLUGIN_ROOT}/skills/mythras-gm"
uv run -q --project "$GM" python "$GM/mythras_gm.py" doctor
```

### Locked-down or disposable containers

Claude Code cloud sessions run in a container whose home directory does not
survive an idle restart, and whose egress gateway refuses `repo.typedb.com`.
Neither is something `init-db` can fix, so each is one environment variable:

| Variable | What it does |
|---|---|
| `MYTHRAS_TYPEDB_HOME` | Where the server binary, PID file, log **and data directory** live. Default `~/.claude/mythras-gm/typedb`. Point it inside the repo checkout so the save survives whatever wipes `$HOME`. |
| `TYPEDB_DIST_BASE` | Directory URL holding `typedb-all-<platform>-<version>.<ext>` flat by filename -- a GitHub release page is the natural mirror, and GitHub asset hosts are reachable where the vendor CDN is not. |
| `TYPEDB_DIST_ARCHIVE` | Path to the archive already on disk. No network at all. Your file is never deleted. |
| `TYPEDB_DIST_SHA256` | Pinned digest the archive must match before anything is unpacked. Set it whenever you use a mirror. |

`doctor` reports all four. When the proxy refuses the download, `init-db`
says so, names the host to allowlist, and names the two variables that route
around it -- rather than the generic "could not download" that once cost a
whole session to diagnose.

**If the database is unreachable the CLI now says so on stdout and exits 1.** It
used to raise, and every documented invocation piped stderr to `/dev/null`, so a
dead database looked like an empty one and a whole session could be played with
nothing persisting. That is why no example here discards stderr.

### Published campaigns

| campaign | install |
|---|---|
| **And Then the Dragons Came: Purewater** — a canal city, a Baron with a concealed champion, three days to the Tourney | `/plugin install purewater@fourth-wall-gaming` |

Campaigns are plugins. They declare a dependency on this engine, ship their own
start command, and import themselves into TypeDB on first run.


Behind the scenes, Claude runs:

```bash
mythras_gm.py import-campaign --path ~/veilwrack-campaign --new-ids
```

The `--new-ids` flag remaps every entity ID so the campaign imports cleanly
into any database. All relations -- faction membership, lore links, character
presence, event involvement -- are rebuilt automatically. The round trip is
lossless.

After import, `get-context --campaign <id>` loads the full state: current
scene, PC/NPC sheets, factions, locations, a lore index (the entire
worldbook), and the last 15 journal events. That's the save file -- Claude
reads it and picks up exactly where the last session left off.

**Or start from scratch:** say *"Create a new Mythras campaign"* and the
GM will walk you through worldbuilding and character creation.

### Published campaigns

| Campaign | Repo | Description |
|---|---|---|
| **The Veilwrack: The Stilling** | [fourth-wall-gaming/veilwrack-campaign](https://github.com/fourth-wall-gaming/veilwrack-campaign) | An original sky realm -- 46 lore entries, 10+ characters, 7 factions, 5-act arc. No ground, winged peoples, dead leviathans as architecture, and the wind is dying. |

To publish your own campaign, use `export-campaign --campaign <id> --output <dir>`,
commit the output directory to a GitHub repo, and share the clone URL. Anyone
can load it with `import-campaign --path <clone> --new-ids`.

## Quick start (standalone)

For use without Claude Code. Prereqs: Python 3.11+, `typedb-driver>=3.8.0`,
a running TypeDB 3.x server with the
[alhazen-core](https://github.com/sciknow-io/skillful-alhazen/tree/main/skills/alhazen-core)
base schema loaded.

```bash
# environment (defaults shown)
export TYPEDB_HOST=localhost TYPEDB_PORT=1730 TYPEDB_DATABASE=mythras

# 1. load the myth- namespace schema
python - <<'PY'
from typedb.driver import TypeDB, TransactionType, Credentials, DriverOptions
driver = TypeDB.driver("localhost:1729", Credentials("admin","password"),
                       DriverOptions(is_tls_enabled=False))
with driver.transaction("mythras", TransactionType.SCHEMA) as tx:
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
