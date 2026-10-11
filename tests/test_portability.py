"""Invariants that keep this plugin installable in both Claude Code and Codex.

Codex reads this repository's Claude manifests directly -- `.claude-plugin/
marketplace.json` is a recognised legacy marketplace, `.claude-plugin/
plugin.json` a recognised compatibility manifest, `hooks/hooks.json` is
discovered by default, and `CLAUDE_PLUGIN_ROOT` is set for hook commands in both
hosts. So there is no second plugin to build and no sync job to run: there is one
plugin, and these tests are what stops it quietly becoming Claude-only again.

Every check here exists because the construct it bans breaks exactly one host,
silently, in a way play does not reveal until somebody is mid-session:

- `${CLAUDE_PLUGIN_ROOT}` in a skill body is host-substituted *text*, not a
  shell variable (it is absent from the model's environment in both hosts).
  Claude Code expands it when it loads the file; Codex documents it only as a
  hook variable. Left in shipped prose it expands to nothing under Codex and
  every documented command becomes `uv run --project /skills/mythras-gm`, which
  fails with a path error the model reads as "the engine is missing".
- A hook `timeout` is in SECONDS in both hosts. This file's own hook carried
  `180000` -- fifty hours, i.e. no timeout at all -- for its whole life.
- Codex has no commands component: skills, MCP servers and hooks only. A
  ritual that lives only in `commands/` reaches Codex users not at all.
- A bare `AGENTS.md` beside a `CLAUDE.md` is read by Codex and *ignored* by
  Claude Code, which reads `CLAUDE.md` only. Two divergent copies of the GM
  canon is the failure mode this whole branch exists to avoid, so the canon
  lives in `AGENTS.md` and `CLAUDE.md` imports it.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Vendored trees are nobody's instructions, and a third-party doc
# that happens to mention the variable must not fail this guard.
VENDORED = (".venv", "__pycache__", "node_modules", "site-packages")

SKILL_DOCS = sorted(p for p in (ROOT / "skills").rglob("*.md")
                    if not any(part in VENDORED for part in p.parts))
COMMANDS = sorted((ROOT / "commands").glob("*.md"))
SKILL_FILES = sorted((ROOT / "skills").glob("*/SKILL.md"))

# Hook scripts and hooks.json are the ONE place the variable belongs: both hosts
# export it to hook commands. README.md is prose about how the plugin is built,
# not instructions a model follows.
PROSE_EXEMPT = {"README.md"}


def frontmatter(path):
    """The YAML block between the opening and closing `---`, as a flat dict.

    Parsed with a regex rather than PyYAML so this guard has no dependency of
    its own -- it must be able to run in any checkout.
    """
    text = path.read_text()
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    fields = {}
    for line in match.group(1).splitlines():
        if re.match(r"^\s", line) or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip("\"'")
    return fields


def test_there_are_files_to_check_at_all():
    """Every test below globs the tree. If a layout change empties a glob, they
    would all pass vacuously, which is worse than failing."""
    assert len(SKILL_DOCS) > 5, f"only found {len(SKILL_DOCS)} skill docs"
    assert COMMANDS, "no commands/*.md found"
    assert SKILL_FILES, "no skills/*/SKILL.md found"


@pytest.mark.parametrize("doc", SKILL_DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_plugin_root_literal_in_shipped_prose(doc):
    """A path a Codex session cannot resolve. The engine's location comes from
    the preflight line instead, which resolves it from the variable in the one
    place both hosts actually set it."""
    if doc.name in PROSE_EXEMPT:
        pytest.skip(f"{doc.name} is prose about the build, not instructions")
    hits = [n for n, line in enumerate(doc.read_text().splitlines(), 1)
            if "CLAUDE_PLUGIN_ROOT" in line]
    assert not hits, (
        f"{doc.relative_to(ROOT)} names CLAUDE_PLUGIN_ROOT on line(s) "
        f"{hits}; under Codex that expands to nothing. Use the absolute "
        f"invocation the session-start hook prints."
    )


def test_hook_timeouts_are_plausible_seconds():
    """`timeout` is seconds in both hosts (Claude Code: "Seconds before
    cancelling", default 600; Codex: the same, max 600 for most events). A
    millisecond value reads as decades and silently disables the timeout."""
    spec = json.loads((ROOT / "hooks" / "hooks.json").read_text())
    found = []
    for event, groups in spec.get("hooks", {}).items():
        for group in groups:
            for hook in group.get("hooks", []):
                if "timeout" in hook:
                    found.append((event, hook["timeout"]))
    assert found, "no hook declares a timeout; this test would pass vacuously"
    too_long = [(e, t) for e, t in found if t > 600]
    assert not too_long, (
        f"timeout is in SECONDS, not milliseconds: {too_long}. Codex caps most "
        f"events at 600."
    )


@pytest.mark.parametrize("command", COMMANDS, ids=lambda p: p.name)
def test_every_command_delegates_to_a_skill(command):
    """Codex has no commands component. A command file is a Claude-Code-only
    entry point, so its body must live in a skill that both hosts can load.

    The delegation is declared as a `skill:` frontmatter field rather than
    inferred from the prose: every one of these files mentions "mythras-gm"
    somewhere, so matching on the text alone passed two commands that delegated
    to nothing."""
    names = {f.parent.name for f in SKILL_FILES}
    declared = frontmatter(command).get("skill")
    assert declared, (
        f"commands/{command.name} declares no `skill:` in its frontmatter, so "
        f"its body reaches no Codex session. Move the body into a skill and "
        f"point at it."
    )
    assert declared in names, (
        f"commands/{command.name} delegates to {declared!r}, which is not one "
        f"of {sorted(names)}"
    )


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_skill_declares_itself(skill):
    """Both hosts match on the description and address the skill by `name`; a
    name that disagrees with its directory is unaddressable in one of them."""
    fields = frontmatter(skill)
    assert fields.get("name"), f"{skill.relative_to(ROOT)} has no `name`"
    assert fields.get("description"), (
        f"{skill.relative_to(ROOT)} has no `description`; without one neither "
        f"host can decide when to load it"
    )
    assert fields["name"] == skill.parent.name, (
        f"{skill.relative_to(ROOT)} is named {fields['name']!r} but sits in "
        f"{skill.parent.name!r}"
    )


def test_manifests_parse_and_agree_on_the_plugin_name():
    """Codex installs from these two files. A name mismatch installs a plugin
    whose hooks and skills resolve under a different directory."""
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    local = [p for p in market["plugins"] if p.get("source") == "./"]
    assert local, "marketplace.json has no entry sourced from this repo"
    assert local[0]["name"] == plugin["name"], (
        f"marketplace entry {local[0]['name']!r} != plugin.json "
        f"{plugin['name']!r}"
    )


def test_the_session_start_hook_publishes_an_absolute_invocation():
    """The hook is the only place `CLAUDE_PLUGIN_ROOT` is resolvable in both
    hosts, so it is where the engine's absolute path has to be published. If it
    stops printing it, the skills have no path at all under Codex."""
    script = (ROOT / "hooks" / "session-start.sh").read_text()
    ready = [line for line in script.splitlines()
             if "mythras-gm ready" in line]
    assert ready, "the hook no longer prints a ready line"
    assert any("$GM" in line or "${GM}" in line for line in ready), (
        "the ready line does not name $GM, so it publishes no path the skills "
        "can use"
    )


def test_the_canon_is_single_sourced_for_both_hosts():
    """Claude Code reads AGENTS.md only when no CLAUDE.md exists at or above
    cwd; Codex reads AGENTS.md only. The documented way to have one file serve
    both is a CLAUDE.md that imports it."""
    agents = ROOT / "AGENTS.md"
    claude = ROOT / "CLAUDE.md"
    assert agents.exists(), (
        "no AGENTS.md: a Codex session gets none of the GM canon"
    )
    assert claude.exists(), "no CLAUDE.md"
    assert "@AGENTS.md" in claude.read_text(), (
        "CLAUDE.md does not import AGENTS.md, so Claude Code reads CLAUDE.md "
        "only and the two can drift"
    )
    assert "ALWAYS MOVE THE ACTION FORWARD" in agents.read_text(), (
        "AGENTS.md exists but does not hold the canon"
    )


# --- the cold start on a host nobody has configured -----------------------
#
# The install these tests protect is not an engineer's. A player installs the
# plugin in Codex, opens a session, and the game either comes up or it does
# not; if it does not, the thing in front of them must say what to do in words
# they already know, and do the part it can do itself.
#
# The worst case is specific and worth naming: Codex does not trust a plugin's
# hooks until the user reviews them, so on a fresh install the preflight NEVER
# RUNS -- and the preflight is the thing that would otherwise print the
# warning. No message can come from the hook, because the hook is what is
# missing. Only the skill can notice, so the skill has to.

VERIFY = ROOT / "scripts" / "verify-install.sh"
SETUP_SKILL = ROOT / "skills" / "mythras-setup" / "SKILL.md"
GM_SKILL = ROOT / "skills" / "mythras-gm" / "SKILL.md"


def test_the_install_check_exists_and_runs():
    """The instrument for a second machine: one command, no checkout, no
    arguments. If it needs explaining it is not the right tool."""
    import os
    import subprocess
    assert VERIFY.exists(), "scripts/verify-install.sh is missing"
    assert os.access(VERIFY, os.X_OK), "verify-install.sh is not executable"
    out = subprocess.run(["bash", str(VERIFY)], capture_output=True, text=True,
                         timeout=180)
    assert "install check" in out.stdout.lower(), \
        f"no recognisable report on stdout:\n{out.stdout}\n{out.stderr}"
    # Exit code is the verdict: 0 when nothing blocks play.
    assert out.returncode in (0, 1), \
        f"unexpected exit {out.returncode}:\n{out.stdout}\n{out.stderr}"


def test_the_install_check_reports_every_thing_that_can_block_play():
    """Each of these has stopped a real install dead. A check that omits one
    sends somebody to look in the wrong place."""
    import subprocess
    out = subprocess.run(["bash", str(VERIFY)], capture_output=True, text=True,
                         timeout=180).stdout.lower()
    for thing in ["host", "engine", "uv", "database", "writable", "network"]:
        assert thing in out, f"the check never mentions {thing!r}"


def test_the_install_check_explains_the_untrusted_hook_in_plain_words():
    """The failure that prints nothing on its own. The remedy is a click in a
    menu, so it has to be described as one -- not as a hook, a lifecycle event
    or a trust policy."""
    text = VERIFY.read_text()
    assert "/plugins" in text, \
        "the check never tells anyone where to approve the startup check"
    assert "startup check" in text.lower(), \
        "the check calls it a hook; a player does not know what that is"


def test_the_setup_skill_offers_to_fix_rather_than_instructs():
    """A player cannot be handed a TOML stanza and a file path. The model can
    open that file itself, so the skill must have it offer, with permission,
    instead of describing the edit."""
    text = SETUP_SKILL.read_text()
    assert "offer to" in text.lower(), \
        "the setup skill never offers to make the change itself"
    assert "config.toml" in text, \
        "the setup skill cannot apply the sandbox fix without naming the file"
    assert "restart" in text.lower(), \
        "a config change needs a restart; the skill must say so"


def test_the_gm_skill_notices_a_session_the_preflight_never_reached():
    """No ready line in context means the preflight did not run, which under
    Codex most often means the startup check is not approved yet. The skill
    must check rather than narrate on, because narrating on is how a session
    gets played with nothing saved."""
    text = GM_SKILL.read_text().lower()
    assert "ready line" in text, \
        "SKILL.md never refers to the preflight's ready line"
    assert "doctor" in text, \
        "SKILL.md gives the model no way to check a cold start for itself"


# --- the pointer a campaign plugin reads to find this engine --------------
#
# A plugin cannot resolve a sibling plugin's root; there is no variable for it.
# So the engine writes its own location to a file and a campaign reads it. That
# file lived at ~/.claude/mythras-gm/engine-root, which is where it was first
# put rather than a statement about which agent is installed -- it works under
# Codex unchanged. But a campaign author cannot know that from the path, so the
# engine writes a host-neutral location too, and keeps the original because
# every campaign already shipped reads only that one.

import mythras_gm as gm  # noqa: E402  (conftest puts the engine on sys.path)


def test_the_pointer_is_written_host_neutrally_and_to_the_legacy_path(tmp_path):
    """Both, in that order. The host-neutral path is what a new campaign will
    be told to read; the legacy path is what the installed ones already read."""
    paths = (str(tmp_path / "neutral" / "engine-root"),
             str(tmp_path / "legacy" / "engine-root"))
    results = gm._write_engine_pointers("/somewhere/engine", paths)

    assert [ok for _, ok, _ in results] == [True, True], results
    for p in paths:
        assert open(p).read() == "/somewhere/engine\n"


def test_the_host_neutral_pointer_is_checked_first():
    """Order is the contract Task 2's shell reader copies. If these two ever
    disagree, the host-neutral one is the one to believe."""
    assert gm.ENGINE_POINTERS[0].endswith("/.mythras-gm/engine-root")
    assert gm.ENGINE_POINTERS[1].endswith("/.claude/mythras-gm/engine-root")
    assert gm.ENGINE_POINTER == gm.ENGINE_POINTERS[1], \
        "the old name must keep meaning the old path; docs and campaigns cite it"


def test_one_unwritable_pointer_does_not_stop_the_other(tmp_path):
    """A sandboxed host can allow one location and refuse the other. Writing
    is a convenience; losing it must not cost us the location that did work."""
    blocked = tmp_path / "blocked"
    blocked.write_text("I am a file, not a directory")
    good = str(tmp_path / "good" / "engine-root")
    results = gm._write_engine_pointers("/somewhere/engine",
                                        (str(blocked / "engine-root"), good))

    assert [ok for _, ok, _ in results] == [False, True], results
    assert open(good).read() == "/somewhere/engine\n"
    assert results[0][2], "a failure must carry a detail string to report"


def test_every_pointer_unwritable_is_survivable(tmp_path):
    """Review Focus 1: a read-only home. init-db reports Ready regardless, so
    the writer must return failures rather than raise them."""
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")
    results = gm._write_engine_pointers(
        "/somewhere/engine",
        (str(blocked / "a" / "engine-root"), str(blocked / "b" / "engine-root")))
    assert [ok for _, ok, _ in results] == [False, False], results


def test_the_pointer_paths_survive_no_home(monkeypatch):
    """Review Focus 4: cron, or a bare container. Computing the paths must not
    raise, and must not land them in the working directory."""
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)
    import importlib
    reloaded = importlib.reload(gm)
    try:
        for p in reloaded.ENGINE_POINTERS:
            assert p.startswith("/") or p.startswith("~"), \
                f"{p} is relative; init-db would write into the user's cwd"
    finally:
        monkeypatch.undo()
        importlib.reload(gm)


def _run_check_in_isolation(tmp_path, home, extra_env=None):
    """Run verify-install.sh from a copy OUTSIDE this repo.

    Copying matters: the script's own location is one of its probes, so run in
    place it finds this checkout and the pointer probe is never reached.
    """
    import os
    import shutil
    import subprocess
    staged = tmp_path / "staged"
    staged.mkdir(exist_ok=True)
    shutil.copy2(VERIFY, staged / "verify-install.sh")
    env = dict(os.environ)
    env["HOME"] = str(home)
    for k in ("MYTHRAS_GM_ROOT", "MYTHRAS_TYPEDB_HOME"):
        env.pop(k, None)
    env.update(extra_env or {})
    return subprocess.run(["bash", str(staged / "verify-install.sh")],
                          capture_output=True, text=True, env=env,
                          cwd=str(staged), timeout=180)


def _fake_engine(at):
    """A directory that looks like an engine install to a path probe."""
    cli = at / "skills" / "mythras-gm" / "mythras_gm.py"
    cli.parent.mkdir(parents=True, exist_ok=True)
    cli.touch()
    return at


def test_the_check_finds_the_engine_from_the_host_neutral_pointer(tmp_path):
    """The whole point of Task 1: a campaign or a diagnostic on any host can
    read one file instead of guessing at an install layout."""
    home = tmp_path / "home"
    engine = _fake_engine(tmp_path / "engine")
    pointer = home / ".mythras-gm" / "engine-root"
    pointer.parent.mkdir(parents=True)
    pointer.write_text(str(engine) + "\n")

    out = _run_check_in_isolation(tmp_path, home).stdout
    assert str(engine) in out, f"the host-neutral pointer was not read:\n{out}"


def test_the_check_still_reads_the_legacy_pointer(tmp_path):
    """Machines that have only ever run an older engine have only this file."""
    home = tmp_path / "home"
    engine = _fake_engine(tmp_path / "engine")
    pointer = home / ".claude" / "mythras-gm" / "engine-root"
    pointer.parent.mkdir(parents=True)
    pointer.write_text(str(engine) + "\n")

    out = _run_check_in_isolation(tmp_path, home).stdout
    assert str(engine) in out, f"the legacy pointer was not read:\n{out}"


def test_a_stale_pointer_is_skipped_rather_than_reported(tmp_path):
    """Review Focus 2: a plugin upgrade moves the engine and leaves the
    pointer naming a directory with no CLI in it. Reporting that path as the
    engine sends somebody to debug a directory that is not the problem."""
    home = tmp_path / "home"
    gone = tmp_path / "gone-away"
    pointer = home / ".mythras-gm" / "engine-root"
    pointer.parent.mkdir(parents=True)
    pointer.write_text(str(gone) + "\n")

    out = _run_check_in_isolation(tmp_path, home).stdout
    assert str(gone) not in out, f"a stale pointer was believed:\n{out}"
    assert "engine" in out.lower()


def test_the_newer_pointer_wins_when_the_two_disagree(tmp_path):
    """Review Focus 3. Both exist, both resolve, and they name different
    installs; the host-neutral one is the one written by the current engine."""
    home = tmp_path / "home"
    new = _fake_engine(tmp_path / "new-engine")
    old = _fake_engine(tmp_path / "old-engine")
    for rel, target in ((".mythras-gm", new), (".claude/mythras-gm", old)):
        p = home / rel / "engine-root"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(target) + "\n")

    out = _run_check_in_isolation(tmp_path, home).stdout
    assert str(new) in out and str(old) not in out, \
        f"the host-neutral pointer must win:\n{out}"


def test_an_empty_pointer_file_is_treated_as_absent(tmp_path):
    """Review Focus 5: an interrupted write. An empty file must not resolve to
    /skills/mythras-gm/mythras_gm.py and must not crash the check."""
    home = tmp_path / "home"
    pointer = home / ".mythras-gm" / "engine-root"
    pointer.parent.mkdir(parents=True)
    pointer.write_text("   \n")

    r = _run_check_in_isolation(tmp_path, home)
    assert r.returncode in (0, 1), f"exit {r.returncode}:\n{r.stdout}\n{r.stderr}"
    assert "unbound variable" not in r.stderr, r.stderr
    assert "/skills/mythras-gm" not in r.stdout.replace(str(home), ""), \
        f"an empty pointer resolved to a root-relative path:\n{r.stdout}"
