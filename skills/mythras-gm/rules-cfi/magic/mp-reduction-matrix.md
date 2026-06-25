---
id: "cfi/magic/mp-reduction-matrix"
title: "Magic Point Reduction Matrix (Caster Rank vs Spell Rank)"
system: "classic-fantasy"
category: "magic"
domain: "magic"
topic: "casting-procedure"
kind: "table"
summary: "For each Rank above 1, a caster reduces the final MP cost of lower-Rank spells by 2 MP per Rank of difference, to a minimum of 1."
facets: {"magic-system": ["arcane", "divine"], "kind": ["table"]}
links: ["cfi/magic/casting-cost", "cfi/magic/casting-cost-reduction"]
---

Higher-Rank casters channel magical energy more efficiently. For each Rank above 1, reduce the **final** Casting Cost of a lower-Rank spell by 2 MP per Rank of difference. This reduction applies to the total cost, not per Intensity. Minimum final cost: 1 MP.

**MP Reduction Matrix** (rows = Caster Rank, columns = Spell Rank):

| Caster \\ Spell | Rank 1 | Rank 2 | Rank 3 | Rank 4 | Rank 5 |
| :-: | :-: | :-: | :-: | :-: | :-: |
| Rank 1 | 0 | -- | -- | -- | -- |
| Rank 2 | -2 | 0 | -- | -- | -- |
| Rank 3 | -4 | -2 | 0 | -- | -- |
| Rank 4 | -6 | -4 | -2 | 0 | -- |
| Rank 5 | -8 | -6 | -4 | -2 | 0 |

Example: A Rank 3 caster casting a Rank 1 spell reduces the final cost by 4 MP.
