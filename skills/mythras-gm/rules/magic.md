# Mythras Imperative — Magic & Powers Reference

Distilled from the Mythras Imperative SRD chapter "Magic and Powers."
Two separate frameworks: **Magic** (spells, for magicians) and
**Superpowers** (core powers + Boosts + Limits, for super-beings).
Settings rename and re-flavor these (e.g. the Veilwrack campaign's
Windworking is the Magic system verbatim — see that campaign's lore).

## Magic

**Skill:** Magic (POW+CHA), a Professional skill. No skill, no magic.
**Pool:** Magic Points = POW. Recovery: Healing Rate per hour of full rest.

**Casting:** one Action + a Magic skill roll:

| Roll | MP cost | Result |
|---|---|---|
| Critical | 0 | spell works |
| Success | 1 | spell works |
| Failure | 1 | spell fails |
| Fumble | 1d3 | spell fails (GM may add a mishap) |

All spells are Intensity/Magnitude 1 (petty magic). Duration: the scene,
unless the spell is *Instant*, *Concentration*, or has a special duration.

**Traits:**
- *Instant* — happens immediately, no duration
- *Concentration* — lasts while the caster concentrates undisturbed
- *Ranged* — up to Magic skill score in metres; unseen targets = one grade harder
- *Touch* — physical contact required (unwilling targets generally need Grip/surprise)
- *Resist (Endurance/Evade/Willpower)* — opposed roll vs the casting result;
  Evade resists cost the target an Action Point

**Starting spells:** 1d4+1. **Learning:** 3 Experience Rolls + one week +
a teacher or reliable source.

**Counter-magic in combat:** Avert (or setting equivalent) via the Counter
Spell reactive action; held spells use the Hold Magic action.

### SRD spell list (traits)

Alarm (special duration) · Avert (Instant, Ranged) · Befuddle (Ranged,
Resist Willpower) · Bladesharp (Touch: +1 damage die step, edged) ·
Bludgeon (Touch: as Bladesharp, blunt) · Breath (Touch: hold air POW/2
minutes) · Calm (Ranged, Resist Willpower) · Chill (Instant, Touch) ·
Darkness (Concentration, Ranged: POW sq m shadow) · Disruption (Instant,
Ranged, Resist Endurance: 1d3 ignoring armor) · Extinguish (Instant,
Ranged) · Find X (Concentration, Ranged, Resist special) · Firearrow
(Touch: missiles +1d3 fire) · Fireblade (Touch: melee +1d3 fire) · Glue
(Touch: Brawn POW×5 bond) · Heal (Instant, Touch: minor wounds fully
restored; serious/major stabilized only) · Ignite (Instant, Ranged) ·
Knock (Instant, Touch) · Light (Concentration, Ranged) · Lock (Touch,
special: MP doesn't recover while active) · Phantasm (Concentration,
Ranged) · Sleep (Touch, Resist Endurance: POW/2 hours; fails in combat) ·
Vigor (Touch: suspend exertion Fatigue) · Witchsight (Ranged, Resist
Willpower: see magic/invisible/true forms)

## Superpowers

**Pool:** Power Points = POW. Recovery: 1 per minute of rest, or spend a
Luck Point for 1d4+1 immediately. Core powers are always-on or at-will and
free; **Boosts** cost Power Points.

**Build:** core powers = POW + (CON for altered physiology | INT for
tech/training), per table: ≤12 → 1, 13-20 → 2, 21-30 → 3, 31-40 → 4,
40+ → 5. Trade one core power for two Boosts. Up to two **Limits**: one
Limit = bonus Boost; two Limits = bonus core power.

**Core powers (summary):** Animation (constructs from material) · Combat
Expert · Durability (HP from CON+SIZ+POW) · Elemental Control · Energy
Blast · Enhanced Reactions · Enhanced Speed · Enhanced Strength · Flight
(POW m move) · Heightened Sense · Inherent Armor (CON/3 all locations) ·
Life Support (immune to 2 environmental conditions) · Lucky · Regeneration
(1 HP/round to non-Major wounds) · Savant (3 skills one grade easier) ·
Teleport · Vaporous Form

**Limits:** Activation Cost · External Power Source · Fatal Flaw · Limited
Control (fumble on 90-00) · Limited Power (conditional) · Physical
Limitation · Vulnerability (double damage from X)

## GM guidance

- Use **Magic** for the setting's learnable tradition (folk-scale, costed,
  resistible). Use **Superpowers** for beings whose nature IS the power —
  monsters, the touched, the transformed. Don't mix frameworks on one
  character without good reason.
- Spell saturation: magic at this scale changes daily life (Heal, Vigor,
  Light) more than battles. Let NPC casters exist in the economy.
- Resist rolls use the CLI: `roll-opposed` with the caster's casting result
  re-entered as a flat skill if needed, or roll the target's resist via
  `roll-skill` against the cast quality narratively.
