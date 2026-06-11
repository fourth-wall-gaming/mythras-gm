# Mythras Imperative — Combat Reference

Combat is tracked blow-by-blow in 5-second Combat Rounds. The CLI
(`mythras_gm.py`) manages encounter state in TypeDB: round counter, initiative
order, action points, and per-location damage. Your job as GM is narration and
adjudication; the CLI does the arithmetic.

## Combat Round Sequence

1. **Start encounter:** `start-encounter`, then `add-combatant` for each participant.
2. **Initiative:** `roll-initiative` — 1d10 + Initiative Bonus per combatant
   (highest first; ties broken by DEX). Initiative persists between rounds.
   Surprise: −10 initiative, flat-footed until their turn, first hit on them
   gains a bonus Special Effect.
3. **Turns:** count down initiative. On each combatant's turn they spend 1
   Action Point on a Proactive Action. Anyone may spend AP on Reactive Actions
   (Parry, Evade, Interrupt) when threatened. All ordinary characters have
   **2 AP per round**; unused AP do not carry over. `next-round` resets AP.
4. Round ends when all AP are spent/held; loop to 3.

## Actions

**Proactive (on your turn):** Attack · Brace · Cast Magic · Change Range ·
Charge · Delay · Mount · Move · Outmaneuver · Ready Weapon · Regain Footing ·
Struggle · Take Cover.

**Reactive (any time, vs a threat):** Parry · Evade · Interrupt (if Delaying) ·
Counter Spell.

**Free (no AP):** Assess Situation (Perception) · Drop Item · Signal · Speak
(5 words-ish) · Use Luck Point · Ward Location (passive block).

## Attack Resolution (the core loop)

1. Attacker spends 1 AP, rolls Combat Style → note success level.
2. Defender MAY spend 1 AP to Parry (roll Combat Style) or Evade.
   No AP / chooses not to defend = automatic Failure for the comparison.
3. Compare as **Differential Roll** → difference in success levels = number of
   **Special Effects** for the better side. Effects chosen BEFORE damage roll.
4. Attacker succeeded → roll weapon damage + Damage Modifier; roll 1d20 hit
   location (unless Choose Location).
5. Defender parried successfully → reduce damage by comparative weapon size:
   equal/bigger parry = ALL damage blocked; one size smaller = HALF; two+
   smaller = NONE.
6. Subtract location Armor Points from remaining damage. Apply to location HP.

Use `resolve-attack` in the CLI: it performs steps 1-6 in one call and reports
special effects available, damage dealt, location, and resulting wound level.

## Hit Locations

### Humanoid (1d20)
1-3 R Leg · 4-6 L Leg · 7-9 Abdomen · 10-12 Chest · 13-15 R Arm · 16-18 L Arm · 19-20 Head

### Winged Alar / avianoid (1d20) — used for all Alar PCs and NPCs
| 1d20 | Location |
|---|---|
| 1-2 | Right Leg |
| 3-4 | Left Leg |
| 5-7 | Abdomen |
| 8-10 | Chest |
| 11-12 | Right Wing |
| 13-14 | Left Wing |
| 15-16 | Right Arm |
| 17-18 | Left Arm |
| 19-20 | Head |

**Wing wounds:** A Serious Wound to a wing means no flight (failed Endurance
opposed vs attack = wing useless). A flying Alar whose wing is disabled falls —
see Falling. A Major Wound to a wing while airborne is usually fatal at altitude.

## Wound Levels

- **Minor:** location HP still positive. No mechanical effect.
- **Serious:** location at 0 or below. 1d3 turns unable to attack (can still
  parry/evade). Limb: opposed Endurance vs attack roll or limb useless.
  Torso/head: opposed Endurance or unconscious for minutes = damage dealt.
- **Major:** location at −(starting HP) or worse. Incapacitated immediately.
  Limb severed/shattered; death in 5×HealingRate minutes untreated.
  Torso/head: unconscious; opposed Endurance or instant death.

The CLI tracks current HP per location and reports the wound level whenever
damage is applied (`apply-damage`).

## Special Effects (choose when you win levels of success)

**Offensive:** Bash (knockback) · Bleed (cutting; Endurance vs attack or lose
1 Fatigue/round) · Bypass Armor (crit) · Choose Location · Circumvent Parry
(crit) · Damage Weapon · Disarm (opposed Combat Style) · Grip (unarmed) ·
Impale (impaling weapons; roll damage twice take best; weapon stuck = grade
penalty) · Maximize Damage (crit, stackable) · Stun Location (bludgeoning;
Endurance vs attack or location incapacitated for turns = damage) · Sunder
(2H; damage armor itself) · Trip (opposed Brawn/Evade/Acrobatics or prone).

**Defensive:** Arise (stand up free) · Blind Opponent (crit) · Damage Weapon ·
Disarm · Enhance Parry (crit, blocks all damage) · Force Failure (foe fumbled) ·
Prepare Counter · Scar Foe · Select Target (attacker fumbled — hits bystander) ·
Slip Free (crit) · Trip · Withdraw (break engagement free).

**Aerial additions (setting rule):** when both combatants are flying, Trip
becomes **Tumble** (forced 1d10m altitude loss + Flight roll to recover) and
Bash knocks the target back/down 1m per 2 damage in 3D.

## Situational Modifiers (most common)

| Situation | Grade |
|---|---|
| Attacking helpless target | Automatic |
| Confined space / unstable footing / crouching / poor visibility | Hard |
| Defending vs attack from behind / fighting prone / dim light | Formidable |
| Pitch black / blinded | Herculean |
| Target running (ranged) | Hard |
| Target sprinting (ranged) | Formidable |
| Light/moderate/strong wind (ranged) | Hard/Formidable/Herculean |
| Attacker flying in turbulence (setting) | capped by Flight skill |

Fighting while flying caps Combat Style at the character's Flight skill
(analogous to the SRD's mounted-combat cap by Ride).

## Charging & Aerial Charges

Charge: move at Run/Sprint into contact, attack at Hard, weapon Size +1 step,
Damage Modifier +1 step (bipeds). **Diving attack (setting):** an Alar diving
≥10m onto a target counts as a charge with Damage Modifier +2 steps, but a
miss requires an immediate Flight roll or the attacker tumbles past prone /
loses 1d10m of altitude.

## Falling

| Distance | Damage |
|---|---|
| ≤1m | none |
| 2-5m | 1d6, one location |
| 6-10m | 2d6, two locations |
| 11-15m | 3d6, three locations |
| 16-20m | 4d6, four locations |
| each +5m | +1d6 |

Armor does NOT protect; Damage Modifier applies. A falling Alar with at least
one working wing may attempt a Flight roll (Hard if injured) to halve effective
fall distance, or fully arrest the fall on a Critical.

## Ranged Combat

Resolved like melee but only shields can parry; otherwise Evade (dive prone)
or cover. Force vs parry size; Long range = half damage, −1 Force step.
Aiming a full round = reduce one situational/range grade.

Sample weapons (Veilwrack flavors in parentheses):

| Weapon | Damage | Size | Notes |
|---|---|---|---|
| Talon-hook (axe) | 1d6+1 | M | can sunder |
| Spurblade (shortsword) | 1d6 | M | — |
| Wingspear 1H | 1d8+1 | M | set vs charge |
| Wingspear 2H | 1d10+1 | L | set vs charge |
| Beak/claws (natural) | 1d3 | S | unarmed |
| Bola-net (net) | 1d4 | S | entangle, thrown |
| Stormbow (bow) | 1d8 | L (force) | DM applies, 15/100/200m |
| Sling-darts (sling) | 1d8 | L (force) | 10/150/300m |
| Dagger | 1d4+1 | S | thrown 5/10/20m |

Armor: quilted windsilk 2 AP · lacquered bone-scale 4 AP · drake-leather 3 AP ·
Wardens' alloy harness 5 AP (torso only; +flight penalty). Total AP worn ≥8
imposes movement penalties and the highest worn AP subtracts from Initiative.
Flying with >12 total AP requires a Flight roll per scene; Alar generally
armor only the torso and head.
