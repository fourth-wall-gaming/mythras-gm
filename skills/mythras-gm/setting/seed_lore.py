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
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", required=True)
    args = ap.parse_args()

    for title, category, visibility, summary, content in ENTRIES:
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
    print("Lore seeding complete.")


if __name__ == "__main__":
    main()
