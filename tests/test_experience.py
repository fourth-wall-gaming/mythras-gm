"""award-experience and improve-skill.

The rules graph has told GMs to run these two commands since it was written,
and neither existed. The gap surfaced at the table: a session ended, three
experience rolls were owed, `get-rule skill/experience` said to use
`award-experience` and `improve-skill`, and both were unknown commands. The
rolls were done by hand with a shell loop.

The rule, verbatim from skill/experience:

    Award 1-3 Experience Rolls per session at natural break points. The player
    rolls 1d100+INT vs the skill: >= skill -> +1d4+1%; < skill -> +1%. Skills
    fumbled during play gain a free +1%.

Two things in that are easy to get backwards and are pinned below. The roll is
1d100 PLUS INT against the skill, so a LOW skill is easy to beat and improves
fast while a high one grinds -- the opposite of a roll-under check, and the
reason a 51 went to 52 while a 56 went to 61 in the same session. And the
fumble point is free: it costs no experience roll, because it is awarded for
having failed badly rather than for having been taught.
"""
import io
import json
import contextlib

import pytest

import mythras_gm as gm


def run(cmd, *, expect_success=True, **flags):
    argv = [cmd]
    for key, value in flags.items():
        if value is None:
            continue
        flag = "--" + key.replace("_", "-")
        argv += [flag] if value is True else [flag, str(value)]
    args = gm.build_parser().parse_args(argv)
    if hasattr(args, "campaign"):
        args.campaign = gm.resolve_campaign(args.campaign)
    gm._resolve_aliases(args)
    fn = getattr(gm, "cmd_" + cmd.replace("-", "_"))
    buf = io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf):
            fn(args)
    except SystemExit as exc:
        code = exc.code or 0
    raw = buf.getvalue().strip()
    assert raw, f"`{cmd}` produced no output"
    payload = json.loads(raw.splitlines()[-1])
    if expect_success:
        assert payload.get("success") is not False, f"`{cmd}` failed: {payload}"
        assert code == 0
    return payload


STATS = '{"STR":12,"CON":13,"SIZ":11,"DEX":14,"INT":13,"POW":12,"CHA":11}'


@pytest.fixture
def pc(throwaway_database):
    """A fresh character per test: these commands mutate skills and rolls."""
    if throwaway_database is None:
        pytest.skip("TypeDB unreachable")
    camp = run("create-campaign", name="XP")["id"]
    cid = run("create-character", campaign=camp, name="Scholar", type="pc",
              species="humanoid", stats=STATS,
              skills='{"Crossing":51,"Athletics":56,"Influence":39,"Insight":41}',
              passions='{"Love (testing)":70}',
              combat_styles='{"Drill (baton)":45}')["id"]
    yield {"campaign": camp, "id": cid}
    run("delete-campaign", campaign=camp, yes=True)


def skills_of(cid):
    c = run("get-character", id=cid)["character"]
    s = c["myth-skills-json"]
    return json.loads(s) if isinstance(s, str) else s


def rolls_of(cid):
    return run("get-character", id=cid)["character"]["myth-experience-rolls"]


# --- award-experience ------------------------------------------------------

def test_award_experience_adds_rolls(pc):
    assert rolls_of(pc["id"]) == 0
    r = run("award-experience", id=pc["id"], rolls=3)
    assert r["experience_rolls"] == 3
    assert rolls_of(pc["id"]) == 3


def test_award_experience_accumulates_rather_than_replacing(pc):
    """A GM who awards after each of two sessions must not silently overwrite
    the first award."""
    run("award-experience", id=pc["id"], rolls=2)
    run("award-experience", id=pc["id"], rolls=1)
    assert rolls_of(pc["id"]) == 3


def test_award_experience_defaults_to_one(pc):
    run("award-experience", id=pc["id"])
    assert rolls_of(pc["id"]) == 1


def test_award_experience_refuses_a_nonsense_count(pc):
    r = run("award-experience", id=pc["id"], rolls=0, expect_success=False)
    assert r["success"] is False
    assert rolls_of(pc["id"]) == 0


# --- improve-skill ---------------------------------------------------------

def test_improve_spends_a_roll(pc):
    run("award-experience", id=pc["id"], rolls=2)
    run("improve-skill", id=pc["id"], skill="Crossing")
    assert rolls_of(pc["id"]) == 1


def test_improve_refuses_with_no_rolls_left(pc):
    """Spending experience nobody awarded is how a sheet drifts upward between
    sessions without anybody deciding to."""
    r = run("improve-skill", id=pc["id"], skill="Crossing",
            expect_success=False)
    assert r["success"] is False
    assert skills_of(pc["id"])["Crossing"] == 51, "the skill moved anyway"


def test_beating_the_skill_gains_1d4_plus_1(pc):
    """1d100+INT >= skill. With INT 13 and a roll of 93 that is 106 against 56,
    which beats it, so the gain is 1d4+1 -- between 2 and 5."""
    run("award-experience", id=pc["id"], rolls=1)
    r = run("improve-skill", id=pc["id"], skill="Athletics", roll=93)
    assert r["beat"] is True
    assert r["total"] == 106
    assert 2 <= r["gain"] <= 5, r
    assert r["from"] == 56
    assert r["to"] == 56 + r["gain"]
    assert skills_of(pc["id"])["Athletics"] == r["to"]


def test_falling_short_gains_exactly_one(pc):
    """19+13 = 32 against 51. Falls short, so +1 and no dice."""
    run("award-experience", id=pc["id"], rolls=1)
    r = run("improve-skill", id=pc["id"], skill="Crossing", roll=19)
    assert r["beat"] is False
    assert r["total"] == 32
    assert r["gain"] == 1
    assert r["to"] == 52
    assert skills_of(pc["id"])["Crossing"] == 52


def test_int_is_added_to_the_roll_not_subtracted(pc):
    """The check is 1d100+INT vs the skill, so a LOW skill is easy to beat.
    Getting the sign wrong would make bad skills nearly unimprovable, which is
    backwards and would have gone unnoticed for a long time."""
    run("award-experience", id=pc["id"], rolls=1)
    r = run("improve-skill", id=pc["id"], skill="Influence", roll=30)
    assert r["total"] == 43, "INT 13 was not added to the roll"
    assert r["beat"] is True, "43 beats Influence 39 and must gain 1d4+1"


def test_the_boundary_is_greater_than_or_equal(pc):
    """'>= skill' -- an exact tie beats it."""
    run("award-experience", id=pc["id"], rolls=1)
    r = run("improve-skill", id=pc["id"], skill="Crossing", roll=38)
    assert r["total"] == 51
    assert r["beat"] is True, "a tie must count as beating the skill"


def test_improve_reports_which_skill_it_resolved(pc):
    """Partial names are allowed everywhere else in this CLI, and silently
    improving the wrong skill is worse than an error."""
    run("award-experience", id=pc["id"], rolls=1)
    r = run("improve-skill", id=pc["id"], skill="cross", roll=19)
    assert r["skill"] == "Crossing"


def test_improve_can_raise_a_combat_style(pc):
    run("award-experience", id=pc["id"], rolls=1)
    r = run("improve-skill", id=pc["id"], skill="Drill", roll=99)
    assert r["skill"] == "Drill (baton)"
    c = run("get-character", id=pc["id"])["character"]
    styles = c["myth-combat-styles-json"]
    styles = json.loads(styles) if isinstance(styles, str) else styles
    assert styles["Drill (baton)"] == r["to"]


def test_improve_can_raise_a_passion(pc):
    run("award-experience", id=pc["id"], rolls=1)
    r = run("improve-skill", id=pc["id"], skill="Love (testing)", roll=99)
    c = run("get-character", id=pc["id"])["character"]
    passions = c["myth-passions-json"]
    passions = json.loads(passions) if isinstance(passions, str) else passions
    assert passions["Love (testing)"] == r["to"]


def test_improve_leaves_the_other_skills_alone(pc):
    """The write is a merge. A replace would wipe every skill not named."""
    run("award-experience", id=pc["id"], rolls=1)
    run("improve-skill", id=pc["id"], skill="Crossing", roll=19)
    after = skills_of(pc["id"])
    assert after["Athletics"] == 56
    assert after["Influence"] == 39
    assert after["Insight"] == 41


def test_improve_rejects_an_unknown_skill_without_spending_the_roll(pc):
    run("award-experience", id=pc["id"], rolls=1)
    r = run("improve-skill", id=pc["id"], skill="Underwater Basketweaving",
            expect_success=False)
    assert r["success"] is False
    assert rolls_of(pc["id"]) == 1, "a failed improve still spent the roll"


# --- the free fumble point -------------------------------------------------

def test_a_fumbled_skill_gains_one_point_for_free(pc):
    """'Skills fumbled during play gain a free +1%.' Free means it costs no
    experience roll: it is awarded for having failed badly, not for study."""
    r = run("improve-skill", id=pc["id"], skill="Insight", fumbled=True)
    assert r["gain"] == 1
    assert r["to"] == 42
    assert r["fumbled"] is True
    assert skills_of(pc["id"])["Insight"] == 42
    assert rolls_of(pc["id"]) == 0, "the fumble point spent a roll"


def test_the_fumble_point_does_not_roll_at_all(pc):
    r = run("improve-skill", id=pc["id"], skill="Insight", fumbled=True)
    assert r.get("roll") is None and r.get("total") is None, \
        "the free point must not involve a check"
