# Vendored rulebooks — the canonical ruleset

This game runs on **Mythras Imperative** plus **Classic Fantasy Imperative**.
Both are vendored here verbatim so that every ruling has a source in the repo
rather than in my recollection of a book I have not read.

| | source | pinned at |
|---|---|---|
| `mythras-srd/` | https://github.com/raleel/mythras-srd | `1b802fe` |
| `cfi-srd/` | https://github.com/raleel/cfi-srd | `be7fd58` |

Only `rules/en` is vendored — upstream carries fifty localisations and we need
one. `LICENSE` and `COMMIT` travel with each.

## Why this is here

The rules graph (`skills/mythras-gm/rules/`, 112 entries) was built from the
Mythras Imperative SRD alone and contains **no Classic Fantasy content at all**.
An audit of the live campaign found **20 of 91 spells in play had a rule**; the
other 71, including every cleric and druid spell on every sheet, did not exist
in the graph.

The failure mode that produced this file: asked to cast *Command*, I searched
the graph, found nothing, reasoned by analogy from Befuddle, and ruled it as
1 MP with a scene-long effect. The actual rule (`cfi-srd/rules-en/0010_Spells.md`)
is **Cost 3, Duration 1 Minute, Range 100 ft, Resist Willpower**, and it is a
single word obeyed for a single Turn. Improvising against a missing rulebook
does not read as improvisation; it reads as the rules.

## Licence

Both are published under the **ORC License**, which explicitly permits use,
adaptation and redistribution — including by AI — and requires attribution.
Full text in each directory's `LICENSE`.

> _Mythras Imperative_ is licensed under the ORC License, held at the Library of
> Congress and available online, including at
> [Paizo.com](https://paizo.com/community/blog/v5748dyo6sico).
>
> _Classic Fantasy Imperative_ is licensed under the ORC License on the same
> terms.

ORC's share-alike applies to game mechanics we publish downstream. World lore,
story arcs and characters — Purewater, the Baron, the campaign — are Reserved
Material and remain ours.

## Do not edit these files

They are upstream copies. House rules and setting spells belong in the rules
graph, marked as house rules, so that the difference between *the book says* and
*we decided* stays visible.
