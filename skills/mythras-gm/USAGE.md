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
4. **`tick --campaign <id> --to "<time key>"`** before each new scene — advance
   the world clock and see what the NPCs did while the party was elsewhere.
   (See **Living World** below.)
5. Setting knowledge lives in the campaign's **lore entries** — browse with
   `list-lore`, read with `get-lore`; never show the player entries with
   visibility `gm`.
6. Recap the situation to the player in 2-4 sentences, then play.

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
| Advance world time | `tick --campaign C --to "d-2/dawn"` |
| Who wants what | `list-agendas --campaign C --compact` |
| What happens next | `list-beats --campaign C --pending` |
| Resolve a due beat | `fire-beat --id B --outcome played\|narrated --campaign C --log` |
| Bend a stale beat | `revise-beat --id B --when "d-1/dusk" --at <loc>` |
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

## Living World (agendas, clocks, beats)

The simulation layer: what the world is doing while the PCs are somewhere else.
It exists so the story is driven by what NPCs *want* rather than by a fixed
sequence of scenes, and so player action visibly changes the board.

### The model

- **Agenda** — a goal held by a character or faction, with a progress clock.
  *"Santo means to bind a demon into a courtesan and prove himself to his
  father."* `clock 0/6`, `priority 5`.
- **Beat** — the next concrete thing that agenda produces if nobody interferes,
  scheduled against world time (`--when "d-3/night"`) or a clock threshold
  (`--trigger "clock>=4"`). A beat carries a place and a cast.
- **Front** — there is no separate entity; a **faction** is the front. Give the
  faction the agendas and the NPCs inside it their own, sometimes conflicting.

### The world clock

Time keys are `d<day>/<watch>` — day signed and usually counting down to a fixed
event (`d-3` is three days before, `d0` the day itself), watch one of
`dawn | day | dusk | night`. They sort chronologically, which is all `tick`
needs. `tick` refuses to move backwards unless you pass `--rewind`.

### The loop

```bash
# 1. What is in motion?
list-agendas --campaign C --compact

# 2. Move time; find out what came due and whether the PCs can see it
tick --campaign C --to "d-3/night" --set-date "The night before the tourney"

# 3. Beats flagged onscreen -> play them as scenes, then
fire-beat --id B --outcome played --campaign C --log \
          --summary "..." --narrative "..." --advance 2

# 4. Beats flagged offscreen -> they happen anyway; record them as
#    discoverable facts, not as things the PCs witnessed
fire-beat --id B --outcome narrated --campaign C --log --type gm-note \
          --summary "Nus was killed and his body displayed at the Reach"

# 5. When play earns it, move a clock
advance-agenda --id A --by 2 --campaign C --note "The Baron doubled the guard"
```

**Staging is not a GM choice.** A due beat comes back `onscreen` only when a PC
is at its location or named in its cast (read from `myth-presence`), otherwise
`offscreen`. Move the party and the same beat changes character: the attack the
PCs interrupt is the attack they hear about the next morning.

**Outcomes:** `played` (PCs were there), `narrated` (happened off-camera),
`preempted` (PCs stopped it before it fired), `rewritten` (superseded — pair
with `revise-beat`), `cancelled` (no longer possible).

### Adapting as you go

The clocks are there to keep the world honest, not to hold the story on rails.
When play makes a plan stale, change the plan:

- `revise-beat --id B --when ... --at ... --cast ... --onscreen-if ...` — move
  it, restage it, recast it.
- `add-agenda` mid-session when PC action creates a new interest (someone robbed
  now wants restitution; an ally made now has a stake).
- `set-agenda-status --status thwarted` when the players genuinely beat it, and
  let the holder react with a new agenda rather than quietly re-running the old.

The test of a good beat is that it would happen without the PCs. If it only
makes sense when they are watching, it is a scene, not a beat.

## Facts and Knowledge (who knows what)

The state model. **Ground truth lives in exactly one place; everything else is
a query into it.** There is no per-character state store -- a character's
knowledge is a filtered read of the campaign's fact graph, which is what makes
it reconcilable by construction.

### The model

- **`myth-fact`** -- one proposition ("Santo carved Emmeralda at the Sylph's
  Embrace"). It has a **status** (`not-yet-true` -> `established` ->
  `superseded`), a **truth** (`true | false | partial`), and the world-clock
  index at which it became true. Facts are owned by the beat that produces
  them, so the campaign ships with its future already enumerated but not yet
  real.
- **`myth-knows`** -- the edge from a character or faction to a fact, carrying
  **certainty** (`knows | believes | suspects | wrong`), **source**
  (`witnessed | told | deduced | rumor`) and **since** (when they learned it).

Status and truth are independent on purpose. `truth: false` is how you model
the rumour that drives a manhunt -- a proposition that is not true, that people
nonetheless act on.

### The loop

```bash
# what can this character legitimately act on right now?
character-view --campaign C --id <pc> --compact

# a beat fires -> its facts become real -> the people present learn them
establish-fact --id F --when "d-3/night"
learn --knower <pc> --fact F --certainty knows --source witnessed --at "d-3/night"

# who could betray this?
who-knows --campaign C --fact F

# reconcile everything against everything
check-consistency --campaign C
```

`check-consistency` reports:

| Problem | Meaning |
|---|---|
| `knows-unestablished` | someone knows a thing that has not happened yet |
| `knew-too-early` | learned before the fact became true |
| `dangling-knowledge` | edge points at a fact that no longer exists |
| `overdue-fact` | scheduled in the past but never established |

### Knowledge-gated agendas

```bash
require-fact --agenda <a> --fact <f>
```

A **dormant** agenda whose holder knows all its required facts is activated
automatically by `tick`, which reports it in `activated_agendas`. This is how
"the Baron acts the moment he learns he has another son" stops being a note in
a file and becomes a computed consequence of what the players let him see.

### What is a fact, and what is not

**If two characters could act differently depending on whether they know it,
it is a fact. Otherwise it is colour.** A campaign this size wants roughly
20-40 facts, not 500. Weather is not a fact. Who owns the knife is.

Character prose describes **character** -- temperament, skill, history. It must
never assert situation: a sheet that says "he attempted the ritual and fled"
cannot be reconciled against a clock, and will be wrong the moment play
diverges.

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
