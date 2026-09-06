"""Unit tests for the pure Mythras Imperative rules engine.

Run:  python -m pytest tests/ -v
(No TypeDB required.)
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "mythras-gm"))
import mythras_engine as eng

CHARS = {"STR": 11, "CON": 12, "SIZ": 10, "DEX": 15, "INT": 13, "POW": 12, "CHA": 10}


# --- dice ---------------------------------------------------------------

def test_dice_expressions():
    rng = random.Random(42)
    assert eng.roll_dice("1d8+1", rng)["total"] >= 2
    assert eng.roll_dice("+0")["total"] == 0
    assert eng.roll_dice("1d10+1d8", rng)["total"] >= 2
    assert eng.roll_dice("-1d4", rng)["total"] <= -1
    assert eng.roll_dice("3")["total"] == 3


def test_bad_dice_expression():
    try:
        eng.roll_dice("banana")
        assert False, "should raise"
    except ValueError:
        pass


# --- skill checks --------------------------------------------------------

def test_success_levels():
    assert eng.skill_check(60, roll=6)["level"] == "critical"
    assert eng.skill_check(60, roll=7)["level"] == "success"
    assert eng.skill_check(60, roll=61)["level"] == "failure"
    assert eng.skill_check(60, roll=99)["level"] == "fumble"
    assert eng.skill_check(3, roll=4)["level"] == "success"      # 01-05 always succeeds
    assert eng.skill_check(120, roll=99)["level"] == "failure"   # 96-00 always fails
    assert eng.skill_check(120, roll=100)["level"] == "fumble"   # >100 fumbles only on 00


def test_difficulty_grades():
    r = eng.skill_check(60, "hard", roll=40)
    assert r["effective"] == 40 and r["level"] == "success"
    assert eng.skill_check(60, "formidable", roll=31)["level"] == "failure"
    assert eng.skill_check(60, "herculean", roll=12)["level"] == "success"


# --- derived attributes ---------------------------------------------------

def test_damage_modifier():
    assert eng.damage_modifier(11, 12) == "+0"
    assert eng.damage_modifier(16, 16) == "+1d4"
    assert eng.damage_modifier(5, 5) == "-1d6"
    assert eng.damage_modifier(22, 24) == "+1d10"


def test_derive_attributes():
    a = eng.derive_attributes(CHARS)
    assert a["action_points"] == 2
    assert a["initiative_bonus"] == 14
    assert a["healing_rate"] == 2
    assert a["luck_points"] == 2
    assert a["magic_points"] == 12


# --- hit locations ---------------------------------------------------------

def test_avian_hit_locations():
    locs = eng.build_hit_locations(CHARS, "avian", {"Chest": 4})
    names = [l["name"] for l in locs]
    assert "Right Wing" in names and "Left Wing" in names and "Head" in names
    chest = next(l for l in locs if l["name"] == "Chest")
    assert chest["ap"] == 4 and chest["hp"] == 7  # CON+SIZ 22 -> band 21-25
    assert eng.roll_hit_location(locs, roll=11)["location"] == "Right Wing"
    assert eng.roll_hit_location(locs, roll=20)["location"] == "Head"


def test_damage_and_wounds():
    locs = eng.build_hit_locations(CHARS, "avian", {"Chest": 4})
    rep = eng.apply_damage(locs, "Chest", 9)
    assert rep["net_damage"] == 5 and rep["wound"] == "minor"
    rep = eng.apply_damage(locs, "Chest", 10)
    assert rep["wound"] == "serious"
    rep = eng.apply_damage(locs, "Chest", 15)
    assert rep["wound"] == "major"


def test_parry_reduction():
    assert eng.parry_reduction(10, "M", "M") == 0   # equal size blocks all
    assert eng.parry_reduction(10, "L", "M") == 5   # one smaller halves
    assert eng.parry_reduction(10, "H", "S") == 10  # two+ smaller blocks none


# --- contests ---------------------------------------------------------------

def test_differential_auto_fail():
    rng = random.Random(7)
    d = eng.differential_roll(70, 0, b_auto_fail=True, rng=rng)
    assert d["b"]["level"] == "failure"
    assert d["beneficiary"] in ("a", None)


def test_over_100_adjustment():
    a, b = eng._over_100_adjust(130, 60)
    assert (a, b) == (100, 30)


# --- character generation -----------------------------------------------------

def test_base_skills_avian():
    sk = eng.base_skills(CHARS, "avian")
    assert "Flight" in sk and "Swim" not in sk
    assert sk["Endurance"] == 24
    assert sk["Customs"] == 66          # INTx2 + 40
    assert sk["Native Tongue"] == 63    # INT+CHA+40


def test_roll_characteristics_avian_mods():
    rng = random.Random(3)
    c = eng.roll_characteristics("avian", rng)
    assert 4 <= c["SIZ"] <= 15   # 2d6+6 minus 3, floor 4
    assert 5 <= c["DEX"] <= 20   # 3d6 plus 2


# --- living world: time, clocks, beats ----------------------------------------

def test_time_key_round_trip():
    for key in ("d-3/dawn", "d-3/night", "d0/day", "d2/dusk"):
        assert eng.format_time_key(eng.parse_time_key(key)) == key


def test_time_keys_order_chronologically():
    assert eng.parse_time_key("d-3/dawn") < eng.parse_time_key("d-3/night")
    assert eng.parse_time_key("d-3/night") < eng.parse_time_key("d-2/dawn")
    assert eng.parse_time_key("d-1/night") < eng.parse_time_key("d0/dawn")


def test_bad_time_keys():
    for bad in ("banana", "d-3/teatime", "d-3", ""):
        try:
            eng.parse_time_key(bad)
            assert False, f"should raise on {bad!r}"
        except ValueError:
            pass


def test_advance_clock_saturates_and_reports_completion_once():
    assert eng.advance_clock(0, 6, 2) == (2, False)
    assert eng.advance_clock(4, 6, 2) == (6, True)      # this call completed it
    assert eng.advance_clock(6, 6, 1) == (6, False)     # already full, not again
    assert eng.advance_clock(5, 6, 99) == (6, True)     # saturates at size


def test_beat_due_on_time_and_on_clock():
    timed = {"time_index": eng.parse_time_key("d-3/night"), "status": "pending"}
    assert not eng.beat_is_due(timed, eng.parse_time_key("d-3/dusk"))
    assert eng.beat_is_due(timed, eng.parse_time_key("d-3/night"))

    clocked = {"trigger": "clock>=4", "agenda": "a1", "status": "pending"}
    assert not eng.beat_is_due(clocked, 999, clock_filled=3)
    assert eng.beat_is_due(clocked, 0, clock_filled=4)


def test_fired_beats_do_not_come_due_again():
    beat = {"time_index": 0, "status": "played"}
    assert not eng.beat_is_due(beat, 999)


def test_due_beats_ordered_by_agenda_priority():
    now = eng.parse_time_key("d-2/dawn")
    beats = [
        {"title": "minor errand", "time_index": 0, "priority": 1, "status": "pending"},
        {"title": "the Baron acts", "time_index": 0, "priority": 5, "status": "pending"},
        {"title": "not yet", "time_index": 9999, "priority": 5, "status": "pending"},
    ]
    got = [b["title"] for b in eng.due_beats(beats, now)]
    assert got == ["the Baron acts", "minor errand"]


def test_beat_staging_follows_actual_pc_presence():
    beat = {"place": "loc-sylph", "cast": ["npc-santo"]}
    # a PC lodged at the Sylph's Embrace witnesses it
    assert eng.beat_staging(beat, ["loc-sylph"], ["pc-magda"]) == "onscreen"
    # the same beat, party elsewhere, happens off-camera
    assert eng.beat_staging(beat, ["loc-oyster"], ["pc-magda"]) == "offscreen"
    # a PC in the cast pulls it onscreen wherever it is
    assert eng.beat_staging({"place": "loc-x", "cast": ["pc-randall"]},
                            ["loc-oyster"], ["pc-randall"]) == "onscreen"


# --- epistemics: facts, knowledge, reconciliation ----------------------------

FACTS = [
    {"id": "f-carved", "statement": "Santo carved Emmeralda", "status": "established",
     "truth": "true", "time_index": eng.parse_time_key("d-3/night")},
    {"id": "f-locket", "statement": "Nus lifted the binding locket",
     "status": "not-yet-true", "truth": "true", "time_index": None},
    {"id": "f-runner", "statement": "The runner who fled was Lord Santo",
     "status": "established", "truth": "false",
     "time_index": eng.parse_time_key("d-3/night")},
]


def test_character_view_is_a_projection_newest_first():
    edges = [
        {"knower": "pc-magda", "fact": "f-carved", "certainty": "knows",
         "source": "witnessed", "since": eng.parse_time_key("d-3/night")},
        {"knower": "pc-magda", "fact": "f-runner", "certainty": "believes",
         "source": "rumor", "since": eng.parse_time_key("d-2/dawn")},
        {"knower": "npc-blau", "fact": "f-carved", "certainty": "suspects",
         "source": "deduced", "since": eng.parse_time_key("d-2/day")},
    ]
    view = eng.character_view(FACTS, edges, "pc-magda")
    assert [f["id"] for f in view] == ["f-runner", "f-carved"]   # newest first
    assert view[0]["certainty"] == "believes"
    # Blau's knowledge is not in Magda's head
    assert all(f["id"] != "f-nothing" for f in view) and len(view) == 2


def test_a_false_fact_is_still_knowable():
    """Rumour and mistaken identity are the engine of this story."""
    edges = [{"knower": "npc-blau", "fact": "f-runner", "certainty": "believes",
              "source": "told", "since": eng.parse_time_key("d-2/dawn")}]
    view = eng.character_view(FACTS, edges, "npc-blau")
    assert view[0]["truth"] == "false"
    assert not eng.knowledge_violations(FACTS, edges)   # believing a lie is legal


def test_knowing_something_that_has_not_happened_is_a_violation():
    """The bug that shipped in v1: a sheet asserting a future event."""
    edges = [{"knower": "npc-ila", "fact": "f-locket", "certainty": "knows",
              "source": "witnessed", "since": eng.parse_time_key("d-3/dawn")}]
    v = eng.knowledge_violations(FACTS, edges)
    assert len(v) == 1 and v[0]["kind"] == "knows-unestablished"


def test_learning_before_it_was_true_is_a_violation():
    edges = [{"knower": "pc-randall", "fact": "f-carved", "certainty": "knows",
              "source": "witnessed", "since": eng.parse_time_key("d-3/dawn")}]
    v = eng.knowledge_violations(FACTS, edges)
    assert len(v) == 1 and v[0]["kind"] == "knew-too-early"


def test_dangling_knowledge_edge_is_a_violation():
    v = eng.knowledge_violations(FACTS, [{"knower": "x", "fact": "f-missing"}])
    assert len(v) == 1 and v[0]["kind"] == "dangling-knowledge"


def test_dormant_agenda_activates_only_when_its_holder_knows():
    agendas = [{"id": "a-bastard", "title": "A di Teufel who is not his",
                "status": "dormant", "holder": "npc-hanzo", "priority": 5}]
    reqs = [{"agenda": "a-bastard", "fact": "f-carved"}]
    # somebody else knowing it does nothing
    assert eng.agendas_to_activate(agendas, reqs,
        [{"knower": "pc-magda", "fact": "f-carved"}]) == []
    # the holder knowing it activates the agenda
    ready = eng.agendas_to_activate(agendas, reqs,
        [{"knower": "npc-hanzo", "fact": "f-carved"}])
    assert [a["id"] for a in ready] == ["a-bastard"]


def test_activation_needs_every_required_fact():
    agendas = [{"id": "a", "status": "dormant", "holder": "h", "priority": 3}]
    reqs = [{"agenda": "a", "fact": "f-carved"}, {"agenda": "a", "fact": "f-runner"}]
    assert eng.agendas_to_activate(agendas, reqs, [{"knower": "h", "fact": "f-carved"}]) == []
    both = [{"knower": "h", "fact": "f-carved"}, {"knower": "h", "fact": "f-runner"}]
    assert len(eng.agendas_to_activate(agendas, reqs, both)) == 1


def test_already_active_agendas_are_not_reactivated():
    agendas = [{"id": "a", "status": "active", "holder": "h", "priority": 3}]
    reqs = [{"agenda": "a", "fact": "f-carved"}]
    assert eng.agendas_to_activate(agendas, reqs, [{"knower": "h", "fact": "f-carved"}]) == []
