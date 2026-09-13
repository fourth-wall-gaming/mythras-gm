"""CFI is the base and no new spells are written, so anything CFI has no entry
for is a Mythras power. These pin that boundary in the places it can rot: the
schema, the CLI, the round trip, and the audit that compares sheets to books."""
import json
import subprocess
import sys
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


def test_registry_is_current():
    """Regenerating must be a no-op, or the audit is describing an older game."""
    before = (GM / "spell_registry.json").read_text()
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_spell_registry.py")],
                   check=True, capture_output=True)
    assert (GM / "spell_registry.json").read_text() == before
