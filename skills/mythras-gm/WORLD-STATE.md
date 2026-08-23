# World State

How the campaign database answers three questions the GM cannot otherwise ask:
**is this still true**, **who was there and who knows**, and **what happens next**.

Companion to `CHARACTER-SCORES.md`. A score is *who an NPC is* in a scene; this
document is about the world between scenes.

## The problem it solves

Four sessions of one campaign produced four GM failures. None was carelessness;
each was a thing the data model could not represent.

| # | Failure | What was missing |
|---|---|---|
| 1 | The retired first crew's history — their dragon patron, their scrap trade — was attributed to the active second crew, mid-scene | Nothing said whose story an event belonged to |
| 2 | GM truth from a rejected earlier version of the campaign was read as live and played at the table | Nothing marked dead canon dead |
| 3 | A location could be described but not *moved*: "eighteen mercenaries on the gate" was a tableau, not a situation | No NPC carried anything forward-looking |
| 4 | Six NPCs ran the same beat for three sessions | Fixed by `score`; `doing` is its forward-facing twin |

Failure 1 has a precise mechanism worth naming. `get-context` filtered player
characters to `status == "active"`, so a retired crew **vanished from the save
file entirely** while every event they were in stayed in the log with no visible
owner. Orphaned history attaches itself to whoever is currently on screen.

## The three axes

| Axis | Question | Mechanism |
|---|---|---|
| **Liveness** | Is this still true? | `myth-canon-status` — absent means live |
| **Attribution** | Who was there, and who knows? | `myth-event-involvement`, finally read; `myth-event-visibility` |
| **Forward** | What happens next? | `doing`, sibling of `score` in `myth-extras-json` |

Every schema addition is optional and absent means the sane default, so nothing
needed backfilling to keep working.

## Liveness

Canon that stops being true is **retired, not deleted** — deleting loses the
audit trail, and you often need to know what you used to believe.

```bash
retire-canon --id <entity-id> --status superseded --by <replacement-id>
retire-canon --id <entity-id> --status retracted     # simply wrong, never true
retire-canon --id <entity-id> --status live          # un-retire
```

Works on lore, events, characters, locations and factions. Retired records leave
`list-lore`, `get-log` and `get-context`. `get-lore --id` still returns one you
ask for by name, but **labelled** with `canon_status` — an explicit request
should be answered, not silently refused.

## Attribution

Every `log-event` names its participants in `--involves`. That relation existed
for a long time before anything read it; now it is the backbone of two queries:

```bash
get-log --involving <ids>     # what has this crew, or this NPC, been part of
get-log --known-to <char-id>  # what could THIS character actually know
```

`--known-to` is the command behind the operating rule that character knowledge
is per-character. Use it before giving a PC a fact.

**An empty result is not proof of ignorance.** If participants were never
recorded, a participation filter drops the event silently — so `get-log` reports
the count of unattributed events and warns. Treat that warning as a to-do.

### Where the camera was

`--visibility` is a **second axis** from `--type`: an offscreen event can still
be a combat.

| Value | Meaning |
|---|---|
| `played` | On screen, the party was there. The default; absent means this. |
| `reported` | The party was told about it in the fiction. |
| `offscreen` | Happened elsewhere. GM-side only. |
| `meta` | Bookkeeping *about* the campaign, not an event *in* it. |

`meta` earns its place: GM correction notes name the entire cast, so without it
they both poison `--known-to` (telling a goblin it knows about your corrections)
and crowd the recent-events window with admin instead of play.

**Players learn of offscreen action only through consequences.** No cutaways.
Offscreen records never appear in player-facing output.

**Promotion is append-only.** When the party finds out, do not mutate the
original — log a *new* `played` event describing the finding out. The record of
what happened and the record of them learning it are different facts.

## Forward state: `doing`

Sits beside `score` in `myth-extras-json`.

```json
{"doing": {
  "goal":        "one line: what they are trying to bring about",
  "next":        "the very next concrete thing they will do",
  "where":       "myth-loc-... or free text",
  "with":        ["myth-char-..."],
  "blocked_by":  "what would stop them",
  "as_of_session": 5,
  "log":         ["s5: bought out the second barge"]
}}
```

A status line, not a character study. `score` is who they are; `doing` is what
they are occupied with on the days the party is not in front of them.

```bash
set-doing --id <char> --goal "..." --next "..." --where "..." --blocked-by "..."
set-doing --id <char> --did "s5: went to the Slake and paid" --next "..."
```

`--did` appends to the log. There is no `advance` verb because off-camera
movement is nearly always *"they did X, so next is now Y"*, which is one call.
Merging means a partial write never discards the rest.

### Anti-goals

Written down so the next design pass does not re-propose them:

- **There is no clock.** No `progress`, `segments`, `deadline`, `eta` or
  `threat_level`. `goal` + `next` is a sentence, not a meter.
- **Nothing advances unless you said it did.** `as_of_session` is a staleness
  *label* so a reader can see a line is three sessions old. It does not tick.
- **Factions have no agenda; named people do.** If something acts against the
  party, it is a person with a face, who can be met, bribed or knifed. Factions
  stay as flavour text.
- **Off-camera action is decided at the table and recorded after**, never
  pre-scheduled on a timetable.

## The loop

1. **Session start.** `get-context --compact` gives the live PCs, the former
   crews (named and dated), one `doing` line per active NPC, recent play with
   participants, and any offscreen developments.
2. **Before a scene.** `get-character --brief <id>` — score, doing, lore written
   about them, and the last five events they were actually in. Not a stat block.
3. **During.** `log-event` with `--involves` and, when the camera was elsewhere,
   `--visibility`.
4. **Before giving a PC a fact.** `get-log --known-to <them>`.
5. **Session end.** For each NPC with a `doing`: either `set-doing --did`
   because it moved, or leave it because it did not. No `doing` should sit
   unexamined for more than two sessions.
6. **When a crew retires.** Mark the PCs `retired` *and* `retire-canon
   --status superseded` any lore that was only ever true for them.
