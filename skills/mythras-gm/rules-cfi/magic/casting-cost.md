---
id: "cfi/magic/casting-cost"
title: "Casting Cost and Skill Roll Results"
system: "classic-fantasy"
category: "magic"
domain: "magic"
topic: "casting-procedure"
kind: "procedure"
summary: "MP cost depends on spell Intensity; the casting roll result determines whether full, half, or no MP (and EXP rolls) are spent, and whether the spell is cast or expunged from memory."
facets: {"magic-system": ["arcane", "divine"], "kind": ["procedure"], "phase": ["action"]}
links: ["cfi/magic/casting-time", "cfi/magic/magic-points", "cfi/magic/magnitude-intensity", "cfi/magic/mp-reduction-matrix"]
---

Spells are cast at a base Intensity of 1 and may be increased to Maximum Intensity at extra MP cost. Cost formats:
- **"1"** -- fixed 1 MP; cannot be boosted.
- **"1, +1/additional Intensity"** -- 1 MP base, +1 per Intensity beyond 1.
- **"3/Intensity"** -- 3 MP per Intensity level.
- **"(+1 EXP)"** -- additionally requires 1 or more unspent Experience Rolls (permanent life-force sacrifice); spells with EXP costs have their Magnitude doubled for dispelling purposes.

**MP and EXP are only paid on the final Turn of casting.** After determining final Intensity and cost, make the Arcane Casting or Divine Channeling roll:

| Roll Result | Outcome |
| :-- | :-- |
| **Critical** | Spell works; only **half MP** expended (minimum 1 if cost was 1). EXP rolls halved (minimum 1). |
| **Success** | Spell works; **full MP and EXP** expended. |
| **Failure** | Spell fails; **no MP or EXP spent**. Optionally, the caster may **Force** the spell: treat as Success for MP/EXP cost and effect, but the spell is **expunged from memory** (must be re-memorized). |
| **Fumble** | Spell fails; **half MP** expended; EXP rolls retained. Spell is **expunged from memory**. |

**Rank limit on EXP per session:** A caster may spend EXP rolls on spells up to a maximum equal to their Rank per game session. Once the session's limit is reached, further EXP-costing spells cannot be cast until the next session.

**Minimum cost:** No spell's final MP cost may be reduced below 1.
