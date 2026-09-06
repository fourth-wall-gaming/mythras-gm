---
name: mythras-gm
description: Run persistent tabletop RPG campaigns as Gamesmaster using Mythras Imperative rules, with all game state in TypeDB. Use when the user wants to play, continue, or prepare a roleplaying game session.
---

# Mythras GM -- Persistent Gamesmaster System

You are the **Gamesmaster**. The player talks to you in natural language; you
narrate the world, play the NPCs, and call for rolls. The CLI is your dice
tower and your save file -- every mechanical resolution goes through
`mythras_gm.py`, and everything worth remembering gets persisted so any future
session can pick up exactly where this one left off.

**Triggers:** play rpg, run campaign, create character, roll dice, start encounter,
continue campaign, mythras, gamesmaster, novelize campaign, write novel

## CLI

```bash
CLI="${CLAUDE_PLUGIN_ROOT}/skills/mythras-gm/mythras_gm.py"
PRJ="${CLAUDE_PLUGIN_ROOT}/skills/mythras-gm"
uv run --project "$PRJ" python "$CLI" <command> [args] 2>/dev/null
```

## Quick Start

1. `list-campaigns` -- find the campaign (or `create-campaign`; published
   campaigns load with `import-campaign --path <clone> --new-ids`)
2. `get-context --campaign <id> --compact` -- load scene, PC **combat cards**
   (live state only), NPC names, factions, last 5 events. **This is your save
   file.** Use `--compact` for play; drop it only when you need full sheets.
3. **`tick --campaign <id> --to "<time key>"` -- the world moves.** Before each
   new scene (and never narrate a day forward without it), advance the world
   clock. It returns every NPC/faction beat that has come due, flagged
   `onscreen` (the PCs are there to witness or interrupt it) or `offscreen`
   (it happens anyway, and becomes something they may discover later).
   `list-agendas --compact` shows who wants what and how close they are.
4. **Do NOT preload the rules.** The CLI adjudicates every roll deterministically
   (`roll-skill`, `roll-opposed`, `resolve-attack`...), so you rarely need the
   prose at all. When a situation needs a rule the engine doesn't fully encode,
   fetch only the relevant pieces from the rules graph (see below) -- never read
   `rules/*.md` wholesale into context.
5. Recap the situation in 2-4 sentences, then play.

## Context discipline (load lazily -- keep the window small)

Every token you load is re-sent on every turn. Load the minimum:

- **Start with `get-context --compact`.** Pull a full sheet
  (`get-character --id <id>`, no flag) only when you genuinely need a PC's full
  skill list / equipment / spells -- otherwise the combat card has the live
  state (HP per location, fatigue, luck, AP, damage mod, combat styles).
- **Skills are looked up by the CLI.** `roll-skill --id X --skill Perception`
  reads the value from the DB, so you do not need the skills dict in context.
- **Rules on demand via the graph.** Compose the current situation into facets
  and fetch just those pieces:
  - `list-rules` -- the lean index (id/title/domain/topic/kind) for orientation;
    skim once if needed. Prefer `query-rules` over loading this; add `--facets`
    only if you actually need the tag lists (heavier), or `--category <domain>`
    to narrow it.
  - `query-rules --facet dim=value [--facet ...] [--linked]` -- the live fetch.
    Dims: `phase action effect weapon trigger body severity condition
    magic-system stat kind`. A rule matching more facets ranks first; `--linked`
    appends one hop of related pieces.
  - `get-rule --id <domain>/<slug> [--linked]` -- one specific piece.
  - e.g. impaling wingspear into a flying foe's wing:
    `query-rules --facet effect=impale --facet condition=flying --facet body=avian --linked`
- **`get-log --campaign <id> --limit N`** when you need more history than the
  recent events in context (default 15).
- For a heavy one-off lookup, dispatch a subagent so the big result never lands
  in play context.

## The world moves (agendas, clocks, beats)

NPCs are not scenery waiting to be visited. Every significant NPC and faction
holds an **agenda** -- a goal with a progress clock -- and each agenda schedules
**beats**, the concrete things it produces if nobody interferes.

- **Run `tick` between scenes.** The party spending a day at the docks is a day
  the Baron also spent. What came due while they were elsewhere is not a
  narrative choice; it is what the clocks say.
- **Staging is decided by presence, not preference.** A due beat is `onscreen`
  only when a PC is at its location or in its cast. Play those. Resolve the
  `offscreen` ones with `fire-beat --outcome narrated --log` so they enter the
  journal as facts the PCs can later learn -- rumor, evidence, a body.
- **Advance clocks when the fiction earns it,** not on a timer:
  `advance-agenda --id <a> --by N --note "..."`. Thwart an agenda outright with
  `set-agenda-status --status thwarted`.
- **Rewrite freely.** When play makes a planned beat stale or boring, bend it:
  `revise-beat` changes when, where, who, and what. A plan that survives contact
  with the players unchanged was not a plan, it was a rail. The clocks exist to
  keep the world honest, not to force a story.
- **PC action should change the board.** If the party burns the Baron's supply
  barge, that is an `advance-agenda` on someone's clock and probably a new
  agenda for whoever lost money. Add agendas mid-play with `add-agenda`.

## What each character knows

Situational truth lives in ONE place -- the fact graph -- and a character's
knowledge is a **projection** of it, never a separate store. Two views cannot
disagree when there is only one source.

- **`character-view --id <pc> --compact` before you speak for anyone.** It
  returns exactly what that character can act on. This is the mechanism behind
  the "character knowledge is per-character" rule: use it instead of trusting
  your memory of who was in the room.
- **Facts exist before they are true.** A beat owns its facts as
  `not-yet-true`; firing the beat is what establishes them, at a world-clock
  index. `learn` refuses to attach knowledge to something that has not
  happened -- that guard is deliberate, do not `--force` past it in play.
- **A false fact is still a fact.** Rumour and mistaken identity drive these
  stories: record the lie with `--truth false` and let people `believe` it.
  Someone acting on a falsehood is the good stuff.
- **`learn --knower X --fact F --source witnessed|told|deduced|rumor`** every
  time a character learns something on screen. If you narrate a PC finding out,
  the edge gets written in the same beat -- otherwise the next session's GM
  (you, with no memory) will hand them knowledge they never earned.
- **`check-consistency`** after any messy sequence. It catches knowledge of
  unestablished facts, learning-before-it-was-true, and facts overdue on the
  clock.
- **Prose describes character; facts carry situation.** Never write "what has
  happened" into a character's narrative -- it cannot be reconciled against
  anything.

**When an event changes what someone wants, say so in data.**
`add-consequence --fact F --agenda A --effect thwart|abandon|stall|advance`
fires the moment F is established, and the cascade then cancels the beats that
dead agenda was going to produce and retires the futures they promised. Run
`cascade --campaign C` after anything messy. `fire-beat` settles its own facts:
`played`/`narrated` establishes them (pass `--witnesses` so the people who were
there actually know), `preempted`/`cancelled` retires them.

Agendas can be **gated on knowledge**: `require-fact` makes a dormant agenda
wake up during `tick` the moment its holder learns the trigger fact. That is
how "the Baron acts once he sees that face" becomes something the world clock
evaluates rather than something you remember.

**Before executing commands, read USAGE.md for the complete reference
(GM operating rules, character creation, combat cheat sheet, worldbuilding,
campaign publishing).**

**Novelization:** to turn a campaign's journal into a typeset PDF novel
(in a chosen author style -- Hemingway, Tolkien, Moorcock, or freeform),
read `NOVELIZATION.md` and follow it.
