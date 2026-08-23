"""Unit tests for world-state helpers.

Run:  uv run --project skills/mythras-gm python -m pytest tests/test_world_state.py -v
(No TypeDB required.)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "mythras-gm"))
import world_tools as wt


# A miniature of the real failure: two crews, one campaign. Sessions 1-2 are the
# first crew (Ommet), 3-4 the second (Krench). Nothing in the log itself says so
# -- only the participant links do, which is the whole point.
OMMET = "myth-char-ommet"
KRENCH = "myth-char-krench"
AURENGALL = "myth-char-aurengall"

LOG = [
    {"id": "e1", "session": 1, "summary": "The Itch: a scale from a living dragon",
     "who": [(OMMET, "Ommet"), (AURENGALL, "Aurengall")]},
    {"id": "e2", "session": 2, "summary": "Site Six descent, the pick",
     "who": [(OMMET, "Ommet")]},
    {"id": "e3", "session": 3, "summary": "The killing at Cauk's",
     "who": [(KRENCH, "Krench")]},
    {"id": "e4", "session": 4, "summary": "Muster-yard, the Nibb deal",
     "who": [(KRENCH, "Krench")]},
    {"id": "e5", "session": 4, "summary": "A drow rides for the Slake",
     "who": [], "visibility": "offscreen"},
    {"id": "e6", "session": 4, "summary": "Word reaches the squad of a rider",
     "who": [(KRENCH, "Krench")], "visibility": "reported"},
]


def ids(rows):
    return [r["id"] for r in rows]


# --- involving ----------------------------------------------------------

def test_involving_selects_one_crews_arc():
    assert ids(wt.filter_log(LOG, involving=[KRENCH])) == ["e3", "e4", "e6"]


def test_involving_the_other_crew_is_disjoint():
    assert ids(wt.filter_log(LOG, involving=[OMMET])) == ["e1", "e2"]


def test_involving_is_or_across_ids():
    assert ids(wt.filter_log(LOG, involving=[OMMET, KRENCH])) == [
        "e1", "e2", "e3", "e4", "e6"]


def test_involving_matches_npcs_too():
    assert ids(wt.filter_log(LOG, involving=[AURENGALL])) == ["e1"]


def test_no_filters_returns_everything():
    assert len(wt.filter_log(LOG)) == len(LOG)


# --- known_to -----------------------------------------------------------

def test_known_to_excludes_offscreen():
    """The regression that matters: an offscreen event is not knowledge."""
    out = ids(wt.filter_log(LOG, known_to=KRENCH))
    assert "e5" not in out


def test_known_to_includes_reported():
    assert "e6" in ids(wt.filter_log(LOG, known_to=KRENCH))


def test_known_to_absent_visibility_counts_as_played():
    """Existing events carry no visibility attribute; they must still be known."""
    assert "e3" in ids(wt.filter_log(LOG, known_to=KRENCH))


def test_known_to_does_not_leak_the_other_crews_history():
    out = ids(wt.filter_log(LOG, known_to=KRENCH))
    assert "e1" not in out and "e2" not in out


def test_known_to_retired_pc_returns_the_old_arc_only():
    assert ids(wt.filter_log(LOG, known_to=OMMET)) == ["e1", "e2"]


# --- visibility / session ----------------------------------------------

def test_visibility_filter():
    assert ids(wt.filter_log(LOG, visibility="offscreen")) == ["e5"]


def test_visibility_played_matches_absent_attribute():
    assert ids(wt.filter_log(LOG, visibility="played")) == ["e1", "e2", "e3", "e4"]


def test_since_session():
    assert ids(wt.filter_log(LOG, since_session=4)) == ["e4", "e5", "e6"]


def test_filters_compose():
    assert ids(wt.filter_log(LOG, involving=[KRENCH], since_session=4)) == ["e4", "e6"]


# --- liveness (forward-compatible with Stage 4) -------------------------

def test_retracted_events_excluded_by_default():
    log = LOG + [{"id": "e7", "session": 4, "summary": "v1 residue",
                  "who": [], "canon": "retracted"}]
    assert "e7" not in ids(wt.filter_log(log))


def test_retracted_events_included_on_request():
    log = LOG + [{"id": "e7", "session": 4, "summary": "v1 residue",
                  "who": [], "canon": "retracted"}]
    assert "e7" in ids(wt.filter_log(log, include_retired=True))


def test_is_live_treats_absent_as_live():
    assert wt.is_live(None) is True
    assert wt.is_live("live") is True
    assert wt.is_live("superseded") is False
    assert wt.is_live("retracted") is False


# --- purity -------------------------------------------------------------

def test_filter_does_not_mutate_input():
    before = [dict(e) for e in LOG]
    wt.filter_log(LOG, involving=[KRENCH], known_to=KRENCH)
    assert LOG == before


# --- unattributed events (silent-emptiness guard) -----------------------

def test_count_unattributed():
    """Only 2 of 48 real events had participants when this was written."""
    assert wt.count_unattributed(LOG) == 1  # e5 has who=[]


def test_unattributed_is_not_the_same_as_nobody_knows():
    """An event with no recorded participants must not be read as knowledge
    about anybody -- but the caller has to be able to see it was dropped."""
    sparse = [{"id": "x1", "session": 1, "summary": "nobody recorded", "who": []}]
    assert wt.filter_log(sparse, known_to=OMMET) == []
    assert wt.count_unattributed(sparse) == 1
