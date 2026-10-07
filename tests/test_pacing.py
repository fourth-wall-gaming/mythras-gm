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
