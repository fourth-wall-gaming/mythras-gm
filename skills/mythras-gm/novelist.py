#!/usr/bin/env python3
"""novelist.py -- campaign journal -> manuscript -> typeset PDF.

Usage:
    extract --campaign ID [--out DIR]     # TypeDB -> novels/<slug>/source.md + book.yaml
    build --manuscript DIR                # chapters/*.md -> pandoc -> typst -> <slug>.pdf

The CLI is deterministic plumbing only -- Claude writes the prose between
`extract` and `build` (see NOVELIZATION.md). Pure helpers live at the top of
this file so they can be unit-tested without TypeDB or the toolchain.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import mythras_gm as gm  # driver, _fetch, escape_string, out, fail

import yaml

SKILL_DIR = os.path.dirname(os.path.realpath(__file__))
TEMPLATE_PATH = os.path.join(SKILL_DIR, "book_template", "novel.typ")

TOOL_HINTS = {"pandoc": "brew install pandoc", "typst": "brew install typst"}


class BuildError(Exception):
    pass


# ---------------------------------------------------------------------------
# Pure helpers (no DB, no subprocess)
# ---------------------------------------------------------------------------

def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", (name or "untitled").lower()).strip("-") or "untitled"


def filter_player_lore(rows):
    """Drop GM-only lore; missing visibility counts as player-visible."""
    return [r for r in rows if (r.get("visibility") or "player") != "gm"]


def render_source_md(campaign, events, characters, locations, factions, lore):
    """Render extracted campaign data as the manuscript's raw-material file."""
    lines = [f"# Source Material \u2014 {campaign['name']}", ""]

    def section(title, items, body_keys):
        if not items:
            return
        lines.append(f"## {title}")
        lines.append("")
        for it in items:
            lines.append(f"### {it['name']} <!-- id: {it['id']} -->")
            for key in body_keys:
                if it.get(key):
                    lines.append("")
                    lines.append(str(it[key]))
            lines.append("")

    section("Dramatis Personae", characters, ["description", "content"])
    section("Locations", locations, ["description", "content"])
    section("Factions", factions, ["description", "content"])
    section("Lore (player-visible)", lore, ["description", "content"])

    lines.append("## Journal")
    lines.append("")
    for n, e in enumerate(events, 1):
        meta = f"id: {e['id']}, type: {e['type']}, at: {e['at']}"
        if e.get("session") is not None:
            meta += f", session: {e['session']}"
        if e.get("participants"):
            meta += ", involves: " + ", ".join(p["name"] for p in e["participants"])
        lines.append(f"### Event {n} <!-- {meta} -->")
        lines.append("")
        lines.append(e["summary"])
        if e.get("narrative"):
            lines.append("")
            lines.append(e["narrative"])
        lines.append("")
    return "\n".join(lines) + "\n"


def chapter_files(manuscript_dir):
    """Sorted chapter markdown filenames (not paths)."""
    cdir = os.path.join(manuscript_dir, "chapters")
    if not os.path.isdir(cdir):
        return []
    return sorted(f for f in os.listdir(cdir) if f.endswith(".md"))


def validate_manuscript(manuscript_dir):
    """Return a list of human-readable problems; empty list means buildable."""
    errors = []
    if not os.path.exists(os.path.join(manuscript_dir, "book.yaml")):
        errors.append("book.yaml missing -- run extract first")
    files = chapter_files(manuscript_dir)
    if not files:
        errors.append("chapters/ is empty -- draft chapters first (see NOVELIZATION.md)")
        return errors
    nums = []
    for f in files:
        m = re.match(r"(\d+)-.+\.md$", f)
        if not m:
            errors.append(f"chapter filename not NN-<slug>.md: {f}")
        else:
            nums.append(int(m.group(1)))
    if nums and sorted(nums) != list(range(1, len(nums) + 1)):
        errors.append(f"chapter numbering has gaps or duplicates: {sorted(nums)}")
    for f in files:
        with open(os.path.join(manuscript_dir, "chapters", f), encoding="utf-8") as fh:
            if "[TODO" in fh.read():
                errors.append(f"unresolved [TODO] marker in {f}")
    return errors


def missing_tools(path=None):
    """Names of required binaries not on PATH, with brew install hints."""
    return [f"{tool} not found -- install with: {hint}"
            for tool, hint in TOOL_HINTS.items()
            if shutil.which(tool, path=path) is None]


# ---------------------------------------------------------------------------
# TypeDB extraction
# ---------------------------------------------------------------------------

def _members(driver, campaign_id, etype, extra_attrs):
    """Campaign members of one type with id+name plus optional extra attrs.

    extra_attrs: list of (typedb_attr, output_key). Optional attributes must be
    fetched one query at a time in TypeDB 3.x (absent attr in fetch = error).
    """
    cid = gm.escape_string(campaign_id)
    rows = gm._fetch(driver, f'''
        match
          $camp isa myth-campaign, has id "{cid}";
          (campaign: $camp, element: $x) isa myth-campaign-membership;
          $x isa {etype}, has id $i, has name $n;
        fetch {{ "id": $i, "name": $n }};''')
    result = []
    for r in rows:
        d = dict(r)
        for attr, key in extra_attrs:
            v = gm._fetch(driver, f'''
                match $x isa {etype}, has id "{gm.escape_string(d["id"])}", has {attr} $v;
                fetch {{ "v": $v }};''')
            d[key] = v[0]["v"] if v else None
        result.append(d)
    return result


def fetch_campaign_data(campaign_id):
    """Everything the novelization needs: (campaign, events, chars, locs, factions, lore)."""
    cid = gm.escape_string(campaign_id)
    with gm.get_driver() as driver:
        camp = gm._fetch(driver, f'''
            match $c isa myth-campaign, has id "{cid}";
            fetch {{ "id": $c.id, "name": $c.name }};''')
        if not camp:
            gm.fail(f"campaign not found: {campaign_id}")
        campaign = dict(camp[0])

        events = [dict(r) for r in gm._fetch(driver, f'''
            match
              $camp isa myth-campaign, has id "{cid}";
              (campaign: $camp, element: $e) isa myth-campaign-membership;
              $e isa myth-game-event, has id $i, has description $d,
                 has myth-event-type $t, has created-at $ts;
            fetch {{ "id": $i, "summary": $d, "type": $t, "at": $ts }};''')]
        events.sort(key=lambda e: (str(e["at"]), e["id"]))
        for e in events:
            eid = gm.escape_string(e["id"])
            for attr, key in (("content", "narrative"), ("myth-session-number", "session")):
                v = gm._fetch(driver, f'''
                    match $e isa myth-game-event, has id "{eid}", has {attr} $v;
                    fetch {{ "v": $v }};''')
                e[key] = v[0]["v"] if v else None
            e["participants"] = [dict(p) for p in gm._fetch(driver, f'''
                match
                  $e isa myth-game-event, has id "{eid}";
                  (event: $e, participant: $p) isa myth-event-involvement;
                  $p has id $pi, has name $pn;
                fetch {{ "id": $pi, "name": $pn }};''')]

        characters = _members(driver, campaign_id, "myth-character",
                              [("description", "description"), ("content", "content")])
        locations = _members(driver, campaign_id, "myth-location",
                             [("description", "description"), ("content", "content")])
        factions = _members(driver, campaign_id, "myth-faction",
                            [("description", "description"), ("content", "content")])
        lore = filter_player_lore(
            _members(driver, campaign_id, "myth-lore",
                     [("description", "description"), ("content", "content"),
                      ("myth-lore-visibility", "visibility")]))
    return campaign, events, characters, locations, factions, lore


def cmd_extract(args):
    campaign, events, chars, locs, facs, lore = fetch_campaign_data(args.campaign)
    if not events:
        gm.fail("campaign has no journal events -- play some sessions first")
    slug = slugify(campaign["name"])
    mdir = args.out or os.path.join(os.getcwd(), "novels", slug)
    os.makedirs(os.path.join(mdir, "chapters"), exist_ok=True)

    with open(os.path.join(mdir, "source.md"), "w", encoding="utf-8") as fh:
        fh.write(render_source_md(campaign, events, chars, locs, facs, lore))

    book_path = os.path.join(mdir, "book.yaml")
    if os.path.exists(book_path):
        with open(book_path, encoding="utf-8") as fh:
            book = yaml.safe_load(fh) or {}
    else:
        book = {"title": campaign["name"], "author": "Fourth Wall Gaming",
                "slug": slug, "campaign_id": campaign["id"],
                "style": None, "status": "outline-pending"}
    book["high_water_mark"] = events[-1]["id"]
    with open(book_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(book, fh, sort_keys=False, allow_unicode=True)

    gm.out({"success": True, "manuscript": os.path.abspath(mdir),
            "events": len(events), "high_water_mark": book["high_water_mark"]})
