# Independent storyline clocks

A campaign contains one world and one canonical history, but several protagonists
can be played at different dates. A **storyline** owns a clock, scene, session,
arc and PC membership. PCs travelling together use one storyline. The campaign's
numeric time is only a monotonic high-water mark; switching protagonists never
advances their rest, spells, rent, knowledge or local deadlines.

## Start or resume

```bash
# Campaign inferred from MYTHRAS_CAMPAIGN or the only campaign.
gm list-storylines --campaign C
gm get-context --campaign C --pc PC_ID --compact
gm get-context --campaign C --storyline Nimras --compact
gm tick --campaign C --pc PC_ID --minutes 15
gm tick --campaign C --storyline Nimras --to d8/dusk
gm set-scene --campaign C --pc PC_ID --scene 'At the workshop'
```

`gm` above abbreviates `uv run -q --project "$GM" python "$GM/mythras_gm.py"`.
You can instead set `MYTHRAS_STORYLINE` to a name or ID. Explicit `--pc` overrides
that environment default; explicit `--storyline` and `--pc` together must agree.
A command without either selector refuses ambiguous play state once a campaign
has storylines. `--storyline world` explicitly selects shared administration.
Legacy campaigns with no storylines continue to work without new flags.

`world_clock` is the selected local clock; `world_high_water` is the furthest
shared date. `storyline.minute_in_watch` provides sub-watch duration tracking.
A watch remains the engine's six-hour unit. `tick --to` preserves the minute
offset if staying within the same watch; use `--minutes` for elapsed time.

Never use `tick --rewind` merely to switch protagonists. Local corrections are
explicit; the high-water mark never rewinds through a local correction.

## Create, group, and migrate

```bash
gm create-storyline --campaign C --name Nimras --pcs PC_ID \
  --at d8/day --minute 13 --session 8 --scene 'In the Lullwater' \
  --arc-file /absolute/path/to/nimras-arc.md
gm update-storyline --campaign C --id STORY_ID --scene 'Corrected pointer'
gm assign-storyline --campaign C --id PARTY_STORY_ID --pcs PC_ID,OTHER_PC
```

A PC belongs to one storyline. Joining a different party requires matching
local dates **and minutes**; the command refuses to invent catch-up, rest,
wages, travel or encounters. The old empty storyline may remain as an archival
scene pointer. Use `split-storyline` to give selected party members a new
clock at the same timestamp; pre-split journal history follows them. Joining
retains their prior journal history without transferring character knowledge.

Migration is deliberate, not guessed from the shared clock. Checkpoint first,
read each PC's last scene and date, then create their storylines. Load the schema
with `load-schema` before using this feature on an older database. Do not import
or clone a live campaign to obtain separate clocks.

Existing operations/events can be assigned without duplication:

```bash
gm assign-storyline-record --campaign C --ids EVENT_ID,AGENDA_ID,BEAT_ID \
  --to STORY_ID
gm assign-storyline-record --campaign C --id EVENT_ID --to STORY_ID --when d8/day
```

Unowned operations are shared world operations. Ownership does not make facts
private: established truths remain shared, but each knower needs an earned,
dated knowledge edge. Legacy journal entries lacking game dates are retained
only for their own PC's storyline history; undated NPC-only/offscreen entries
are hidden from local context until their actual date is backfilled. Real-world
write time is never used to guess a fictional date.

## Spells, rest and lodging

After resolving a casting, record its **already paid** effect:

```bash
gm add-timed-effect --campaign C --pc PC_ID --id PC_ID \
  --name 'Change Appearance' --minutes 15 --reserved-mp 1
gm dismiss-effect --campaign C --pc PC_ID --id PC_ID --effect EFFECT_ID
gm rest-character --campaign C --pc PC_ID --id PC_ID --hours 8 --safe
gm rest-character --campaign C --pc PC_ID --id PC_ID --kind short --hours 0.25
```

Tracking does not spend MP again. A critical free spell reserves zero points.
Effects expire only against their owner's party clock. Dismissal frees capacity
but never refunds spent MP. Rest advances that storyline's time, reports due
operations, and restores **only the specified PC**. A full safe rest needs eight
hours; a short spellbook/prayer rest restores one MP per fifteen minutes.
Ongoing effects reserve their MP under CFI. Rest never resets Luck or assumes
other party members also slept. GM approval of safe shelter is represented by
`--safe`; dangerous rest and interrupted rest need actual adjudication.

`get-character` and `get-context` include `clock_status`: effects, reserved MP,
and whether the existing prepaid lodging is still active on that local date.
No rent is silently charged, extended or refunded. Migrate legacy `active_magic`
entries before automated recovery; the rest command refuses unknown lingering
costs rather than guessing. The tracker is authoritative after migration;
legacy entries can be retained as explicitly migrated audit records.

## Temporal knowledge and shared history

- New events and operations acquire their selected storyline automatically;
  event dates, default learning dates and scene/session/arc reads use its clock.
- Fact occurrence and learning dates both bound character knowledge. Future
  facts/interpretations cannot leak through context, journals or character-view.
- Encounter views are isolated to the storyline and date.
- Mutable character state and presence written through the CLI are versioned.
  Earlier NPC edits do not overwrite that NPC's later state. Existing pre-feature
  history cannot be reconstructed from nothing: the migration retains the
  current state as a baseline; ambiguous historical changes require GM review.
- A resolved shared beat is idempotent. It cannot be fired again for a second
  outcome, payment or agenda advance. `tick` reports existing shared outcomes
  encountered by a later-reaching camera to the GM, without granting PC knowledge.
- An earlier action that contradicts already-played later history requires an
  explicit, audited reconciliation. Independent clocks are not parallel worlds.
- In an earlier camera, cascade settles its own plans without rewriting shared
  plans using another camera's future state.

Exports include `storylines.json`, temporal metadata and state histories. Import
preserves them and remaps IDs under `--new-ids`. Older exports remain readable.
Use `--storyline world` for campaign export/administration; play remains scoped.

## Continuing discipline

Keep all gameplay commands scoped. Before speaking for an NPC use `brief` and
`character-view` with the same storyline selector. Do not copy another PC's arc,
scene, rest, Luck or private discoveries into the current one. Pause all clocks
during OOC review. Do not narrate time, pay rent or refresh resources merely
because a different protagonist has advanced farther.

Split a party at its current timestamp with `split-storyline --campaign C --id SOURCE --name NEW --pcs PC_ID`. Pre-split journal history follows the new party. To join, synchronise the dates and minute offsets through play, then use `assign-storyline --campaign C --id DEST --pcs PC_ID`. No recovery or knowledge transfer is inferred.
