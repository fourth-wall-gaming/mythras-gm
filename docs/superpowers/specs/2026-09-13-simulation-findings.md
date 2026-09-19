# Playtest by simulation — findings

**Method.** `scripts/simulate.py` steps a campaign package watch by watch,
once per PC, and reports what the GM would actually have in front of them at
each watch. Then a narrative pass on top, playing both sides, stopping at the
first of: the game concludes, too much exposition, it is not obvious what to do
next, the position is hopeless, or death.

The script cannot judge whether a scene is good. It answers a narrower and more
useful question: **at 07:00 on day two, is there anything at all for this
character to do?** That defect is invisible while reading a plan top to bottom,
because reading a plan never puts you inside a single watch.

## The numbers

24 watches, `d-3/dawn` to `d2/night`, over the current package.

| PC | ENGAGED | WITNESS | OFFSTAGE | EMPTY |
|---|---|---|---|---|
| Conall | **3** | 15 | 3 | 3 |
| Randall | **2** | 15 | 4 | 3 |
| Gardwen | **1** | 16 | 4 | 3 |
| Magda | **0** | 17 | 4 | 3 |

Decisions offered: **5 of 24 watches**, identically for all four.
All four reach the end. All four trip condition **B** at `d-1/day` and stay
tripped for seven consecutive watches.

## What works

- **The catalog/plan split does what it was meant to.** Running the sim I
  read the plan to know what an act was for, and opened one beat to run the
  scene. I never needed both, and never had to reconcile two descriptions.
- **The countdown clock is legible.** Every watch has a name and a position
  relative to the Tourney, and the pressure reads without effort.
- **Causal ordering within a watch paid off immediately.** Act V ran
  room → shot → flight without my having to think about it.
- **Beats with conditions are the only ones that feel like story.** The
  standoff needing the private audience is the one place where the structure
  says *because* rather than *then*.
- **The stop conditions are a good test.** They found real defects in under a
  minute that three read-throughs of the plan had not.

## What does not work

### 1. The PCs are cast in almost nothing

**The single worst finding.** Magda is in the cast of zero beats. Gardwen is in
one, out of twenty-four — and Gardwen is the emotional spine of the entire
campaign. She is a *spectator at her own story*.

The beats were written from the world's point of view: they describe what NPCs
do. That is the correct instinct for a doomline and the wrong one for a game.

### 2. Seven consecutive watches with no decision

`d-1/day` to `d0/dawn` — the presentation through to the archery, which is the
middle of the game — asks the party for nothing. That is exactly the stretch
where a session dies, and it is 29% of the running time.

Overall: **5 of 24 watches offer a decision.** Nineteen do not.

### 3. The inciting incident is a coincidence

`santo-carves-emmeralda` has `onscreen_if: "Any PC lodged at or visiting the
Sylph's Embrace that night"` — and **nothing in the structure puts them there.**
The scene that starts the campaign fires whether or not anybody can see it.

This is systemic, not one beat's bug. `onscreen_if` is phrased passively
throughout: *if they happen to be present*. No beat states why a PC would be.

### 4. Beats say what happens, never what the PC can do

The best-written beat in the package offers *"What a PC standing there gets:"*
followed by information. That is a briefing, not a problem. A beat should state
the question it puts to the player; most of these state the answer to a question
about the world.

### 5. Seven dead watches per PC

Three EMPTY and four OFFSTAGE. Dead air is where I improvise, and improvising is
where the drift this whole system exists to prevent comes from.

### 6. Cost is recorded at the wrong granularity

"Every act takes something" is an act-level rule, so it is checked nowhere. No
beat states what it costs the person who engages with it.

## What to change

**1. `pull` replaces `onscreen_if`.** Not *if a PC is there* but **why they
are**: who sends for them, what they want that is in that room, what they lose
by not going. A beat that cannot state its pull is an NPC event, and those
should be a minority rather than the default. This alone fixes finding 3.

**2. `costs` on every beat.** One line: what engaging takes from whoever does.
Then the act-level rule becomes checkable — an act with no beat that costs
anything has not happened.

**3. `asks` on every beat.** The question put to the player. If a beat cannot
state one, it is exposition: merge it into a neighbour or cut it. This turns
finding 4 from a matter of taste into a lint.

**4. Cast PCs deliberately.** Target: every PC ENGAGED in at least a quarter of
watches. Magda at zero is not a near miss, it is a character who does not exist
in the plan.

**5. Opportunity beats are the cure for dead watches**, and there is currently
**one**. Seven dead watches per PC is exactly the hole they fill: things
standing in places, waiting to be reached. The board should be thick enough
that no watch is empty for a party that goes looking.

**6. Make the simulator a test.** Run it over the package in CI and fail on:
any PC below the engagement floor, more than three consecutive dry watches, an
act with no beat-level cost, or a beat with no `asks`. The findings above
should not be discoverable only by someone remembering to look.

## Limits of the harness

Stated plainly so the numbers are not over-trusted:

- It cannot judge prose. Condition D (hopeless position) and E (death) are not
  detectable without playing, and did not arise in the narrative pass.
- Its decision detector is a **regex over beat bodies** looking for rolls and
  choices. It will miss a decision phrased unusually and count a mention of
  "combat" as one. It is a smoke alarm, not a scale.
- It ignores opportunity beats entirely — it pops them off and never places
  them — which means the dead-watch count is a **worst case** that a party
  actively looking for trouble would not hit.
- It assumes every PC is present for the whole campaign and never moves, so
  OFFSTAGE is approximate.
