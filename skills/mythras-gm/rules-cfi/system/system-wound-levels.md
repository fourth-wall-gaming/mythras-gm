---
id: "cfi/system/wound-levels"
title: "Wound Levels and Damage Resolution"
system: "classic-fantasy"
category: "system"
domain: "system"
topic: "wound-levels"
kind: "procedure"
summary: "Damage to a Hit Location is classified as Minor (HP positive), Serious (HP 0 or below), or Major (HP negative by starting value or more), each with escalating consequences."
facets: {"kind": ["procedure"], "phase": ["damage"], "severity": ["minor","serious","major"]}
links: ["cfi/system/hit-locations", "cfi/system/blood-loss", "cfi/system/healing-from-injury"]
---

**Damage Calculation Order:**

1. Apply attacker's Damage Modifier.
2. Apply weapon-enhancing or -reducing magic.
3. Reduce by parry (comparative weapon sizes).
4. Reduce by location Armor Points.
5. Remaining damage removes Hit Points from the location.

**Wound Categories:**

- **Minor Wound:** Location still has positive Hit Points. Cuts, bruises, sprains; no mechanical penalty.
- **Serious Wound:** Location reduced to 0 HP or below. Location permanently scarred; victim cannot attack or cast for next 1d3 Turns (can still Parry/Evade). Endurance rolls required (Opposed vs. attack roll):
  - Limb: failure = limb useless until HP positive (if leg: fall prone; if arm: drop held item unless strapped).
  - Abdomen/Chest/Head: failure = unconscious for minutes equal to damage dealt.
  - GM may impose -1 grade on tasks using that location until reduced to Minor Wound.
- **Major Wound:** Location reduced to negative HP equal to or greater than its starting HP. Character immediately Incapacitated and drops prone. Endurance Opposed Test vs. attack roll:
  - Limb: failure = unconscious from agony. Treat within minutes equal to Healing Rate x5 or character dies.
  - Abdomen/Chest/Head: failure = instant death. Treat within Combat Rounds equal to Healing Rate x2 or character dies.

**Endurance rolls** for Serious/Major wounds are Opposed vs. the original attack roll value. Not repeated unless the location is wounded again.
