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
2. `get-context --campaign <id>` — returns campaign scene/date, full PC
   sheets, NPC roster, locations, factions, active encounters, the campaign's
   **lore index** (titles + categories), and the last 15 journal events.
   **This is your save file. Read it before narrating.**
   Pull full worldbuilding text on demand with `get-lore --id <lore-id>`;
   never show the player entries with visibility `gm`.
3. Read the rules references before adjudicating:
   - `rules/core-mechanics.md` — checks, difficulty grades, opposed rolls, luck, fatigue, healing
   - `rules/combat.md` — full combat procedure, special effects, hit locations
   - `rules/magic.md` — Magic (spells, MP-by-roll-result, traits) and Superpowers frameworks
4. Setting knowledge lives in the campaign's **lore entries** (step 2's lore
   index) — never show the player entries with visibility `gm`.
5. Recap the situation to the player in 2-4 sentences, then play.

## GM Operating Rules

- **Narrate first, roll second.** Only call for rolls when failure is
  interesting. Routine competence is an Automatic success.
- **Use the CLI for all dice.** Never invent roll results. The player should
  be able to audit every outcome from the JSON.
- **Difficulty grades are your main dial:** veryeasy/easy/standard/hard/
  formidable/herculean. State the grade out loud before rolling.
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
- **Record only what happened in the game — no embellishment.** The journal
  is a factual record of play, not prose. Quote only lines actually spoken
  at the table; never invent dialogue, sensory detail, or interiority. Log
  just enough that a novelization could be written from it later, and no
  more — embellishment belongs in the novelization layer and must never be
  written back into the journal or lore.
- **Session boundaries:** open with `log-event --type session-start`, close
  with `--type session-end` plus a summary narrative, bump
  the campaign session number, and award 1-3 experience rolls.
- **Player agency is sacred.** Describe situations, not solutions. NPCs have
  their own goals (see faction narratives in the DB — `get-character`,
  faction `content` fields).
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
special effects (list in `rules/combat.md`) — apply their mechanical
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
   `--stats` for point-build/assigned.
3. Skills: base values are auto-computed from characteristics; add culture +
   career + bonus allocations (100/100/150 points, or the Skill Pyramid:
   50/40×2/30×3/20×4/10×5) and pass the final values via `--skills`.
4. Combat style (name it evocatively), equipment, armor, up to 3 passions
   (+40/+30/+20 over base).
5. `create-character --campaign <id> --name ... --narrative "<backstory>"`.

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
| `rules/core-mechanics.md` | Skill system, attributes, fatigue, healing, experience |
| `rules/combat.md` | Combat procedure, special effects, weapons, falling |
| `rules/magic.md` | SRD Magic & Superpowers frameworks (setting-agnostic) |
| `schema.tql` | TypeDB myth- namespace |

Campaign settings are published as separate repos (e.g.
[veilwrack-campaign](https://github.com/fourth-wall-gaming/veilwrack-campaign))
and loaded with `import-campaign`.
