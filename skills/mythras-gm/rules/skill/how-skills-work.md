---
id: "skill/how-skills-work"
title: "Skill Checks (success, critical, fumble)"
category: "skill"
domain: "skill"
topic: "how-skills-work"
kind: "procedure"
summary: "Roll 1d100 vs skill; success, critical at one-tenth of skill, fumble on 99-00."
facets: {"phase": ["skill-check"], "kind": ["procedure"]}
links: ["skill/difficulty-grades", "skill/opposed-rolls"]
---

Roll 1d100 against the skill value:

- <= skill = **Success**; > skill = **Failure**.
- 01-05 always succeeds; 96-00 always fails.
- **Critical** = roll <= ceil(skill/10) (after modifiers).
- **Fumble** = 99-00 (just 00 if skill > 100).

The CLI command `roll-skill` returns the success level automatically.
