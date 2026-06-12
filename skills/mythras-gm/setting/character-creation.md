# CHARACTER CREATION & ROLEPLAY GUIDE
### Making an Alar of the Veilwrack (Mythras Imperative)

*A complete table procedure. Mechanics follow the Mythras Imperative SRD
with the Veilwrack adaptations from alar-options.md; this document is the
player-facing walkthrough plus the roleplay layer — passions, upbringing,
and development.*

---

## Step 0 — Concept, in one sentence

Before dice: *"A ___ from ___ who wants ___ and fears ___."* The setting
pulls hardest on characters with (a) a reason to fly toward trouble and
(b) someone or somewhere they cannot bear to lose. The Gale Wardens are the
default frame — assume your character has just joined, or is about to.

With the GM, pick your **upbringing** and read your page of
upbringings.md ("What my Mother/Father/Priest/Chief told me"). That
document is what your character *believes*. You start the campaign inside
one of those four worldviews; the campaign is partly about what happens
to it.

## Step 1 — Characteristics

Roll STR, CON, DEX, POW, CHA on **3d6**; INT and SIZ on **2d6+6** (or
point-build by table agreement). Then apply the Alar frame: **SIZ −3
(minimum 4), DEX +2.**

Kindred adjustments and bonus (choose one kindred):

| Kindred | Adjustment | Kindred bonus |
|---|---|---|
| **Vael** (kestrel-kin) | −1 SIZ further, +1 DEX | +5 to one DEX-based skill |
| **Roak** (corvid-kin) | — | +5 to one INT-based skill |
| **Ossuin** (condor-kin) | +2 SIZ | +5 Endurance **or** Willpower |

Derive attributes as standard Mythras (the CLI does this automatically:
`create-character --roll` or `--stats`): Action Points, Damage Modifier,
Experience Modifier, Healing Rate, Luck Points, Magic Points = POW,
Initiative Bonus. Movement: **4m walking / 12m flying** (see Aerial
Movement rules for gaits, altitude, and carrying).

## Step 2 — Culture

Your culture is *where* you fledged, not your kindred (a Roak raised on
the Moult is Nomadic). It sets your Standard-skill bonuses and Professional
options per the SRD:

- **Nomadic** (the Moult, courier families, gleaner-bands)
- **Civilized** (Suruveil's Crown, Brightgyre, the big spire-towns)
- **Barbarian** (Carrowspar, the lesser roosts, the Spindles, the Reefs)

Spend **100 points** among your cultural skills (max +15 to any one at
creation). Every Alar culture includes **Flight (STR+DEX)** as a Standard
skill. No Alar culture grants Swim.

## Step 3 — Career

Spend **100 points** among your career skills (same +15 cap). The ten
setting careers are in alar-options.md — Lane Courier, Gale Warden, Quill,
Wind-Pilot, Death-Diver, Marrow-Miner, Shrine-Cantor, Windworker, Crown
Agent, and the SRD's generic careers re-skinned freely. Your career also
hands you a starting organization membership (Step 6) and your kit.

## Step 4 — Bonus points & combat style

Spend **150 bonus points** anywhere (career, culture, or any Standard
skill; same cap), **or** use the Skill Pyramid for a more dramatic spread:
one skill +50, two +40, three +30, four +20, five +10.

Take **one combat style** at STR+DEX, improved like any skill. Pick from
the six Veilwrack styles in alar-options.md (each carries an SRD trait —
e.g. *Warden Skirmisher* for sky-rescue fighting, *Stoopwing* for diving
attacks) or name your own with the GM and pick a fitting trait. Equipment
per career: bone, horn, lacquer, and sinew weapons are standard; steel is
heirloom-tier; armor is torso-and-head only (wings are always bare — see
the anatomy lore).

## Step 5 — Windworking (optional)

If your concept is a Windworker, take the **Magic (POW+CHA)** Professional
skill via culture/career/bonus points and roll **1d4+1 starting spells**
from the Windworking list (alar-options.md). Casting economy, traits, and
learning rules are the SRD Magic system (rules/magic.md). Remember the two
setting facts every Windworker knows in their feathers: the Breath answers
*slowly* these days — and in a Stilling it does not answer at all.

## Step 6 — Organization

Choose one membership at entry rank from organizations.md (Gale Wardens,
Quillate, Deepway lay-bearer, Cantorate wick, Featherwrights, Combine,
even — bravely — the Choir's outer ring). Write down: your rank, your
sponsor's name (make one up with the GM), and **one thing the organization
expects of you that you'd rather it didn't.**

## Step 7 — Passions

Take **three passions**: one at 40+POW+CHA, one at 30+POW+CHA, one at
20+POW+CHA. Passions augment skills (+1/5th of the passion, via the CLI's
`--augment`), can be rolled to resist compulsion or temptation, and are
the GM's invitation list for your subplots. Build each from a different
row:

| Row | Pattern | Veilwrack examples |
|---|---|---|
| **Loyalty** (person/company) | Loyalty to ___ | wing-sister; Commander Esk; my stair-cohort; the rafts of my mother's tether |
| **Love/Protect** (place/people) | Protect ___ | Lanternfall's lamp-children; the Spindles nets; my home shrine; the Moult |
| **Duty/Creed** (belief) | Uphold ___ | the lane-songs; the funeral right; the completeness of the Record; the guild oath ("no one falls") |
| **Hate/Fear** (shadow) | Hate/Fear ___ | the still air; the Combine; tether-cutters; what my lineage is hiding |
| **Yearning** (want) | ___ | to kiss the Glare; to read the sealed stacks; to hear what the divers heard; a deed-name worth keeping |

**Rule of thumb:** at least one passion that binds you to another PC or to
the company, and at least one that will someday point *against* the
mission. The campaign's decision points are built to pull passions in two
directions; a character whose passions can't conflict is a character the
finale can't reach.

## Step 8 — Finishing touches

- **Backstory:** answer your upbringing-page's four questions *in your own
  character's words* — one paragraph total is plenty. Give the GM one name
  from your past (kin, rival, debt) — it will come back.
- **The keepsake:** every Alar carries one object that doesn't appear on
  any equipment list. Name it. (A primary feather from a dead sister; a
  lane-favor chit, uncashed for nine years; a mist-pearl you shouldn't
  have.)
- **Persist it:** the GM records the finished character with
  `create-character --campaign <id> --narrative "<backstory>"` — the
  narrative field is your save file; write it like you'll want it back in
  six months, because you will.

## Roleplay Guidelines

- **Fly like it costs something.** Flight is freedom, fatigue, and risk in
  one. Say *how* you fly — riding the well, stooping, laboring under cargo
  — and watch your Fatigue.
- **Grounded is vulnerable.** An Alar with a wounded wing plays it like a
  sighted person gone blind: Grounded Dread is in the racial abilities for
  a reason. Don't shrug it off; mine it.
- **Sound is safety.** Alar culture is loud — drumming roosts, sung
  schedules, whistled right-of-way. Quiet places make your character's
  hackles rise *before* the player knows why. Use that instinct; it is
  usually right.
- **Believe your catechism.** Play your upbringing's answers as true until
  the world breaks them. The campaign's revelations land hardest on
  characters who genuinely believed their mother.
- **Honor the three irreversibilities.** Wing-loss, the Long Drop, and the
  Quieting are the setting's permanent stakes. The table should treat all
  three with table-wide gravity — no comedy Quieting, ever.

## Development & Downtime

Experience Rolls per the SRD (typically 1–3 per session; the CLI tracks
them). Between sessions, downtime maps to the setting:

- **Training** with your organization (◆ skills cheaper; new spells need a
  teacher, 3 Experience Rolls, and a week).
- **The Patching** (Long Calm season): repair gear, mend relationships,
  raise a passion by 1d10 if you spent the season honoring it — or lower
  one you betrayed.
- **Rank advancement** when the fiction supports it (see organizations.md
  — promotions are story events, not purchases).
- **Wealth** arrives as scrip, favors, and obligations, rarely as
  treasure. The best loot in the Veilwrack is *access*: a chart, a
  witness-mark, a song, a name.

## Sample Company Frames (pick one, or improvise)

1. **The Lanternfall Draft** (default): you are the Warden flight assigned
   to the dying lane — a courier, a fighter, a healer/priest, a scholar or
   Windworker. Built-in patron, mission, and first session.
2. **The Survey:** a Quillate-funded mixed company re-charting a retired
   lane that has started, impossibly, to sing again.
3. **The Bier-Party:** Deepway lay-bearers and hired wings carrying an
   important body to Carrowspar — through pirate sky, with something in
   the wax that three factions want.
