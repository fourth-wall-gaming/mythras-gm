"""Unit tests for novelist.py pure helpers (no TypeDB, no pandoc/typst)."""

import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "mythras-gm"))
import novelist as nov


# --- slugify ---------------------------------------------------------------

def test_slugify():
    assert nov.slugify("The Stilling!") == "the-stilling"
    assert nov.slugify("") == "untitled"
    assert nov.slugify(None) == "untitled"


# --- lore filtering ----------------------------------------------------------

def test_filter_player_lore_excludes_gm():
    rows = [
        {"id": "a", "name": "Public", "visibility": "player"},
        {"id": "b", "name": "Secret", "visibility": "gm"},
        {"id": "c", "name": "Unset", "visibility": None},
    ]
    kept = nov.filter_player_lore(rows)
    assert [r["id"] for r in kept] == ["a", "c"]


# --- source.md rendering ------------------------------------------------------

CAMPAIGN = {"id": "myth-camp-1", "name": "The Stilling"}
EVENTS = [
    {"id": "ev-1", "type": "scene", "at": "2026-06-01T10:00:00",
     "summary": "Esk reaches the chart-room.", "narrative": "Wind hissed in the spars.",
     "session": 1, "participants": [{"id": "ch-1", "name": "Esk"}]},
    {"id": "ev-2", "type": "combat", "at": "2026-06-01T11:00:00",
     "summary": "Skirmish on the windlane.", "narrative": None,
     "session": None, "participants": []},
]
CHARS = [{"id": "ch-1", "name": "Esk", "description": "A wary navigator.", "content": "Born aloft."}]


def test_render_source_md_structure():
    md = nov.render_source_md(CAMPAIGN, EVENTS, CHARS, [], [], [])
    assert md.startswith("# Source Material — The Stilling")
    assert "## Dramatis Personae" in md
    assert "### Esk <!-- id: ch-1 -->" in md
    assert "Born aloft." in md
    # events in order, with metadata comments
    i1 = md.index("Esk reaches the chart-room.")
    i2 = md.index("Skirmish on the windlane.")
    assert i1 < i2
    assert "id: ev-1, type: scene" in md
    assert "session: 1" in md
    assert "involves: Esk" in md
    assert "Wind hissed in the spars." in md


def test_render_source_md_omits_empty_sections():
    md = nov.render_source_md(CAMPAIGN, EVENTS, [], [], [], [])
    assert "## Dramatis Personae" not in md
    assert "## Locations" not in md
    assert "## Journal" in md
