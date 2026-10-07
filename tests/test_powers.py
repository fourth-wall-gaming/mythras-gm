"""CFI is the base and no new spells are written, so anything CFI has no entry
for is a Mythras power. These pin that boundary in the places it can rot: the
schema, the CLI, the round trip, and the audit that compares sheets to books."""
import json
import subprocess
import sys

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "mythras-gm"))
import mythras_gm as gm

GM = ROOT / "skills" / "mythras-gm"
SCHEMA = (GM / "schema.tql").read_text()
REGISTRY = json.loads((GM / "spell_registry.json").read_text())
RULES = GM / "rules" / "magic"


def test_schema_gives_characters_powers():
    assert "attribute myth-powers-json, value string;" in SCHEMA
    char = SCHEMA[SCHEMA.index("entity myth-character"):]
    assert "owns myth-powers-json" in char[:char.index(";")]


def test_update_character_can_write_powers():
    args = gm.build_parser().parse_args(
        ["update-character", "--id", "myth-char-1",
         "--powers", '[{"name": "Berserk", "rule": "magic/powers/berserk"}]'])
    assert json.loads(args.powers)[0]["name"] == "Berserk"


def test_powers_ride_on_the_combat_card():
    """Berserk changes every number in a fight, so it cannot be reference data."""
    card = gm._combat_card({
        "id": "myth-char-1", "name": "Magda",
        "myth-powers-json": [{"name": "Berserk"}, {"name": "Hel's Mark"}],
        "myth-spells-json": {"arcane": ["Sleep"]},
    })
    assert card["powers"] == ["Berserk", "Hel's Mark"]
    assert "spells" not in card          # looked up when cast, not carried


def test_every_spell_on_a_sheet_is_publishable():
    """The whole point of the consolidation: no sheet may depend on a book we
    cannot ship. A failure here means a spell came back onto a sheet."""
    bad = {n: v["source"] for n, v in REGISTRY["spells"].items()
           if v["licence"] != "orc"}
    assert not bad, f"not ours to publish: {bad}"


def test_every_spell_and_power_has_a_rule():
    everything = {**REGISTRY["spells"], **REGISTRY["powers"]}
    gap = sorted(n for n, v in everything.items() if not v["rule"])
    assert not gap, f"named on a sheet with no rule behind it: {gap}"


def test_the_binding_school_is_powers_now():
    """It was nine spells cast for one Magic Point each, which it never was."""
    for gone in ("spell-spirit-sight", "spell-unseat", "spell-seat-the-bound",
                 "spell-open-the-channel", "spell-draw-forth", "spell-anchor",
                 "spell-reinforce-the-seat", "spell-speak-with-the-bound"):
        assert not (RULES / f"{gone}.md").exists(), f"{gone} is a power now"
    for power in ("the-binding", "the-wild-line", "berserk",
                  "the-rites-of-the-lady"):
        assert (RULES / "powers" / f"{power}.md").exists()


def test_which_book_names_the_one_that_governs():
    """Both books are loaded and they disagree, so a lookup can land wrong."""
    text = (RULES / "which-book.md").read_text()
    assert "Classic Fantasy Imperative governs" in text
    assert "Channel (INT+CHA)" in text and "Devotion (POW+CHA)" in text


# build_spell_registry.py audits a campaign package against the books, and
# defaults to ../purewater-campaign-v2 -- a SIBLING repository. It is present
# on a developer's machine and absent from a CI checkout, so this test was
# green locally and could never be green anywhere else.
AUDITED_PACKAGE = ROOT.parent / "purewater-campaign-v2"


def test_registry_is_current():
    """Regenerating must be a no-op, or the audit is describing an older game."""
    if not AUDITED_PACKAGE.is_dir():
        pytest.skip(
            f"the audited campaign package is not checked out at "
            f"{AUDITED_PACKAGE}; the registry audit compares sheets in a "
            f"sibling repository against the books and cannot run without it"
        )
    before = (GM / "spell_registry.json").read_text()
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_spell_registry.py")],
        capture_output=True, text=True)
    assert r.returncode == 0, (
        f"build_spell_registry.py failed:\n{r.stdout}\n{r.stderr}")
    assert (GM / "spell_registry.json").read_text() == before


def test_the_registry_audit_names_its_own_dependency():
    """A test that silently depends on a sibling checkout is a test that cannot
    be trusted when it passes. The script must say what it could not find."""
    src = (ROOT / "scripts" / "build_spell_registry.py").read_text()
    assert "no such campaign package" in src, \
        "the script does not say which package it wanted"
