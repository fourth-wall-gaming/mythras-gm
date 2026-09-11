"""Regression tests for the table-prose auditor.

The point of these is not to check arithmetic on word counts. It is to pin the
DETECTORS: every banned construction in TABLE.md has a positive case here taken
from real play, and a negative case that must not trip. If someone loosens a
pattern to make a session pass, these fail.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "voice_audit.py"
_spec = importlib.util.spec_from_file_location("voice_audit", _SCRIPT)
va = importlib.util.module_from_spec(_spec)
sys.modules["voice_audit"] = va
_spec.loader.exec_module(va)


def hits(text, label=None):
    """Count banned-construction hits in a bare passage of prose."""
    found = {}
    for name, pat in va.BANNED:
        n = len(pat.findall(text))
        if n:
            found[name] = n
    return found.get(label, 0) if label else found


# --- positive cases, all lifted from the live transcript -------------------

@pytest.mark.parametrize("label,passage", [
    ("arithmetic-metaphor",
     "You can see the arithmetic happening behind her eyes."),
    ("arithmetic-metaphor",
     "First just the arithmetic of it, and then the fear."),
    ("furniture-metaphor",
     "Said twice in front of him as though he were furniture."),
    ("antithesis-correction",
     "It's not a word. It's the noise you make at a gate that's swollen shut."),
    ("antithesis-correction",
     "That's not a monster. That's a prisoner."),
    ("raised-finger",
     'He holds up a finger. "Leave the ring on him."'),
    ("raised-finger",
     "She holds up one finger and waits for the room."),
    ("punctuation-gesture",
     'He tilts his head slightly. "Or we can do the other thing."'),
    ("narrated-emotional-price",
     "You keep your face absolutely straight. It costs you something."),
    ("question-flattery",
     '"Nobody has ever asked me that before," she says.'),
    ("being-difficult",
     '"That is not me being difficult, that is the arrangement I am in."'),
    ("off-camera",
     "Meanwhile: nobody in this yard has looked twice at the litter."),
    ("assistant-register",
     "### Where we left off\n\nSanto is dead."),
])
def test_banned_construction_is_caught(label, passage):
    assert hits(passage, label) >= 1, f"{label} not detected in: {passage!r}"


# --- negative cases: house style and ordinary prose must not trip ----------

@pytest.mark.parametrize("passage", [
    # gully-burns signature moves are NOT tics and must survive.
    "A beat.",
    "Another beat, and then her composure went.",
    "It is never wise to appear distracted on the open streets.",
    "This was a mistake.",
    "The Lakelady's Javelin put an arrow through the awning.",
    # "furniture" is only banned as a METAPHOR; a room may contain some.
    "The room was bare of furniture except for a washstand and a chair.",
    # A legitimate question inside dialogue at the end of a turn.
    '"Do you have money?" she asks, and does not wait for an answer.',
    # Description with no gesture-punctuation.
    "She stands very straight and she has not taken her hand off the wolf.",
])
def test_house_style_and_plain_prose_do_not_trip(passage):
    assert hits(passage) == {}, f"false positive on: {passage!r}"


def test_arithmetic_is_banned_outright_even_when_literal():
    """A deliberate over-catch, recorded so nobody "fixes" it later.

    "arithmetic" is banned as a WORD in table prose, not merely as a metaphor.
    A character literally doing sums is vanishingly rare in a scene; the
    metaphorical use ("you can see the arithmetic happening", "he knows the
    arithmetic exactly") was the single most characteristic tic in the baseline
    transcript, at eight hits. Missing the tic is worse than occasionally
    flagging a clerk with a slate.
    """
    assert hits("He did the arithmetic on a slate.", "arithmetic-metaphor") == 1


# --- turn-level measurements ----------------------------------------------

def _transcript(tmp_path, *turns):
    body = ""
    for i, t in enumerate(turns):
        body += f"===== ASSISTANT [2026-09-06T00:0{i}:00.000Z] =====\n{t}\n\n"
    p = tmp_path / "t.md"
    p.write_text(body)
    return p


def test_turn_ending_on_a_question_is_flagged(tmp_path):
    r = va.audit(_transcript(tmp_path, "The door is open.\n\nWhat do you do?"))
    assert r["turns_ending_in_question"] == 1
    assert r["turns_containing_invitation"] == 1


def test_turn_ending_on_an_object_is_clean(tmp_path):
    r = va.audit(_transcript(tmp_path, "The door is open. The boat-hook leans\nagainst the wall where somebody put it down."))
    assert r["turns_ending_in_question"] == 0
    assert r["turns_containing_invitation"] == 0


def test_npc_question_inside_dialogue_is_not_a_trailing_question(tmp_path):
    r = va.audit(_transcript(tmp_path, 'She does not move.\n\n"Have you got three pennies?"'))
    assert r["turns_ending_in_question"] == 0


def test_mechanics_blocks_are_not_counted_as_prose(tmp_path):
    r = va.audit(_transcript(
        tmp_path,
        "She looks at the water.\n\n> ⟦ Gardwen · Insight (Hard 44) → 83 · failure ⟧\n\nNothing comes."))
    # 9 words of prose, the mechanics line stripped
    assert r["words_per_turn"]["max"] < 15


def test_quoted_line_lengths_are_measured(tmp_path):
    long_line = " ".join(["word"] * 70)
    r = va.audit(_transcript(tmp_path, f'He said, "{long_line}"'))
    assert r["quoted_line_words"]["over_60"] == 1


def test_targets_cover_every_table_rule_with_a_number():
    # If a numeric rule is added to TABLE.md it needs a target here too.
    assert set(va.TARGETS) == {
        "words_per_turn.median",
        "words_per_turn.p90",
        "words_per_turn.over_400",
        "quoted_line_words.p90",
        "quoted_line_words.over_60",
        "turns_ending_in_question",
        "banned_total",
    }
