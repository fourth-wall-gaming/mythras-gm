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
