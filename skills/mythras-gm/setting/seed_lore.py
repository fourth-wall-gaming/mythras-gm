#!/usr/bin/env python3
"""
seed_lore.py -- load the Veilwrack worldbuilding into TypeDB as myth-lore.

Slices the setting markdown files into categorized lore entries (plus a few
synthesized ones) and inserts them via the mythras_gm CLI. Run AFTER
seed_veilwrack.sh, from the repo root:

    python skills/mythras-gm/setting/seed_lore.py --campaign <campaign-id>

Generic pattern: any campaign can do the same -- write worldbuilding docs,
slice them into lore entries by category, and the GM agent retrieves them
with list-lore / get-lore during play.
"""

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
CLI = os.path.join(HERE, "..", "mythras_gm.py")


def section(path, header):
    """Return the markdown section starting at `## header` (exclusive of the
    next ## heading)."""
    text = open(os.path.join(HERE, path)).read()
    pattern = rf"^## {re.escape(header)}.*?(?=^## |\Z)"
    m = re.search(pattern, text, re.M | re.S)
    if not m:
        raise SystemExit(f"Section '## {header}' not found in {path}")
    return m.group(0).strip()


def whole(path):
    return open(os.path.join(HERE, path)).read().strip()


def section_until(path, header, stop):
    """Section starting at `## header`, truncated before `stop` marker."""
    text = section(path, header)
    return text.split(stop)[0].strip()


def subsection(path, header, start):
    """The trailing part of a section from the `start` marker onward."""
    text = section(path, header)
    idx = text.find(start)
    if idx < 0:
        raise SystemExit(f"Marker '{start}' not found in section '{header}' of {path}")
    return text[idx:].strip()


ANATOMY = """## Alar Anatomy and Body Plan

The Alar are winged humanoids with a six-limbed body plan: two legs, two
arms, AND two wings (the angel configuration, not the harpy one -- arms and
wings are separate limbs, so an Alar can fight, craft, and carry while
flying).

Layout, top to bottom: a beaked, keen-eyed head; two large shoulder-mounted
wings rising from the upper back above and behind the arms; two fully
functional arms with hands; a keeled chest anchoring the flight muscle; an
abdomen; and two legs ending in clawed feet that grip and climb bone-stone
at full walking speed.

Combat consequences (avian hit location table, 1d20): 1-2 R Leg, 3-4 L Leg,
5-7 Abdomen, 8-10 Chest, 11-12 R Wing, 13-14 L Wing, 15-16 R Arm,
17-18 L Arm, 19-20 Head. Nine locations versus a human's seven. Wings are
the great tactical vulnerability: a Serious Wound to a wing (failed
Endurance contest) means no flight and triggers Grounded Dread; a Major
Wound to a wing while airborne is usually fatal at altitude. Armor doctrine
follows the anatomy: torso and head only, wings always bare.

Physique: hollow-boned and slight (SIZ -3, DEX +2 vs human baseline);
knockback against an Alar is doubled; a Flight roll halves falling distance
(arrests it entirely on a critical). Kindred variation: Vael slightest and
fastest, Roak middle-built, Ossuin +2 SIZ -- big heavy gliders built for the
long descent."""

ENTRIES = [
    # (title, category, visibility, summary, content)
    ("The World of the Veilwrack", "cosmology", "player",
     "No ground; an endless sky over the Undermist. Civilization lives on Spires: floating husks of dead sky-leviathans. The wind (the Breath) is alive.",
     section("veilwrack.md", "The World")),
    ("Alar Anatomy and Body Plan", "species", "player",
     "Six-limbed winged humanoids: legs, arms, AND wings. Nine hit locations; wings are the tactical vulnerability; armor torso-and-head only.",
     ANATOMY),
    ("The Three Kindreds", "culture", "player",
     "Vael (kestrel couriers, Nomadic), Roak (corvid archivists, Civilized), Ossuin (condor death-priests, Barbarian) - and what each believes the Breath is.",
     section("veilwrack.md", "The Alar")),
    ("The Stilling", "threat", "player",
     "Spreading zones of dead air: flight fails, sound dies, Windworking stops, spires sink. Home of Stillwights and the Hushed.",
     section("veilwrack.md", "The Threat: The Stilling")),
    ("Factions of the Veilwrack", "factions", "player",
     "Gale Wardens, Spirarchy, Quillate, Hushed Choir, Marrowers - what each wants and what each knows.",
     section("veilwrack.md", "Factions")),
    ("Key Locations", "geography", "player",
     "Suruveil's Crown, the Moult, Greywake, the Windlanes, the Spire-roots.",
     section("veilwrack.md", "Key Locations")),
    ("Alar Racial Abilities", "species", "player",
     "Wings, hollow bones, keen eyes, Grounded Dread, no swimmers; kindred bonuses.",
     section("alar-options.md", "Alar Racial Abilities (all kindreds)")),
    ("Careers of the Veilwrack", "careers", "player",
     "Ten setting careers in SRD format: Lane Courier, Gale Warden, Quill, Wind-Pilot, Death-Diver, Marrow-Miner, Shrine-Cantor, Windworker, Crown Agent.",
     section("alar-options.md", "Careers")),
    ("Windworking", "magic-system", "player",
     "The Alar magic = the SRD Magic system (POW+CHA, MP-by-roll-result, traits). 17 adapted SRD spells + 10 originals. Dead in Stillings; MP recovers only in living wind.",
     section_until("alar-options.md", "Windworking (Magic)",
                   "### Powers (the SRD superpower framework)")),
    ("Powers of the Touched", "magic-system", "gm",
     "GM only: the SRD superpowers framework builds the Hushed (Life Support + Silence Aura, heavily Limited) and the leviathan-touched finale option.",
     subsection("alar-options.md", "Windworking (Magic)",
                "### Powers (the SRD superpower framework)")),
    ("Mythras Magic and Powers Rules", "rules-reference", "player",
     "Setting-agnostic SRD reference: Magic casting economy, spell traits, full SRD spell list, and the Superpowers build framework.",
     open(os.path.join(HERE, "..", "rules", "magic.md")).read().strip()),
    ("Combat Styles and Traits", "house-rules", "player",
     "Six named Veilwrack combat styles with SRD traits (Warden Skirmisher, Courier's Defense, Stoopwing...).",
     section("alar-options.md", "Combat Style Traits (Veilwrack styles)")),
    ("Aerial Movement Rules", "house-rules", "player",
     "Fly gaits (12/36/60m), hover and glide, altitude bands, carrying aloft, armor limits, aerial engagement (Tumble, sinking melee).",
     section("alar-options.md", "Movement & Aerial Rules")),
    ("Currency and Gear", "economy", "player",
     "Lacquer-scrip, lane-favors, mist-pearls; breath-bottles, still-gauges, kite-rigs and other setting equipment.",
     section("alar-options.md", "Equipment & Currency")),
    ("Bestiary of the Veilwrack", "bestiary", "gm",
     "Full stat blocks and tactics: Hushed Alar, Stillwight, Sky-Drake, Marrower Bravo, Warden Skirmisher.",
     whole("bestiary.md")),
    ("GM Secrets: The Truth, the Arc, the NPCs", "gm-secret", "gm",
     "Why the wind is dying, the Founding Compact, the Quieting, the Unsung, the five-act campaign arc, and the NPC quick list. NEVER reveal directly.",
     whole("gm-secrets.md")),

    # --- The expanded worldbook (added 1001 A.S. edition) -------------------
    # Geography & politics
    ("The Shape of the World: Altitude Bands", "geography", "player",
     "The five altitude bands - Glare, Reach, Shade, Root-Dark, Undermist - and the charted lanes vs the open Wrack.",
     section("geography.md", "The Shape of the World")),
    ("The Great Polities", "politics", "player",
     "Crown Dominion, the Moult, Carrowspar Synod, Veyl Reefs, Brightgyre Compact - governments, rulers, and how each holds power.",
     section("geography.md", "The Great Polities")),
    ("Lesser Powers and Places", "geography", "player",
     "Lanternfall, Greywake, the Spindles, Hollow Vesse, and the lane-shrine network.",
     section("geography.md", "Lesser Powers and Places")),
    ("How Power Works in the Veilwrack", "politics", "player",
     "The four currencies of power: lift, lanes, the Record, and the funeral right.",
     section("geography.md", "How Power Actually Works")),
    ("Distances and Travel", "geography", "player",
     "Wind-days, the major routes table, off-lane and night flying, cargo barges.",
     section("geography.md", "Distances and Travel")),
    # History
    ("A History of the Veilwrack", "history", "player",
     "The full chronicle 0-1001 A.S.: the Elder Sky, the Hole in the Record, the Settling, Charter Wars, Marrow Rush, Long Calm, Stilling Age - plus the Skeptic's Chronology.",
     whole("history.md")),
    # Upbringings (character background catechisms)
    ("What My Mother Told Me (Vael)", "upbringing", "player",
     "The Vael childhood catechism: the herd, the hoofprints of the dead, why we carry, how to regard the other kindreds.",
     section("upbringings.md", "What My Mother Told Me (a Vael childhood, the Moult)")),
    ("What My Father Told Me (Roak)", "upbringing", "player",
     "The Roak childhood catechism: the missing first pages, nothing recorded is wholly dead, completing the Record.",
     section("upbringings.md", "What My Father Told Me (a Roak childhood, Suruveil's Crown)")),
    ("What My Priest Told Me (Ossuin)", "upbringing", "player",
     "The Ossuin childhood catechism: the world as exhalation, death as installment, keeping the door.",
     section("upbringings.md", "What My Priest Told Me (an Ossuin childhood, Carrowspar)")),
    ("What My Chief Told Me (the Roostless)", "upbringing", "player",
     "The Spindles childhood catechism: a secondhand world, the Thread-book, catching what falls.",
     section("upbringings.md", "What My Chief Told Me (a Spindles childhood, the roostless)")),
    # Organizations (GM - each contains stated vs actual aims and hooks)
    ("Organization: The Gale Wardens", "organization", "gm",
     "PC patron org: ranks Tail to Warden-Marshal, benefits, the Acceleration Map, the Causists.",
     section("organizations.md", "1. The Gale Wardens")),
    ("Organization: The Spirarchy and Crown Agents", "organization", "gm",
     "The state church and its secret service: ranks, benefits, what Velute actually protects.",
     section("organizations.md", "2. The Spirarchy of Suruveil's Crown (and the Crown Agents)")),
    ("Organization: The Quillate", "organization", "gm",
     "Archive-guild ranks and benefits; the deliberately cut hole; Orrocan's self-filling stacks.",
     section("organizations.md", "3. The Quillate")),
    ("Organization: The Deepway", "organization", "gm",
     "The funeral order: ranks, universal safe-conduct, and the real reason diving stopped.",
     section("organizations.md", "4. The Deepway (the Ossuin priesthood)")),
    ("Organization: The Lane-Shrine Cantorate", "organization", "gm",
     "The windlane religion: shrine neutrality, and the lane-songs as a 900-year record of the Breath's decline.",
     section("organizations.md", "5. The Lane-Shrine Cantorate")),
    ("Organization: The Marrower Combine", "organization", "gm",
     "The lift cartel: ranks, the burned sink-data, Brell Coinfeather's insurance copy.",
     section("organizations.md", "6. The Marrower Combine")),
    ("Organization: The Hushed Choir", "organization", "gm",
     "The Stilling cult: outer creed, the Sotto Voce's two practical secrets, ranks to the Quieted.",
     section("organizations.md", "7. The Hushed Choir")),
    ("Organization: The Featherwrights' Guild", "organization", "gm",
     "The artisan league: wing-surgeons, the Fallen Fund, and the actuarial tables that know too much.",
     section("organizations.md", "8. The Featherwrights' Benevolent Guild")),
    ("Using Organizations in Play", "organization", "gm",
     "GM guidance: memberships at creation, rank advancement as story, benefits with handles, cross-loyalties.",
     section("organizations.md", "Using Organizations in Play")),
    # Antagonists (GM)
    ("Antagonists and Opposition Structure", "gm-guide", "gm",
     "Five opposition tiers (world, predators, human, institutional, mythic), recurring villains, clocks, and the rules for running adversity.",
     whole("antagonists.md")),
    # Natural philosophy
    ("Natural Philosophy: The Quillate Consensus", "natural-philosophy", "player",
     "The plausible physics: the planet, buoyant bone, the Undermist, and the Vital Circulation Hypothesis - the one biological miracle.",
     section("natural-philosophy.md", "The Quillate Consensus (player-facing)")),
    ("Natural Philosophy: GM Appendix", "natural-philosophy", "gm",
     "GM only: closing the loop between the Vital Circulation Hypothesis and the campaign secret; rulings stance.",
     section("natural-philosophy.md", "GM Appendix: closing the loop (GM only)")),
    # Daily life
    ("The Calendar and the Festivals", "daily-life", "player",
     "Four wind-seasons, the nine-day week, First Lift, Tanksfull, the Patching, Lastlight, millennium dread.",
     section("life-aloft.md", "The Calendar and the Festivals")),
    ("Alar Names", "daily-life", "player",
     "Naming customs of the Vael, Roak, Ossuin, and the roostless.",
     section("life-aloft.md", "Names")),
    ("Law and Justice", "daily-life", "player",
     "Sky Law and the three fall-crimes; Crown, Moult, and Reef legal cultures.",
     section("life-aloft.md", "Law and Justice")),
    ("Money and Daily Economy", "daily-life", "player",
     "Lacquer-scrip, lane-favors, mist-pearls; wages, prices, and what people actually eat.",
     section("life-aloft.md", "Money and Daily Economy")),
    ("Living on a Spire", "daily-life", "player",
     "The vertical city: crown to root-line, flight-wells, roosts, and who sleeps where.",
     section("life-aloft.md", "Living on a Spire")),
    ("Etiquette Worth Knowing", "daily-life", "player",
     "Greetings, gifts of lift, primaries, singing, speaking of the dead, and 'may your air move'.",
     section("life-aloft.md", "Etiquette Worth Knowing")),
    ("Rumors Current in 1001 A.S.", "gm-guide", "gm",
     "Six table-ready rumors with true/false annotations for the GM.",
     section("life-aloft.md", "Rumors Current in 1001 A.S. (table seed)")),
    # Character creation
    ("Character Creation and Roleplay Guide", "character-creation", "player",
     "The full table procedure: concept, characteristics, culture, career, combat style, Windworking, organizations, passions, roleplay guidelines, development, and company frames.",
     whole("character-creation.md")),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", required=True)
    args = ap.parse_args()

    # Idempotency: skip entries whose title already exists in the campaign.
    res = subprocess.run(
        [sys.executable, CLI, "list-lore", "--campaign", args.campaign],
        capture_output=True, text=True)
    try:
        existing_payload = json.loads(res.stdout.strip().splitlines()[-1])
        existing = {e["title"] for e in existing_payload.get("lore", [])}
    except Exception:
        print(f"FAILED to list existing lore:\n{res.stdout}\n{res.stderr}",
              file=sys.stderr)
        sys.exit(1)

    skipped = 0
    for title, category, visibility, summary, content in ENTRIES:
        if title in existing:
            skipped += 1
            print(f"  = (exists) {title}")
            continue
        cmd = [sys.executable, CLI, "add-lore",
               "--campaign", args.campaign,
               "--title", title,
               "--category", category,
               "--visibility", visibility,
               "--summary", summary,
               "--narrative", content]
        res = subprocess.run(cmd, capture_output=True, text=True)
        try:
            payload = json.loads(res.stdout.strip().splitlines()[-1])
        except Exception:
            print(f"FAILED: {title}\n{res.stdout}\n{res.stderr}", file=sys.stderr)
            sys.exit(1)
        if not payload.get("success"):
            print(f"FAILED: {title}: {payload}", file=sys.stderr)
            sys.exit(1)
        print(f"  + [{category}/{visibility}] {title} -> {payload['id']}")
    print(f"Lore seeding complete ({skipped} already present, skipped).")


if __name__ == "__main__":
    main()
