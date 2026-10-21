# SCENARIO.md — building an antagonist and a scenario at the table

**`TABLE.md` governs how you narrate. This file governs what there is to
narrate about.** Read it when a campaign has no live antagonist, when a session
has gone inert, and whenever a new PC arrives — their arrival is the moment to
build this and the cheapest it will ever be.

Where this file and `TABLE.md` disagree, `TABLE.md` wins on conduct and this
file wins on construction.

---

## 0. The failure this exists to prevent

Two separate campaigns produced the same report from the player, in almost the
same words: **"this is boring — who is the antagonist?"**

Both times the prose was fine. Both times the GM had read the conduct rules at
the top of the session. Both times the answer to the question was that there
wasn't one — the pressure in the campaign was coming from a timetable, a
maintenance figure, or a slow institutional problem, and **nothing in the world
wanted anything that cost the player anything.**

A warm, well-written scene in which nobody wants anything feels like good work
while you are writing it. That is the whole trap. You cannot catch it by
reading your own prose, because the prose is not what is wrong. You catch it by
counting.

**The count, at the end of every session: what did the player lose?** If the
answer is nothing, the session did not happen.

---

## 1. Build the antagonist out of the PC's sheet

An antagonist chosen to fit the setting produces a plot. An antagonist chosen
to fit the **protagonist** produces a story. This is the step that gets skipped
and it is the one that matters.

### The method, in four moves

1. **Name the character's engine.** One sentence, and not a list of skills: the
   contradiction they walk around with. Read the *passions* first — a campaign's
   best fault lines are already written there, usually as two passions a few
   points apart that cannot both be satisfied. Then read the lowest skill on the
   sheet, because that is where the player has already told you what their
   character cannot do.
2. **Name the one asset the engine runs on.** There is almost always exactly
   one. Testimony. Standing. A name. A trade. One person's protection. The
   ability to walk away.
3. **Build somebody whose ORDINARY DAILY BUSINESS destroys that asset.** Not
   somebody who hates the PC — somebody for whom ruining them is Tuesday, who
   would be doing it whoever was standing there, and who is pleasant about it.
   This antagonist attacks what the character *is*.
4. **Then build a second one who can kill them.** Competent, physical, and
   able to win. This antagonist attacks whether the character *continues*.

**You need both.** One alone fails in a predictable way: a purely social
antagonist makes a campaign with no jeopardy, and a purely violent one makes a
campaign the PC's sheet is already built to beat.

### The sharpest version of move 3

**Cancel the PC's advantage with somebody who has the same advantage**, or with
somebody against whom it simply does not apply. A PC who always knows the truth
needs an enemy who controls whether truth *counts*. A PC nobody can catch needs
an enemy who does not chase. A PC who can talk anybody into anything needs an
enemy who is not listening and has already decided.

An antagonist who is merely stronger is an obstacle. An antagonist who makes
the PC's best thing worthless is a story.

### Three tests before you keep one

- **Can they win?** Not "could they theoretically". Is there a version of the
  next month in which they get what they want and the PC does not stop them?
- **Are they doing something today?** If their plan starts when the PC arrives,
  they are scenery. Two things should already have happened.
- **Can the PC hate them cleanly?** If yes, weaken it. The best ones are warm,
  are partly right, and would be good company for an hour.

---

## 2. Plot in sequences

A **beat** is a unit of catalog — one event, with a time and a trigger. A
**sequence** is a unit of drama. Campaigns run out of drama while still having
plenty of beats, which is how a GM ends up with a full catalog and an inert
table.

Every sequence gets four lines written down *before* it is run:

| | |
|---|---|
| **Question** | the dramatic question this sequence exists to answer, phrased so it can be answered yes or no |
| **Moves first** | who acts before the PC does, and what they do. Nearly always the antagonist |
| **Reversal** | the thing that makes the obvious answer wrong halfway through |
| **Cost** | what the PC loses whichever way it goes |

**If you cannot fill in Cost, it is not a sequence.** It is a transition, and it
gets compressed to one sentence or cut (`TABLE.md` §2a).

### Shapes that work, and the reason they work

- **Give the win, charge for it.** The PC succeeds completely and immediately,
  and the success is what exposes them. This is the strongest opening sequence
  there is, because it teaches the player that acting works and that acting
  costs, in one move.
- **The helpful thief.** An antagonist agrees with the PC entirely, takes the
  thing, reports it accurately, and leaves the PC out. Nothing was stolen and
  nothing was lied about. Rage with nowhere to go is the most motivating thing
  you can hand a player.
- **The ally who is the danger.** The one person who believes the PC is the one
  who will do something terrible about it. An ally who is a danger is worth four
  who are nice.
- **The enemy who is not here for you.** The violent antagonist arrives for
  somebody else — a minor NPC the PC met once and liked. Now the PC's choice is
  whether to be there, and the stakes belong to somebody with no plot armour.
- **The secret that is a weapon.** The violent antagonist is wrong about
  something load-bearing in their own life, and the PC can find it out. The
  truth works better than any skill on the sheet, and using it costs something
  too.

### Sequence count

Six to eight per act. Fewer than six and the act has no middle; more than eight
and it is two acts.

---

## 3. Clocks, and the rule that makes it not boring

Every antagonist gets an **agenda with a clock**, and the clock is the whole
mechanism. A plan in your head decays; a clock in the save does not.

- **Size the clock to the act.** Four for a thing that should land inside this
  act. Six to eight for a thing that should threaten for the whole of it.
- **Name what fires at which segment** when you create it, not later. An agenda
  with no beat hanging off it is a note, not a threat.
- **Advance on a watch, not on a scene.** Every antagonist's clock moves when
  the world's clock moves, whether or not the player was looking. `tick`.
- **And answer within a watch.** Write the counters as *triggers* — when they do
  this, he does that — and fire them while the party is still in the room, not
  into the journal for later discovery.

Two or three clocks running at once is right. One is a timetable. Five is
weather.

---

## 4. It is not built until it is in the save

Your plan will drop out of context and nothing will tell you it has gone. This
is not a theoretical risk; it is the single most common way a good scenario
stops existing. So the work ends with the save, every time:

1. **`add-agenda`** for each antagonist, with holder and clock size, and a
   `--note` saying what fires where.
2. **`add-beat`** for each sequence, with `--when` as the LATEST it can happen
   and the real condition in `onscreen_if`. A `when` is a backstop; conditions
   bring it forward.
3. **Write the acts into `story.md`** — what each act is FOR and what it
   **TAKES** — and push it with `update-campaign --arc-file`, because `arc`
   rides on `get-context`, `forecast` and `tick`, and therefore cannot decay.
4. **`add-fact --status established`** for anything the PC now holds, with
   `--learned-by`, in the same call.
5. **Keep the prose somewhere** — `docs/scenarios/<name>.md` in the campaign
   repo — because the save holds the structure and not the argument.

Then verify by reading it back **out of the graph**, not off your own notes.

---

## 5. Every act takes something

From `TABLE.md` §2b, restated here because it is the acceptance test for a
scenario rather than for a scene:

**An act in which the player only gains has not happened.** Name the loss in
the act's `TAKES` line before you run a scene of it. Not a setback — something
that does not come back: a person, a place, a standing, a route, a name.

The best losses are **caused by the player being right.** That is not cruelty;
it is what makes the next decision hard, and a campaign is a sequence of hard
decisions or it is a travelogue.

---

## 6. When a new PC arrives

Do this then. It takes about twenty minutes and it is the cheapest it will ever
be, because the sheet is in front of you and nothing has been established yet.

1. Read the arc — what each act is FOR and what it TAKES.
2. Read the PC's passions and their lowest skill, and write the engine sentence.
3. Build the two antagonists by §1.
4. Plot six to eight sequences by §2, and make at least two of them the PC's
   angle on a beat that already exists, so the thread braids into the campaign
   instead of running beside it.
5. Put the clocks in the save by §4.

A thread with no shared beats is a second campaign.
