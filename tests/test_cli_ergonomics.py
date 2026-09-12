"""The flag names drifted as the CLI grew. These pin the ergonomics down."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "mythras-gm"))
import mythras_gm as gm


CHAR = {
    "name": "Gardwen",
    "myth-skills-json": {"Piety": 87, "Perception": 79, "Track": 60},
    "myth-combat-styles-json": {
        "Druid (club, dagger, dart, hammer, sickle, scimitar, shield, sling, "
        "spear, staff, staff sling, whip)": 59
    },
    "myth-passions-json": {
        "Love (Brother + Family)": 80,
        "Love (Elves)": 45,
        "Love (Nature + Wilderness)": 65,
    },
}


@pytest.mark.parametrize("query,expected", [
    ("Piety", "Piety"),
    ("piety", "Piety"),
    ("Piety (Devotion)", "Piety"),          # the form that failed mid-session
    ("Druid", "Druid (club, dagger, dart, hammer, sickle, scimitar, shield, "
              "sling, spear, staff, staff sling, whip)"),
    ("druid staff sling", "Druid (club, dagger, dart, hammer, sickle, scimitar, "
                          "shield, sling, spear, staff, staff sling, whip)"),
    ("Love (Brother", "Love (Brother + Family)"),
    ("love brother", "Love (Brother + Family)"),
    ("Love (Brother + Family)", "Love (Brother + Family)"),
])
def test_skill_resolves(query, expected):
    name, value = gm._resolve_skill(CHAR, query)
    assert name == expected


def test_ambiguous_skill_names_the_candidates(capsys):
    with pytest.raises(SystemExit):
        gm._resolve_skill(CHAR, "Love")
    err = capsys.readouterr().out
    assert "ambiguous" in err
    assert "Love (Elves)" in err


def test_missing_skill_lists_what_there_is(capsys):
    with pytest.raises(SystemExit):
        gm._resolve_skill(CHAR, "Juggling")
    assert "Perception" in capsys.readouterr().out


def test_every_alias_points_at_a_real_flag():
    """An alias for a dest the command does not have would silently do nothing."""
    parser = gm.build_parser()
    sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
    for cmd, mapping in gm.ALIASES.items():
        p = sub.choices[cmd]
        dests = {a.dest for a in p._actions}
        for alias, canonical in mapping.items():
            assert canonical in dests, f"{cmd}: alias {alias} -> unknown dest {canonical}"
            assert alias in {o for a in p._actions for o in a.option_strings}


def test_alias_folds_onto_canonical():
    class A:
        pass
    a = A()
    a._alias_id = "myth-fact-1"
    a.id = None
    gm._resolve_aliases(a)
    assert a.id == "myth-fact-1"
    assert not hasattr(a, "_alias_id")


def test_alias_conflicting_with_canonical_is_an_error(capsys):
    class A:
        pass
    a = A()
    a._alias_id = "myth-fact-2"
    a.id = "myth-fact-1"
    with pytest.raises(SystemExit):
        gm._resolve_aliases(a)
    assert "disagree" in capsys.readouterr().out


def test_relaxed_flags_are_re_enforced():
    """Adding an alias un-requires the canonical flag; it must be enforced later."""
    gm.build_parser()
    assert "id" in gm.RELAXED_REQUIRED.get("brief", set())
