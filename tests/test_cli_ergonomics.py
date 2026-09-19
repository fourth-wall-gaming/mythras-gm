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


PREFLIGHT = ROOT / "hooks" / "session-start.sh"


def _hook_command():
    hook = _json.loads((ROOT / "hooks" / "hooks.json").read_text())
    return hook["hooks"]["SessionStart"][0]["hooks"][0]["command"]


def test_the_hook_delegates_to_a_script_we_can_read():
    """The hook used to be one 1,400-character line of shell inside JSON, which
    is why it went wrong and stayed wrong: nothing could read it, including us."""
    cmd = _hook_command()
    assert "session-start.sh" in cmd, "hook should call the script, not inline shell"
    assert len(cmd) < 120, f"hook command is growing shell again ({len(cmd)} chars)"
    assert PREFLIGHT.exists(), "hooks/session-start.sh is missing"


def test_the_hook_and_the_cli_agree_on_the_database():
    """The original clean-install failure: the hook loaded this skill's schema
    into alhazen-core's database while the CLI read its own, so every query
    came back empty on a fresh machine."""
    src = (ROOT / "skills" / "mythras-gm" / "mythras_gm.py").read_text()
    db = _re.search(r'TYPEDB_DATABASE = os\.getenv\("TYPEDB_DATABASE", "([^"]+)"\)', src).group(1)
    port = _re.search(r'TYPEDB_PORT = int\(os\.getenv\("TYPEDB_PORT", "([^"]+)"\)\)', src).group(1)
    pre = PREFLIGHT.read_text()
    assert 'export TYPEDB_DATABASE=' in pre and db in pre, f"preflight does not export {db}"
    assert 'export TYPEDB_PORT=' in pre and port in pre, f"preflight does not export port {port}"
    marker = (ROOT / "skills" / "mythras-gm" / ".standalone-db")
    assert marker.exists() and db in marker.read_text()
    # and the compose file must serve that port, or the hook points at nothing
    compose = (ROOT / "docker-compose.yml").read_text()
    assert f'"${{MYTHRAS_PORT:-{port}}}:1729"' in compose, \
        f"compose does not publish {port} by default"


def test_the_hook_says_so_when_it_cannot_set_the_game_up():
    """It used to echo a mild note and exit 0 into a session with no schema, so
    the model went on GMing with nothing persisting. The refusal has to be
    unmissable and it has to enumerate what not to do."""
    pre = PREFLIGHT.read_text()
    assert "PREFLIGHT FAILED" in pre
    for forbidden in ("do not narrate", "do not roll", "persisted"):
        assert forbidden in pre, f"refusal does not forbid: {forbidden}"
    assert "doctor" in pre, "refusal should hand the user a diagnostic"


def test_the_hook_never_blocks_and_never_pulls():
    """Two deliberate constraints. A user with this plugin enabled who opens
    Claude in an unrelated directory with Docker off must not have the session
    seized; and an image pull inside SessionStart is indistinguishable from a
    hang."""
    pre = PREFLIGHT.read_text()
    assert "exit 1" not in pre and "exit 2" not in pre, \
        "the preflight must not block the session"
    assert pre.count("exit 0") >= 3, "every path should exit 0"
    assert "--pull" not in pre, "the hook must never pull an image; that is /mythras-gm:setup"
    setup = (ROOT / "commands" / "setup.md").read_text()
    assert "--pull" in setup, "the slow path should be the one that pulls"


def test_no_shipped_doc_teaches_the_model_to_discard_errors():
    """`2>/dev/null` on every documented call is how a dead database looked like
    an empty one for a whole session."""
    for f in sorted(ROOT.glob("skills/**/*.md")) + sorted(ROOT.glob("commands/*.md")) \
            + sorted(ROOT.glob("agents/*.md")):
        assert "2>/dev/null" not in f.read_text(), f"{f.name} discards stderr"


def test_the_base_schema_covers_every_alh_supertype_used():
    """schema.tql inherits from alh- types that used to come from another
    plugin. If a new one is added there and not here, a fresh install fails on
    an undefined type."""
    skill = ROOT / "skills" / "mythras-gm"
    used = set(_re.findall(r"sub (alh-[a-z-]+)", (skill / "schema.tql").read_text()))
    base = (skill / "schema-base.tql").read_text()
    defined = set(_re.findall(r"entity (alh-[a-z-]+)", base))
    assert used, "expected schema.tql to inherit from alh- supertypes"
    assert used <= defined, f"schema-base.tql is missing: {sorted(used - defined)}"
    assert "owns id @key" in base, "id must keep @key -- it is what stops a double import"


def test_the_engine_declares_no_plugin_dependencies():
    """alhazen-core was absorbed. If it comes back, it needs a real
    `dependencies` entry and a cross-marketplace allowance, not a find glob."""
    plugin = _json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert not plugin.get("dependencies"), plugin.get("dependencies")
    assert "requires" not in plugin, "`requires` is not a real manifest field"
    assert "alhazen" not in PREFLIGHT.read_text(), "preflight still hunts for alhazen-core"


def test_the_marketplace_lists_the_campaign_too():
    """A campaign plugin has to be installable, and it must resolve inside this
    same marketplace or its dependency on the engine needs a cross-marketplace
    allowance."""
    mk = _json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    names = {p["name"] for p in mk["plugins"]}
    assert {"mythras-gm", "purewater"} <= names, names
    pw = next(p for p in mk["plugins"] if p["name"] == "purewater")
    assert pw["source"]["source"] == "github", "campaign should come from its own repo"
    assert pw["source"].get("ref"), "pin the campaign to a tag so installs are reproducible"


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


# --- GLAV migration --------------------------------------------------------

def test_migration_rules_parse_and_order():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "glav", ROOT / "scripts" / "glav_migrate.py")
    glav = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(glav)

    rules = glav.load_rules(ROOT / "migrations" / "legacy-mythras")
    assert len(rules) == 16
    ordered = glav.topological_sort(rules)
    seen = set()
    for r in ordered:
        assert set(r.depends_on) <= seen, f"{r.name} runs before its dependencies"
        seen.add(r.name)
    # entities must all precede the membership relation that links them
    names = [r.name for r in ordered]
    assert names.index("campaign") < names.index("campaign_membership")
    assert names.index("campaign_membership") < names.index("presence")


def test_substitute_keeps_the_terminator_when_the_last_line_drops():
    """Dropping a trailing optional attribute used to take the ';' with it,
    which TypeDB rejects with a syntax error a long way from the cause."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "glav", ROOT / "scripts" / "glav_migrate.py")
    glav = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(glav)

    tmpl = "insert $x isa t,\n  has id $id,\n  has content ?content,\n  has session ?session;"
    q = glav.substitute(tmpl, {"id": "abc"})          # both optionals absent
    assert q.endswith(";") and ",;" not in q.replace("\n", "")
    assert "?" not in q

    # datetimes go in bare; quoting them is a type error
    assert glav.format_value("2026-06-12T04:40:00.000000000") == "2026-06-12T04:40:00"
    assert glav.format_value("just a string").startswith('"')
    # type answers flatten to their label, for !raw substitution
    assert glav.normalise({"label": "myth-character", "kind": "entity"}) == "myth-character"


def test_tick_and_forecast_report_silent_agendas():
    """An active agenda with no pending beat is indistinguishable from one
    being pursued, so a character can quietly stop existing while their agenda
    still reads 'active'. A GM-run PC went eight watches without acting that
    way before anything reported it."""
    src = (ROOT / "skills" / "mythras-gm" / "mythras_gm.py").read_text()
    # once in cmd_tick's output, once in cmd_forecast's
    assert src.count('"silent_agendas"') == 2, "tick and forecast must both report it"
    assert "def cmd_forecast(" in src

    parser = gm.build_parser()
    sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
    assert "forecast" in sub.choices
    dests = {a.dest for a in sub.choices["forecast"]._actions}
    assert {"campaign", "all"} <= dests


def test_pivot_branches_are_declared_in_advance():
    """A pivot's outcomes are written down before the dice, so consequences
    cannot be quietly reshaped afterwards to suit the result."""
    src = (ROOT / "skills" / "mythras-gm" / "mythras_gm.py").read_text()
    assert "def _apply_branch(" in src
    assert "def cmd_timeline(" in src
    schema = (ROOT / "skills" / "mythras-gm" / "schema.tql").read_text()
    assert "myth-beat-branches-json" in schema
    assert "myth-beat-result" in schema

    parser = gm.build_parser()
    sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
    for cmd in ("add-beat", "revise-beat"):
        assert "branches" in {a.dest for a in sub.choices[cmd]._actions}
    assert "branch" in {a.dest for a in sub.choices["fire-beat"]._actions}
    assert "timeline" in sub.choices


def test_a_branch_applies_before_the_cascade():
    """Futures a branch opens or closes must be part of what the cascade then
    reconciles, not settled behind its back."""
    src = (ROOT / "skills" / "mythras-gm" / "mythras_gm.py").read_text()
    i = src.index("def cmd_fire_beat(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert body.index("_apply_branch(") < body.index("cascade = _cascade(")


def test_the_arc_document_is_the_source_and_the_beats_are_a_projection():
    """An arc is a story and has to be rewritable in one pass. Holding it as
    eighteen separate beat rows meant the connective tissue lived nowhere and
    re-dating one thing cost a round trip."""
    src = (ROOT / "skills" / "mythras-gm" / "mythras_gm.py").read_text()
    assert "def cmd_sync_arc(" in src
    assert "def _read_arc(" in src

    parser = gm.build_parser()
    sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
    assert "sync-arc" in sub.choices
    dests = {a.dest for a in sub.choices["sync-arc"]._actions}
    assert {"file", "campaign", "dry_run"} <= dests


def test_sync_never_rewrites_the_past():
    """Played and narrated beats are left alone: the past is not the arc's."""
    src = (ROOT / "skills" / "mythras-gm" / "mythras_gm.py").read_text()
    i = src.index("def cmd_sync_arc(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert '"played", "narrated"' in body
    assert "skipped_played" in body
    # dropped entries are cancelled, never deleted -- something may point at them
    assert '"myth-beat-status", "cancelled"' in body
    assert "delete" not in body.lower().replace("deleted", "")


def test_arc_front_matter_parses(tmp_path):
    import importlib
    doc = tmp_path / "arc.md"
    doc.write_text(
        "---\n"
        "campaign: myth-campaign-x\n"
        "thread:\n"
        "- when: d1/dawn\n"
        "  title: A thing happens\n"
        "---\n"
        "# The prose starts here\n")
    parsed, text, m = gm._read_arc(str(doc))
    assert parsed["campaign"] == "myth-campaign-x"
    assert parsed["thread"][0]["title"] == "A thing happens"
    assert text[m.end():].startswith("# The prose")


def test_arc_without_front_matter_is_rejected(tmp_path, capsys):
    doc = tmp_path / "plain.md"
    doc.write_text("# Just prose\n")
    with pytest.raises(SystemExit):
        gm._read_arc(str(doc))
    assert "front matter" in capsys.readouterr().out
