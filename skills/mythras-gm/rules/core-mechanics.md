# Mythras Imperative — Core Mechanics Reference

Distilled from the Mythras Imperative SRD (https://github.com/raleel/mythras-srd).
This is the GM agent's rules reference. The `mythras_gm.py` CLI implements the dice
math; this doc tells you *when* to call it and *how* to interpret results.

## Characteristics

Seven characteristics define every character:

| Char | Meaning | At zero... |
|---|---|---|
| STR | Physical strength | cannot move/lift |
| CON | Health and hardiness | death |
| SIZ | Mass (height/weight) | — |
| DEX | Agility, reflexes | paralysis |
| INT | Cognitive ability | mindless |
| POW | Spirit / magic capacity | loses independent will |
| CHA | Presence and personality | socially inert |

Generation: 3d6 for STR, CON, DEX, POW, CHA; 2d6+6 for SIZ and INT.
(For Alar avians in the Veilwrack setting, see setting/bestiary.md for racial mods.)

## Derived Attributes

| Attribute | Formula |
|---|---|
| Action Points | 2 (always, for ordinary characters) |
| Damage Modifier | from STR+SIZ (see table below) |
| Experience Modifier | CHA 6- = -1, 7-12 = 0, 13-18 = +1, each +6 = +1 |
| Healing Rate | CON 6- = 1, 7-12 = 2, 13-18 = 3, each +6 = +1 |
| Initiative Bonus | (DEX + INT) / 2, round down |
| Luck Points | POW 6- = 1, 7-12 = 2, 13-18 = 3, each +6 = +1 |
| Magic Points | = POW |
| Movement | 6m base (humans); Alar walk 4m, fly 12m |

### Damage Modifier Table (STR+SIZ)

| STR+SIZ | Mod | STR+SIZ | Mod |
|---|---|---|---|
| ≤5 | -1d8 | 41-45 | +1d8 |
| 6-10 | -1d6 | 46-50 | +1d10 |
| 11-15 | -1d4 | 51-60 | +1d12 |
| 16-20 | -1d2 | 61-70 | +2d6 |
| 21-25 | +0 | 71-80 | +1d8+1d6 |
| 26-30 | +1d2 | 81-90 | +2d8 |
| 31-35 | +1d4 | 91-100 | +1d10+1d8 |
| 36-40 | +1d6 | 101-110 | +2d10 |

### Hit Points per Location (CON+SIZ)

| Location | 1-5 | 6-10 | 11-15 | 16-20 | 21-25 | 26-30 | 31-35 | 36-40 | each +5 |
|---|---|---|---|---|---|---|---|---|---|
| Head | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | +1 |
| Chest | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | +1 |
| Abdomen | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | +1 |
| Each Arm | 1 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | +1 |
| Each Leg | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | +1 |
| Each Wing* | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | +1 |

*Wings use the leg row. Avian (Alar) hit location table is in `combat.md`.

## Skill Checks

Roll 1d100 against skill value:
- ≤ skill = **Success**; > skill = **Failure**
- 01-05 always succeeds; 96-00 always fails
- **Critical** = roll ≤ ceil(skill/10) (after modifiers)
- **Fumble** = 99-00 (just 00 if skill > 100)

The CLI command `roll-skill` returns the success level automatically.

### Difficulty Grades

Apply BEFORE finding critical range:

| Grade | Modifier |
|---|---|
| Very Easy | skill × 2 |
| Easy | skill × 1.5 |
| Standard | — |
| Hard | skill × 2/3 |
| Formidable | skill × 1/2 |
| Herculean | skill × 1/5 |
| Hopeless | cannot attempt |

When multiple penalties apply, use the most severe only.

### Standard Skills (base values)

Athletics STR+DEX · Boating STR+CON · Brawn STR+SIZ · Combat Style STR+DEX ·
Conceal DEX+POW · Customs INT×2+40 · Dance DEX+CHA · Deceit INT+CHA ·
Drive DEX+POW · Endurance CON×2 · Evade DEX×2 · First Aid DEX+INT ·
Influence CHA×2 · Insight INT+POW · Locale INT×2 · Native Tongue INT+CHA+40 ·
Perception INT+POW · Ride DEX+POW · Sing POW+CHA · Stealth DEX+INT ·
Swim STR+CON · Unarmed STR+DEX · Willpower POW×2

In the Veilwrack setting, **Flight (STR+DEX)** replaces Swim as a standard skill
for Alar, and **Ride** is rarely used. Use Flight for aerial maneuvers, racing,
carrying loads aloft, and flying in turbulence.

Professional skills (selected): Acrobatics STR+DEX, Acting CHA×2, Commerce INT+CHA,
Courtesy INT+CHA, Craft DEX+INT, Healing INT+POW, Lore INT×2, Navigation INT+POW,
Oratory POW+CHA, Survival CON+POW, Track INT+CON, Musicianship DEX+CHA,
Lockpicking DEX×2, Mechanisms DEX+INT, Sleight DEX+CHA, Streetwise POW+CHA,
Magic POW+CHA (called **Windworking** in Veilwrack).

### Opposed Rolls

Both roll. Winner = higher level of success. Tie on level → higher dice roll
that is still within skill range wins. Both fail → re-roll or GM narrates.
Use `roll-opposed` in the CLI. Common pairings: Stealth vs Perception,
Deceit vs Insight, Influence vs Willpower, Brawn vs Brawn.

### Differential Rolls (used in combat)

Both roll independently; difference in success levels = number of Special
Effects for the better side. Crit beats Success by 1 level, Success beats
Failure by 1, etc. (Crit vs Fumble = 3 levels.)

### Skills Over 100%

In opposed/differential contests, the highest-skilled participant subtracts
(skill − 100) from EVERYONE's skill including their own.

## Luck Points

One per action max. Spend to: re-roll or swap digits of any roll (own or
force opponent re-roll); gain +1 Action Point this round; downgrade a Major
Wound to a Serious Wound. Replenish each session.

## Passions

Rated like skills (e.g. "Loyalty to the Murmuration 60%"). Use to:
- Augment a related skill: +20% of the passion's value
- Drive behavior: roll vs passion; success = act in accordance
- Oppose another passion or resist manipulation (substitute for Willpower)

## Fatigue

Each failed exertion roll (Athletics/Brawn/Endurance) adds a level:
Fresh → Winded (skills Hard) → Tired (Hard, -1m move) → Wearied (Formidable,
-2m, -2 init) → Exhausted (Formidable, move halved, -4 init, -1 AP) →
Debilitated (Herculean, -6 init, -2 AP) → Incapacitated → Semi-Conscious →
Comatose → Dead. Recovery = period/HealingRate (15min for Winded up to 24h+).

**Veilwrack note:** flight in still air is exhausting — see setting docs;
Stilled-air zones force Flight rolls each round or accrue Fatigue.

## Healing

- Minor Wound (location HP > 0): heal HealingRate HP/day
- Serious Wound (location ≤ 0): HealingRate HP/week; 1d3 turns stunned when
  suffered; limb may be disabled (Endurance opposed vs attack roll)
- Major Wound (location ≤ −starting HP): incapacitated; needs Healing skill
  treatment or death in minutes; HealingRate HP/month
- First Aid: once per injury, heals 1d3 HP.

## Experience

Award 1-3 Experience Rolls per session at natural break points. Player rolls
1d100+INT vs skill: ≥ skill → +1d4+1%; < skill → +1%. Fumbled skills during
play gain a free +1%. Use CLI `award-experience` and `improve-skill`.
