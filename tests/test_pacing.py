"""Pacing: make the save notice when play has stopped being a game.

The failure this exists to catch is gradual and that is why a written rule does
not catch it. A GM runs one scene in a room, which is fine; a second, justified
by the first; a third, which is a continuation. No single step is wrong and the
table has not rolled a die in forty minutes.

The data was always there. Every logged event carries a type, so a run of
`scene` events with no `skill-roll` or `combat` between them IS the signal --
sitting in the journal, unexamined. This surfaces it in get-context, which is
what a GM loads at the start of a session and again mid-play.

Caught in a real session: a records office, a ready room, a registry, and a
councillor drafting a position, in a game for ten-to-fifteen-year-olds, while a
door that nobody understood sat unused two decks away.
"""
import mythras_gm as gm


def ev(type_, visibility="played"):
    return {"type": type_, "visibility": visibility}


def test_a_roll_in_the_last_events_is_not_drift():
    events = [ev("scene"), ev("skill-roll"), ev("scene")]
    assert gm.pacing_streak(events) == 1


def test_a_run_of_talking_scenes_is_counted():
    events = [ev("skill-roll"), ev("scene"), ev("decision"), ev("scene")]
    assert gm.pacing_streak(events) == 3


def test_combat_resets_it_too():
    events = [ev("scene"), ev("scene"), ev("combat")]
    assert gm.pacing_streak(events) == 0


def test_meta_and_bookkeeping_do_not_count_either_way():
    """A gm-note about the arc is not a scene and must not inflate the streak,
    or every session boundary would read as drift."""
    events = [ev("skill-roll"), ev("gm-note", "meta"),
              ev("session-end", "meta"), ev("scene")]
    assert gm.pacing_streak(events) == 1


def test_offscreen_events_do_not_count():
    """A beat fired offscreen is world movement, not a scene at the table."""
    events = [ev("skill-roll"), ev("scene", "offscreen"), ev("scene")]
    assert gm.pacing_streak(events) == 1


def test_an_empty_journal_is_not_drift():
    assert gm.pacing_streak([]) == 0


def test_the_threshold_is_three():
    """Two scenes in a row is ordinary. Three is the tell."""
    assert gm.PACING_WARN_AT == 3


def test_the_warning_says_what_to_do_about_it():
    warning = gm.pacing_warning(4)
    assert warning, "no warning produced at four"
    low = warning.lower()
    assert "4" in warning
    assert "cut" in low, "the warning does not say to cut"
    assert "physical" in low or "jeopardy" in low, \
        "the warning does not say what to cut TO"


def test_no_warning_below_the_threshold():
    assert gm.pacing_warning(2) is None
    assert gm.pacing_warning(0) is None


def test_get_context_reports_pacing():
    """It has to appear where a GM actually looks, which is get-context."""
    import inspect
    src = inspect.getsource(gm.cmd_get_context)
    assert "pacing" in src, "get-context does not report pacing"


# --- the committee detector ------------------------------------------------
#
# The second failure caught at the table: the player character reduced to a
# courier of narrative between NPCs who hold all the insights. Scenes-since-a-
# roll does not see it, because the rolls keep happening -- they are just rolls
# to persuade somebody in a room.
#
# The measurable proxy is CAST SIZE. Three or more NPCs in a room with the PC is
# a committee, and a committee is where agency goes to die.

def ev_cast(n, type_="scene", visibility="played"):
    return {"type": type_, "visibility": visibility,
            "who": [f"npc{i}" for i in range(n)]}


def test_a_two_hander_is_not_a_committee():
    assert gm.committee_streak([ev_cast(2), ev_cast(1)]) == 0


def test_three_npcs_counts():
    assert gm.committee_streak([ev_cast(1), ev_cast(3)]) == 1


def test_consecutive_committees_accumulate():
    assert gm.committee_streak([ev_cast(4), ev_cast(3), ev_cast(5)]) == 3


def test_a_small_scene_breaks_the_streak():
    assert gm.committee_streak([ev_cast(4), ev_cast(5), ev_cast(1)]) == 0


def test_a_roll_does_not_break_a_committee_streak():
    """This is the whole point: persuading four people in an office is still a
    committee, and the dice do not redeem it."""
    assert gm.committee_streak([ev_cast(4), ev_cast(4, "skill-roll")]) == 2


def test_the_committee_threshold_is_three():
    assert gm.COMMITTEE_AT == 3


def test_the_committee_warning_asks_the_right_question():
    w = gm.committee_warning(3)
    assert w
    low = w.lower()
    assert "3" in w
    assert "nobody else" in low or "can do" in low, \
        "the warning should ask what the PC can do that nobody else in the room can"


def test_no_committee_warning_below_two_in_a_row():
    assert gm.committee_warning(1) is None


def test_get_context_reports_the_committee_streak():
    import inspect
    src = inspect.getsource(gm.cmd_get_context)
    assert "committee" in src
