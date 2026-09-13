#!/usr/bin/env python3
"""Build the spell registry: every spell name on a character sheet, where its
rule actually lives, and whether we may publish that rule.

The failure this exists to stop: a sheet carries a spell, nothing in the rules
graph answers to it, and the ruling gets invented at the table by analogy. That
happened -- Command was ruled 1 MP for a scene when the book says Cost 3 for one
Turn. A name with no rule behind it is a bug, and now it is a visible one.

`licence` says whether we may REPUBLISH the rule. It never says whether we may
play it: a book we own is a book we may play from.

Usage:
    build_spell_registry.py [<campaign-package-dir>]
"""
import argparse, json, glob, os, re, collections, sys

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GM     = os.path.join(ROOT, 'skills', 'mythras-gm') + os.sep
VENDOR = os.path.join(ROOT, 'vendor') + os.sep

ap = argparse.ArgumentParser()
ap.add_argument('--strict', action='store_true',
                help='exit non-zero if any spell on a sheet has no rule')
ap.add_argument('package', nargs='?',
                default=os.path.join(os.path.dirname(ROOT), 'purewater-campaign-v2'),
                help='campaign package to audit (default: ../purewater-campaign-v2)')
args = ap.parse_args()
PKG = args.package.rstrip(os.sep) + os.sep
if not os.path.isdir(PKG):
    sys.exit(f'no such campaign package: {PKG}')

def srd_names(path, start=None, end=None):
    txt = open(path, encoding='utf-8').read()
    if start: txt = txt.split(start)[1]
    if end:   txt = txt.split(end)[0]
    out = []
    for n in re.findall(r'^#### (.+)$', txt, re.M):
        out.append(re.sub(r'\s*\\?\((R|T)\\?\)\*?\s*$', '', n).replace('\\', '').strip())
    return out

CFI = set(srd_names(VENDOR + 'cfi-srd/rules-en/0010_Spells.md'))
MI  = set(srd_names(VENDOR + 'mythras-srd/rules-en/0007_Magic.md',
                    '## Spell Descriptions', '## Superpowers'))

# Ours: a rule file already in the graph that is not an SRD spell.
RULE_OF = {}          # spell title -> rule id in the graph
for f in glob.glob(GM + 'rules/magic/**/spell-*.md', recursive=True):
    t = open(f, encoding='utf-8').read()
    title = re.search(r'^title: "(.+)"$', t, re.M)
    rid   = re.search(r'^id: "(.+)"$', t, re.M)
    if title and rid:
        RULE_OF[title.group(1)] = rid.group(1)
OURS = {t for t in RULE_OF if t not in CFI and t not in MI}

# Names on sheets that are the same spell under another label. Checked against
# the vendored text, one at a time -- not guessed from the shape of the word.
ALIAS = {
    "Flaming Hands":        "Burning Hands",
    "Charm Being":          "Charm Person",
    "Illusion, Lesser":     "Illusion",
    "Illusion Greater":     "Illusion",
    "Invisibility, Lesser": "Invisibility",
    "Invisibility Radius":  "Invisibility, 10 ft. Radius",
    "Arcane Lock":          "Mage Lock",
    "Create Water":         "Create Food and Water",
    "Purify Water":         "Purify Food and Drink",
    "Know Passions":        "Know Alignment",
    "Find":                 "Find (X)",
}

# Not in either vendored SRD. Naming the book they came from is the whole point:
# each of these is a thing we may play and may not ship.
OUTSIDE = {
    # Full Mythras -- folk magic beyond the Imperative's twenty-four.
    "Babble": "mythras", "Mimic": "mythras", "Incognito": "mythras",
    "MindSpeech": "mythras",
    # Full Classic Fantasy -- mage and cleric spells CFI left out.
    "Affect Normal Fires": "classic-fantasy", "Audible Illusion": "classic-fantasy",
    "Color Cascade": "classic-fantasy", "Counterspell": "classic-fantasy",
    "Fog Cloud": "classic-fantasy", "Friendship": "classic-fantasy",
    "Hypnotism": "classic-fantasy", "Mage Hand": "classic-fantasy",
    "Misdirection": "classic-fantasy", "Ray of Enfeeblement": "classic-fantasy",
    "Read Thoughts": "classic-fantasy", "Scrying Pool": "classic-fantasy",
    "Shocking Grasp": "classic-fantasy", "Shocking Touch": "classic-fantasy",
    "Suggestion": "classic-fantasy", "Ventriloquism": "classic-fantasy",
    "Water Walk": "classic-fantasy",
    # Full Classic Fantasy -- the druid list, which CFI has no trace of.
    "Animal Friendship": "classic-fantasy", "Barkskin": "classic-fantasy",
    "Entangle": "classic-fantasy",
}

sheets = collections.defaultdict(set)
for f in glob.glob(PKG + 'characters/**/*.json', recursive=True) + \
         glob.glob(PKG + 'templates/**/*.json', recursive=True):
    d = json.load(open(f, encoding='utf-8'))
    s = d.get('spells')
    if isinstance(s, dict):
        for lst in s.values():
            for n in lst:
                sheets[n].add(d.get('name') or os.path.basename(f))

reg, unknown = {}, []
for name in sorted(sheets):
    canon = ALIAS.get(name, name)
    if canon in OURS:     src, lic = "ours", "ours"
    elif canon in MI:     src, lic = "mythras-imperative", "orc"
    elif canon in CFI:    src, lic = "classic-fantasy-imperative", "orc"
    elif name in OUTSIDE: src, lic = OUTSIDE[name], "not-ours"
    else:                 src, lic = "unknown", "unknown"; unknown.append(name)
    e = {"source": src, "licence": lic, "rule": RULE_OF.get(canon),
         "used_by": sorted(sheets[name])}
    if canon != name: e["canonical"] = canon
    reg[name] = e

out = {
    "_comment": "Generated by scripts/build_spell_registry.py; edit ALIAS and "
                "OUTSIDE there, not here. `licence` says whether we may publish "
                "the rule, never whether we may play it.",
    "spells": reg,
}
json.dump(out, open(GM + 'spell_registry.json', 'w'), indent=2, ensure_ascii=False)
open(GM + 'spell_registry.json', 'a').write('\n')

c = collections.Counter(v["licence"] for v in reg.values())
print(f'{len(reg)} spell names on sheets')
for k, v in c.most_common(): print(f'  {k:10} {v}')
if unknown:
    print('UNCLASSIFIED: ' + ', '.join(unknown))

# The guardrail. A spell on a sheet with no rule in the graph is a ruling
# waiting to be invented at the table, which is how this went wrong before.
gap = sorted(n for n, v in reg.items() if not v["rule"])
if gap:
    print(f'\n{len(gap)} of {len(reg)} have NO RULE in the graph:')
    for n in gap:
        v = reg[n]
        canon = f' (= {v["canonical"]})' if v.get("canonical") else ''
        print(f'  {n}{canon}  [{v["source"]}]  {", ".join(v["used_by"])}')
    if args.strict:
        sys.exit(1)
else:
    print('\nEvery spell on every sheet has a rule behind it.')
