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


# --- doing: forward state -----------------------------------------------

DOING = {
    "goal": "the pattern, worth more than the tools",
    "next": "weigh whatever the Sundries bring and ask what else they have",
    "where": "the Slake",
    "with": ["myth-char-cauk"],
    "blocked_by": "she will not move against the Spindle openly",
    "as_of_session": 4,
    "log": ["s3: traded the bog knife for a chip of dragon scale"],
}


def test_build_doing_keeps_only_known_slots():
    d = wt.build_doing(goal="g", next="n", nonsense="x", session=4)
    assert d["goal"] == "g" and d["next"] == "n"
    assert "nonsense" not in d
    assert d["as_of_session"] == 4


def test_build_doing_omits_empty_slots():
    d = wt.build_doing(goal="g", session=1)
    assert "where" not in d and "blocked_by" not in d


def test_valid_doing_has_no_warnings():
    assert wt.validate_doing(DOING) == []


def test_warns_when_next_is_missing():
    """A goal with no next action is a wish, not an agenda."""
    assert any("next" in w for w in wt.validate_doing({"goal": "g", "as_of_session": 1}))


def test_warns_when_next_merely_restates_goal():
    bad = dict(DOING, next=DOING["goal"])
    assert any("next" in w for w in wt.validate_doing(bad))


def test_warns_when_undated():
    bad = {k: v for k, v in DOING.items() if k != "as_of_session"}
    assert any("as_of_session" in w for w in wt.validate_doing(bad))


def test_validate_doing_never_raises():
    assert isinstance(wt.validate_doing({}), list)
    assert isinstance(wt.validate_doing("nonsense"), list)


def test_doing_line_renders_goal_and_next():
    line = wt.doing_line(DOING, current_session=4)
    assert "the pattern" in line and "next:" in line


def test_doing_line_flags_staleness():
    assert "2 sessions stale" in wt.doing_line(DOING, current_session=6)


def test_doing_line_no_staleness_when_current():
    assert "stale" not in wt.doing_line(DOING, current_session=4)


def test_doing_line_truncates():
    assert len(wt.doing_line(DOING, current_session=4, width=40)) <= 40


def test_doing_line_empty_for_no_doing():
    assert wt.doing_line(None, current_session=4) == ""
    assert wt.doing_line({}, current_session=4) == ""


# --- meta: bookkeeping is not fiction -----------------------------------

META = {"id": "m1", "session": 4, "who": [(KRENCH, "Krench"), (OMMET, "Ommet")],
        "summary": "GM CORRECTION - CREW CONFUSION", "visibility": "meta"}


def test_meta_is_never_knowledge():
    """A GM note naming the cast must not tell --known-to that a goblin is
    aware of my own corrections."""
    assert wt.filter_log([META], known_to=KRENCH) == []


def test_meta_excluded_from_fiction():
    assert wt.filter_log(LOG + [META], fiction_only=True) == wt.filter_log(LOG)


def test_offscreen_is_still_fiction():
    """Offscreen happened in the world; the party just did not see it."""
    assert wt.is_fiction({"visibility": "offscreen"}) is True
    assert wt.is_fiction({"visibility": "meta"}) is False
    assert wt.is_fiction({}) is True


# --- CLI wiring ---------------------------------------------------------

def _gm_source():
    path = os.path.join(os.path.dirname(__file__), "..", "skills",
                        "mythras-gm", "mythras_gm.py")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _schema():
    path = os.path.join(os.path.dirname(__file__), "..", "skills",
                        "mythras-gm", "schema.tql")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def test_schema_declares_new_attributes_additively():
    s = _schema()
    for attr in ("myth-event-visibility", "myth-canon-status", "myth-superseded-by"):
        assert f"attribute {attr}, value string;" in s, f"{attr} not declared"
    # Additive define only: a redefine, or an annotation narrowing an existing
    # type, would force a migration of the live database. @card on a role of a
    # relation declared in this same file is not that -- myth-knows uses it to
    # make `fact` and `subject` both optional, which is how one edge carries
    # both knowledge shapes -- so allow it there and nowhere else.
    assert "redefine" not in s and "@values" not in s
    for line in s.split("\n"):
        if "@card" in line:
            assert line.strip().startswith(("relates fact", "relates subject")), \
                f"unexpected @card annotation: {line.strip()}"


def test_canon_status_owned_by_every_canon_bearing_entity():
    s = _schema()
    assert s.count("owns myth-canon-status") == 5


def test_event_visibility_owned_by_game_event():
    s = _schema()
    block = s.split("entity myth-game-event")[1].split(";")[0]
    assert "owns myth-event-visibility" in block


def test_commands_registered():
    s = _gm_source()
    for cmd in ("set-doing", "retire-canon"):
        assert f'sub.add_parser("{cmd}"' in s, f"{cmd} not registered"
    assert 'add_argument("--brief"' in s
    assert 'add_argument("--known-to"' in s
    assert 'add_argument("--involving"' in s


def test_retire_canon_fails_on_unknown_id():
    body = _gm_source().split("def cmd_retire_canon(")[1].split("\ndef ")[0]
    assert "fail(" in body
    assert "TYPEDB_DATABASE" in body, "error must name the database"


def test_set_doing_merges_rather_than_overwrites():
    body = _gm_source().split("def cmd_set_doing(")[1].split("\ndef ")[0]
    assert "deep_merge" in body, "set-doing must merge, not replace extras"


def test_read_paths_respect_canon_status():
    s = _gm_source()
    for fn in ("cmd_list_lore", "cmd_get_log"):
        body = s.split(f"def {fn}(")[1].split("\ndef ")[0]
        assert "canon" in body, f"{fn} does not consider canon status"


def test_context_excludes_meta_and_surfaces_doing():
    body = _gm_source().split("def cmd_get_context(")[1].split("\ndef ")[0]
    assert "fiction_only=True" in body, "meta notes must not fill recent_events"
    assert "doing_line" in body, "context must surface what NPCs are doing"
    assert "former_player_characters" in body


# --- knowledge: the character-centred graph -----------------------------

GOOD_K = {"depth": "knows", "route": "inferred",
          "note": "they are holding out on me", "attitude": "will not deal until they name it"}


def test_valid_knowledge_has_no_warnings():
    assert wt.validate_knowledge(GOOD_K) == []


def test_warns_on_unknown_depth():
    assert any("depth" in w for w in wt.validate_knowledge(dict(GOOD_K, depth="certain")))


def test_warns_on_unknown_route():
    assert any("route" in w for w in wt.validate_knowledge(dict(GOOD_K, route="osmosis")))


def test_warns_when_edge_carries_neither_note_nor_attitude():
    """An edge with neither says only THAT they know, which participation
    already told us. The value is the reading and the feeling."""
    bare = {"depth": "knows", "route": "told"}
    assert any("note" in w or "attitude" in w for w in wt.validate_knowledge(bare))


def test_note_alone_is_enough():
    assert wt.validate_knowledge({"depth": "knows", "note": "x"}) == []


def test_warns_on_witnessed_but_glimpsed():
    odd = dict(GOOD_K, route="witnessed", depth="glimpsed")
    assert any("glimpsed" in w for w in wt.validate_knowledge(odd))


def test_validate_knowledge_never_raises():
    assert isinstance(wt.validate_knowledge({}), list)
    assert isinstance(wt.validate_knowledge("nonsense"), list)


def test_knowledge_line_carries_reading_and_feeling():
    line = wt.knowledge_line(GOOD_K)
    assert "knows" in line and "holding out" in line and "name it" in line


def test_knowledge_line_truncates():
    assert len(wt.knowledge_line(GOOD_K, width=30)) <= 30


def test_knowledge_line_empty_for_nothing():
    assert wt.knowledge_line(None) == "" and wt.knowledge_line({}) == ""


def test_knowledge_commands_registered():
    s = _gm_source()
    for cmd in ("set-knowledge", "get-knowledge"):
        assert f'sub.add_parser("{cmd}"' in s, f"{cmd} not registered"
    assert 'add_argument("--knower"' in s
    assert 'add_argument("--attitude"' in s


def test_set_knowledge_replaces_rather_than_accumulates():
    """One edge per (knower, subject) -- a character's understanding is revised
    as they learn more, not stacked up in duplicate."""
    body = _gm_source().split("def cmd_set_knowledge(")[1].split("\ndef ")[0]
    assert "delete $r" in body, "set-knowledge must clear the prior edge first"
    assert "fail(" in body, "must fail loudly on an unknown knower or subject"


def test_schema_declares_the_knowledge_graph():
    """There is ONE knowledge relation, and it carries both vocabularies.

    This model arrived as a second relation, `myth-knowledge`, alongside the
    living world's `myth-knows`. Two relations meant a character could know a
    thing twice, in two vocabularies, with no way to reconcile them -- so they
    were merged onto myth-knows, which now relates a knower to EITHER a fact
    (engine-facing, what agendas gate on) or a subject (GM-facing annotation).
    """
    s = _schema()
    assert "relation myth-knowledge," not in s, \
        "myth-knowledge came back; it belongs on myth-knows"
    assert "relation myth-knows," in s
    for attr in ("myth-knowledge-depth", "myth-knowledge-route",
                 "myth-knowledge-note", "myth-attitude"):
        assert f"attribute {attr}, value string;" in s
        assert f"    owns {attr}," in s, f"{attr} is declared but not owned by myth-knows"
    # both roles, both optional, so an edge plays exactly one of them
    assert "relates fact @card(0..1)," in s
    assert "relates subject @card(0..1);" in s
    # the knower is always a named character; subjects are broad
    assert s.count("plays myth-knows:subject") >= 5


# --- the merged knowledge edge ------------------------------------------
#
# These guard the resolution of a real fork: `myth-knowledge` (knower ->
# subject, depth/route/note/attitude) grew on main while `myth-knows` (knower ->
# fact, certainty/source/since) grew on the living-world branch. Two relations
# meant a character could know a thing twice, in two vocabularies, with nothing
# able to reconcile them. They are one relation now, and these tests are what
# stop them splitting again.

def test_one_knowledge_relation_only():
    s = _schema()
    assert s.count("relation myth-knows,") == 1
    assert "relation myth-knowledge," not in s


def test_myth_knows_owns_both_vocabularies():
    s = _schema()
    block = s.split("relation myth-knows,")[1].split(";")[0]
    for attr in ("myth-knowledge-certainty", "myth-knowledge-source",
                 "myth-knowledge-since", "myth-knowledge-depth",
                 "myth-knowledge-route", "myth-knowledge-note",
                 "myth-attitude", "myth-session-number"):
        assert f"owns {attr}," in block, f"myth-knows does not own {attr}"


def test_both_roles_are_optional():
    """An edge plays `fact` or `subject`, never both and never neither-allowed.

    Without @card(0..1) TypeDB requires every declared role, so a fact-shaped
    edge would refuse to insert for want of a subject.
    """
    s = _schema()
    block = s.split("relation myth-knows,")[1].split(";")[0]
    assert "relates fact @card(0..1)" in block
    assert "relates subject @card(0..1)" in block


def test_depth_and_route_map_onto_the_engine_vocabulary():
    """set-knowledge must write certainty/source too, or a GM-facing edge is
    invisible to require-fact, forecast, tick and check-consistency."""
    import world_tools as wt
    assert set(wt.DEPTH_TO_CERTAINTY) == set(wt.KNOWLEDGE_DEPTHS)
    assert set(wt.ROUTE_TO_SOURCE) == set(wt.KNOWLEDGE_ROUTES)
    # every mapped value must be one the fact graph actually accepts
    assert set(wt.DEPTH_TO_CERTAINTY.values()) <= {"knows", "believes",
                                                   "suspects", "wrong"}
    assert set(wt.ROUTE_TO_SOURCE.values()) <= {"witnessed", "told",
                                                "deduced", "rumor"}
    assert wt.as_certainty("can-prove") == "knows"
    assert wt.as_source("rumour") == "rumor"
    assert wt.as_certainty(None) is None and wt.as_source("nonsense") is None


def test_set_knowledge_writes_both_halves():
    source = _gm_source() if "_gm_source" in globals() else open(
        os.path.join(os.path.dirname(__file__), "..", "skills", "mythras-gm",
                     "mythras_gm.py"), encoding="utf-8").read()
    body = source.split("def cmd_set_knowledge(")[1].split("\ndef ")[0]
    assert "wt.as_certainty(" in body and "wt.as_source(" in body, \
        "set-knowledge writes only the GM vocabulary; the living world cannot read it"
    assert "isa myth-knows" in body and "myth-knowledge (" not in body


def test_every_character_view_sees_both_shapes():
    """A character holding only a subject-shaped edge must not read as knowing
    nothing. All three read paths were checked; two of them used to."""
    source = open(os.path.join(os.path.dirname(__file__), "..", "skills",
                               "mythras-gm", "mythras_gm.py"),
                  encoding="utf-8").read()
    for fn, key in (("cmd_character_view", '"reads"'),
                    ("cmd_brief", '"believes"'),
                    ("cmd_get_character", '"knows"')):
        body = source.split(f"def {fn}(")[1].split("\ndef ")[0]
        assert "_subject_knowledge_edges(" in body, f"{fn} cannot see subject edges"
        assert key in body, f"{fn} does not report them"


# --- reading a database older than the schema ----------------------------
#
# Merging the world-state work added nine attributes. TypeDB fails type
# inference on a query naming an undeclared type -- it does not return empty --
# so every one of those attributes broke reads against any save written before
# it existed. The live game database stopped answering get-campaign,
# get-context and export-campaign entirely. Requiring a schema migration before
# you can READ your own save is the wrong trade.

def test_optional_attributes_are_filtered_through_declared():
    source = open(os.path.join(os.path.dirname(__file__), "..", "skills",
                               "mythras-gm", "mythras_gm.py"),
                  encoding="utf-8").read()
    assert "def declared(driver" in source, "the schema probe is gone"
    # No raw `try { $x has <new attr> }` may survive: `try` guards a missing
    # VALUE, not a missing TYPE.
    for attr in ("myth-event-visibility", "myth-canon-status", "myth-system"):
        for line in source.splitlines():
            if f"try {{{{ $" in line and attr in line:
                raise AssertionError(
                    f"{attr} is named in a raw try clause, which still breaks "
                    f"an older database: {line.strip()}")


def test_writes_of_new_attributes_are_guarded_too():
    """Writing an undeclared attribute fails the whole insert. Losing a journal
    entry because the camera position could not be recorded is a bad trade."""
    source = open(os.path.join(os.path.dirname(__file__), "..", "skills",
                               "mythras-gm", "mythras_gm.py"),
                  encoding="utf-8").read()
    for fn, attr in (("cmd_log_event", "myth-event-visibility"),
                     ("cmd_create_campaign", "myth-system")):
        body = source.split(f"def {fn}(")[1].split("\ndef ")[0]
        assert "declared(driver" in body, \
            f"{fn} writes {attr} without checking the database declares it"
