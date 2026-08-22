"""Unit tests for character score helpers.

Run:  uv run --project skills/mythras-gm python -m pytest tests/test_character_scores.py -v
(No TypeDB required.)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "mythras-gm"))
import score_tools as st


# --- deep_merge ---------------------------------------------------------

def test_merge_preserves_siblings():
    current = {"want": "respect", "ought": "diligence"}
    assert st.deep_merge(current, {"want": "praise"}) == {
        "want": "praise", "ought": "diligence"}


def test_merge_is_recursive():
    current = {"score": {"want": "respect", "focus": "prevention"}}
    merged = st.deep_merge(current, {"score": {"focus": "promotion"}})
    assert merged == {"score": {"want": "respect", "focus": "promotion"}}


def test_merge_extends_lists_rather_than_replacing():
    current = {"score": {"observed": ["s3: caught the lie"]}}
    merged = st.deep_merge(current, {"score": {"observed": ["s4: carried the paper"]}})
    assert merged["score"]["observed"] == [
        "s3: caught the lie", "s4: carried the paper"]


def test_merge_does_not_mutate_inputs():
    current = {"a": {"b": 1}}
    incoming = {"a": {"c": 2}}
    st.deep_merge(current, incoming)
    assert current == {"a": {"b": 1}}
    assert incoming == {"a": {"c": 2}}


def test_merge_overwrites_scalars():
    assert st.deep_merge({"focus": "prevention"}, {"focus": "promotion"}) == {
        "focus": "promotion"}


def test_merge_with_empty_current():
    assert st.deep_merge({}, {"want": "respect"}) == {"want": "respect"}


# --- validate_score -----------------------------------------------------

GOOD = {
    "want": "to be told I did well",
    "ought": "to handle the paper properly",
    "driver": "terror of going back down a rung",
    "stated_reason": "somebody has to keep the records straight",
    "focus": "prevention",
    "status": {"Vorgath": "low, appeasing"},
    "tactics": ["appease", "over-explain", "invoke procedure", "collapse (fawn)"],
    "when_lied_to": "miss",
    "blind_spot": "thinks he is respected rather than tolerated",
    "rhythm": "runs on, then stops mid-clause",
    "physical": "writing case held against the chest",
    "secret": "he cannot actually read quickly",
    "observed": [],
}


def test_valid_score_has_no_warnings():
    assert st.validate_score(GOOD) == []


def test_warns_when_stated_reason_matches_driver():
    bad = dict(GOOD, stated_reason=GOOD["driver"])
    warnings = st.validate_score(bad)
    assert any("stated_reason" in w for w in warnings)


def test_warns_on_unknown_when_lied_to_value():
    bad = dict(GOOD, when_lied_to="sometimes")
    assert any("when_lied_to" in w for w in st.validate_score(bad))


def test_warns_on_unknown_focus_value():
    bad = dict(GOOD, focus="sideways")
    assert any("focus" in w for w in st.validate_score(bad))


def test_warns_on_missing_slots():
    warnings = st.validate_score({"want": "x"})
    assert any("missing" in w.lower() for w in warnings)


def test_warns_when_tactics_ladder_too_short():
    bad = dict(GOOD, tactics=["appease"])
    assert any("tactics" in w for w in st.validate_score(bad))


def test_validate_never_raises_on_junk():
    assert isinstance(st.validate_score({}), list)
    assert isinstance(st.validate_score({"tactics": "not a list"}), list)


# --- CLI wiring ---------------------------------------------------------

def _gm_source():
    path = os.path.join(os.path.dirname(__file__), "..", "skills",
                        "mythras-gm", "mythras_gm.py")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def test_extras_is_a_mergeable_attribute():
    """mythras_gm must treat extras like skills: merged, not replaced."""
    source = _gm_source()
    assert '"myth-extras-json": args.extras' in source, \
        "update-character does not pass --extras through to the update dict"
    assert '"myth-extras-json"' in source.split("MERGEABLE_JSON_ATTRS")[1][:200], \
        "myth-extras-json is not in MERGEABLE_JSON_ATTRS"
    assert 'add_argument("--extras"' in source, "--extras flag is not registered"


def test_merge_helper_is_used_by_mythras_gm():
    source = _gm_source()
    assert "from score_tools import" in source or "import score_tools" in source, \
        "mythras_gm does not import the pure merge helper"
    assert "deep_merge" in source, "mythras_gm does not use deep_merge"


# --- update-campaign ----------------------------------------------------

def test_update_campaign_is_registered_and_wired():
    source = _gm_source()
    assert 'sub.add_parser("update-campaign")' in source, \
        "update-campaign subcommand is not registered"
    assert "def cmd_update_campaign(" in source, "cmd_update_campaign is missing"


def test_update_campaign_verifies_the_campaign_exists():
    """The data-loss bug was writes succeeding against a campaign that was not
    there. Every campaign-scoped write must check first."""
    source = _gm_source()
    body = source.split("def cmd_update_campaign(")[1].split("\ndef ")[0]
    assert "fail(" in body, \
        "cmd_update_campaign does not fail when the campaign does not exist"
    assert "myth-campaign" in body


def test_update_campaign_covers_the_editable_attributes():
    source = _gm_source()
    body = source.split("def cmd_update_campaign(")[1].split("\ndef ")[0]
    for attr in ("description", "myth-session-number", "myth-system", "content"):
        assert attr in body, f"cmd_update_campaign does not handle {attr}"


# --- update-character --attributes --------------------------------------

def test_attributes_is_a_mergeable_attribute():
    """Derived attributes need correcting when an engine formula is fixed.
    Merging matters: writing only action_points must not drop damage_modifier."""
    source = _gm_source()
    assert '"myth-attributes-json": args.attributes' in source, \
        "update-character does not pass --attributes through"
    assert '"myth-attributes-json"' in source.split("MERGEABLE_JSON_ATTRS")[1][:260], \
        "myth-attributes-json is not in MERGEABLE_JSON_ATTRS"
    assert 'add_argument("--attributes"' in source, "--attributes flag is not registered"
