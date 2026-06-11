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
