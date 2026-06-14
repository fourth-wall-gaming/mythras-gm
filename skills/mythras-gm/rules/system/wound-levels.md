---
id: "system/wound-levels"
title: "Wound Levels (Minor / Serious / Major)"
category: "system"
domain: "system"
topic: "wound-levels"
kind: "procedure"
summary: "Minor, Serious, and Major wounds by location HP, with their mechanical consequences."
facets: {"phase": ["wound"], "kind": ["procedure"], "severity": ["minor", "serious", "major"], "body": ["head", "chest", "abdomen", "arm", "leg", "wing"], "stat": ["hit-points"]}
links: ["system/healing", "combat/hit-locations", "skill/opposed-rolls"]
---

- **Minor:** location HP still positive. No mechanical effect.
- **Serious:** location at 0 or below. 1d3 turns unable to attack (can still parry/evade). Limb: opposed Endurance vs attack roll or limb useless. Torso/head: opposed Endurance or unconscious for minutes equal to damage dealt.
- **Major:** location at -(starting HP) or worse. Incapacitated immediately. Limb severed/shattered; death in 5x Healing Rate minutes untreated. Torso/head: unconscious; opposed Endurance or instant death.

The CLI tracks current HP per location and reports the wound level whenever damage is applied (`apply-damage`).
