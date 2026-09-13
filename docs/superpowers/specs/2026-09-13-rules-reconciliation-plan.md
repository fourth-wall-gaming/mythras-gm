# Reconciling the rules — plan

## The problem in one line

The game is played on **Classic Fantasy**, and only **Classic Fantasy
Imperative** is ours to redistribute.

## The licence boundary

Three populations, and they must stop being stored the same way.

| | what it is | may we republish? |
|---|---|---|
| **ORC** | Mythras Imperative SRD, CFI SRD — both vendored, both ORC licensed | **Yes**, with the ORC notice. Share-alike applies to mechanics we publish. |
| **Full Classic Fantasy** | the commercial book: Berserker, Druid, Paladin, Ranger, Bard, Monk, their rank tables and spell lists | **No.** Not ORC. We may *play* it from a book we own; we may not ship it. |
| **Ours** | Purewater, its people, the binding school, the wild-elf line, the Order's rites | Yes — Reserved Material, ours to keep. |

**What CFI actually contains:** four classes (Cleric, Fighter, Magic-User,
Rogue), two spell lists (Cleric, Mage), 143 spells, and Barbarian as a
**culture**. Berserker appears once, inside an example sentence about race/class
flexibility, with no write-up. Druid appears zero times.

**So both PCs sit outside it.** Magda is a barbarian berserker — the culture is
CFI, the class is not. Gardwen is a druid with a druid spell list (Barkskin,
Entangle, Animal Friendship, Slow Poison), none of which is in CFI.

This is not a legal opinion. It is the prudent reading, and the repo is public.

## What to do about the two characters

Three options, cheapest first. **This is the one decision I cannot make alone**,
because it changes two player characters.

1. **Rebuild on CFI classes.** Magda becomes a Fighter of Barbarian culture with
   a Berserk *passion* driving Rage rather than a class feature; Gardwen becomes
   a Cleric of a woodland faith whose spell list is drawn from CFI's cleric list
   plus our own woodland spells. Cheapest to ship, and both characters survive
   in play almost unchanged, because what makes them is the passions and the
   cards, not the class label.
2. **Keep the builds, ship nothing.** Mark both sheets `licence: private` and
   exclude them from the published package. The game runs; the repo carries a
   hole where two PCs should be.
3. **Reimplement in our own words.** Write our own berserker and druid rules
   from Mythras Imperative mechanics, sharing no CFI text. Legitimate, most
   work, and the result is ours.

**Recommendation: 1.** It removes the problem rather than managing it, and the
characters lose nothing a player would notice.

## The spell audit, and the three populations in it

78 real spell names are in play. CFI covers 30. The other 48 are not one thing:

- **Renames of CFI spells.** `flaming hands` is CFI's **Burning Hands**;
  `charm being` is **Charm Person/Monster**; `illusion, lesser` and
  `audible illusion` look like relabelled CFI entries. These need mapping, not
  writing — we are otherwise inventing rules that already exist.
- **Ours already.** The binding school (`open the channel`, `seat the bound`,
  `reinforce the seat`, `draw forth`) and the wild-elf line (`spirit sight`,
  `speak with the bound`, `unseat`) are in the rules graph and are Reserved
  Material. Correct as they stand.
- **Full Classic Fantasy.** Druid spells with no CFI equivalent. These follow
  whichever option is chosen above.
- **Not spells at all.** Prose leaked into the `spells` field — Nerissa carries
  *"Exhort 80 — she can ask the Lady for things outside the spell list"* and
  *"the Drowning is not expertise and must never be played as such…"* as if they
  were spell names. They can never resolve and they corrupt every audit.

## Order of work

1. **Separate the prose out of `spells`.** Pure data cleaning, no decisions.
   Those lines are GM notes and belong in `actor_notes`. Do this first, because
   every count below is wrong until it is done.
2. **Map the renames to CFI.** Produce an explicit alias table, checked in, so
   `flaming hands → Burning Hands` is recorded rather than rediscovered.
3. **Classify every remaining spell** as `orc` / `ours` / `full-cf`, as a field
   on the rule, not as a guess made at the table.
4. **Decide the character question** (above). Then apply it.
5. **Ingest CFI into the rules graph** — classes, both spell lists, magic
   chapter — so that `query-rules` answers a spell lookup instead of returning
   nothing and inviting me to improvise. This is the fix for the actual failure:
   Command was ruled 1 MP for a scene when the book says Cost 3 for one Turn.
6. **Record the house rules that already exist**, explicitly, as house rules:
   - casting rolls on **Piety 87 / Channel 85**, where Mythras says
     **Magic (POW+CHA)** — which for Gardwen would be 32. That is a very large
     house rule and no file records it as a decision.
   - petty-magic conventions carried over from earlier runs.
7. **Add the guardrail.** A check that fails when a character sheet references a
   spell with no rule behind it. The whole failure chain here — 71 uncovered
   spells, a ruling invented from analogy — was invisible because nothing ever
   compared the sheets to the rulebook.

## Not in scope

- Re-ingesting Mythras Imperative; the existing 112 rules are from it and are
  fine.
- Rewriting any vendored file. They are upstream copies and stay verbatim.
