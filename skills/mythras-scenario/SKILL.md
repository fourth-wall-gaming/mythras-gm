---
name: mythras-scenario
description: Build an antagonist and a scenario from a PC's own character sheet, then write it into the save as agendas, beats and an act structure. Use when a campaign has no live antagonist, when a session has gone inert or the player says it is boring, and whenever a new PC arrives.
---

# Build a scenario

`$GM` is the engine directory — the session-start hook's ready line names it
absolutely; see **CLI** in the `mythras-gm` skill for the fallback.

**Read `$GM/SCENARIO.md` in full before doing any of this.** It is the method.
This file is the order of operations.

If the player has just told you the game is boring, do not defend the prose.
The prose is usually not what is wrong. Go to step 2.

## 1. Load the real state, not your memory of it

- `get-context --campaign <id> --compact` — the save, including `arc`.
- `list-agendas --campaign <id>` — and **look at the clocks.** A column of
  agendas sitting at `0/N` or `None/None` after several sessions is the
  diagnosis: nothing has been acting. Say so out loud, out of character.
- `list-beats --campaign <id>` — what the catalog already holds. You will
  almost certainly find built antagonists you have not used.
- `get-character --campaign <id> --id <pc>` — the sheet. You need the
  **passions** and the **lowest skills**, not the highest.

Read the character cards of every antagonist the campaign already has before
inventing one. The commonest finding at this step is that the campaign already
contains exactly the right person, fully written, unused.

## 2. Write the engine sentence

One sentence about the PC that is a contradiction and not a list of skills.
Build it from the passions and the floor of the sheet. Then name the single
asset that sentence runs on.

Put it in front of the player and let them correct it. It is their character.

## 3. Build two antagonists

By `SCENARIO.md` §1: one whose ordinary daily business destroys that asset, one
who can kill them. Prefer somebody already in the campaign; `brief --id` them
first. Where you must invent, `create-character --type npc --species humanoid`
— **pass `--species`, because the default is avian** — and card them with
`update-character --actor-notes` using the `TABLE.md` §6 fields.

## 4. Plot six to eight sequences

Each with Question, Moves first, Reversal, Cost. A sequence with no Cost is cut.
Make at least two of them the PC's angle on a beat the catalog already holds.

## 5. Write it into the save, or it does not exist

```
add-agenda   --campaign <id> --holder <npc> --title "..." --clock <size> \
             --note "fires at N: ...; at M: ..."
add-beat     --campaign <id> --title "..." --when "<latest>" --agenda <id> \
             --place <loc> --body "..."
add-fact     --campaign <id> --status established --learned-by <pc> --statement "..."
update-campaign --campaign <id> --arc-file <story.md>
```

A `--when` is the LATEST a beat can happen; carry the real condition in
`onscreen_if` and in the body. Then **read it back out of the graph** and check
the clocks and the arc are what you think they are.

Keep the prose in `docs/scenarios/<name>.md` in the campaign repo. The save
holds the structure; the file holds the argument.

## 6. Hand back

Tell the player, plainly and out of character: who the antagonists are, why
those two for this character, what is now running on a clock, and what the act
is going to take from them. Name the loss. Then ask where they want to pick up.

Do not foreshadow inside the fiction afterwards (`TABLE.md` §0, rule 8). The
beat list is yours; the pressure is theirs to feel.
