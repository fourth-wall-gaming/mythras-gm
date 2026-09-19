"""Tests for the combat special-effects table.

Eligibility is the whole point of this module: offering a player an effect they
cannot legally take is worse than not offering one at all, because they will
plan around it.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_SKILL = Path(__file__).resolve().parent.parent / "skills" / "mythras-gm"
sys.path.insert(0, str(_SKILL))
import mythras_effects as fx  # noqa: E402


def ids(*a, **k):
    return {e["id"] for e in fx.available(*a, **k)}


# --- the vocabulary --------------------------------------------------------

def test_every_effect_in_the_rules_graph_vocabulary_is_present():
    """These ids double as `effect=` facet values in the rules graph.

    If the two drift, `query-rules --facet effect=<id>` silently returns
    nothing -- it does not error -- so a lookup would report "no such rule"
    for an effect the player was just offered.
    """
    from_rules = {
        "impale", "sunder", "disarm", "choose-location", "maximize-damage",
        "bypass-armor", "grip", "damage-weapon", "bleed", "bash",
        "stun-location", "arise", "blind-opponent", "enhance-parry",
        "force-failure", "prepare-counter", "scar-foe", "select-target",
        "slip-free", "withdraw", "circumvent-parry", "trip",
    }
    assert set(fx.BY_ID) == from_rules


def test_american_spelling_is_the_canonical_one():
    # bypass-armour / maximise-damage are the natural British spellings and
    # would fail silently against the graph. Pin the ones that actually exist.
    assert "bypass-armor" in fx.BY_ID and "bypass-armour" not in fx.BY_ID
    assert "maximize-damage" in fx.BY_ID and "maximise-damage" not in fx.BY_ID


def test_every_effect_has_a_phase_and_a_one_line():
    for e in fx.EFFECTS:
        assert e["phase"] in ("pre-damage", "post-damage", "followup"), e["id"]
        assert e["one_line"], e["id"]


# --- eligibility -----------------------------------------------------------

def test_critical_only_effects_need_a_critical():
    assert "bypass-armor" not in ids("offense", "success", "failure")
    assert "bypass-armor" in ids("offense", "critical", "failure")


def test_fumble_triggered_effects_need_the_opponent_to_fumble():
    assert "force-failure" not in ids("defense", "success", "failure")
    assert "force-failure" in ids("defense", "success", "fumble")


def test_impale_needs_an_impaling_weapon():
    rapier = {"name": "Rapier", "notes": "Impale"}
    club = {"name": "Club", "notes": "Stun Location"}
    assert "impale" in ids("offense", "success", "failure", rapier)
    assert "impale" not in ids("offense", "success", "failure", club)


def test_bludgeoning_effects_need_a_bludgeoning_weapon():
    club = {"name": "Quarterstaff", "notes": "Stun Location"}
    assert "stun-location" in ids("offense", "success", "failure", club)
    assert "stun-location" not in ids("offense", "success", "failure",
                                      {"name": "Rapier", "notes": "Impale"})


def test_explicit_traits_beat_sniffing_the_notes():
    w = {"name": "Odd Thing", "notes": "impale impale impale",
         "traits": ["bludgeoning"]}
    assert fx.weapon_traits(w) == {"bludgeoning"}


def test_arise_only_when_prone():
    assert "arise" not in ids("defense", "success", "failure")
    assert "arise" in ids("defense", "success", "failure", None, True)


def test_offence_and_defence_get_different_lists():
    off = ids("offense", "success", "failure")
    dfn = ids("defense", "success", "failure")
    assert "choose-location" in off and "choose-location" not in dfn
    assert "withdraw" in dfn and "withdraw" not in off
    # damage-weapon and trip are available to either side
    assert "damage-weapon" in off and "damage-weapon" in dfn


def test_a_weaponless_winner_still_gets_the_trait_free_effects():
    got = ids("offense", "success", "failure", None)
    assert "choose-location" in got
    assert "impale" not in got


# --- validation ------------------------------------------------------------

def test_cannot_take_more_effects_than_earned():
    err = fx.validate(["choose-location", "trip"], "offense", "success",
                      "failure", 1)
    assert err and "only 1" in err


def test_unknown_effect_is_rejected_with_a_suggestion():
    err = fx.validate(["bypa"], "offense", "critical", "failure", 1)
    assert err and "bypass-armor" in err


def test_ineligible_effect_is_rejected_with_a_reason():
    err = fx.validate(["bypass-armor"], "offense", "success", "failure", 1)
    assert err and "critical" in err


def test_only_maximize_damage_stacks():
    assert fx.validate(["maximize-damage", "maximize-damage"], "offense",
                       "critical", "failure", 2) is None
    err = fx.validate(["choose-location", "choose-location"], "offense",
                      "success", "failure", 2)
    assert err and "more than once" in err


def test_a_legal_selection_validates():
    rapier = {"name": "Rapier", "notes": "Impale"}
    assert fx.validate(["impale", "choose-location"], "offense", "success",
                       "failure", 2, rapier) is None
