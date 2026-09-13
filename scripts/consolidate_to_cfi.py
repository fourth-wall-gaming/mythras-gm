#!/usr/bin/env python3
"""One-shot: put every character on CFI spells + Mythras powers, and nothing else.

CFI is the base and no new spells are written, so a name CFI does not carry is
either a CFI spell under another label, or it is not a spell -- it becomes a
power, or it comes off the sheet. Every call below is a judgement weighted to
preserving game balance, and the reason is on the line.

Run once. Kept for the record of what changed and why.
"""
import json, glob, os, sys

PKG = sys.argv[1] if len(sys.argv) > 1 else '/Users/gullyburns/purewater-campaign-v2'

# --- spells renamed to their CFI entry -------------------------------------
RENAME = {
    "Flaming Hands": "Burning Hands", "Charm Being": "Charm Person",
    "Illusion, Lesser": "Illusion", "Illusion Greater": "Illusion",
    "Invisibility, Lesser": "Invisibility",
    "Invisibility Radius": "Invisibility, 10 ft. Radius",
    "Arcane Lock": "Mage Lock", "Create Water": "Create Food and Water",
    "Purify Water": "Purify Food and Drink", "Know Passions": "Know Alignment",
    "Find": "Locate Object",
    # Not renames -- nearest CFI entry, chosen so nobody gains power.
    "Affect Normal Fires": "Ignite",        # Mage 0, as it always effectively was
    "Audible Illusion": "Magic Mouth",      # CFI Illusion is silent; this is the sound one
    "Babble": "Befuddle",                   # Rank 0 either way; garbled thought for garbled speech
    "Color Cascade": "Dancing Lights",
    "Friendship": "Glamour",                # Mage 0: alluring, grants nothing mechanical
    "Mage Hand": "Magic Tricks",            # Mage 0 cantrip, which is what it was being used as
    "Ray of Enfeeblement": "Slow",          # the debuff slot, at a Rank she can carry
    "Scrying Pool": "Wizard Sight",         # Mage 3 -- she is a spymaster and it is her whole method
    "Shocking Grasp": "Magic Missile",      # CFI has no touch-shock; same Rank, same job
    "Shocking Touch": "Magic Missile",
    "Suggestion": "Charm Person",
    "Barkskin": "Protection",               # Cleric 0, and she now has the whole Rank 0 list
    "Extinguish": "Dry",                    # Mage 0; not on the cleric list, see note
    "Find (X)": "Locate Object",
    "Vigor": "Might",                       # Cleric 0
    "Sanctuary": "Spiritshield",            # Cleric 0: deters spirits from entering. Same job, in the book
}

# --- names that come off the sheet, with the reason ------------------------
DROP = {
    "Animal Friendship": "power: Woodwise",
    "Entangle": "covered by Hold Person, which she has",
    "Counterspell": "covered by Dispel Magic, which she has",
    "Fog Cloud": "covered by Darkness, which she has",
    "Hypnotism": "covered by Charm Person, which he has",
    "Incognito": "covered by Change Appearance, which he has",
    "Mimic": "covered by Magic Mouth",
    "Ventriloquism": "covered by Magic Mouth",
    "Misdirection": "covered by Mirror Image, which she has",
    "MindSpeech": "no CFI equivalent; telepathy on a PC is too large a change",
    "Read Thoughts": "no CFI equivalent; mind-reading dissolves investigation scenes",
    "Water Walk": "power: The Rites of the Lady",
    "Spirit Sight": "power: The Wild Line / The Binding",
    "Speak with the Bound": "power: The Wild Line / The Binding",
    "Unseat": "power: The Wild Line",
    "Open the Channel": "power: The Binding",
    "Seat the Bound": "power: The Binding",
    "Reinforce the Seat": "power: The Binding",
    "Anchor": "power: The Binding",
    "Draw Forth": "power: The Binding",
}

# --- powers, by character name --------------------------------------------
POWERS = {
    "Magda": [
        {"name": "Berserk", "rule": "magic/powers/berserk",
         "boosts": ["Stay over (2 PP)", "Take it with her (2 PP)"],
         "limits": ["Limited Control", "Limited Power -- cannot retreat, must engage"]},
        {"name": "Hel's Mark", "rule": "magic/powers/hels-mark",
         "boosts": [], "limits": []},
    ],
    "Gardwen": [
        {"name": "The Wild Line", "rule": "magic/powers/the-wild-line",
         "boosts": ["Sanctuary (2 PP)", "Unseat (4 PP)"],
         "limits": ["Limited Power -- spirits and the spirit-touched only"]},
        {"name": "Woodwise", "rule": "magic/powers/woodwise",
         "boosts": [], "limits": []},
    ],
    "Hanzo di Teufel": [
        {"name": "The Binding", "rule": "magic/powers/the-binding",
         "boosts": ["Open the Channel (2 PP)", "Seat the Bound (4 PP)",
                    "Anchor (2 PP)", "Reinforce the Seat (1 PP)",
                    "Draw Forth (4 PP)"],
         "limits": ["Limited Power -- spirits only",
                    "Fatal Flaw -- every seat reinforced every morning"]},
    ],
    "Santo di Teufel": [
        {"name": "The Binding", "rule": "magic/powers/the-binding",
         "boosts": ["Open the Channel (2 PP)"],
         "limits": ["Limited Power -- spirits only"],
         "note": "An apprentice. He has cut a channel and does not know what came through it."},
    ],
    "High Priestess Nerissa": [
        {"name": "The Rites of the Lady", "rule": "magic/powers/the-rites-of-the-lady",
         "boosts": ["The Lady's Washing (2 PP)", "Blessing of the Waters (2 PP)",
                    "Consecration (4 PP)", "The Asking (4 PP)",
                    "The Raising (8 PP + 1 EXP)"],
         "limits": ["Limited Power -- the place, the people and the time, or it does not happen",
                    "Activation Cost -- spent afterwards"]},
    ],
    "Lilura Deepcurrent": [
        {"name": "The Rites of the Lady", "rule": "magic/powers/the-rites-of-the-lady",
         "boosts": ["The Lady's Washing (2 PP)", "Blessing of the Waters (2 PP)",
                    "Consecration (4 PP)", "The Asking (4 PP)"],
         "limits": ["Limited Power -- the place, the people and the time, or it does not happen",
                    "Activation Cost -- spent afterwards"],
         "note": "Fourteen months of the Asking going unanswered, and she has told nobody."},
    ],
}

# --- casting skills: CFI names, and the numbers the table has been using ----
SKILL_FIX = {
    "Gardwen":                {"rename": {"Piety": "Devotion"}},
    "High Priestess Nerissa": {"rename": {"Exhort": None}, "set": {"Channel": 92, "Devotion": 92}},
    "Lilura Deepcurrent":     {"rename": {"Exhort": None}, "set": {"Channel": 85, "Devotion": 88}},
}

# Clerics do not own a spell list; they have access to their whole Rank.
CLERIC_RANK = {"Gardwen": 2, "High Priestess Nerissa": 4, "Lilura Deepcurrent": 4}

# Abilities that were class features of a class we do not use.
ABILITIES = {
    "Magda": ["Artful Dodger (CFI) -- unburdened and in light armor or less, Evade a "
              "melee attack without going prone; prone against a ranged attack only "
              "on a failure",
              "Berserk, Hel's Mark -- see powers"],
    "Gardwen": ["The Wild Line, Woodwise -- see powers"],
}

log = []
for f in sorted(glob.glob(os.path.join(PKG, 'characters/**/*.json'), recursive=True)):
    d = json.load(open(f, encoding='utf-8'))
    name, changed = d.get('name'), False

    # 1. spells -> CFI only
    if isinstance(d.get('spells'), dict):
        out = {}
        for trad, lst in d['spells'].items():
            keep = []
            for s in lst:
                if s in DROP:
                    log.append(f'{name}: drop {s} ({DROP[s]})'); continue
                new = RENAME.get(s, s)
                if new != s:
                    log.append(f'{name}: {s} -> {new}')
                if new not in keep:
                    keep.append(new)
                elif new != s:
                    log.append(f'{name}: {new} was already there, deduped')
            if keep:
                out[trad] = sorted(keep)
        if name in CLERIC_RANK:                      # one key: what is in memory
            mem = sorted({s for lst in out.values() for s in lst})
            out = {"memorized": mem}
            d.setdefault('extras', {})['magic_rank'] = CLERIC_RANK[name]
            d['extras']['spell_access'] = (
                f'CFI cleric, Rank {CLERIC_RANK[name]}: access to every cleric spell '
                f'of that Rank or below. "memorized" is what is currently prayed for, '
                f'not what she can have.')
            d['extras'].pop('spell_ranks', None)
        if out != d['spells']:
            d['spells'], changed = out, True

    # 2. powers
    if name in POWERS:
        d['powers'], changed = POWERS[name], True
        log.append(f'{name}: powers = ' + ', '.join(p['name'] for p in POWERS[name]))

    # 3. casting skills under their CFI names
    if name in SKILL_FIX:
        fix = SKILL_FIX[name]
        for old, new in fix.get('rename', {}).items():
            if old in d['skills']:
                v = d['skills'].pop(old)
                if new:
                    d['skills'][new] = v
                    log.append(f'{name}: skill {old} -> {new} ({v})')
                else:
                    log.append(f'{name}: skill {old} {v} removed (folded into the rites power)')
                changed = True
        for k, v in fix.get('set', {}).items():
            if d['skills'].get(k) != v:
                d['skills'][k] = v; changed = True
                log.append(f'{name}: skill {k} = {v}')
        d['skills'] = dict(sorted(d['skills'].items()))

    # 4. abilities that belonged to a class we do not use
    if name in ABILITIES:
        d.setdefault('extras', {})['abilities'] = ABILITIES[name]
        changed = True
        log.append(f'{name}: extras.abilities rewritten')

    if changed:
        json.dump(d, open(f, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
        open(f, 'a', encoding='utf-8').write('\n')

for line in log:
    print(line)
print(f'\n{len(log)} changes')
