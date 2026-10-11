# Purewater Codex Portability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Purewater campaign plugin work under Codex as well as Claude Code, without a second build — the same approach already shipped for the engine.

**Architecture:** Purewater carries the engine's four host divergences (unresolvable plugin-root paths in shipped prose, a millisecond hook timeout, a ritual that lives only in `commands/`, contributor instructions only Claude Code reads) plus one the engine does not have: `scripts/engine.sh` locates its *sibling* engine plugin by searching, and every search path is `~/.claude`-shaped. That locator is the only real engineering here; the rest is the pattern already proven in `mythras-gm`.

**Tech Stack:** bash, Python 3.12+, pytest. No new dependencies.

**Spec:** `mythras-gm/docs/CODEX.md` — the dual-host contract this campaign must satisfy. The engine-side precedent is `mythras-gm/tests/test_portability.py` and commit `2670871`.

**Repo:** `purewater-campaign` (`/Users/gullyburns/purewater-campaign`, remote `fourth-wall-gaming/purewater-campaign`). Branch off `main` as `feat/codex-portability`. **This plan does not execute in the `mythras-gm` checkout it is stored in.**

**Depends on:** `2026-10-10-host-neutral-engine-pointer.md` Task 1 for the host-neutral pointer path. Task 1 below reads that path, so it must tolerate the pointer being absent — which it does, since reading a missing file falls through to the next probe. The two plans can therefore ship in either order.

## Global Constraints

- Hook `timeout` is **seconds** in both hosts. Codex caps most events at 600. The current value is `120000`.
- Codex has no commands component — skills, MCP servers and hooks only. Anything load-bearing must live in a skill.
- `scripts/engine.sh` is sourced by a hook running `set -u`. **Every** environment variable it reads must use `:-`. A bare expansion aborts the caller; this has already happened once and `tests/test_engine_probe.py` exists because of it.
- `scripts/session-start.sh` must never exit non-zero and must never call `init-db` in the normal path — the engine's own hook does that at the same moment, and when both called it the loser reported a healthy save as missing.
- The campaign's file tree is a **source export, not a save**. No change may encourage GMing off the files.
- Codex installs plugins to `~/.codex/plugins/cache/$MARKETPLACE/$PLUGIN/$VERSION/`; for a local marketplace `$VERSION` is the literal `local`. Claude Code uses `cache/<marketplace>/<plugin>/<version>/`, `synced/<bucket>/<plugin>/`, and `marketplaces/<marketplace>/` — only the first has a version segment.
- Test command (matches CI): `uv run --with pytest --with pyyaml --with pillow pytest -q tests/`

## Review Focus

Five conditions these changes imply that no happy path exercises. Each has its test placed in the task that owns the code.

1. **Both hosts installed on one machine, engine present only under `~/.codex`** — the probe must not stop at the first *tree* that exists, only at the first *hit*. The obvious loop shape gets this wrong. *(Task 1)*
2. **`$HOME` unset while the hook runs** — the locator must return "not found" rather than abort the session under `set -u`. *(Task 1)*
3. **The skill loaded with no hook output in context** — untrusted hooks under Codex, so `$PW` was never published. The skill must resolve its own root rather than source an empty path. *(Task 3)*
4. **A Codex session reading an instruction to type `/purewater:start`** — a command that does not exist there. Every host-specific entry point in shipped prose must name its skill too. *(Task 3)*
5. **An engine found but older than the host-neutral pointer** — the campaign must still work against an engine that writes only the legacy pointer, because the engine is a separately versioned plugin. *(Task 1)*

---

### Task 1: The locator finds an engine installed under Codex

**Files:**
- Modify: `scripts/engine.sh` (probe 2, the breadcrumb; probe 4, the install-tree search)
- Test: `tests/test_engine_probe.py` (modify `LAYOUTS`, the `empty_home` fixture; append tests)

**Interfaces:**
- Consumes: `~/.mythras-gm/engine-root`, written by the engine (other plan, Task 1). Must work when absent.
- Produces: `GM_ROOT`, `GM_SKILL`, `GM_CLI` and the `gm()` shell function, exported by sourcing `scripts/engine.sh` — unchanged names, now resolvable on both hosts. Tasks 2 and 3 rely on these.

- [ ] **Step 1: Extend the layout table and the fixture**

In `tests/test_engine_probe.py`, replace the `LAYOUTS` dict:

```python
# Every layout a host is known to install a plugin into. Only the Claude Code
# cache and the Codex cache have a version segment, which is exactly what the
# old probe assumed of all of them.
LAYOUTS = {
    "cache": ".claude/plugins/cache/fourth-wall-gaming/mythras-gm/1.0.0",
    "synced": ".claude/plugins/synced/aaaa_bbbb/mythras-gm",
    "marketplaces": ".claude/plugins/marketplaces/fourth-wall-gaming",
    # Codex: ~/.codex/plugins/cache/$MARKETPLACE/$PLUGIN/$VERSION/, and a
    # locally-sourced marketplace entry installs with the literal version
    # "local" rather than a number.
    "codex-cache": ".codex/plugins/cache/fourth-wall-gaming/mythras-gm/1.0.0",
    "codex-local": ".codex/plugins/cache/fourth-wall-gaming/mythras-gm/local",
}
```

and replace the `empty_home` fixture so both hosts' trees exist:

```python
@pytest.fixture
def empty_home(tmp_path):
    h = tmp_path / "home"
    (h / ".claude").mkdir(parents=True)
    (h / ".codex").mkdir(parents=True)
    return h
```

- [ ] **Step 2: Add the tests for the new conditions**

Append to `tests/test_engine_probe.py`:

```python


def test_the_host_neutral_breadcrumb_is_read(empty_home, tmp_path):
    """The engine writes ~/.mythras-gm/engine-root as well as the original
    under ~/.claude. Reading one file beats searching four trees."""
    engine = tmp_path / "engine"
    (engine / GM_REL).parent.mkdir(parents=True)
    (engine / GM_REL).touch()
    pointer = empty_home / ".mythras-gm" / "engine-root"
    pointer.parent.mkdir(parents=True)
    pointer.write_text(str(engine) + "\n")

    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    got, err = _source_engine(empty_home, nowhere)
    assert got == str(engine), f"host-neutral breadcrumb not read: {got}\n{err}"


def test_the_legacy_breadcrumb_still_works_alone(empty_home, tmp_path):
    """Review Focus 5: the engine is a separately versioned plugin. An install
    running an older engine writes only ~/.claude/mythras-gm/engine-root, and
    this campaign must keep working against it."""
    engine = tmp_path / "engine"
    (engine / GM_REL).parent.mkdir(parents=True)
    (engine / GM_REL).touch()
    pointer = empty_home / ".claude" / "mythras-gm" / "engine-root"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(str(engine) + "\n")

    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    got, err = _source_engine(empty_home, nowhere)
    assert got == str(engine), f"legacy breadcrumb not read: {got}\n{err}"


def test_a_codex_install_is_found_when_the_claude_tree_exists_but_is_empty(
        empty_home, tmp_path):
    """Review Focus 1. A machine with both agents installed has both trees on
    disk; only one holds the engine. A loop that stops at the first tree that
    EXISTS rather than the first that HITS reports the engine as missing on a
    perfectly good install -- and both directories exist on this developer's
    own machine, so the bug would not show up locally."""
    (empty_home / ".claude" / "plugins" / "cache").mkdir(parents=True)
    root = empty_home / LAYOUTS["codex-cache"]
    (root / GM_REL).parent.mkdir(parents=True)
    (root / GM_REL).touch()

    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    got, err = _source_engine(empty_home, nowhere)
    assert got == str(root), f"expected {root}, got {got or '<empty>'}\n{err}"


def test_no_home_at_all_is_a_miss_not_an_abort(tmp_path):
    """Review Focus 2: cron, or a bare container. Under `set -u` an unguarded
    ${HOME} aborts the hook that sourced this, which is the one thing the
    hook's header promises never happens."""
    import os
    import subprocess
    env = dict(os.environ)
    for k in ("MYTHRAS_GM_ROOT", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR",
              "HOME"):
        env.pop(k, None)
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    r = subprocess.run(
        ["bash", "-c", f'set -uo pipefail; . "{ENGINE}"; printf "%s" "${{GM_ROOT:-}}"'],
        capture_output=True, text=True, env=env, cwd=str(nowhere),
    )
    assert "unbound variable" not in r.stderr, r.stderr
    assert r.returncode == 0, f"exit {r.returncode}: {r.stderr}"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd /Users/gullyburns/purewater-campaign && uv run --with pytest --with pyyaml --with pillow pytest -q tests/test_engine_probe.py -v`

Expected: FAIL on `codex-cache`, `codex-local`, `test_the_host_neutral_breadcrumb_is_read`, and `test_a_codex_install_is_found_when_the_claude_tree_exists_but_is_empty` — each reporting an empty `GM_ROOT`. The three original layouts and the legacy-breadcrumb test PASS.

- [ ] **Step 4: Replace probe 2 (the breadcrumb)**

In `scripts/engine.sh`, replace:

```bash
  # 2. The breadcrumb the engine's own init-db drops. Deterministic and
  #    version-agnostic -- but a plugin upgrade can leave it stale, so check.
  local pointer="${HOME:-}/.claude/mythras-gm/engine-root"
  if [ -n "${HOME:-}" ] && [ -f "$pointer" ]; then
    local p; p=$(head -1 "$pointer" 2>/dev/null)
    if [ -n "$p" ] && [ -f "${p}/${gm_rel}" ]; then
      printf '%s' "$p"; return 0
    fi
  fi
```

with:

```bash
  # 2. The breadcrumb the engine's own init-db drops. Deterministic and
  #    version-agnostic -- but a plugin upgrade can leave it stale, so check.
  #
  #    Two locations, host-neutral first. The ~/.claude one is not a statement
  #    that Claude Code is installed; it is simply where the engine first put
  #    it, and an engine older than this campaign writes only that one. The
  #    engine is a separately versioned plugin, so both must be read.
  local pointer p
  for pointer in "${HOME:-}/.mythras-gm/engine-root" \
                 "${HOME:-}/.claude/mythras-gm/engine-root"; do
    [ -n "${HOME:-}" ] || break
    [ -f "$pointer" ] || continue
    # `read -r` trims the ends and nothing else: a whitespace-only file (an
    # interrupted write) reads as empty, while a path that legitimately
    # contains a space survives intact.
    p=""; read -r p < "$pointer" 2>/dev/null || true
    if [ -n "$p" ] && [ -f "${p}/${gm_rel}" ]; then
      printf '%s' "$p"; return 0
    fi
  done
```

- [ ] **Step 5: Replace probe 4 (the install-tree search)**

In `scripts/engine.sh`, replace:

```bash
  local root hit
  for root in cache synced marketplaces; do
    [ -d "${plugins}/${root}" ] || continue
    hit=$(find "${plugins}/${root}" -maxdepth 7 -path "*/${gm_rel}" 2>/dev/null \
          | sort -V | tail -1)
    if [ -n "$hit" ]; then
      printf '%s' "${hit%/${gm_rel}}"; return 0
    fi
  done
```

with:

```bash
  # Both hosts keep plugins in their own tree, and a machine can have both
  # installed with the engine in only one of them. Note the loop returns on the
  # first HIT, not the first tree that exists -- stopping at an existing but
  # empty tree is how this would report a good install as missing, and it would
  # not reproduce on a machine that has both.
  #
  #   ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/skills/...
  #   ~/.claude/plugins/synced/<bucket>/<plugin>/skills/...
  #   ~/.claude/plugins/marketplaces/<marketplace>/skills/...
  #   ~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/skills/...
  #
  # Only the two caches have a version segment, so match on the skills-path
  # suffix -- the one part that is identical in all four -- and take the
  # highest version within whichever tree answers.
  local host_tree root hit
  for host_tree in "${HOME:-}/.claude/plugins" "${HOME:-}/.codex/plugins"; do
    [ -d "$host_tree" ] || continue
    for root in cache synced marketplaces; do
      [ -d "${host_tree}/${root}" ] || continue
      hit=$(find "${host_tree}/${root}" -maxdepth 7 -path "*/${gm_rel}" 2>/dev/null \
            | sort -V | tail -1)
      if [ -n "$hit" ]; then
        printf '%s' "${hit%/${gm_rel}}"; return 0
      fi
    done
  done
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd /Users/gullyburns/purewater-campaign && uv run --with pytest --with pyyaml --with pillow pytest -q tests/test_engine_probe.py -v`
Expected: PASS, all of them, including the three original layouts and the `set -u` tests.

- [ ] **Step 7: Confirm it still finds the engine on this machine**

Run: `cd /Users/gullyburns/purewater-campaign && bash -c 'set -uo pipefail; . scripts/engine.sh; echo "GM_ROOT=$GM_ROOT"'`
Expected: `GM_ROOT=` naming a real engine directory. On this developer's machine that is `/Users/gullyburns/mythras-gm` via probe 5 — which is exactly why the tests above fake a home directory rather than trusting this.

- [ ] **Step 8: Commit**

```bash
git add scripts/engine.sh tests/test_engine_probe.py
git commit -m "fix(engine-probe): find the engine when it is installed under Codex

Every search path was ~/.claude-shaped: the install-tree probe looked only
there, and the breadcrumb probe knew only the legacy pointer. Codex installs to
~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/, so on a Codex-only
machine the campaign announced that its own engine was missing.

Both trees are searched now, returning on the first HIT rather than the first
tree that exists -- a machine with both agents has both directories, so the
wrong loop shape would have passed here and failed for everyone else. The
breadcrumb probe reads the host-neutral pointer first and keeps the legacy one,
because the engine is separately versioned and an older one writes only that."
```

---

### Task 2: The preflight publishes the campaign root and speaks to both hosts

**Files:**
- Modify: `scripts/session-start.sh` (every message branch)
- Test: `tests/test_engine_probe.py` (append)

**Interfaces:**
- Consumes: `GM_ROOT` from Task 1.
- Produces: hook stdout containing the absolute campaign root as `PUREWATER_ROOT=<path>`. Task 3's skill reads that line.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_engine_probe.py`:

```python


def test_the_hook_publishes_the_campaign_root_absolutely(empty_home, tmp_path):
    """The skill needs this package's own path and cannot compute it: a skill
    body is prose, and the plugin-root variable a host substitutes into it
    under Claude Code expands to nothing under Codex. The hook CAN resolve it
    -- both hosts set the variable for hook commands -- so the hook publishes
    it and the skill reads it from there. Same fix as the engine's own.
    """
    import shutil
    import subprocess
    staged = tmp_path / "staged-plugin"
    (staged / "scripts").mkdir(parents=True)
    for name in ("engine.sh", "session-start.sh"):
        shutil.copy2(ROOT / "scripts" / name, staged / "scripts" / name)

    env = _clean_env(empty_home)
    env["CLAUDE_PLUGIN_ROOT"] = str(staged)
    r = subprocess.run(["bash", str(staged / "scripts" / "session-start.sh")],
                       capture_output=True, text=True, env=env, cwd=str(staged))

    assert r.returncode == 0, f"exit {r.returncode}\n{r.stdout}\n{r.stderr}"
    assert f"PUREWATER_ROOT={staged}" in r.stdout, (
        "the hook must publish this package's absolute path in every branch; "
        f"without it a Codex session has no path to the campaign files:\n{r.stdout}")


def test_the_hook_names_a_skill_not_only_a_slash_command(empty_home, tmp_path):
    """Review Focus 4. Codex has no commands component, so an instruction to
    type /purewater:start is an instruction a Codex user cannot follow."""
    import shutil
    import subprocess
    staged = tmp_path / "staged-plugin"
    (staged / "scripts").mkdir(parents=True)
    for name in ("engine.sh", "session-start.sh"):
        shutil.copy2(ROOT / "scripts" / name, staged / "scripts" / name)
    env = _clean_env(empty_home)
    env["CLAUDE_PLUGIN_ROOT"] = str(staged)
    out = subprocess.run(["bash", str(staged / "scripts" / "session-start.sh")],
                         capture_output=True, text=True, env=env,
                         cwd=str(staged)).stdout

    assert "purewater-start" in out, (
        "the engine-missing branch sends the player to a Claude-Code-only "
        f"install command with no skill named:\n{out}")
    assert "/plugin install" not in out, (
        "that command does not exist in Codex; describe the plugin browser")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/gullyburns/purewater-campaign && uv run --with pytest --with pyyaml --with pillow pytest -q tests/test_engine_probe.py -k "publishes or names_a_skill" -v`
Expected: FAIL — no `PUREWATER_ROOT=` in stdout; `/plugin install` present.

- [ ] **Step 3: Publish the root and neutralise the engine-missing branch**

In `scripts/session-start.sh`, replace the engine-missing message:

```bash
if [ -z "${GM_ROOT}" ]; then
  cat <<MSG
purewater: the mythras-gm engine is not installed, so this campaign cannot run.

  /plugin install mythras-gm@fourth-wall-gaming

Purewater declares that dependency, so it should have arrived automatically --
if it did not, install it by hand, or set MYTHRAS_GM_ROOT to a checkout. Until
then: do not GM this campaign off the files in this package. They are a source
export, not a save file, and nothing you change in them reaches the game.
MSG
  exit 0
fi
```

with:

```bash
if [ -z "${GM_ROOT}" ]; then
  cat <<MSG
purewater: the mythras-gm engine is not installed, so this campaign cannot run.
PUREWATER_ROOT=${PW}

Install it from the same marketplace this campaign came from -- open the plugin
browser (/plugins in Codex, /plugin in Claude Code), find mythras-gm, install
it, and START A NEW SESSION: a plugin's skills only appear in a session opened
after it was installed.

Purewater declares that dependency, so it should have arrived automatically. If
it did not, set MYTHRAS_GM_ROOT to a checkout of the engine. If it IS installed
and you are reading this anyway, run the engine's install check -- it reports
which lookup failed:

  mythras-gm/scripts/verify-install.sh

Until then: do not GM this campaign off the files in this package, and do not
follow the purewater-start skill. They are a source export, not a save file,
and nothing you change in them reaches the game.
MSG
  exit 0
fi
```

- [ ] **Step 4: Publish the root in the remaining branches**

In the same file, append ` PUREWATER_ROOT=${PW}` to each of the other three terminal messages. The not-started branch:

```bash
    echo "purewater: the campaign is imported and has not been started (clock ${CLOCK}). Follow the purewater-start skill (/purewater:start in Claude Code) to choose a character and open the scenario. MYTH_CAMPAIGN=${SEED_ID} PUREWATER_ROOT=${PW}"
```

The in-progress branch:

```bash
    echo "purewater: a game is in progress -- ${SEED_ID}, clock ${CLOCK}, session ${SESSION}. Resume it with the mythras-play skill (/mythras-gm:play in Claude Code). Do NOT follow purewater-start; it is for a campaign that has not begun. PUREWATER_ROOT=${PW}"
```

The not-imported branch:

```bash
echo "purewater: the campaign is installed but has not been imported into the database yet. Follow the purewater-start skill (/purewater:start in Claude Code) -- it will import ${SEED_ID} from ${PW} and walk the player through choosing a character. Do not GM from the files in this package; they are a source export, not the save. PUREWATER_ROOT=${PW}"
```

And in the preflight-failed branch, replace `Offer to run /mythras-gm:setup.` with:

```bash
Offer to follow the mythras-setup skill (/mythras-gm:setup in Claude Code).
PUREWATER_ROOT=${PW}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd /Users/gullyburns/purewater-campaign && uv run --with pytest --with pyyaml --with pillow pytest -q tests/test_engine_probe.py -v`
Expected: PASS, all of them — including the pre-existing `test_the_hook_never_exits_non_zero`, which asserts the engine-missing branch still says "not installed".

- [ ] **Step 6: Run the hook by hand and read what it says**

Run: `cd /Users/gullyburns/purewater-campaign && bash scripts/session-start.sh`
Expected: one branch's message, carrying `PUREWATER_ROOT=/Users/gullyburns/purewater-campaign`, exit 0.

- [ ] **Step 7: Commit**

```bash
git add scripts/session-start.sh tests/test_engine_probe.py
git commit -m "fix(preflight): publish the campaign's absolute root, and speak to both hosts

The skill needs this package's path and cannot compute one: a skill body is
prose, and the plugin-root variable Claude Code substitutes into it expands to
nothing under Codex. The hook can resolve it -- both hosts set that variable for
hook commands -- so the hook now publishes PUREWATER_ROOT in every branch.

Also stopped sending players to /plugin install and /purewater:start as if they
were the only route. Codex has no commands component, so each entry point names
its skill with the slash command in parentheses."
```

---

### Task 3: The start ritual becomes a skill both hosts can load

**Files:**
- Create: `skills/purewater-start/SKILL.md` (the body of `commands/start.md`, 147 lines, with its 7 plugin-root literals replaced)
- Modify: `commands/start.md` (reduced to a wrapper)
- Modify: `skills/purewater/SKILL.md:18` (the `PW=` assignment) and `skills/purewater/SKILL.md:118-122` (the entry-point table)
- Modify: `tests/test_seed.py:66` (the `shipped` list), `:88` and `:97` (two tests that read `commands/start.md` by path)
- Test: `tests/test_portability.py` (create)

**Interfaces:**
- Consumes: `PUREWATER_ROOT=<path>` from Task 2's hook output; `GM_ROOT`/`GM_SKILL`/`gm()` from Task 1's `engine.sh`.
- Produces: skill `purewater-start`, named by `commands/start.md`'s `skill:` frontmatter field and by Task 2's hook messages.

- [ ] **Step 1: Write the failing guard**

Create `tests/test_portability.py`:

```python
"""Invariants that keep this campaign installable in both Claude Code and Codex.

Codex reads this repository's Claude manifests directly -- `.claude-plugin/
plugin.json` is a recognised compatibility manifest and `hooks/hooks.json` is
discovered by default -- so there is no second plugin to build. What Codex does
NOT have is a commands component, and it does not substitute a plugin-root
variable into skill prose. These tests are what stops either difference
quietly returning.

The engine's equivalent is mythras-gm/tests/test_portability.py; the reasoning
is argued there in full.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

VENDORED = (".venv", "__pycache__", "node_modules", "site-packages")
SKILL_DOCS = sorted(p for p in (ROOT / "skills").rglob("*.md")
                    if not any(part in VENDORED for part in p.parts))
COMMANDS = sorted((ROOT / "commands").glob("*.md"))
SKILL_FILES = sorted((ROOT / "skills").glob("*/SKILL.md"))


def frontmatter(path):
    """The YAML block between the opening and closing `---`, as a flat dict.
    Regex rather than PyYAML so this guard has no dependency of its own."""
    match = re.match(r"^---\n(.*?)\n---\n", path.read_text(), re.DOTALL)
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
    """If a layout change empties a glob, every test below passes vacuously."""
    assert SKILL_DOCS, "no skills/**/*.md found"
    assert COMMANDS, "no commands/*.md found"
    assert SKILL_FILES, "no skills/*/SKILL.md found"


@pytest.mark.parametrize("doc", SKILL_DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_plugin_root_literal_in_shipped_prose(doc):
    """A path a Codex session cannot resolve. The variable is host-substituted
    text, not a shell variable -- it is absent from the model's environment in
    both hosts, and Claude Code was expanding it when it loaded the file. Under
    Codex it expands to nothing, so `. "/scripts/engine.sh"` fails and the
    campaign reports its own engine as missing on a working install."""
    hits = [n for n, line in enumerate(doc.read_text().splitlines(), 1)
            if "CLAUDE_PLUGIN_ROOT" in line]
    assert not hits, (
        f"{doc.relative_to(ROOT)} names CLAUDE_PLUGIN_ROOT on line(s) {hits}; "
        f"use $PW, which the preflight publishes as PUREWATER_ROOT.")


@pytest.mark.parametrize("command", COMMANDS, ids=lambda p: p.name)
def test_every_command_delegates_to_a_skill(command):
    """Codex has no commands component, so a command file is a Claude-Code-only
    entry point and its body must live in a skill both hosts can load. The
    delegation is a frontmatter field rather than inferred from the prose:
    every one of these files mentions "purewater" somewhere."""
    names = {f.parent.name for f in SKILL_FILES}
    declared = frontmatter(command).get("skill")
    assert declared, (
        f"commands/{command.name} declares no `skill:`, so its body reaches no "
        f"Codex session. Move the body into a skill and point at it.")
    assert declared in names, (
        f"commands/{command.name} delegates to {declared!r}, not one of {sorted(names)}")


@pytest.mark.parametrize("skill", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_skill_declares_itself(skill):
    """Both hosts match on the description and address the skill by `name`."""
    fields = frontmatter(skill)
    assert fields.get("name"), f"{skill.relative_to(ROOT)} has no `name`"
    assert fields.get("description"), f"{skill.relative_to(ROOT)} has no `description`"
    assert fields["name"] == skill.parent.name, (
        f"{skill.relative_to(ROOT)} is named {fields['name']!r} but sits in "
        f"{skill.parent.name!r}")


def test_the_start_skill_can_resolve_its_own_root(skill=None):
    """Review Focus 3. On a fresh Codex install the hooks are not trusted yet,
    so the preflight never ran and PUREWATER_ROOT was never published. The
    skill must say where else to get the path rather than sourcing an empty
    one, because sourcing an empty one reports the engine as missing."""
    text = (ROOT / "skills" / "purewater-start" / "SKILL.md").read_text()
    assert "PUREWATER_ROOT" in text, "the skill never says where $PW comes from"
    assert "directory" in text.lower(), (
        "the skill gives no fallback for a session where the preflight did not "
        "run; it must say the package root is this skill's own parent")


@pytest.mark.parametrize("doc", SKILL_DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_shipped_skill_names_a_slash_command_without_its_skill(doc):
    """Review Focus 4: a Codex session cannot type /purewater:start. Naming the
    slash command is fine -- as a parenthetical beside the skill."""
    text = doc.read_text()
    for command, skill in (("/purewater:start", "purewater-start"),
                           ("/mythras-gm:play", "mythras-play"),
                           ("/mythras-gm:setup", "mythras-setup")):
        if command in text:
            assert skill in text, (
                f"{doc.relative_to(ROOT)} tells the reader to run {command} and "
                f"never names the {skill} skill, which is the only route in Codex")
```

- [ ] **Step 2: Run the guard to verify it fails**

Run: `cd /Users/gullyburns/purewater-campaign && uv run --with pytest --with pyyaml --with pillow pytest -q tests/test_portability.py -v`

Expected: FAIL on `skills/purewater/SKILL.md` (the `PW=` literal), on `commands/start.md` (no `skill:` field), on `test_the_start_skill_can_resolve_its_own_root` (no such file), and on the slash-command test for `skills/purewater/SKILL.md`.

- [ ] **Step 3: Move the start ritual into a skill**

```bash
cd /Users/gullyburns/purewater-campaign
mkdir -p skills/purewater-start
git mv commands/start.md skills/purewater-start/SKILL.md
```

Replace the frontmatter of `skills/purewater-start/SKILL.md` with:

```markdown
---
name: purewater-start
description: Begin the Purewater campaign from the beginning — introduce Mythras, import the scenario, make or choose a character, and open the first scene. Use only when the campaign has never been played on this machine; a game already in progress is resumed with the mythras-play skill instead.
---
```

Then replace the engine-resolution block (the first code fence, formerly lines 12-17):

```bash
. "${CLAUDE_PLUGIN_ROOT}/scripts/engine.sh"   # sets GM_ROOT, GM_SKILL, GM_CLI, gm()
[ -z "$GM_ROOT" ] && echo "mythras-gm is not installed: /plugin install mythras-gm@fourth-wall-gaming"
```

with:

```bash
. "${PW}/scripts/engine.sh"   # sets GM_ROOT, GM_SKILL, GM_CLI, gm()
[ -z "$GM_ROOT" ] && echo "the mythras-gm engine is not installed or cannot be found"
```

and insert immediately above that fence:

```markdown
**Where `$PW` comes from**, in this order: the preflight prints
`PUREWATER_ROOT=<path>` at session start — use that. If this session has no such
line (on Codex that usually means the plugin's startup check has not been
approved yet), `$PW` is the **directory two levels above this `SKILL.md`** —
this file is at `<PW>/skills/purewater-start/SKILL.md`. Do not reach for a
plugin-root environment variable: your host sets one for hook commands only,
never in your shell, so here it expands to nothing and every path below becomes
a path that does not exist.

If the engine cannot be found at all, stop. Say the engine is not installed,
point at the plugin browser, and do not GM from the files in this package —
they are a source export, not a save.
```

- [ ] **Step 4: Replace the remaining six literals**

In `skills/purewater-start/SKILL.md`, replace every remaining `${CLAUDE_PLUGIN_ROOT}` with `${PW}`:

```bash
cd /Users/gullyburns/purewater-campaign
python3 - <<'PY'
import pathlib
p = pathlib.Path("skills/purewater-start/SKILL.md")
t = p.read_text()
n = t.count("${CLAUDE_PLUGIN_ROOT}")
p.write_text(t.replace("${CLAUDE_PLUGIN_ROOT}", "${PW}"))
print(f"replaced {n}")
PY
```

Expected: `replaced 6` (the seventh was the engine-resolution line, already rewritten by hand in Step 3).

- [ ] **Step 5: Leave the command as a wrapper**

Create `commands/start.md`:

```markdown
---
description: Begin Purewater from the beginning — introduce Mythras, import the scenario, make or choose a character, and open the first scene.
skill: purewater-start
---

Follow the **`purewater-start`** skill, in full and in order.

The ritual lives in the skill rather than here because Codex has no commands
component — skills, MCP servers and hooks only — so a ritual kept in this file
would reach a Codex session not at all. This command is the slash-menu entry
point for it; the skill is the thing itself.
```

- [ ] **Step 6: Fix the campaign skill's own root and entry-point table**

In `skills/purewater/SKILL.md`, replace:

```bash
PW="${CLAUDE_PLUGIN_ROOT}"
. "${PW}/scripts/engine.sh"    # sets GM_ROOT, GM_SKILL, GM_CLI and a gm() shell function
```

with:

```bash
. "${PW}/scripts/engine.sh"    # sets GM_ROOT, GM_SKILL, GM_CLI and a gm() shell function
```

and insert above that fence:

```markdown
`$PW` is this package's root. The preflight prints it as `PUREWATER_ROOT=<path>`
at session start; failing that it is the directory two levels above this
`SKILL.md`. A plugin-root environment variable is not it — your host sets one
for hook commands only, never in your shell.
```

Then replace the entry-point table at the end of the file:

```markdown
| `/purewater:start` | first run: brief, import, choose or roll a character, open the scene |
| `/mythras-gm:play` | every session after that |
| `/mythras-gm:setup` | once per machine, if the database is not up |
```

with:

```markdown
| skill | slash command (Claude Code) | when |
|---|---|---|
| `purewater-start` | `/purewater:start` | first run: brief, import, choose or roll a character, open the scene |
| `mythras-play` | `/mythras-gm:play` | every session after that |
| `mythras-setup` | `/mythras-gm:setup` | once per machine, if the database is not up |

Name the **skill** when you tell a player what to do next. The slash commands
exist only in Claude Code; in Codex there is nothing to type.
```

- [ ] **Step 7: Name the resume skill, not only its slash command**

The body of the moved file tells a returning player to use `/mythras-gm:play`,
which does not exist in Codex — and `tests/test_seed.py:90` asserts that string
is present, because handing an in-progress game to the resume path is the worst
thing this plugin could get wrong. Keep the slash command and add the skill:

```bash
cd /Users/gullyburns/purewater-campaign
python3 - <<'PY'
import pathlib
p = pathlib.Path("skills/purewater-start/SKILL.md")
t = p.read_text()
old = "stop and use `/mythras-gm:play`\ninstead**"
new = "stop and use the **`mythras-play`** skill\n(`/mythras-gm:play` in Claude Code) instead**"
assert old in t, "the in-progress warning has been reworded; find it and fix by hand"
p.write_text(t.replace(old, new))
print("ok")
PY
```

If the assertion fires, the warning has been reworded since this plan was
written: find the `/mythras-gm:play` mention in the first twelve lines and add
`mythras-play` beside it by hand. Do not delete the slash command — a test
depends on it.

- [ ] **Step 8: Repoint the seed tests at the moved file**

Three sites in `tests/test_seed.py` read `commands/start.md`. Two will fail
outright; the first will **silently stop checking**, which is worse — its loop
has an `if not f.exists(): continue`, so the campaign-id assertion would just
skip the file from now on.

In `tests/test_seed.py:66`, replace the `shipped` list:

```python
    shipped = ["campaign.yaml", "README.md", "skills/purewater/SKILL.md",
               "skills/purewater-start/SKILL.md", "scripts/session-start.sh"]
```

and directly below it, replace the silent skip:

```python
    for rel in shipped:
        f = ROOT / rel
        if not f.exists():
            continue
```

with:

```python
    for rel in shipped:
        f = ROOT / rel
        # No skip-if-missing. A renamed file used to drop out of this check
        # silently, which is how a document naming a dead campaign id would
        # survive the very test written to catch it.
        assert f.exists(), f"{rel} is in the shipped list but not on disk"
```

Then in both `test_the_start_command_guards_against_resetting_a_live_game` and
`test_the_new_player_path_briefs_before_it_asks`, replace:

```python
    cmd = (ROOT / "commands" / "start.md").read_text()
```

with:

```python
    cmd = (ROOT / "skills" / "purewater-start" / "SKILL.md").read_text()
```

- [ ] **Step 9: Run the guard to verify it passes**

Run: `cd /Users/gullyburns/purewater-campaign && uv run --with pytest --with pyyaml --with pillow pytest -q tests/test_portability.py -v`
Expected: PASS, all of them.

- [ ] **Step 10: Run the whole suite**

Run: `cd /Users/gullyburns/purewater-campaign && uv run --with pytest --with pyyaml --with pillow pytest -q tests/`
Expected: exit 0, including `test_seed.py`'s three repointed assertions and `test_guide.py` (which reads `guide/` and `lore/`, not `commands/`, so it is unaffected).

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "feat(start): the zero-state ritual becomes a skill both hosts can load

commands/start.md was the only route into a new game, and Codex has no commands
component -- so the whole path (brief, import, make a character, open scene one)
reached a Codex session not at all. It is now skills/purewater-start, with the
command kept as the Claude Code slash-menu wrapper.

Its seven plugin-root literals, and the campaign skill's own PW= assignment,
expanded to nothing under Codex: the variable is host-substituted text, not a
shell variable, and Claude Code was expanding it at load time. \$PW now comes
from the PUREWATER_ROOT line the preflight publishes, with this skill's own
location as the fallback for a session whose hooks are not trusted yet.

Entry points name their skill, with the slash command as a parenthetical.

test_seed.py's three references follow the file. Its campaign-id loop loses its
skip-if-missing guard at the same time: a renamed file dropped out of that check
silently, which is how a document naming a dead campaign id would have survived
the very test written to catch it."
```

---

### Task 4: The hook timeout, and contributor instructions Codex can read

**Files:**
- Modify: `hooks/hooks.json:11` (`timeout`)
- Rename: `CLAUDE.md` → `AGENTS.md`; create a new `CLAUDE.md` importing it
- Modify: `README.md` (3 plugin-root literals in contributor examples)
- Test: `tests/test_portability.py` (append)

**Interfaces:**
- Consumes: the guard file created in Task 3.
- Produces: nothing later tasks rely on. This is the last task.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_portability.py`:

```python


def test_hook_timeouts_are_plausible_seconds():
    """`timeout` is seconds in both hosts (Claude Code: "Seconds before
    cancelling", default 600; Codex: the same, and it caps most events at 600).
    A millisecond value reads as days and silently disables the timeout."""
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
        f"timeout is in SECONDS, not milliseconds: {too_long}")


def test_the_contributor_instructions_reach_both_agents():
    """Claude Code reads AGENTS.md only when no CLAUDE.md sits at or above the
    working directory; Codex reads AGENTS.md only. So a bare AGENTS.md beside a
    CLAUDE.md is read by one and ignored by the other. The documented way to
    have one file serve both is a CLAUDE.md that imports it.

    This repository's instructions are for contributors in a clone, not for
    players -- they are not shipped. But a contributor using Codex in that
    clone currently gets none of them."""
    agents = ROOT / "AGENTS.md"
    claude = ROOT / "CLAUDE.md"
    assert agents.exists(), "no AGENTS.md: a Codex contributor gets no instructions"
    assert claude.exists(), "no CLAUDE.md"
    assert "@AGENTS.md" in claude.read_text(), (
        "CLAUDE.md does not import AGENTS.md, so Claude Code reads CLAUDE.md "
        "only and the two can drift")
    assert "campaign package" in agents.read_text(), (
        "AGENTS.md exists but does not hold the contributor instructions")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/gullyburns/purewater-campaign && uv run --with pytest --with pyyaml --with pillow pytest -q tests/test_portability.py -k "timeout or contributor" -v`
Expected: FAIL — `timeout is in SECONDS, not milliseconds: [('SessionStart', 120000)]`, and `no AGENTS.md`.

- [ ] **Step 3: Fix the timeout**

In `hooks/hooks.json`, change `"timeout": 120000` to `"timeout": 120`.

- [ ] **Step 4: Move the contributor instructions**

```bash
cd /Users/gullyburns/purewater-campaign
git mv CLAUDE.md AGENTS.md
cat > CLAUDE.md <<'EOF'
@AGENTS.md

## Why this file is two lines

The instructions live in `AGENTS.md` so that one file serves both agents. Codex
reads `AGENTS.md` directly; Claude Code reads it **only** when no `CLAUDE.md`
sits at or above the working directory — and this repository has one, so without
the import above, Claude Code would read this file and silently ignore them.

Keep the instructions in `AGENTS.md`. Add Claude-Code-specific notes below this
line, never above it, and never a second copy of anything in `AGENTS.md`.
EOF
```

- [ ] **Step 5: Fix the README's contributor examples**

The three plugin-root literals in `README.md` are in examples showing a campaign how to find the engine, so they teach the broken pattern. Replace them:

```bash
cd /Users/gullyburns/purewater-campaign
python3 - <<'PY'
import pathlib
p = pathlib.Path("README.md")
t = p.read_text()
t = t.replace(
    'A plugin\'s `${CLAUDE_PLUGIN_ROOT}` resolves to its own directory and there is no',
    'A plugin\'s own plugin-root variable resolves to its own directory, is set for\nhook commands only, and there is no')
t = t.replace('. "${CLAUDE_PLUGIN_ROOT}/scripts/engine.sh"',
              '. "${PW}/scripts/engine.sh"   # $PW: see PUREWATER_ROOT in the preflight output')
t = t.replace('3. `gm import-campaign --path "${CLAUDE_PLUGIN_ROOT}"`.',
              '3. `gm import-campaign --path "${PW}"`.')
p.write_text(t)
print("remaining:", t.count("CLAUDE_PLUGIN_ROOT"))
PY
```

Expected: `remaining: 0`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd /Users/gullyburns/purewater-campaign && uv run --with pytest --with pyyaml --with pillow pytest -q tests/test_portability.py -v`
Expected: PASS, all of them.

- [ ] **Step 7: Run the whole suite and the hook once more**

Run:
```bash
cd /Users/gullyburns/purewater-campaign
uv run --with pytest --with pyyaml --with pillow pytest -q tests/
bash scripts/session-start.sh
```
Expected: suite exit 0; the hook prints one branch's message with `PUREWATER_ROOT=` and exits 0.

- [ ] **Step 8: Commit, push and open the PR**

```bash
cd /Users/gullyburns/purewater-campaign
git add -A
git commit -m "fix(hooks): the timeout was in milliseconds, and the canon reached one agent

120000 seconds is thirty-three hours: no timeout at all, for this hook's whole
life. It is seconds in both hosts.

The contributor instructions move to AGENTS.md with CLAUDE.md importing them.
Codex reads AGENTS.md only, Claude Code reads it only when no CLAUDE.md sits
beside it -- so a bare AGENTS.md would have been read by one agent and ignored
by the other. The README's examples stop teaching the plugin-root pattern that
does not survive Codex."
git push -u origin feat/codex-portability
gh pr create --base main --title "Run Purewater in Codex: the sibling-engine locator, and the three shipped divergences" --body "See mythras-gm/docs/superpowers/plans/2026-10-10-purewater-codex-portability.md for the argument. Engine-side precedent: fourth-wall-gaming/mythras-gm#12."
```

---

## Self-Review

**Spec coverage.** Against `mythras-gm/docs/CODEX.md`: unresolvable plugin-root paths → Tasks 2 and 3; no commands component → Task 3; hook timeout units → Task 4; `AGENTS.md` vs `CLAUDE.md` → Task 4; the sibling-engine lookup, which that document names as the campaign-specific case → Task 1. Nothing in the contract is unaddressed.

**Placeholders.** None: every step carries the code, the command, or the exact replacement text, and Step 8 of Task 3 names the one thing that may need a judgement call (a sibling test referencing the moved file) with instructions for handling it.

**Type consistency.** `GM_ROOT`, `GM_SKILL`, `GM_CLI` and `gm()` keep their names throughout — Task 1 produces them, Tasks 2 and 3 consume them. `PUREWATER_ROOT` is the hook's published key in Task 2 and the string Task 3's tests and prose both look for. `$PW` is the shell variable in every skill body. The guard's `frontmatter()` helper has the same signature as the engine repo's, deliberately, so the two files stay comparable.

**Review Focus coverage.** 1 → Task 1 (`test_a_codex_install_is_found_when_the_claude_tree_exists_but_is_empty`). 2 → Task 1 (`test_no_home_at_all_is_a_miss_not_an_abort`). 3 → Task 3 (`test_the_start_skill_can_resolve_its_own_root`). 4 → Task 2 (`test_the_hook_names_a_skill_not_only_a_slash_command`) and Task 3 (`test_no_shipped_skill_names_a_slash_command_without_its_skill`). 5 → Task 1 (`test_the_legacy_breadcrumb_still_works_alone`).

**Ordering note.** Task 1 must land before Task 2, because Task 2's tests source `engine.sh` under a faked home and would otherwise fail for Task 1's reason rather than their own. Tasks 3 and 4 are independent of each other.

**Not in scope.** The Veilwrack campaign has the same shape and is not touched here; once this lands, Tasks 1-4 are a template for it. Porting `agents/*.md`-style subagents is not in scope for either — this repository has none.
