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


def test_ids_splits_a_list():
    assert gm._ids("a, b ,c") == ["a", "b", "c"]
    assert gm._ids("") == []
    assert gm._ids(None) == []
    assert gm._ids("solo") == ["solo"]


def test_learn_takes_a_list_of_knowers():
    """Writing one edge should not need a shell loop -- that is how the sixth
    edge ends up not written at all."""
    parser = gm.build_parser()
    sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
    args = sub.choices["learn"].parse_args(["--knower", "a,b,c", "--fact", "f"])
    assert gm._ids(args.knower) == ["a", "b", "c"]


@pytest.mark.parametrize("cmd", ["add-fact", "establish-fact"])
def test_fact_commands_can_write_the_edge_in_the_same_call(cmd):
    """The edge belongs in the call that lands the fact, not a later one."""
    parser = gm.build_parser()
    sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
    dests = {a.dest for a in sub.choices[cmd]._actions}
    assert "learned_by" in dests
    assert "certainty" in dests
    assert "source" in dests


def test_known_by_is_still_a_filter_not_a_writer():
    """list-facts --known-by filters; the writer is --learned-by. Two flags,
    two meanings, deliberately not the same word."""
    parser = gm.build_parser()
    sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
    assert "known_by" in {a.dest for a in sub.choices["list-facts"]._actions}
    assert "learned_by" not in {a.dest for a in sub.choices["list-facts"]._actions}


def test_query_rules_has_an_explicit_match_mode():
    """The docs promised AND while the code did OR. Now it is a flag."""
    parser = gm.build_parser()
    sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
    action = [a for a in sub.choices["query-rules"]._actions if a.dest == "match"][0]
    assert action.default == "any"
    assert set(action.choices) == {"any", "all"}


def test_list_facets_exists_so_a_query_need_not_guess():
    parser = gm.build_parser()
    sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
    assert "list-facets" in sub.choices
    assert hasattr(gm, "cmd_list_facets")
    assert hasattr(gm, "_facet_vocabulary")


def test_get_log_can_reach_the_narrative():
    """log-event --narrative was write-only until --full existed."""
    parser = gm.build_parser()
    sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
    dests = {a.dest for a in sub.choices["get-log"]._actions}
    assert {"full", "session", "limit", "type"} <= dests


# --- packaging -------------------------------------------------------------

import json as _json
import re as _re

ROOT = Path(__file__).resolve().parent.parent


def test_the_hook_and_the_cli_agree_on_the_database():
    """The original clean-install failure: the hook loaded this skill's schema
    into alhazen-core's database while the CLI read its own, so every query
    came back empty on a fresh machine."""
    src = (ROOT / "skills" / "mythras-gm" / "mythras_gm.py").read_text()
    default = _re.search(r'TYPEDB_DATABASE = os\.getenv\("TYPEDB_DATABASE", "([^"]+)"\)', src).group(1)
    hook = _json.loads((ROOT / "hooks" / "hooks.json").read_text())
    cmd = hook["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert 'export TYPEDB_DATABASE=' in cmd
    assert default in cmd, f"hook does not export {default}"
    assert (ROOT / "skills" / "mythras-gm" / ".standalone-db").exists()


def test_the_hook_says_so_when_it_cannot_set_the_game_up():
    """It used to echo a note and exit 0 into a session with no schema."""
    hook = _json.loads((ROOT / "hooks" / "hooks.json").read_text())
    cmd = hook["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert cmd.count("CANNOT run") >= 3, "each failure path must say the game cannot run"
    for probe in ("init failed", "schema load failed", "not found"):
        assert probe in cmd


def test_versions_are_in_step():
    plugin = _json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
    pyproject = _re.search(
        r'^version\s*=\s*"([^"]+)"',
        (ROOT / "skills" / "mythras-gm" / "pyproject.toml").read_text(), _re.M).group(1)
    assert plugin == pyproject, f"plugin.json {plugin} != pyproject {pyproject}"


def test_the_commands_exist_and_declare_themselves():
    for name in ("play", "audit"):
        p = ROOT / "commands" / f"{name}.md"
        assert p.exists(), f"missing /mythras-gm:{name}"
        assert p.read_text().startswith("---"), "command needs frontmatter"
        assert "description:" in p.read_text()


def test_retrieval_agents_are_flat_read_only_and_declare_a_miss():
    """The deleted agents/gamemaster/ failed three ways: a nested shape that was
    never discovered, write tools, and a second set of GM conduct rules that
    contradicted TABLE.md. These must not repeat any of it."""
    agents = sorted((ROOT / "agents").glob("*.md"))
    assert {p.stem for p in agents} == {"rules-lookup", "setting-lookup", "recall"}
    assert not list((ROOT / "agents").glob("*/*.md")), "agents must be flat files"
    for p in agents:
        body = p.read_text()
        fm = body.split("---")[1]
        assert _re.search(r"^name:\s*" + p.stem + r"\s*$", fm, _re.M)
        tools = _re.search(r"^tools:\s*(.+)$", fm, _re.M).group(1)
        assert "Write" not in tools and "Edit" not in tools
        assert "NOT FOUND" in body or "NOT ESTABLISHED" in body or "NOT IN THE JOURNAL" in body, \
            f"{p.stem} must have an explicit miss contract"
        assert "Never write to the database" in body


def test_skill_yaml_version_is_in_step_too():
    """A third file carries the version; it drifted out of the earlier check."""
    plugin = _json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
    sy = (ROOT / "skills" / "mythras-gm" / "skill.yaml").read_text()
    assert _re.search(r"^version:\s*" + _re.escape(plugin) + r"\s*$", sy, _re.M), \
        f"skill.yaml is not at {plugin}"
