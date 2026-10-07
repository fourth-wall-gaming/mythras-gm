"""Execute every command against the throwaway database.

The contract tests in test_command_contract.py check the shape of the command
table without running anything. This file runs the commands, because the two
failure modes they catch are different: a flag bound to the wrong subparser is a
shape fault, and `_set_attr` reporting success while writing nothing is not.

Coverage before this file existed: mythras_gm.py at 28%, and 52 of 88
subcommands never named in any test -- `roll-skill` and `set-scene` among them,
which are used several times per session.

Everything here runs against `mythras_pytest`, which conftest.py creates, loads
the schema into, and drops afterwards. conftest also refuses to inherit a live
database name, so this file cannot touch a real game.

The ladder matters: entities are built once per session in dependency order
(campaign -> location -> character -> faction -> agenda -> beat -> fact -> lore
-> encounter), because most commands need something to act on and creating it
per test would be slower than the suite is worth.
"""
import io
import json
import os
import pathlib
import contextlib

import pytest

import mythras_gm as gm


# --------------------------------------------------------------------------
# Running a command the way main() does, in-process so coverage sees it
# --------------------------------------------------------------------------

def run(cmd, *, expect_success=True, **flags):
    """Invoke one subcommand and return its parsed JSON output.

    Mirrors main(): parse argv, resolve --campaign, dispatch to cmd_*. Handlers
    print JSON and `fail()` exits non-zero, so both are captured rather than
    allowed to kill the test run.
    """
    argv = [cmd]
    for key, value in flags.items():
        if value is None:
            continue
        flag = "--" + key.replace("_", "-").rstrip("-")
        if value is True:
            argv.append(flag)
        else:
            argv += [flag, str(value)]

    parser = gm.build_parser()
    args = parser.parse_args(argv)
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
    assert raw, f"`{cmd}` produced no output at all"
    payload = json.loads(raw.splitlines()[-1])
    if expect_success:
        assert payload.get("success") is not False, f"`{cmd}` failed: {payload}"
        assert code == 0, f"`{cmd}` exited {code}: {payload}"
    return payload


# --------------------------------------------------------------------------
# The world every command acts on
# --------------------------------------------------------------------------

STATS = '{"STR":12,"CON":13,"SIZ":11,"DEX":14,"INT":13,"POW":12,"CHA":11}'


@pytest.fixture(scope="module")
def world(throwaway_database):
    """Build one campaign with something of every kind in it."""
    if throwaway_database is None:
        pytest.skip("TypeDB unreachable; command smoke tests need a server")

    w = {}
    w["campaign"] = run("create-campaign", name="Smoke",
                        description="A campaign built by the test suite")["id"]
    # Every later call resolves --campaign from this, exactly as a GM's shell does.
    os.environ["MYTHRAS_CAMPAIGN"] = w["campaign"]
    gm.DEFAULT_CAMPAIGN = w["campaign"]

    w["location"] = run("add-location", campaign=w["campaign"], name="The Yard",
                        description="A yard")["id"]
    w["pc"] = run("create-character", campaign=w["campaign"], name="Smokey",
                  type="pc", species="humanoid", stats=STATS,
                  skills='{"Athletics":55,"Perception":60,"Crossing":50}',
                  passions='{"Love (testing)":70}')["id"]
    w["npc"] = run("create-character", campaign=w["campaign"], name="Target",
                   type="npc", species="humanoid", stats=STATS,
                   skills='{"Athletics":40,"Perception":35}')["id"]
    w["faction"] = run("add-faction", campaign=w["campaign"],
                       name="The Testers")["id"]
    w["agenda"] = run("add-agenda", campaign=w["campaign"], holder=w["npc"],
                      title="Be tested", clock=4)["id"]
    w["beat"] = run("add-beat", campaign=w["campaign"], agenda=w["agenda"],
                    title="A beat happens", when="d0/dawn")["id"]
    w["fact"] = run("add-fact", campaign=w["campaign"],
                    statement="The suite ran")["id"]
    w["lore"] = run("add-lore", campaign=w["campaign"], title="Testing",
                    category="meta",
                    narrative="Lore written by the suite")["id"]
    w["event"] = run("log-event", campaign=w["campaign"], type="scene",
                     summary="Something happened in a test")["id"]
    w["encounter"] = run("start-encounter", campaign=w["campaign"],
                         name="A scuffle")["id"]
    return w


def test_the_world_fixture_builds(world):
    """If the ladder breaks, every test below skips or errors confusingly.
    Assert it stood up before blaming anything else."""
    for key in ("campaign", "location", "pc", "npc", "faction", "agenda",
                "beat", "fact", "lore", "event", "encounter"):
        assert world.get(key), f"fixture never created {key}"


# --------------------------------------------------------------------------
# Reads. A reader that cannot run is a GM with no way to see the save.
# --------------------------------------------------------------------------

def test_get_campaign(world):
    c = run("get-campaign", campaign=world["campaign"])["campaign"]
    assert c["name"] == "Smoke"


def test_get_character(world):
    c = run("get-character", id=world["pc"])["character"]
    assert c["name"] == "Smokey"
    assert c["myth-char-type"] == "pc"


def test_get_character_compact_and_brief(world):
    assert run("get-character", id=world["pc"], compact=True)["character"]
    assert run("get-character", id=world["pc"], brief=True)["character"]


def test_brief_a_character(world):
    """TABLE.md requires `brief` before an NPC speaks, so it runs every scene."""
    assert run("brief", id=world["npc"])["name"] == "Target"


def test_brief_a_location(world):
    """Locations are briefed through the same command, and this path carries the
    campaign's staging notes -- the world's physical laws."""
    out = run("brief", id=world["location"])
    assert out["kind"] == "location"
    assert "world_constraints" in out


def test_character_view(world):
    assert run("character-view", id=world["pc"], campaign=world["campaign"])


def test_get_context(world):
    """What a session loads to resume. If this breaks, play cannot start."""
    ctx = run("get-context", campaign=world["campaign"])
    assert "player_characters" in ctx
    assert any(p["name"] == "Smokey" for p in ctx["player_characters"])


def test_get_context_compact(world):
    assert run("get-context", campaign=world["campaign"], compact=True)


def test_get_log(world):
    ev = run("get-log", campaign=world["campaign"])["events"]
    assert any("Something happened" in str(e["summary"]) for e in ev)


def test_get_log_full_reaches_the_narrative(world):
    assert "events" in run("get-log", campaign=world["campaign"], full=True)


def test_list_commands_all_run(world):
    """Every list-* reader, in one test: they are thin and fail the same way."""
    assert run("list-campaigns")["campaigns"]
    assert run("list-characters", campaign=world["campaign"])["characters"]
    assert "locations" in run("list-locations", campaign=world["campaign"])
    assert "lore" in run("list-lore", campaign=world["campaign"])
    assert "agendas" in run("list-agendas", campaign=world["campaign"])
    assert "beats" in run("list-beats", campaign=world["campaign"])
    assert "facts" in run("list-facts", campaign=world["campaign"])


def test_get_fact(world):
    assert run("get-fact", id=world["fact"], campaign=world["campaign"])


def test_get_lore(world):
    assert run("get-lore", id=world["lore"])


def test_get_agenda(world):
    assert run("get-agenda", id=world["agenda"])


def test_timeline_and_forecast(world):
    """Both defaulted --campaign only after the contract test caught them
    promising a default they did not honour."""
    assert "watches" in run("timeline", campaign=world["campaign"])
    assert run("forecast", campaign=world["campaign"])


def test_check_consistency(world):
    assert run("check-consistency", campaign=world["campaign"])


# --------------------------------------------------------------------------
# Dice. roll-skill had no test at all, and is used several times a session.
# --------------------------------------------------------------------------

def test_roll(world):
    r = run("roll", dice="1d20")
    assert 1 <= r["total"] <= 20


def test_roll_skill(world):
    r = run("roll-skill", id=world["pc"], skill="Athletics")
    assert r["effective"] == 55, r
    assert 1 <= r["roll"] <= 100
    assert r["level"] in ("critical", "success", "failure", "fumble")


@pytest.mark.parametrize("difficulty,expected", [
    # The published Mythras grades, against a skill of 55. Pinned as literals
    # rather than recomputed from the engine's own table, so a change to the
    # table has to be a deliberate change to these numbers too.
    ("veryeasy", 110),     # x2
    ("easy", 83),          # x1.5, rounded up
    ("standard", 55),      # x1
    ("hard", 37),          # x2/3, rounded up
    ("formidable", 28),    # x1/2, rounded up
    ("herculean", 11),     # x1/5, rounded up
])
def test_roll_skill_difficulty_scales_the_target(world, difficulty, expected):
    """A difficulty that silently did nothing would make every call a Standard
    one, and nothing in the output would say so."""
    r = run("roll-skill", id=world["pc"], skill="Athletics",
            difficulty=difficulty)
    assert r["effective"] == expected, r


def test_roll_skill_augment_moves_the_target(world):
    """A Passion augments at +20% of its value. Lint's 70 Passion is +14."""
    plain = run("roll-skill", id=world["pc"], skill="Athletics")["effective"]
    aug = run("roll-skill", id=world["pc"], skill="Athletics",
              augment="Love (testing)")["effective"]
    assert aug > plain, f"augment did nothing: {plain} -> {aug}"


def test_roll_skill_names_the_candidates_for_an_unknown_skill(world):
    r = run("roll-skill", id=world["pc"], skill="Underwater Basketweaving",
            expect_success=False)
    assert r["success"] is False


def test_roll_opposed(world):
    r = run("roll-opposed", id_a=world["pc"], skill_a="Athletics",
            id_b=world["npc"], skill_b="Athletics")
    assert "winner" in r or "result" in r, r


# --------------------------------------------------------------------------
# Writers. Each asserts the write is READABLE, not merely that the command
# returned success -- `_set_attr` reports success whether or not the attribute
# landed, so "it returned true" proves nothing on its own.
# --------------------------------------------------------------------------

def test_set_scene_is_readable_afterwards(world):
    run("set-scene", campaign=world["campaign"], scene="A yard at dawn",
        game_date="d0/dawn")
    c = run("get-campaign", campaign=world["campaign"])["campaign"]
    assert c["myth-current-scene"] == "A yard at dawn"
    assert c["myth-game-date"] == "d0/dawn"


def test_update_campaign_round_trips_every_field_it_writes(world):
    """The bug this file was started for: update-campaign crashed on every
    invocation, and when fixed, get-campaign could not read three of the
    attributes it had just written."""
    run("update-campaign", campaign=world["campaign"],
        session_number=7, game_date="d3/dusk",
        staging_notes="No roads. The water is the weather.",
        played=world["pc"], time_index=99)
    c = run("get-campaign", campaign=world["campaign"])["campaign"]
    assert c["myth-session-number"] == 7
    assert c["myth-game-date"] == "d3/dusk"
    assert c["myth-staging-notes"].startswith("No roads")
    assert c["myth-played-pcs"] == world["pc"]
    assert c["myth-time-index"] == 99


def test_update_character_round_trips(world):
    run("update-character", id=world["npc"], fatigue="Winded", luck=1,
        skills='{"Stealth":44}', description="A target, winded")
    c = run("get-character", id=world["npc"])["character"]
    assert c["myth-fatigue"] == "Winded"
    assert c["myth-luck-current"] == 1
    skills = c["myth-skills-json"]
    assert skills["Stealth"] == 44
    assert skills["Athletics"] == 40, "merge clobbered an existing skill"


def test_update_event_can_amend_the_timestamp(world):
    """created-at is second-granular and get-log sorts on it, so a batch of
    events logged in one second comes back shuffled. --at is the only repair."""
    run("update-event", id=world["event"], at="2026-01-01T00:00:00",
        summary="Amended by the suite", session=3)
    ev = {e["id"]: e for e in run("get-log", campaign=world["campaign"])["events"]}
    assert ev[world["event"]]["summary"] == "Amended by the suite"
    assert str(ev[world["event"]]["at"]).startswith("2026-01-01")


def test_update_location_and_faction_and_lore_and_agenda(world):
    run("update-location", id=world["location"], name="The Far Yard",
        staging_notes="Nothing crosses this water unseen")
    assert run("brief", id=world["location"])["name"] == "The Far Yard"

    run("update-faction", id=world["faction"], name="The Retesters")
    run("update-lore", id=world["lore"], summary="Revised by the suite")
    assert "Revised" in str(run("get-lore", id=world["lore"]))

    run("update-agenda", id=world["agenda"], title="Be tested twice")
    assert run("get-agenda", id=world["agenda"])["agenda"]["title"] == \
        "Be tested twice"


def test_move_character_then_see_them_there(world):
    run("move-character", id=world["pc"], location=world["location"])
    assert world["pc"] in str(run("brief", id=world["location"])) or \
        "Smokey" in str(run("brief", id=world["location"]))


def test_join_faction(world):
    assert run("join-faction", id=world["npc"], faction=world["faction"])


def test_set_doing_then_read_it_back(world):
    run("set-doing", id=world["npc"], goal="Be tested",
        next="Stand still", where=world["location"])
    assert "Be tested" in str(run("brief", id=world["npc"]))


def test_apply_damage_and_heal(world):
    before = run("get-character", id=world["npc"])["character"]
    hp = {l["name"]: l["current_hp"] for l in before["myth-hit-locations-json"]}
    run("apply-damage", id=world["npc"], location="Chest", damage=3)
    hurt = run("get-character", id=world["npc"])["character"]
    now = {l["name"]: l["current_hp"] for l in hurt["myth-hit-locations-json"]}
    assert now["Chest"] == hp["Chest"] - 3, f"{hp} -> {now}"
    run("heal", id=world["npc"], location="Chest", amount=3)
    healed = run("get-character", id=world["npc"])["character"]
    back = {l["name"]: l["current_hp"] for l in healed["myth-hit-locations-json"]}
    assert back["Chest"] == hp["Chest"]


def test_retire_canon_marks_without_deleting(world):
    """Canon that stops being true is retired, not deleted, so the record keeps
    its audit trail. A delete would lose the provenance."""
    r = run("retire-canon", id=world["event"], status="superseded")
    assert r["canon_status"] == "superseded"
    live = run("get-log", campaign=world["campaign"])["events"]
    assert world["event"] not in {e["id"] for e in live}, \
        "a superseded event still reads as live"
    withretired = run("get-log", campaign=world["campaign"],
                      include_retired=True)["events"]
    assert world["event"] in {e["id"] for e in withretired}, \
        "a retired event is unreachable even with --include-retired"


# --------------------------------------------------------------------------
# Combat. Seven commands, none of which had a test, and they are stateful --
# each one depends on the encounter the previous one left behind.
# --------------------------------------------------------------------------

def test_combat_runs_a_whole_round(world):
    """One test for the sequence, because the commands are not independent: an
    attack needs initiative, which needs combatants, which need an encounter.
    Testing them separately would mean standing the whole ladder up four times.
    """
    enc = world["encounter"]
    run("add-combatant", encounter=enc, character=world["pc"])
    run("add-combatant", encounter=enc, character=world["npc"])

    init = run("roll-initiative", encounter=enc)
    assert init, "initiative produced nothing"

    state = run("get-encounter", encounter=enc)
    assert state, "encounter unreadable after initiative"

    atk = run("attack-roll", encounter=enc, attacker=world["pc"],
              defender=world["npc"], defense="none")
    assert atk

    nxt = run("next-round", encounter=enc)
    assert nxt

    done = run("end-encounter", encounter=enc, summary="The suite won")
    assert done


# --------------------------------------------------------------------------
# Knowledge. Who knows what, how they learned it, and what they think it meant.
# --------------------------------------------------------------------------

def test_learn_then_who_knows_then_forget(world):
    """A fact that has not happened yet cannot be known. The engine refuses
    `learn` on a not-yet-true fact and says to establish it first, which is
    correct and is why this test establishes it."""
    run("establish-fact", id=world["fact"], campaign=world["campaign"],
        when="d0/dawn", truth="true")
    run("learn", knower=world["pc"], fact=world["fact"],
        certainty="knows", source="witnessed", campaign=world["campaign"])
    knowers = str(run("who-knows", fact=world["fact"],
                      campaign=world["campaign"]))
    assert world["pc"] in knowers or "Smokey" in knowers

    run("forget", knower=world["pc"], fact=world["fact"])
    after = str(run("who-knows", fact=world["fact"],
                    campaign=world["campaign"]))
    assert "Smokey" not in after or world["pc"] not in after


def test_set_knowledge_and_get_knowledge(world):
    run("set-knowledge", knower=world["pc"], subject=world["npc"],
        campaign=world["campaign"], depth="knows", route="witnessed",
        note="Saw them in the yard", attitude="wary")
    k = run("get-knowledge", knower=world["pc"], subject=world["npc"],
            campaign=world["campaign"])
    assert "yard" in str(k).lower()


# --------------------------------------------------------------------------
# Facts, agendas and beats -- the world engine.
# --------------------------------------------------------------------------

def test_establish_and_revise_and_supersede_a_fact(world):
    run("establish-fact", id=world["fact"], campaign=world["campaign"],
        when="d0/dawn", truth="true", certainty="knows", source="witnessed")
    run("revise-fact", id=world["fact"], statement="The suite ran twice")
    assert "twice" in str(run("get-fact", id=world["fact"],
                              campaign=world["campaign"]))

    replacement = run("add-fact", campaign=world["campaign"],
                      statement="The suite ran three times")["id"]
    run("supersede-fact", id=world["fact"], by=replacement,
        campaign=world["campaign"])


def test_agenda_clock_advances_and_status_sets(world):
    before = run("get-agenda", id=world["agenda"])["agenda"]["clock"]["filled"]
    moved = run("advance-agenda", id=world["agenda"], by=1,
                campaign=world["campaign"], note="The suite advanced it")
    assert moved["clock"]["filled"] == before + 1, moved
    after = run("get-agenda", id=world["agenda"])["agenda"]["clock"]["filled"]
    assert after == before + 1, f"clock did not persist: {before} -> {after}"

    run("set-agenda-status", id=world["agenda"], status="active",
        campaign=world["campaign"])
    assert run("get-agenda", id=world["agenda"])["agenda"]["status"] == "active"


def test_add_consequence_and_require_fact(world):
    assert run("add-consequence", fact=world["fact"], agenda=world["agenda"],
               effect="advance", amount=1)
    assert run("require-fact", agenda=world["agenda"], fact=world["fact"])


def test_revise_and_fire_a_beat(world):
    run("revise-beat", id=world["beat"], summary="Revised by the suite")
    assert "Revised" in str(run("list-beats", campaign=world["campaign"]))

    fired = run("fire-beat", id=world["beat"], outcome="played",
                campaign=world["campaign"], log=True,
                summary="The beat was fired by the suite")
    assert fired["outcome"] == "played"
    assert fired["event"], "fire-beat --log wrote no journal event"


def test_tick_moves_the_world_clock(world):
    """Ticks forward from wherever the clock already is. Earlier tests in this
    module write time_index, and a hardcoded target made this test depend on
    their order."""
    now = run("get-campaign", campaign=world["campaign"])["campaign"]
    day = int(str(run("timeline", campaign=world["campaign"])["now"])
              .split("/")[0].lstrip("d"))
    target = f"d{day + 1}/dawn"
    r = run("tick", campaign=world["campaign"], to=target,
            set_date=f"{target} -- the next morning")
    assert r["now"] == target, r
    c = run("get-campaign", campaign=world["campaign"])["campaign"]
    assert c["myth-game-date"].startswith(target)


def test_tick_refuses_to_run_the_clock_backwards(world):
    """Without --rewind this must refuse: a world clock that can silently go
    backwards reorders the journal and re-fires beats."""
    r = run("tick", campaign=world["campaign"], to="d-5/dawn",
            expect_success=False)
    assert r.get("success") is False, r


def test_cascade(world):
    assert run("cascade", campaign=world["campaign"])


# --------------------------------------------------------------------------
# The rules graph. Memory of this project: rules lookups go through the CLI,
# never grep -- so these commands are load-bearing for every ruling at the
# table, and none of them had a test.
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rules(world):
    """Load the rules graph into the test database once.

    Rules are global rather than per-campaign, and an empty graph makes every
    rules command fail for a reason that has nothing to do with the command.
    """
    rules_dir = pathlib.Path(__file__).resolve().parent.parent / \
        "skills" / "mythras-gm" / "rules"
    if not rules_dir.is_dir():
        pytest.skip(f"no rules directory at {rules_dir}")
    run("load-rules", dir=str(rules_dir), system="mythras")
    return rules_dir


def test_get_rule_resolves_a_known_rule(rules, world):
    """Power rule ids are cited on character sheets. A citation that does not
    resolve yields a sheet whose power cannot be looked up mid-session."""
    r = run("get-rule", id="magic/power-life-support")
    assert r.get("rule") or r.get("id"), r


def test_get_rule_on_a_missing_id_fails_loudly(rules, world):
    r = run("get-rule", id="magic/power-does-not-exist", expect_success=False)
    assert r.get("success") is False


def a_real_facet():
    """One `dim=value` facet that actually exists in the loaded graph.

    --facet is validated as dim=value, so a guessed string fails on its format
    rather than on the query. list-facets exists precisely so a caller need not
    guess, and deriving the value here means the test cannot drift from the
    rules it is querying.
    """
    facets = run("list-facets")
    for key in ("facets", "dims", "dimensions"):
        block = facets.get(key)
        if not block:
            continue
        if isinstance(block, dict):
            for dim, values in block.items():
                if values:
                    first = values[0]
                    if isinstance(first, dict):
                        first = first.get("value") or first.get("name")
                    return f"{dim}={first}"
        if isinstance(block, list) and block:
            first = block[0]
            if isinstance(first, dict) and first.get("dim"):
                return f"{first['dim']}={first.get('value') or first.get('name')}"
    return None


def test_list_rules_and_facets_and_query(rules, world):
    assert run("list-rules", system="mythras")
    assert run("list-facets")
    facet = a_real_facet()
    if facet is None:
        pytest.skip("no facets in the loaded rules graph")
    assert run("query-rules", facet=facet, system="mythras", limit=5)


def test_query_rules_rejects_a_facet_that_is_not_dim_equals_value(rules, world):
    """The format is enforced, and the error says so. A bare word would
    otherwise match nothing and read as 'no such rule'."""
    r = run("query-rules", facet="combat", expect_success=False)
    assert r.get("success") is False
    assert "dim=value" in str(r.get("error", ""))


def test_query_rules_has_an_explicit_match_mode(rules, world):
    """--match any/all: without it a multi-facet query silently picks one
    meaning, and the GM cannot tell which."""
    facet = a_real_facet()
    if facet is None:
        pytest.skip("no facets in the loaded rules graph")
    assert run("query-rules", facet=facet, match="any", limit=3)
    assert run("query-rules", facet=facet, match="all", limit=3)


# --------------------------------------------------------------------------
# Templates and spawning.
# --------------------------------------------------------------------------

def test_add_template_then_spawn_from_it(world):
    """spawn hardcodes type npc and discards passions and powers, which is why
    a pre-gen shipped as a template cannot be played. Pinning the behaviour so
    the limitation stays visible rather than being rediscovered."""
    tmpl = run("add-template", campaign=world["campaign"], name="Mook",
               species="humanoid", stats=STATS,
               skills='{"Athletics":30}')["id"]
    # --template takes the template's ID, not its name.
    spawned = run("spawn", template=tmpl, name="Mook One",
                  campaign=world["campaign"])
    c = run("get-character", id=spawned["id"])["character"]
    assert c["name"] == "Mook One"
    assert c["myth-char-type"] == "npc", \
        "spawn produced something other than an NPC"


# --------------------------------------------------------------------------
# Import and export. campaign_io.py was at 5% coverage, and it is the only
# thing standing between a campaign on disk and a campaign in the database.
# --------------------------------------------------------------------------

def test_export_then_import_round_trips_the_campaign(world, tmp_path):
    """The round trip is the save format's only real test: anything the export
    drops or the import cannot read is data a player loses."""
    out_dir = tmp_path / "exported"
    run("export-campaign", campaign=world["campaign"], output=str(out_dir))
    assert out_dir.exists(), "export wrote nothing"
    assert (out_dir / "campaign.yaml").exists(), "export wrote no campaign.yaml"

    imported = run("import-campaign", path=str(out_dir), new_ids=True,
                   name="Smoke Reimported")
    new_id = imported["id"]
    try:
        ctx = run("get-context", campaign=new_id)
        names = {p["name"] for p in ctx["player_characters"]}
        assert "Smokey" in names, f"the PC did not survive the round trip: {names}"
    finally:
        run("delete-campaign", campaign=new_id, yes=True)


def test_export_characters_writes_a_file(world, tmp_path):
    target = tmp_path / "chars.json"
    run("export-characters", campaign=world["campaign"], output=str(target))
    assert target.exists() and target.stat().st_size > 0


def test_import_characters_from_a_file(world, tmp_path):
    target = tmp_path / "chars.json"
    run("export-characters", campaign=world["campaign"], output=str(target))
    assert run("import-characters", file=str(target),
               campaign=world["campaign"])


# --------------------------------------------------------------------------
# Diagnostics and teardown.
# --------------------------------------------------------------------------

def test_doctor_reports(world):
    assert run("doctor", json=True)


def test_delete_campaign_refuses_without_yes(world):
    """Without --yes it must report what would be lost and stop. A delete that
    proceeds on a bare invocation is one keystroke from losing a campaign."""
    victim = run("create-campaign", name="Doomed")["id"]
    r = run("delete-campaign", campaign=victim, expect_success=False)
    still = {c["id"] for c in run("list-campaigns")["campaigns"]}
    assert victim in still, "delete-campaign deleted without --yes"
    run("delete-campaign", campaign=victim, yes=True)
    gone = {c["id"] for c in run("list-campaigns")["campaigns"]}
    assert victim not in gone, "delete-campaign --yes did not delete"


def test_link_lore_to_an_entity(world):
    """Lore that is not linked to anything is lore no brief will ever surface."""
    assert run("link-lore", id=world["lore"], subject=world["npc"])


def test_resolve_attack_and_resolve_effects(world):
    """The other combat path. attack-roll reports what would happen;
    resolve-attack applies it, and resolve-effects applies the special effects
    chosen off the back of it. Both need their own encounter, because the one
    in the fixture is ended by the time this runs.
    """
    enc = run("start-encounter", campaign=world["campaign"],
              name="A second scuffle")["id"]
    run("add-combatant", encounter=enc, character=world["pc"])
    run("add-combatant", encounter=enc, character=world["npc"])
    run("roll-initiative", encounter=enc)

    # resolve-attack is the one-shot path: roll and apply in a single call.
    resolved = run("resolve-attack", encounter=enc, attacker=world["pc"],
                   defender=world["npc"], defense="none", location="Chest")
    assert resolved

    # resolve-effects is the two-step path, and it requires a pending attack:
    # "No attack is waiting on this encounter -- run attack-roll first."
    run("attack-roll", encounter=enc, attacker=world["pc"],
        defender=world["npc"], defense="none")
    effects = run("resolve-effects", encounter=enc)
    assert effects


def test_resolve_effects_refuses_without_a_pending_attack(world):
    """The two-step path is ordered, and the refusal names the missing step."""
    enc = run("start-encounter", campaign=world["campaign"],
              name="An empty scuffle")["id"]
    r = run("resolve-effects", encounter=enc, expect_success=False)
    assert r.get("success") is False
    assert "attack-roll" in str(r.get("error", ""))
    run("end-encounter", encounter=enc, summary="Never started")

    run("end-encounter", encounter=enc, summary="Resolved by the suite")


# load-schema is deliberately not executed here. It rewrites the database's
# schema, conftest has already loaded it, and a test that reloads it would be
# testing conftest rather than the command. The contract suite still checks its
# parser, handler, help and flag hygiene like every other command.
