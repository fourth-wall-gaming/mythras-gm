---
id: "combat/attack-resolution"
title: "Attack Resolution (the core loop)"
category: "combat"
domain: "combat"
topic: "attack-parry"
kind: "procedure"
summary: "Attack vs defense as a differential roll; special effects, then damage, location, armor."
facets: {"phase": ["attack", "defense", "damage"], "kind": ["procedure"], "action": ["attack", "parry", "evade"], "trigger": ["differential"]}
links: ["combat/special-effects", "combat/hit-locations", "system/wound-levels", "combat/arms-and-armor", "skill/differential-rolls"]
---

1. Attacker spends 1 AP, rolls Combat Style -> note success level.
2. Defender MAY spend 1 AP to Parry (roll Combat Style) or Evade. No AP / chooses not to defend = automatic Failure for the comparison.
3. Compare as a Differential Roll -> difference in success levels = number of Special Effects for the better side. Effects chosen BEFORE the damage roll.
4. Attacker succeeded -> roll weapon damage + Damage Modifier; roll 1d20 hit location (unless Choose Location).
5. Defender parried successfully -> reduce damage by comparative weapon size: equal/bigger parry = ALL damage blocked; one size smaller = HALF; two+ smaller = NONE.
6. Subtract location Armor Points from remaining damage. Apply to location HP.

Use `resolve-attack`: it performs steps 1-6 in one call and reports special effects available, damage dealt, location, and resulting wound level.
