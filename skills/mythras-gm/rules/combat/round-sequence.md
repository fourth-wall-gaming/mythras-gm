---
id: "combat/round-sequence"
title: "The Combat Round"
category: "combat"
domain: "combat"
topic: "rounds-initiative"
kind: "procedure"
summary: "5-second rounds: roll initiative, then each combatant takes one proactive action."
facets: {"phase": ["combat-round"], "kind": ["procedure"], "stat": ["action-points", "initiative"]}
links: ["combat/actions", "skill/how-skills-work"]
---

Combat runs in 5-second Combat Rounds.

1. **Start encounter:** `start-encounter`, then `add-combatant` for each participant.
2. **Initiative:** `roll-initiative` -- 1d10 + Initiative Bonus per combatant (highest first; ties broken by DEX). Initiative persists between rounds. Surprise: -10 initiative, flat-footed until their turn, and the first hit on them gains a bonus Special Effect.
3. **Turns:** count down initiative. On their turn a combatant spends 1 Action Point on ONE Proactive Action -- one per round, no more (Mythras Imperative has no extra action cycles). Remaining AP may only be spent on Reactive Actions (Parry, Evade, Interrupt) when threatened. All ordinary characters have 2 AP per round; unused AP do not carry over. `next-round` resets AP.
4. Round ends once every combatant has had their turn.
