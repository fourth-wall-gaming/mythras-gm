#!/usr/bin/env python3
"""Turn the vendored Classic Fantasy Imperative spell chapter into rule files.

Generated, never hand-edited: re-run it and the graph matches the book. The
point is that `query-rules` answers a spell lookup instead of returning nothing
and inviting me to improvise -- which is how Command came to be ruled 1 MP for
a scene when the book says Cost 3 for one Turn.

CFI is ORC licensed, so adapting it into our schema is permitted; the notice
travels on every file and in vendor/README.md.

Output: skills/mythras-gm/rules/magic/cfi/spell-<slug>.md

They live in their own directory because CFI and Mythras Imperative both have a
Light, a Sleep and a Calm, and they are not the same spell. Keeping both, with
the book named in the id, is the only honest way to hold that.

Usage:  ingest_cfi_spells.py [--check]
"""
import argparse, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(ROOT, 'vendor', 'cfi-srd', 'rules-en', '0010_Spells.md')
OUT  = os.path.join(ROOT, 'skills', 'mythras-gm', 'rules', 'magic', 'cfi')

NOTICE = ("Classic Fantasy Imperative, ORC License. Adapted from the vendored "
          "SRD (vendor/cfi-srd); see vendor/README.md for the notice.")

FIELDS = ("Rank", "Casting Time", "Sphere", "Duration", "Cost", "Range",
          "Area", "Resist")


def slug(name):
    s = name.lower().replace('&', 'and')
    s = re.sub(r"[^a-z0-9]+", "-", s).strip('-')
    return s


def parse(text):
    """Yield (name, school, stats, body) for each `#### Spell` in the chapter."""
    body = text.split('## Spell Descriptions', 1)[1]
    for chunk in re.split(r'^#### ', body, flags=re.M)[1:]:
        lines = chunk.split('\n')
        raw = lines[0].strip()
        name = re.sub(r'\s*\\?\((R|T)\\?\)\*?\s*$', '', raw).replace('\\', '').strip()
        rest = '\n'.join(lines[1:])

        school = ''
        m = re.match(r'\s*\n\((.+?)\)\s*\n', rest)
        if m:
            school = m.group(1).strip()
            rest = rest[m.end():]

        stats = {}
        for cell in re.findall(r'\*\*(.+?):?\*\*\s*([^|\n]*)', rest):
            key = cell[0].strip().rstrip(':')
            if key in FIELDS and key not in stats:
                stats[key] = cell[1].strip()

        # Everything after the stat table is the spell's actual text.
        prose = re.split(r'^\|\s*\*\*Area.*$', rest, flags=re.M)
        prose = prose[-1] if len(prose) > 1 else rest
        prose = re.sub(r'^\|.*$', '', prose, flags=re.M)
        prose = prose.split('\n---')[0]
        prose = re.sub(r'\n{3,}', '\n\n', prose).strip()
        # Docsify links are noise outside the book; keep the words, drop the URL.
        prose = re.sub(r'\[(.+?)\]\(0\d{3}_[^)]+\)', r'\1', prose)
        prose = prose.replace('\\(', '(').replace('\\)', ')')

        yield name, school, stats, prose


def ranks(stats):
    """'Cleric 1, Mage 2' -> ['cleric', 'mage'] -- which list it belongs to."""
    return sorted({w.lower() for w in re.findall(r'(Cleric|Mage)', stats.get('Rank', ''))})


def render(name, school, stats, prose):
    lists = ranks(stats) or ['unlisted']
    facets = ('{"phase": ["casting"], "kind": ["spell"], '
              f'"magic-system": {str(lists).replace(chr(39), chr(34))}, '
              '"licence": ["orc"], "source": ["classic-fantasy-imperative"]}')
    first = re.split(r'(?<=[.!?])\s', prose.replace(chr(10), " "), maxsplit=1)[0]
    first = re.sub(r'\s+', ' ', re.sub(r'\*\*|_|-\s', '', first)).strip()
    summary = f'{stats.get("Rank") or "no rank"}. {first[:160]}'
    head = [
        '---',
        f'id: "magic/cfi/spell-{slug(name)}"',
        f'title: "{name}"',
        'category: "magic"',
        'domain: "magic"',
        'topic: "spells"',
        'kind: "spell"',
        f'summary: "{summary.replace(chr(34), chr(39))}"',
        f'facets: {facets}',
        'links: ["magic/casting", "magic/cfi/spell-list"]',
        f'licence: "orc"',
        f'source: "{NOTICE}"',
        '---',
        '',
    ]
    rows = [f'**{k}:** {stats[k]}' for k in FIELDS if stats.get(k)]
    # Entries with no stat table -- the poison sub-entries -- carry their own,
    # so do not print a half-built one above them.
    tbl = ' · '.join(rows) + '\n\n' if len(rows) > 2 else ''
    return '\n'.join(head) + (f'_{school}_\n\n' if school else '') + \
        tbl + prose + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true',
                    help='report what would be written, write nothing')
    a = ap.parse_args()

    spells = list(parse(open(SRC, encoding='utf-8').read()))
    if not a.check:
        os.makedirs(OUT, exist_ok=True)
    seen, written = {}, 0
    for name, school, stats, prose in spells:
        s = slug(name)
        if s in seen:          # the chapter lists Reincarnation, Arcane twice
            continue
        seen[s] = name
        missing = [f for f in ('Rank', 'Cost') if not stats.get(f)]
        if missing:
            print(f'  ! {name}: no {", ".join(missing)}', file=sys.stderr)
        if not a.check:
            open(os.path.join(OUT, f'spell-{s}.md'), 'w', encoding='utf-8')\
                .write(render(name, school, stats, prose))
        written += 1
    print(f'{written} CFI spells -> {os.path.relpath(OUT, ROOT)}'
          + (' (check only)' if a.check else ''))


if __name__ == '__main__':
    main()
