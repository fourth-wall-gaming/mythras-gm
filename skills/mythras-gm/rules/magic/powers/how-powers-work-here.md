---
id: "magic/powers/how-powers-work-here"
title: "Powers in Purewater: what they are and when to reach for one"
category: "magic"
domain: "magic"
topic: "powers"
kind: "procedure"
summary: "CFI resolves spells. Everything CFI has no entry for is a Mythras Power. No new spells are ever written."
facets: {"phase": ["casting"], "kind": ["procedure"], "magic-system": ["powers"], "licence": ["ours"]}
links: ["magic/superpowers", "magic/limits", "magic/which-book", "magic/cfi/spell-list"]
licence: "ours"
---

Two systems, and the line between them is not about flavour. It is about where
the rule comes from.

- **A spell is CFI.** It is on `magic/cfi/spell-list`, it has a Rank, a Cost and
  a Casting Time, and it is cast on **Channel** or **Arcane Casting**.
  **We never write a new spell.** If a character is described as having one that
  CFI does not list, either it is a CFI spell under another name — check
  `spell_registry.json` — or it is not a spell at all.
- **A power is Mythras.** `magic/superpowers` is the chassis: Power Points =
  POW, core powers are always-on or at-will and free, **Boosts** cost Power
  Points, **Limits** are disadvantages that buy more of both.

Everything this world has that Classic Fantasy has no entry for is a power:
Magda's rage, the binding school, the wild-elf line, the Order's rites. This is
not a workaround. Those things were never spells — none of them is one Action,
one Cost and one target — and writing them as spells is what made them keep
drifting.

## Why it is drawn here

The rules we may publish are the ORC ones: Mythras Imperative and Classic
Fantasy Imperative. Berserker and Druid are full Classic Fantasy and are not
ours to ship. Built as powers on the Mythras chassis, they are **ours** — the
mechanics underneath are ORC, and the thing built on them is Reserved Material,
like Purewater itself.

## How to rule one at the table

1. **Core powers are free and need no roll to have.** Using one in a contested
   way rolls the skill it leans on — Willpower, Perception, Endurance — never a
   casting skill. A power is not cast and cannot be Counterspelled or Dispelled.
2. **Boosts cost Power Points** and are declared before the roll. Power Points
   are a separate pool from Magic Points: **POW, recovering 1 per minute of
   rest**, or a Luck Point for 1d4+1 at once. A caster who is out of Magic
   Points still has their powers.
3. **Limits are the price and they must bite.** A Limit that never costs the
   character anything in play is not a Limit, and the power it paid for should
   come off the sheet.
4. **Rites are powers with `Limited Power`.** They are not cast in an Action.
   They need the place, the people and the time named in their own entry, and
   without those they do not happen at all — which is why a High Priestess is
   formidable in her temple and an ordinary woman on a dredge-boat.

## The registry

`spell_registry.json` lists every spell name on every sheet, what it resolves
to, and whether we may publish it. `scripts/build_spell_registry.py --strict`
fails when a sheet names something with no rule behind it. A power that is not
written down here is the same bug as a spell that is not in the book.
