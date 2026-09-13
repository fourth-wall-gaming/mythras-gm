#!/usr/bin/env python3
"""Turn a vendored CFI chapter into rule files, one per `##` section.

The spell chapter has its own script because a spell is a regular record with a
stat block. Everything else is prose under headings, and a heading is the right
grain: `casting-cost` and `magnitude-and-intensity` are the two rules that were
being improvised, and they want to be separately findable.

CFI is ORC licensed; the notice travels on every generated file.

Usage:  ingest_cfi_chapter.py 0009_Magic magic [--check]
"""
import argparse, os, re, sys

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, 'vendor', 'cfi-srd', 'rules-en')
RULES  = os.path.join(ROOT, 'skills', 'mythras-gm', 'rules')

NOTICE = ("Classic Fantasy Imperative, ORC License. Adapted from the vendored "
          "SRD (vendor/cfi-srd); see vendor/README.md for the notice.")


def slug(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower().replace('&', 'and')).strip('-')


def clean(text):
    text = re.sub(r'\[(.+?)\]\(0\d{3}_[^)]+\)', r'\1', text)
    text = text.replace('\\(', '(').replace('\\)', ')')
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('chapter', help='vendored file stem, e.g. 0009_Magic')
    ap.add_argument('domain', help='rules/<domain>/ to write into, e.g. magic')
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()

    src = os.path.join(VENDOR, a.chapter + '.md')
    if not os.path.isfile(src):
        sys.exit(f'no such vendored chapter: {src}')
    out = os.path.join(RULES, a.domain, 'cfi')

    text = open(src, encoding='utf-8').read()
    sections = re.split(r'^## (?!#)', text, flags=re.M)[1:]
    if not a.check:
        os.makedirs(out, exist_ok=True)

    written = 0
    for sec in sections:
        lines = sec.split('\n')
        title = clean(lines[0]).strip()
        body = clean('\n'.join(lines[1:]))
        if not body:
            continue
        s = slug(title)
        first = re.sub(r'\s+', ' ', re.sub(r'[*_#|]', '', body)).strip()
        first = re.split(r'(?<=[.!?])\s', first, maxsplit=1)[0][:160]
        doc = '\n'.join([
            '---',
            f'id: "{a.domain}/cfi/{s}"',
            f'title: "{title} (Classic Fantasy Imperative)"',
            f'category: "{a.domain}"',
            f'domain: "{a.domain}"',
            f'topic: "{s}"',
            'kind: "procedure"',
            f'summary: "{first.replace(chr(34), chr(39))}"',
            'facets: {"phase": ["casting"], "kind": ["procedure"], '
            '"licence": ["orc"], "source": ["classic-fantasy-imperative"]}',
            f'links: ["{a.domain}/cfi/spell-list", "{a.domain}/casting"]',
            'licence: "orc"',
            f'source: "{NOTICE}"',
            '---',
            '',
            body,
            '',
        ])
        if not a.check:
            open(os.path.join(out, f'{s}.md'), 'w', encoding='utf-8').write(doc)
        written += 1
        print(f'  {s}')
    print(f'{written} sections -> {os.path.relpath(out, ROOT)}'
          + (' (check only)' if a.check else ''))


if __name__ == '__main__':
    main()
