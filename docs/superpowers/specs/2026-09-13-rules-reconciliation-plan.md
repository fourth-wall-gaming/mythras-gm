# Reconciling the rules — plan

> **Status: done.** All seven steps. The decision on step 4 was made by the
> player and it was not one of the three options I offered — see **The
> architecture** below. Three claims in the original plan turned out to be wrong
> when checked against the books; all three are corrected and marked.
>
> **Every spell on every sheet is now ORC and has a rule behind it.** 51 spells,
> 6 powers, nothing outstanding.

## The problem in one line

The game is played on **Classic Fantasy**, and only **Classic Fantasy
Imperative** is ours to redistribute.

## The licence boundary

| | what it is | may we republish? |
|---|---|---|
| **ORC** | Mythras Imperative SRD, CFI SRD — both vendored, both ORC licensed. **CFI for spells, Mythras for powers.** | **Yes**, with the ORC notice. Share-alike applies to mechanics we publish. |
| **Full Classic Fantasy** | the commercial book: Berserker, Druid, Paladin, Ranger, Bard, Monk, their rank tables and spell lists | **No.** Not ORC. We may *play* it from a book we own; we may not ship it. |
| **Full Mythras** | the commercial book — corrected, see below | **No.** Same terms. |
| **Ours** | Purewater, its people, the binding school, the wild-elf line, the Order's rites, Piety-as-devotion | Yes — Reserved Material, ours to keep. |

**What CFI actually contains:** four classes (Cleric, Fighter, Magic-User,
Rogue), two spell lists (Cleric, Mage), 143 spells, and Barbarian as a
**culture**. Berserker appears once, inside an example sentence about race/class
flexibility, with no write-up. Druid appears zero times.

**So both PCs sit outside it.** Magda is a barbarian berserker — the culture is
CFI, the class is not. Gardwen's sheet already reads `class: Cleric`, but four
of her spells (Animal Friendship, Barkskin, Entangle, and Know Passions under
that name) are druid, and CFI has no trace of them.

**Correction — there is a third book, not two.** The plan assumed everything
outside CFI was full Classic Fantasy. It is not. Babble, Mimic, Incognito and
MindSpeech are **full Mythras** folk magic — beyond the Imperative's
twenty-four, and just as much not ours. They are on Conall's sheet.

This is not a legal opinion. It is the prudent reading, and the repo is public.

## The architecture (this is the decision)

I offered three options. The answer was a fourth and a better one, and it
resolves the whole class of problem rather than the two characters:

> **CFI is the base. Magic and spells resolve through it, and no new spells are
> ever written. Mythras provides rules for Powers — use and extend those for
> everything not obvious in CFI.**

That covers Magda's rage, Hanzo's and Gardwen's spirit magic, and Nerissa's
ritual magic on the lake, and it is licence-clean by construction: the
Mythras power chassis is ORC, and what we build on it is ours. Written up as
`magic/powers/how-powers-work-here`.

**A spell is CFI. A power is Mythras. There is no third thing.** If a character
is described with a spell CFI does not list, either it is a CFI spell under
another name — check `spell_registry.json` — or it is not a spell.

### What that produced

| character | was | is |
|---|---|---|
| **Magda** | Berserker class features scattered across `extras.abilities`, including a free Action Point | **Berserk** and **Hel's Mark** as powers; Artful Dodger corrected to the real CFI ability |
| **Gardwen** | druid spells + nine woodland spells | CFI Cleric Rank 2 with access to the whole list; **The Wild Line** and **Woodwise** as powers |
| **Hanzo, Santo** | the binding school as seven spells at 1 MP each | **The Binding** — a six-step sequence with anchors and a morning reinforcement |
| **Nerissa, Lilura** | rites stored inside the `spells` field as prose | **The Rites of the Lady**, with Limited Power doing the work |
| **Conall, Hesper** | 15 spells from books we cannot ship | mapped to their CFI equivalents or dropped as duplicates |

The old three options, kept for the record:

1. **Rebuild on CFI classes.** Magda becomes a Fighter of Barbarian culture with
   a Berserk *passion* driving Rage rather than a class feature; Gardwen stays a
   Cleric and her four druid spells are rewritten as woodland spells of ours,
   alongside the wild-elf line already in the graph. Cheapest to ship, and both
   characters survive in play almost unchanged, because what makes them is the
   passions and the cards, not the class label.
2. **Keep the builds, ship nothing.** Mark both sheets `licence: private` and
   exclude them from the published package. The game runs; the repo carries a
   hole where two PCs should be.
3. **Reimplement in our own words.** Write our own berserker and druid rules
   from Mythras Imperative mechanics, sharing no CFI text. Legitimate, most
   work, and the result is ours.

None of them was taken, and the fourth answer is better than my recommendation
because it stops the problem recurring. The reason the binding school kept
drifting was never the licence — it was that none of those things is one Action,
one Cost and one target, and writing them as spells was fighting the format.

## The spell audit, as it actually came out

78 distinct spell names sit on character sheets. Counted against both vendored
SRDs and the rules graph:

| | count | |
|---|---|---|
| **ORC** | 45 | Mythras Imperative or CFI. Every one now has a rule. |
| **ours** | 9 | the binding school and the wild-elf line. **Now powers, not spells.** |
| **not ours** | 24 | 20 full Classic Fantasy, 4 full Mythras. All resolved — mapped, dropped, or folded into a power. |

**After the consolidation: 51 spell names, all ORC, plus 6 powers, all ours.**

The full table is `skills/mythras-gm/spell_registry.json`, generated by
`scripts/build_spell_registry.py`. Eleven of the 45 are the same spell under
another label and are recorded as aliases — `Flaming Hands → Burning Hands`,
`Charm Being → Charm Person`, `Purify Water → Purify Food and Drink`,
`Know Passions → Know Alignment`, and seven more.

## Order of work

1. ~~**Separate the prose out of `spells`.**~~ **Done.** Thirteen entries, all on
   Nerissa: her rites, her doctrine, and a note on why she is powerful, stored
   as if they were spell names. Moved to `extras`, with the part that changes how
   she is played added to her actor notes. Applied to the package and to the live
   campaign.
2. ~~**Map the renames to CFI.**~~ **Done.** Eleven aliases, each checked against
   the vendored text one at a time rather than guessed from the shape of the word.
3. ~~**Classify every remaining spell.**~~ **Done.** `source` and `licence` on
   every one of the 78, and a `licence` facet on every generated rule, so
   `query-rules --facet licence=orc` answers.
4. ~~**Decide the character question.**~~ **Done, and answered better than
   asked** — see the architecture above. Applied across all 41 characters by
   `scripts/consolidate_to_cfi.py`, which is kept as the record of what changed
   and why: 71 changes, every one with its reason on the line. The live campaign
   was updated alongside the package.

   **Balance was the brief, and the two calls worth naming:** Magda loses the
   free extra Action Point her sheet gave her — a free AP is the strongest thing
   in Mythras combat and no book grants it — and gains nothing back, because
   Berserk already carries her. Gardwen loses three druid spells and gains
   access to the entire CFI cleric list at Rank 2, which is a large net gain;
   her one core power against a budget of four is deliberate, since she is also
   a full caster.
5. ~~**Ingest CFI into the rules graph.**~~ **Done.** 143 spells and the 16
   sections of the magic chapter, generated by `scripts/ingest_cfi_spells.py`
   and `scripts/ingest_cfi_chapter.py`. The graph went from 112 rules to 271.
   `get-rule --id magic/cfi/spell-command` now answers with Cost 3, 1 Minute,
   100 ft, Resist Willpower. Classes are read from the vendored chapter as
   needed rather than ingested — every class in play (Cleric, Fighter,
   Magic-User) is already CFI, so there is nothing to convert.
6. ~~**Record the house rules.**~~ **Done — and there were none.** The premise
   was wrong twice over.

   The plan said casting on Piety 87 was a large house rule against Mythras's
   Magic (POW+CHA) = 32. Wrong book: the game runs **CFI** magic, where a cleric
   casts on **Channel (INT+CHA)**.

   Then I said Piety itself was outside both books, because it appears exactly
   once in the CFI SRD, inside the text of Spiritshield. Also wrong. CFI gives
   every cleric **two** professional skills — Channel *and* **Devotion
   (POW+CHA)**. Piety is our name for Devotion, and Nerissa's own sheet says so:
   *"Piety (Devotion) 92"*. Channel sets a spell's Intensity, Devotion sets its
   Magnitude. Both sheets now use the CFI names.

   The real contradiction was elsewhere and larger. Mythras Imperative makes
   every spell Intensity 1 on a fixed MP ladder; CFI scales Intensity to
   skill/10 and charges the spell's own Cost line, with nothing spent on a
   failure. Both books are in the graph; `magic/which-book` now says which
   governs and tabulates where they part.
7. ~~**Add the guardrail.**~~ **Done, and it is green.**
   `build_spell_registry.py --strict` exits non-zero when a sheet names a spell
   or a power with no rule behind it. It found 57 on the first run, 24 after the
   CFI ingest, and **0 now**. `tests/test_powers.py` holds the line: one test
   fails if any sheet ever again depends on a book we cannot ship, another if a
   name appears with no rule, and a third if the registry has drifted from the
   sheets.

## Not in scope

- Re-ingesting Mythras Imperative; the existing rules are from it and are fine.
- Rewriting any vendored file. They are upstream copies and stay verbatim.
