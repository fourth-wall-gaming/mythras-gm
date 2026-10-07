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


# --- native TypeDB, no Docker required ------------------------------------
#
# TypeDB 3.x is a native Rust binary with no JVM. Docker was never load-
# bearing -- it was just the easiest way to supervise a long-running process
# when this was written -- so this is now the default path, and Docker is an
# explicit opt-in (--docker) for anyone who already has that workflow.

def test_native_platform_covers_the_common_dev_machines():
    for system, machine, expected in [
        ("Darwin", "arm64", "mac-arm64"),
        ("Darwin", "x86_64", "mac-x86_64"),
        ("Linux", "x86_64", "linux-x86_64"),
        ("Linux", "aarch64", "linux-arm64"),
        ("Windows", "AMD64", "windows-x86_64"),
    ]:
        import platform as _platform
        import unittest.mock as mock
        with mock.patch.object(_platform, "system", return_value=system), \
             mock.patch.object(_platform, "machine", return_value=machine):
            assert gm._native_platform() == expected, (system, machine)


def test_native_platform_returns_none_for_the_unsupported():
    import platform as _platform
    import unittest.mock as mock
    with mock.patch.object(_platform, "system", return_value="Plan9"), \
         mock.patch.object(_platform, "machine", return_value="risc-v"):
        assert gm._native_platform() is None


def test_download_url_matches_the_real_typedb_cdn_layout(monkeypatch):
    """Pinned against the actual repo.typedb.com layout, verified by hand:
    typedb-all-<platform>/versions/<version>/typedb-all-<platform>-<version>.<ext>"""
    monkeypatch.delenv("TYPEDB_DIST_BASE", raising=False)
    assert gm._native_dist_url("linux-x86_64", "3.8.0", "tar.gz") == (
        "https://repo.typedb.com/public/public-release/raw/names/"
        "typedb-all-linux-x86_64/versions/3.8.0/typedb-all-linux-x86_64-3.8.0.tar.gz")


# --- native TypeDB inside a locked-down or disposable container -------------
#
# Claude Code cloud sessions run in a container whose egress gateway refuses
# CONNECT to repo.typedb.com, and whose home directory does not survive an idle
# restart. Neither is a bug in this code, but this code has to be steerable
# around both: where the server and its data live, and where the archive comes
# from, are each one environment variable.

def test_native_home_is_overridable_so_data_can_live_where_it_survives(tmp_path):
    """~/.claude is wiped on a cloud container restart. MYTHRAS_TYPEDB_HOME
    moves the binary, the PID file, the log AND the data directory together,
    because a data directory that survives next to a binary that does not is
    just a different way to lose the save."""
    import os
    import subprocess
    r = subprocess.run(
        [sys.executable, "-c",
         "import mythras_gm as gm; import json; "
         "print(json.dumps([gm.NATIVE_HOME, gm.NATIVE_DATA_DIR, gm.NATIVE_PID_FILE]))"],
        capture_output=True, text=True, cwd=str(Path(gm.__file__).parent),
        env={**os.environ, "MYTHRAS_TYPEDB_HOME": str(tmp_path / "engine")})
    assert r.returncode == 0, r.stderr
    home, data, pid = _json.loads(r.stdout)
    assert home == str(tmp_path / "engine")
    assert data.startswith(home) and pid.startswith(home)


def test_dist_base_redirects_the_download_at_a_flat_mirror(monkeypatch):
    """A GitHub release holds assets flat, by filename. TYPEDB_DIST_BASE names
    the directory URL that holds the archive, and nothing else changes."""
    monkeypatch.setenv("TYPEDB_DIST_BASE",
                       "https://github.com/fourth-wall-gaming/mythras-gm/releases/download/typedb-3.8.0/")
    assert gm._native_dist_url("linux-x86_64", "3.8.0", "tar.gz") == (
        "https://github.com/fourth-wall-gaming/mythras-gm/releases/download/"
        "typedb-3.8.0/typedb-all-linux-x86_64-3.8.0.tar.gz")


def _fake_typedb_tarball(path, plat="linux-x86_64", version="3.8.0", payload=b"#!/bin/sh\n"):
    """A tar.gz shaped like the real distribution: <dist>/server/typedb_server_bin."""
    import io
    import tarfile
    with tarfile.open(path, "w:gz") as t:
        info = tarfile.TarInfo(f"typedb-all-{plat}-{version}/server/typedb_server_bin")
        info.size = len(payload)
        info.mode = 0o755
        t.addfile(info, io.BytesIO(payload))


def test_dist_archive_skips_the_network_entirely(tmp_path, monkeypatch):
    """The true escape hatch for any environment with no route out at all:
    hand it an archive on disk and it never opens a socket."""
    import platform as _platform
    import urllib.request
    import unittest.mock as mock
    archive = tmp_path / "typedb.tar.gz"
    _fake_typedb_tarball(archive)
    monkeypatch.setattr(gm, "NATIVE_HOME", str(tmp_path / "engine"))
    monkeypatch.setenv("TYPEDB_DIST_ARCHIVE", str(archive))
    monkeypatch.delenv("TYPEDB_DIST_SHA256", raising=False)
    with mock.patch.object(_platform, "system", return_value="Linux"), \
         mock.patch.object(_platform, "machine", return_value="x86_64"), \
         mock.patch.object(urllib.request, "urlopen",
                           side_effect=AssertionError("network must not be touched")):
        ok, where = gm._download_native("3.8.0")
        assert ok, where
        assert gm._native_server_bin("3.8.0") == str(
            tmp_path / "engine" / "typedb-all-linux-x86_64-3.8.0" / "server" / "typedb_server_bin")
    assert archive.exists(), "a user-supplied archive is theirs; do not delete it"


def test_dist_sha256_rejects_an_archive_that_does_not_match(tmp_path, monkeypatch):
    """Trusting whatever unpacks is fine from the vendor's own CDN and not fine
    from a mirror. A pinned digest turns a tampered or truncated archive into
    a refusal instead of a server binary."""
    import platform as _platform
    import unittest.mock as mock
    archive = tmp_path / "typedb.tar.gz"
    _fake_typedb_tarball(archive)
    monkeypatch.setattr(gm, "NATIVE_HOME", str(tmp_path / "engine"))
    monkeypatch.setenv("TYPEDB_DIST_ARCHIVE", str(archive))
    monkeypatch.setenv("TYPEDB_DIST_SHA256", "0" * 64)
    with mock.patch.object(_platform, "system", return_value="Linux"), \
         mock.patch.object(_platform, "machine", return_value="x86_64"):
        ok, msg = gm._download_native("3.8.0")
        assert not ok
        assert "sha256" in msg.lower()
        assert gm._native_server_bin("3.8.0") is None, "nothing may be unpacked from a bad archive"


def test_dist_sha256_accepts_the_matching_digest(tmp_path, monkeypatch):
    import hashlib
    import platform as _platform
    import unittest.mock as mock
    archive = tmp_path / "typedb.tar.gz"
    _fake_typedb_tarball(archive)
    monkeypatch.setattr(gm, "NATIVE_HOME", str(tmp_path / "engine"))
    monkeypatch.setenv("TYPEDB_DIST_ARCHIVE", str(archive))
    monkeypatch.setenv("TYPEDB_DIST_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())
    import urllib.request
    with mock.patch.object(_platform, "system", return_value="Linux"), \
         mock.patch.object(_platform, "machine", return_value="x86_64"), \
         mock.patch.object(urllib.request, "urlopen",
                           side_effect=AssertionError("network must not be touched")):
        ok, msg = gm._download_native("3.8.0")
    assert ok, msg


def test_download_refused_by_an_egress_proxy_names_the_host_and_the_way_around(tmp_path, monkeypatch):
    """A whole session was spent diagnosing 'could not download ... 403'. When
    the proxy refuses the CONNECT, say which host to allowlist and name the
    two variables that route around it, so the next person spends a minute."""
    import platform as _platform
    import urllib.error
    import urllib.request
    import unittest.mock as mock
    monkeypatch.setattr(gm, "NATIVE_HOME", str(tmp_path / "engine"))
    monkeypatch.delenv("TYPEDB_DIST_ARCHIVE", raising=False)
    monkeypatch.delenv("TYPEDB_DIST_BASE", raising=False)
    refused = urllib.error.URLError("Tunnel connection failed: 403 Forbidden")
    with mock.patch.object(_platform, "system", return_value="Linux"), \
         mock.patch.object(_platform, "machine", return_value="x86_64"), \
         mock.patch.object(urllib.request, "urlopen", side_effect=refused):
        ok, msg = gm._download_native("3.8.0")
    assert not ok
    assert "repo.typedb.com" in msg
    assert "egress" in msg.lower() or "proxy" in msg.lower()
    assert "TYPEDB_DIST_BASE" in msg and "TYPEDB_DIST_ARCHIVE" in msg


def test_download_sends_a_user_agent():
    """The CDN 403s a bare request with no User-Agent at all -- any UA value
    satisfies it, confirmed against the real endpoint. A regression here fails
    silently as a 403, not as an obviously-wrong error."""
    src = open(gm.__file__).read()
    body = src.split("def _fetch_native_archive(")[1].split("\ndef ")[0]
    assert "User-Agent" in body


def test_zip_extraction_restores_the_executable_bit():
    """zipfile.extractall does not restore the executable bit (tarfile does),
    confirmed by an actual extraction that left the binary at mode 644 and
    Popen refusing it with EACCES. Only zip platforms (mac, windows) need the
    explicit chmod; this asserts the fix is still there."""
    src = open(gm.__file__).read()
    body = src.split("def _unpack_native_archive(")[1].split("\ndef ")[0]
    assert "os.chmod(" in body


def test_native_server_is_detached_so_it_outlives_this_process():
    src = open(gm.__file__).read()
    body = src.split("def _start_native_server(")[1].split("\ndef ")[0]
    assert "start_new_session" in body or "DETACHED_PROCESS" in body


def test_pid_file_identifies_only_a_process_we_started():
    """_native_running must not treat an unrelated process that happens to
    reuse an old PID as our server."""
    src = open(gm.__file__).read()
    body = src.split("def _native_running(")[1].split("\ndef ")[0]
    assert "NATIVE_PID_FILE" in body


def test_init_db_checks_for_an_existing_server_before_managing_anything():
    """If something is already listening -- an existing Docker setup included
    -- init-db must not attempt a native download or touch docker at all."""
    body = gm.cmd_init_db.__doc__ or ""
    src = open(gm.__file__).read()
    fn_body = src.split("def cmd_init_db(args):")[1].split("\ndef ")[0]
    already_up_idx = fn_body.index("already_up = _wait_for_port")
    docker_branch_idx = fn_body.index("elif args.docker:")
    native_branch_idx = fn_body.index("ok, msg = _start_native_server()")
    assert already_up_idx < docker_branch_idx < native_branch_idx


def test_docker_is_now_opt_in_not_default():
    src = open(gm.__file__).read()
    fn_body = src.split("def cmd_init_db(args):")[1].split("\ndef ")[0]
    assert "elif args.docker:" in fn_body
    assert 'not args.no_docker and not _wait_for_port' not in fn_body, \
        "docker is still the implicit default path"


def test_stop_db_only_kills_a_server_this_cli_started():
    """No effect on --docker or on someone else's TypeDB -- it reads the pid
    file this CLI itself wrote, and refuses to guess otherwise."""
    src = open(gm.__file__).read()
    body = src.split("def _stop_native_server(")[1].split("\ndef ")[0]
    assert "NATIVE_PID_FILE" in body
    assert 'sub.add_parser("stop-db"' in src


def test_every_handler_reads_only_flags_its_subparser_defines():
    """A handler reading args.X where X is not on its own subparser is an
    AttributeError on every invocation of that command.

    This happened: update-campaign's --staging-notes, --arc-file and --played
    were appended to build_parser after a bare `sub.add_parser("list-campaigns")`,
    so they bound to whatever `s` still pointed at -- retire-canon -- and
    update-campaign crashed on its first line for every caller.
    """
    import inspect
    import re as _re

    parser = gm.build_parser()
    sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
    always = {"command", "func"}
    broken = {}

    for cmd, p in sub.choices.items():
        fn = getattr(gm, "cmd_" + cmd.replace("-", "_"), None)
        if fn is None:
            continue
        src = inspect.getsource(fn)
        # Bare attribute reads only. getattr(args, "x", default) is deliberate
        # and safe, so strip those calls before scanning.
        src = _re.sub(r'getattr\(\s*args\s*,[^)]*\)', '', src)
        read = set(_re.findall(r'\bargs\.([a-zA-Z_][a-zA-Z0-9_]*)', src))
        dests = {a.dest for a in p._actions} | always
        missing = sorted(read - dests)
        if missing:
            broken[cmd] = missing

    assert not broken, (
        "handlers read flags their subparser does not define: " + repr(broken))


def test_get_campaign_reads_back_everything_update_campaign_writes():
    """A save you can write and not read is half a save.

    update-campaign gained --arc-file, --played and --staging-notes; get-campaign's
    fetch list did not, so the arc loaded into the database and no command could
    show it. The GM then has no way to tell a loaded arc from a missing one.
    """
    import inspect
    import re as _re

    # _set_attr(driver, "myth-campaign", <id>, "<attribute>", value): the
    # attribute is the SECOND quoted string, not the first (that is the type).
    written = set(_re.findall(
        r'_set_attr\(\s*driver,\s*"myth-campaign",\s*[^,]+,\s*"([a-z][a-z-]*)"',
        inspect.getsource(gm.cmd_update_campaign)))
    read = set(_re.findall(r'"([a-z][a-z-]*)"',
                           inspect.getsource(gm.cmd_get_campaign)))
    assert "myth-arc-json" in written, "regex no longer matches the handler"
    # _get_entity always returns id and name, so name needs no fetch entry.
    # set-scene owns the scene; update-campaign never writes it.
    missing = sorted(written - read - {"name"})
    assert not missing, (
        "update-campaign writes these and get-campaign cannot read them back: "
        + repr(missing))


def test_arc_acts_parse_for_and_takes_whole(tmp_path):
    """An act's purpose and cost are prose that wraps. Both must survive whole.

    The parser handled **Takes:** but not **For:**, so it fell back to "first
    line that does not look like markup" -- which picked up a WRAPPED
    CONTINUATION of the For paragraph -- and it read only the first physical
    line of Takes. First Through's arc loaded into the save as three acts whose
    purpose and cost were both sentence fragments, and nothing said so.
    """
    doc = tmp_path / "story.md"
    doc.write_text(
        "# ACT I — `d0 to d2` · THE NINE\n"
        "\n"
        "**For:** making the player love this place and these people, and\n"
        "learning the job in their own hands. Light for two beats, then the\n"
        "hardest night of their life.\n"
        "\n"
        "**Takes:** Ladder. Forty-two adults who are alive, well, and\n"
        "permanently out of reach.\n"
        "\n"
        "| beat | who |\n"
        "|---|---|\n"
    )
    acts = gm._parse_arc_acts(str(doc))
    assert len(acts) == 1
    a = acts[0]
    assert a["act"] == "I"
    assert a["when"] == "d0 to d2"
    assert a["title"] == "THE NINE"
    assert a["for"].startswith("making the player love this place")
    assert a["for"].endswith("hardest night of their life.")
    assert a["takes"].startswith("Ladder.")
    assert a["takes"].endswith("permanently out of reach.")


def test_update_event_can_amend_the_timestamp_log_event_can_set():
    """created-at is second-granular, so events logged in one batch tie.

    get-log sorts by (session, created-at), so a session written in a few
    seconds comes back in arbitrary order. log-event --at exists to place an
    event in story order instead of wall-clock order; update-event had no way
    to amend it, so a journal already written out of order could not be
    repaired through the CLI at all.
    """
    import inspect

    parser = gm.build_parser()
    sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
    assert "at" in {a.dest for a in sub.choices["log-event"]._actions}, \
        "log-event lost --at"
    assert "at" in {a.dest for a in sub.choices["update-event"]._actions}, \
        "update-event cannot amend the timestamp log-event can set"
    assert "created-at" in inspect.getsource(gm.cmd_update_event), \
        "update-event takes --at but never writes created-at"
