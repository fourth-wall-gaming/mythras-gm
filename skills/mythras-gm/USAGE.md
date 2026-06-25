# Mythras GM — Complete Reference

Full command reference for the Mythras GM skill. See SKILL.md for quick start.

```bash
CLI="${CLAUDE_PLUGIN_ROOT}/skills/mythras-gm/mythras_gm.py"
PRJ="${CLAUDE_PLUGIN_ROOT}/skills/mythras-gm"
uv run --project "$PRJ" python "$CLI" <command> [args] 2>/dev/null
```

## Session Startup (ALWAYS do this first)

1. `list-campaigns` — find the campaign (or `create-campaign` for a new one;
   published campaigns such as
   [veilwrack-campaign](https://github.com/fourth-wall-gaming/veilwrack-campaign)
   load with `import-campaign --path <clone> --new-ids`).
2. `get-context --campaign <id> --compact` — returns campaign scene/date, PC
   **combat cards** (live state: HP per location, fatigue, luck, AP, damage
   mod, combat styles, passions, characteristics — no skills dict, equipment,
   spells, or prose), NPC roster, locations, factions, active encounters, and
   the last 5 journal events. **This is your save file. Read it before
   narrating.** Drop `--compact` only when you actually need full sheets + the
   lore index. Pull full worldbuilding text on demand with `get-lore --id
   <lore-id>`; never show the player entries with visibility `gm`.
3. **Do not preload the rules.** The CLI resolves every roll deterministically,
   so the rules prose is rarely needed. When a beat needs a rule the engine
   doesn't fully encode, fetch only the relevant pieces from the rules graph:
   - `list-rules` — the lean index (id/title/domain/topic/kind) for orientation;
     add `--facets` for the tag lists (heavier) or `--category <domain>` to narrow.
   - `query-rules --facet dim=value [--facet ...] [--linked]` — the live fetch,
     ranked by how many of the situation's facets a rule matches.
   - `get-rule --id <domain>/<slug> [--linked]` — one specific piece.
   (See **Rules Graph** below for the facet vocabulary.)
4. Setting knowledge lives in the campaign's **lore entries** — browse with
   `list-lore`, read with `get-lore`; never show the player entries with
   visibility `gm`.
5. Recap the situation to the player in 2-4 sentences, then play.

## Rules Graph (faceted, load-on-demand)

The universal Mythras rules are sliced into ~100 small pieces under
`rules/<domain>/<slug>.md` (full SRD coverage: character, skill, system,
combat, magic incl. per-spell/per-power, vehicle, creature), ingested into
TypeDB by `load-rules` (run automatically on session start; idempotent). Each
piece is tagged with facets so you can fetch exactly what a situation needs
instead of loading whole files.

**Facet dimensions (controlled vocabulary):**

| Dim | Example values |
|---|---|
| `phase` | chargen, skill-check, opposed, combat-round, attack, defense, damage, wound, recovery, casting, movement, hazard, downtime |
| `action` | attack, parry, evade, charge, cast, move, outmaneuver, aim, use-luck, ... |
| `effect` | impale, bleed, bash, trip, stun-location, sunder, disarm, ... |
| `weapon` | melee, ranged, thrown, impaling, cutting, bludgeoning, two-handed, shield, natural, size-s/m/l |
| `trigger` | attacker-critical, defender-critical, opponent-fumble, differential |
| `body` | head, chest, abdomen, arm, leg, wing, avian |
| `severity` | minor, serious, major, blood-loss |
| `condition` | prone, flying, falling, charging, knockback, surprised, darkness, fatigued, turbulence, dead-air, ... |
| `magic-system` | magic, superpowers, windworking |
| `stat` | STR, CON, ..., action-points, damage-modifier, hit-points, ... |
| `kind` | procedure, table, modifier, special-effect, condition, reference-list, formula |

Compose the live situation into facets, e.g. an impaling wingspear into a
flying foe's wing:
`query-rules --facet effect=impale --facet condition=flying --facet body=avian --linked`
returns the impale piece, the avian hit-location/aerial pieces, and (via
`--linked`) wound-levels. Editing a `rules/*.md` file then re-running
`load-rules` rebuilds the graph.

## GM Operating Rules

- **Narrate first, roll second.** Only call for rolls when failure is
  interesting. Routine competence is an Automatic success.
- **Play step by step.** One step of the story at a time: narrate the
  current step, hand control back to the player, and wait. Never montage
  through multiple scenes, locations, or plan-stages in one breath — even
  when a plan is agreed, each stage of it is played, not summarized.
  Mechanics rolls happen within a step only when that step needs them.
- **Use the CLI for all dice.** Never invent roll results. The player should
  be able to audit every outcome from the JSON.
- **Difficulty grades are your main dial:** veryeasy/easy/standard/hard/
  formidable/herculean. State the grade out loud before rolling.
- **Narrate every roll as it happens — fiction first, dice second.**
  Beat-by-beat, in this order: (1) describe the situation in the fiction —
  what the character perceives or attempts and why it's uncertain — and
  STOP; (2) let the player respond (how they approach it, augments, luck)
  unless the check is purely reactive; (3) state the check and difficulty
  grade; (4) run the roll; (5) immediately render the outcome in the
  fiction before resolving the next roll. Never describe a situation and
  roll for it in the same breath — the dice must not beat the player to
  the scene. Never open a beat with "give me a Perception check", and
  never run a chain of rolls silently and summarize afterwards. Prefix
  each CLI mechanics call with an `echo` describing the action so the
  resolution is auditable in the terminal output.
- **Read roll quality the Mythras way.** High-but-under-skill is the
  STRONGEST success: opposed rolls are won by the higher roll that still
  succeeds, and ties on success level break to the higher die. Never
  narrate a 47-under-50 as "barely made it" or "not pretty" — that roll
  beats a 03 in any contest. Low rolls are only better for the critical
  threshold (≤1/10 of skill), nothing else.
- **Defense is the player's choice — always ask.** When a PC is attacked,
  stop and ask whether they parry, evade, or take it (and with what), before
  calling `resolve-attack`. Never assume `--defense none` or pick a reaction
  for them; spending a Reactive AP is a player decision like any other.
- **Persist relentlessly.** After every meaningful scene: `log-event`. When
  the party moves: `set-scene` (and `move-character` for map-relevant moves).
  Damage, healing, fatigue, luck spends: apply immediately via CLI so the DB
  is always the truth.
- **Journal every story beat, not just mechanics.** ANY beat or interaction
  gets a `log-event` — conversations (what was actually said: quote the key
  lines in `--narrative`), negotiations, revelations, refusals, gifts,
  threats, partings. Use `--type scene` for interactions and `--type
  decision` for choices. If it happened on screen, it goes in the journal;
  a roll-free scene is still an event.
- **Write events like a news report.** Who did what, where, to whom, and
  why. Lead with the action in `--summary`; name every participant in
  `--involves`; fix the location and motive in the text. Mechanics go after
  the story, not instead of it. The journal is the source of record for
  recaps and novelization — anything you don't log never happened.
- **Log the game fully — text is cheap.** Capture the whole interaction, not
  a one-line gist: the discussion and the back-and-forth, the decisions and
  the reasoning behind them, and the PROVENANCE of things — where a weapon,
  writ, ally, or piece of intel came from and why it was chosen. (If a PC is
  handed a falchion, the record says who gave it, what for, and what was said
  over it.) A terse summary loses the texture that the novelization and a
  future session's GM both depend on; an over-full event costs nothing, a
  detail never written down is gone. This is fullness of FACTUAL capture, not
  embellishment — still only what actually happened, dialogue quoted verbatim.
- **Record only what happened in the game — no embellishment.** The journal
  is a factual record of play, not prose. Quote only lines actually spoken
  at the table; never invent dialogue, sensory detail, or interiority. Log
  the whole of what happened — fully — but only what happened; embellishment
  belongs in the novelization layer and must never be written back into the
  journal or lore.
- **Dialogue is the priority content of a narrative.** Record what was
  actually said — quote the key lines verbatim (NPC and PC both) in
  `--narrative`. Spoken words outrank scenery: extra description is
  unimportant, but a line said at the table is a fact of play and should
  survive in the record.
- **Session boundaries:** open with `log-event --type session-start`, close
  with `--type session-end` plus a summary narrative, bump
  the campaign session number, and award 1-3 experience rolls.
- **Player agency is sacred.** Describe situations, not solutions. NPCs have
  their own goals (see faction narratives in the DB — `get-character`,
  faction `content` fields).
- **Character knowledge is per-character, not per-campaign.** The journal
  and rosters are the GM's memory, not the PC's. Before giving a PC a fact,
  check WHO learned it in the fiction: events another PC played through, or
  lore the character has no path to, must not surface in their head. When in
  doubt, trace the fact to a scene this character was present for.
- **Secrets stay secret.** GM-side material (gm-secrets.md, faction
  narratives, template descriptions) informs your narration but is revealed
  only through play.

## Mechanical Cheat Sheet

| Situation | Command |
|---|---|
| Plain skill check | `roll-skill --id <char> --skill Perception --difficulty hard` |
| Augment with passion | add `--augment "Loyalty to the Wardens"` |
| Contest (stealth vs perception) | `roll-opposed --id-a X --skill-a Stealth --id-b Y --skill-b Perception` |
| Raw dice | `roll --dice 2d6+3` |
| Start a fight | `start-encounter` → `add-combatant` (each) → `roll-initiative` |
| An attack | `resolve-attack --encounter E --attacker A --defender B --weapon Wingspear --defense parry` |
| New round | `next-round` (resets Action Points) |
| Fight status | `get-encounter` (live HP per location, AP, initiative order) |
| Out-of-combat damage (falls, fire) | `apply-damage --id X --location Chest --damage 6 --ignore-armor` |
| Spawn a monster | `spawn --template <tmpl-id> --name "Stillwight A" --campaign C` |
| Browse worldbuilding | `list-lore --campaign C [--category magic-system] [--visibility player]` |
| Read a lore entry | `get-lore --id <lore-id>` (full rich text + linked entities) |
| Record new canon | `add-lore --campaign C --title T --category culture --narrative "..."` |
| Import sheets (Roll20 JSON) | `import-characters --file chars.json --campaign C [--type npc]` |
| Export sheets (Roll20 JSON) | `export-characters --campaign C [--type pc] --output out.json` |
| Publish a campaign (DB → files) | `export-campaign --campaign C --output dir/` |
| Load a published campaign | `import-campaign --path dir/ [--name N] [--new-ids]` |

`resolve-attack` handles the whole differential roll: attack vs parry/evade,
special-effect count, damage + damage modifier, hit location, parry size
reduction, armor, wound level, and AP spend. **You** choose and narrate the
special effects (fetch them on demand with
`query-rules --facet phase=attack --facet trigger=differential` or
`get-rule --id combat/special-effects --linked`) — apply their mechanical
consequences with follow-up CLI calls (e.g. Trip → opposed roll; Bleed →
fatigue tracking via `update-character --fatigue`).

Wound levels from the CLI: `minor` (narrate pain), `serious` (1d3 turns no
attacking; opposed Endurance vs the attack roll or limb useless /
unconscious), `major` (incapacitated; death clock). Run those follow-up
Endurance contests with `roll-opposed` or `roll-skill`.

## Character Creation (collaborative)

Walk the player through it conversationally, then persist once:

1. Concept + setting frame (species/culture options come from the
   campaign's lore entries).
2. Characteristics: `--roll` (3d6/2d6+6, avian mods auto-applied) or
   `--stats` for point-build/assigned. SRD "Dice Roll High" option: roll one
   **extra** die and discard the lowest (3d6 → 4d6 drop lowest;
   2d6+6 → 3d6 drop lowest, +6) — not "roll twice, keep higher".
3. Skills: base values are auto-computed from characteristics; add culture +
   career + bonus allocations (100/100/150 points, or the Skill Pyramid:
   50/40×2/30×3/20×4/10×5) and pass the final values via `--skills`.
4. Combat style (name it evocatively), equipment, armor, up to 3 passions
   (+40/+30/+20 over base).
   **Weapons in `--equipment` MUST be structured objects, not plain
   strings** — `resolve-attack` looks weapons up by `name` and crashes on
   bare strings. Required keys: `name`, `damage`, `size` (S/M/L/H/E):

   ```json
   [{"name": "Wingspear", "damage": "1d8+1", "size": "L"},
    {"name": "Target shield", "damage": "1d3+1", "size": "L"},
    "Warden flight harness", "rations (3 days)"]
   ```

   Non-weapon gear may stay as plain strings.
5. `create-character --campaign <id> --name ... --narrative "<backstory>"`.

## Running a Classic Fantasy Imperative Campaign

Classic Fantasy Imperative (CFI) is a second rule system supported alongside
the standard Mythras Imperative rules. CFI adds four classes (Cleric, Fighter,
Magic-User, Rogue), a 0–5 rank progression, a two-axis Alignment system, class
Oaths, arcane and divine magic disciplines, and a large spell library. The CLI
plumbing is complete; this section covers the GM-facing workflow.

### System Setup (one-time per campaign)

1. Create the campaign with the CFI system flag:
   ```bash
   create-campaign --name "Dungeon of the Iron God" --system classic-fantasy
   ```
2. Load the CFI rules graph (idempotent; safe to re-run):
   ```bash
   load-rules --system classic-fantasy --dir rules-cfi
   ```
   This ingests the 348 CFI pieces (classes, spells, magic procedures,
   character creation steps, alignment, oaths, racial tables, etc.) tagged
   with `system: classic-fantasy` so they never pollute standard Mythras
   queries.
3. During play, query CFI rules with `--system classic-fantasy`:
   ```bash
   query-rules --system classic-fantasy --facet kind=class
   list-rules   --system classic-fantasy --category magic
   get-rule     --id cfi/class/cleric
   ```

### CFI Character Creation

Walk the player through all eight steps conversationally, then persist once.
When in doubt about a specific number (racial modifier, spell count, Rank
threshold), query the rules graph rather than stating values from memory.

**Step 1 — Concept and race.** Agree on race (Human, Dwarf, Elf, Gnome,
Half-Elf, Half-Orc, or Halfling) and class (Cleric, Fighter, Magic-User,
Rogue). Humans additionally choose a Culture (Barbarian, Civilized, or
Nomadic). For the full racial dice ranges and averages:
```bash
get-rule --id cfi/character/racial-characteristics-table
```

**Step 2 — Characteristics.** Use `--roll` for random generation or `--stats`
to pass a pre-built set. Human characteristics are straight 3d6 except SIZ
(2d6+6) and INT (2d6+6). Racial mods are applied by the GM during the
conversational build; only the final values go into `--stats`.

**Step 3 — Attributes.** Derived automatically from characteristics (action
points, damage modifier, initiative bonus, hit points per location, magic
points, movement, luck points). Humans gain +1 Luck Point. For the full
derivation formulae:
```bash
get-rule --id cfi/character/damage-modifier
get-rule --id cfi/character/luck-points
```

**Step 4–6 — Skills (race + class + bonus points).** CFI skill allocation is
three pools applied in sequence:

| Pool | Points | Source |
|------|--------|--------|
| Race/Culture | 100 | racial Standard + Professional bonuses |
| Class | 100 | class Standard + Professional bonuses (max 3 Professional skills) |
| Bonus | 100 | player's free allocation (max +10 per skill at Rank 1) |

Add all three pools to the characteristic-derived base values, then pass the
final totals in `--skills`. For the class skill lists:
```bash
get-rule --id cfi/class/cleric      # or fighter / magic-user / rogue
query-rules --system classic-fantasy --facet kind=class
```

**Step 7 — Rank.** A new character starts at Rank 0 unless they already meet
the Rank 1 threshold (any 5 class skills at 40%+). Most starting characters
qualify for Rank 1 after applying all three skill pools. Rank determines class
Abilities, HP/Luck/Action Point bonuses, and (for casters) spells in memory.
For the full threshold table:
```bash
get-rule --id cfi/class/rank-structure
```

**Step 8 — Alignment, Oath, and Passions.** Each character has two Alignment
codes (Ethical: Lawful/Neutral/Chaotic; Moral: Good/Neutral/Evil), each
starting at INT + POW + 30. Clerics must additionally take a Clerical Oath
(30% + INT + POW) sworn to their religious order. Store both Alignment codes
and the Oath as passions in `--passions`:
```json
{
  "Lawful (Honorable, Disciplined)": 55,
  "Good (Charitable, Merciful)": 55,
  "Oath to the Order of the Golden Sun": 62
}
```
For Alignment rules and Oath mechanics:
```bash
get-rule --id cfi/alignment/alignment-system
get-rule --id cfi/alignment/oaths
```

**Persisting class metadata (extras-json).** The `create-character` command
builds the mechanical sheet (characteristics, derived attributes, skills,
equipment, combat styles). Class, rank, and alignment are CFI-specific
metadata that ride in the character's `extras-json` bag. Pass them via a
complete character JSON sheet with `import-characters`, where any key not
consumed by the standard schema lands in `extras` automatically:

```json
{
  "name": "Sister Aelindra",
  "stats": {"STR": 11, "CON": 12, "SIZ": 10, "DEX": 11, "INT": 13, "POW": 12, "CHA": 14},
  "class": "cleric",
  "rank": 1,
  "rank_title": "Initiate",
  "alignment_ethical": "Lawful",
  "alignment_moral": "Good",
  "skills": {
    "Combat Skill (Cleric)": 46,
    "First Aid": 42,
    "Influence": 48,
    "Insight": 44,
    "Locale": 43,
    "Sing": 41,
    "Willpower": 47,
    "Channel": 45,
    "Devotion (Order of the Golden Sun)": 45,
    "Lore (Religion)": 42,
    "Healing": 40,
    "Oratory": 43
  },
  "passions": {
    "Lawful (Honorable, Disciplined)": 55,
    "Good (Charitable, Merciful)": 55,
    "Oath to the Order of the Golden Sun": 55
  },
  "combat_styles": [
    {"name": "Cleric (mace and shield)", "value": 46,
     "weapons": [
       {"name": "Mace", "damage": "1d8", "size": "M"},
       {"name": "Medium shield", "damage": "1d4", "size": "L"}
     ]}
  ],
  "equipment": ["chainmail", "holy symbol", "rations (3 days)"],
  "hit_locations": [
    {"name": "Right Leg",  "range": "01-03", "ap": 5, "hp": 5},
    {"name": "Left Leg",   "range": "04-06", "ap": 5, "hp": 5},
    {"name": "Abdomen",    "range": "07-09", "ap": 5, "hp": 6},
    {"name": "Chest",      "range": "10-12", "ap": 5, "hp": 7},
    {"name": "Right Arm",  "range": "13-15", "ap": 5, "hp": 4},
    {"name": "Left Arm",   "range": "16-18", "ap": 5, "hp": 4},
    {"name": "Head",       "range": "19-20", "ap": 5, "hp": 5}
  ],
  "notes": "Human (Civilized) Cleric, Rank 1 Initiate, Order of the Golden Sun"
}
```

```bash
import-characters --file sister-aelindra.json --campaign <id>
```

The keys `class`, `rank`, `rank_title`, `alignment_ethical`, and
`alignment_moral` are not part of the consumed schema so they land verbatim in
`myth-extras-json` and are visible on `get-character --id <id>`.

> **`--species` is a body plan, not a CFI race.** `create-character --species`
> only accepts the engine's body archetypes (`humanoid`, `avian`,
> `winged-quadruped`). Every CFI race (human, dwarf, elf, gnome, halfling,
> half-orc, half-elf) is a `humanoid` for hit-location/body purposes — pass
> `--species humanoid` and apply the race's characteristic modifiers yourself
> via `--stats` (see `get-rule --id cfi/race/<name>`), recording the chosen
> race in the sheet's `notes`/`extras`. The `import-characters` sheet above
> sidesteps this by providing `stats` and `hit_locations` directly.

After import, record a Rank 1 Ability chosen at creation (e.g. Powerful
Concentration) as an `add-lore` entry or in the character's narrative so it
isn't lost between sessions.

### CFI Magic

**Two disciplines, same core engine.** Arcane and Divine both use Magic Points
and the standard casting rules (time, cost, opposed resistance). They differ in
how spells are learned and accessed. For the full casting procedures:
```bash
query-rules --system classic-fantasy --facet magic-system=arcane
query-rules --system classic-fantasy --facet magic-system=divine
```

**Arcane (Magic-Users).** Spells live in a personal spell book. The caster
uses Arcane Casting as their casting skill. Arcane casters CANNOT cast in
armor. At character creation they know a handful of spells (exact count from
their INT and Arcane Knowledge — see the Magic-User class write-up); on each
new Rank they gain 3 additional spells for free. Extra spells require research
(EXP rolls + study time) or copying from scrolls/books via Read Magic.
```bash
get-rule --id cfi/magic/learning-arcane-spells
```

**Divine (Clerics).** Spells are granted through prayer. Clerics know ALL
spells of their current Rank or lower automatically upon reaching that Rank —
no research, EXP rolls, or spell book. They cast via their Channel skill (and
Devotion for sustained effects). Armor does NOT hinder divine casting.
```bash
get-rule --id cfi/magic/learning-divine-spells
```

**Spells in memory.** Both disciplines require memorization before casting.
After 8 hours rest, the caster spends 15 minutes per spell (study for Arcane,
prayer for Divine) up to their Rank's memory limit. The limit is specified in
each class's Rank Table (formula: INT/4 round down, plus a per-rank cumulative
bonus). Casting does NOT expunge a spell from memory; it can be recast as long
as MP remain.
```bash
get-rule --id cfi/magic/memorizing-spells
```

**Recording known spells.** CFI reuses the two existing Mythras magic slots:
put CFI divine spells under `theism_spells` and CFI arcane spells under
`sorcery_spells` in the character JSON sheet passed to `import-characters`:

```json
{
  "name": "Sister Aelindra",
  ...
  "theism_spells": ["Avert", "Might", "Calm",
                    "Bless", "Cure Minor Wounds", "Remove Fear"]
}
```

For arcane casters use `"sorcery_spells"` in the import sheet. After import,
the values appear on `get-character` as `theism_spells` / `sorcery_spells`,
stored in `myth-spells-json` under the `theism` / `sorcery` keys respectively.
CFI deliberately reuses those two Mythras magic slots for its divine/arcane
disciplines so that combat-card and Roll20 read-back continue to work.

**Looking up a spell in play.** Fetch one spell by ID or query by facet — do
not load the full list into context:
```bash
get-rule --id cfi/spell/cure-minor-wounds
get-rule --id cfi/spell/magic-missile
query-rules --system classic-fantasy --facet kind=spell --facet magic-system=divine
```

**Turn Undead (Cleric).** Opposed test: Channel vs. highest Willpower undead
in area. Usable once per Short Rest at Rank 1. Use `roll-opposed` for the
resolution, then narrate the result according to the turning outcome table:
```bash
get-rule --id cfi/class/cleric --linked
```

## Worldbuilding During Play

New places, factions, and recurring NPCs the fiction generates should be
persisted the moment they matter: `add-location`, `add-faction`,
`create-character --type npc`, `join-faction`, `move-character`. Put the
rich, reusable detail in `--narrative` (stored as `content` in TypeDB) — a
future session's GM (you, with no memory of today) will rely on it.

**Lore is the deep worldbuilding layer.** Anything that isn't a specific
place/person/faction — cosmology, species anatomy, magic systems, careers,
history, religion, economy, house rules — goes in `add-lore` with a
free-form `--category` and `--visibility player|gm`. Link lore to entities
with `--about id,id` or `link-lore`. When the fiction establishes new canon
("the Ossuin never sing indoors"), capture it as lore immediately. This is
what makes the system setting-agnostic: a new campaign is just
`create-campaign` plus a body of lore entries, locations, factions, and
templates — see the
[veilwrack-campaign](https://github.com/fourth-wall-gaming/veilwrack-campaign)
repo (and its `setting/` seed scripts) for the reference pattern.

## Publishing Campaigns

`export-campaign` serializes an entire campaign to a human-readable file
tree — markdown (with frontmatter) for lore/locations/factions, JSON for
characters/templates/encounters/journal, plus a `campaign.yaml` manifest and
a generated README. Commit that directory to a GitHub repo and the campaign
is published: browsable on the web, and loadable by anyone with
`import-campaign --path <dir> --new-ids` (`--new-ids` remaps every entity id
so the campaign imports cleanly into any database; all relations — presence,
faction membership, lore links, encounter rosters, event involvement — are
rebuilt). The round trip is lossless.

## Files

| File | Purpose |
|---|---|
| `mythras_gm.py` | CLI: persistence + resolution (JSON out) |
| `mythras_engine.py` | Pure rules engine (importable, no I/O) |
| `campaign_io.py` | Campaign publishing: export/import file trees |
| `rules/<domain>/*.md` | The faceted rules graph (~100 pieces, full SRD); ingested by `load-rules`, queried via `list-rules`/`query-rules`/`get-rule` |
| `rules/{core-mechanics,combat,magic}.md` | Legacy monolithic references (human-readable source the pieces were distilled from) |
| `schema.tql` | TypeDB myth- namespace (incl. myth-rule graph) |

Campaign settings are published as separate repos (e.g.
[veilwrack-campaign](https://github.com/fourth-wall-gaming/veilwrack-campaign))
and loaded with `import-campaign`.
