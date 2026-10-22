# CAST.md — inventing people at the table, and keeping the world growing

**`SCENARIO.md` builds the antagonists. This file builds everybody else**, on
demand, mid-scene, and fast enough that you actually do it.

The campaign package is a **seed, not a cast list.** A published campaign ships
thirty-odd people because thirty is what fits in a book. It is not the
population of a star system, and treating it as one is what makes a large
setting feel small.

---

## 0. The two failures, and they are opposites

### Hoarding

Running every scene out of the shipped cast. The tell is that you reach for an
NPC who *nearly* fits rather than inventing the one the scene wants, and after a
few sessions the player has met everybody and the world has a floor and walls.

Observed, First Through session 1: a station of forty thousand people, and five
consecutive scenes played entirely out of six pre-written names, because they
were there and inventing felt like extra work.

### Soup

Inventing freely with no persistence and no connections. Names that no later
session can look up, people who exist for one scene and evaporate, a world that
*sprawls* without ever getting denser. `TABLE.md` §10 already bans the
mechanical half of this — somebody invented at the table does not exist in the
save, and `--involves` can only name records that are already there.

### The rule that separates them

> **Expansion that does not connect is sprawl.** A new person must create at
> least one **edge** to something that already exists.

Three kinds of edge, and one is enough:

- **They want something from somebody who already exists.**
- **They are the reason an existing fact is true.** (Best kind. It makes the
  world retroactively deeper instead of wider.)
- **They are the second half of something you only had one half of** — the other
  name on a quarrel, the person a rumour was about, who taught somebody.

A person with no edge is scenery, and scenery does not need a record.

---

## 1. Tailor the cast to the player, not to the setting

This is the part that makes a world feel like *their* world rather than a place
they are visiting.

You already wrote the PC's **engine sentence** (`SCENARIO.md` §1) — the
contradiction they walk around with, taken from their passions and the floor of
their sheet. The cast is not a list. It is a **function of that sentence.**

The method: from the engine, derive four or five **roles the world must keep
filling**, then fill them with whoever the current scene needs. Roles persist;
the people in them are disposable.

Worked, for a PC whose engine is *"he is always right and nobody listens to
him"*:

| Role | What it does to him | How often |
|---|---|---|
| **The ambient majority** — people who talk over him without malice | makes the engine true continuously, for free, in every crowd | every scene, unnamed, one clause each |
| **The one who listens** — and is dangerous because of it | converts his asset into jeopardy | once an act |
| **Better than him at his own thing** — and generous about it | denies him even the consolation of being special | standing, recurring |
| **Needs exactly what he can do, and does not know it** | gives him somewhere to be the protagonist | one live at all times |
| **Does not need him at all** — complete, busy, uninterested | stops the world existing to serve him | often, and cheap |

Write that table once, for your PC, and keep it in the scenario doc. Then every
time you need somebody, you are not inventing from nothing: you are casting a
role, which takes seconds.

**Different engine, different table.** A PC who can talk anybody into anything
needs *the one who has already decided*, *the one who is not listening*, and
*the one who will agree and then not do it*. Derive it from their sheet, never
from a stock list.

---

## 2. The three-minute person

Invention has to be cheap or you will not do it mid-scene. Four lines and a
command. Not a backstory — a person who can be in a room.

1. **One physical fact** you could spot across a room. Not a description — a
   fact. What their hands are doing, what is wrong with their kit, what they are
   carrying, what they have stopped doing.
2. **One want, in this scene, now**, that the PC can help or hinder. If they
   want nothing, cut them; they are weather.
3. **One thing they will not do**, and the player must be able to see the shape
   of it (`TABLE.md` §6 — a refusal has to be legible).
4. **The edge** to existing canon, from §0.

Then, **before the event that names them**:

```bash
create-character --campaign <id> --type npc --species humanoid \
    --roll --name "..." --description "<the physical fact + the edge>"
update-character --id <new-id> --actor-notes "<CORE / NATURE / WANTS, three lines>"
```

**Pass `--species`.** The default is `avian`, and a human NPC created without it
gets wings, a flight speed and wing hit locations, and there is no flag to repair
locations afterwards — you have to recreate them.

A full `TABLE.md` §6 card (LOOKS / CORE / NATURE / WOUND / WANTS / PRESSURE /
KEY) is for people who are going to matter. For a three-minute person, three
lines is correct, and the rest **accretes** after each scene they survive
(`CHARACTER-SCORES.md`).

---

## 3. Promotion is the player's decision, not yours

Most invented people stay one-scene people. A few become load-bearing, and
**the player chooses which** — by remembering them, asking after them, going
back, or being angry about them.

The ladder, and you climb one rung at a time, after the fact:

| Rung | When | What you add |
|---|---|---|
| Named | they were in a scene | the three-minute record |
| Recurring | the player used their name unprompted | a score (`CHARACTER-SCORES.md`), a `doing` |
| Live | the player went out of their way for or against them | a full §6 card |
| Load-bearing | twice more | an **agenda with a clock**, and a beat hanging off it |

**Never pre-promote.** Giving a brand-new NPC a secret the plot needs is a rail
wearing a person, and the player can smell it. Invent them empty of plot and let
what the player does decide what they turn out to have been.

---

## 4. Open world: grow in the direction they walk

Breadth is cheap and worthless. **Density is the thing that makes a world feel
real**, and density is built where the player actually is.

- **Deepen before you widen.** Until the player goes somewhere new, a new person
  in a place they already know is worth more than a new place. The Nine should
  get its fourth and fifth and sixth inhabitant before the campaign gets its
  tenth system.
- **Every place the player visits gets at least one person who lives there and
  wants something.** A room with no want in it is a corridor.
- **When they go somewhere unplanned, say yes, and populate it on arrival** with
  §2. Three people, one want each. That is a location.
- **Write the place down while the scene is in front of you** —
  `update-location --staging-notes` — because a place with no card is a
  different place next time somebody visits it (`TABLE.md` §6).
- **The world moves without them.** `tick` between scenes, and let offscreen
  beats walk into a live scene (`TABLE.md` §8, §2b). An open world that only
  changes when the player is looking is a stage set.

### What not to invent

- **A new crisis, when an existing one could walk into the room.** Re-homing a
  beat is free; a second parallel emergency halves the weight of both.
- **Somebody to avoid using a built character.** Read the shipped cards first.
  The commonest finding is that the campaign already contains exactly the right
  person, fully written, unused.
- **A replacement for a person the player liked.** If they are gone, they are
  gone, and the hole is the point (`TABLE.md` §2b).

---

## 5. The count, at the end of a session

Two numbers, and they are both easy:

- **How many people did the player meet who did not exist this morning?** If the
  answer is zero for two sessions running, the world has stopped growing.
- **How many of them have an edge to something older?** If the answer is fewer
  than all of them, you are building sprawl.
