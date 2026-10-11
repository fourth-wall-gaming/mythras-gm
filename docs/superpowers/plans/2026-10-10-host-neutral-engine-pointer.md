# Host-Neutral Engine Pointer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the pointer file a campaign plugin uses to find this engine readable on any host, so the one lookup probe that survives Codex becomes reliable rather than incidental.

**Architecture:** `init-db` writes the engine's own path to a breadcrumb file so a campaign plugin — which cannot resolve a sibling plugin's root — can read it instead of searching. Today that file is `~/.claude/mythras-gm/engine-root`, a path chosen when Claude Code was the only host. The path has nothing to do with Claude Code being installed, so it keeps working under Codex, but a campaign author cannot know that and will not trust it. This writes **both** a host-neutral location and the original, extracting the write into a small function so it is unit-testable and so one unwritable location cannot stop the other.

**Tech Stack:** Python 3.12+, pytest, bash. No new dependencies.

**Spec:** `docs/CODEX.md` — the shipped dual-host contract. The decisions this plan implements were settled in the session that produced `tests/test_portability.py`; this document is the argument for them.

**Repo:** `mythras-gm` (this one). Branch off `main`.

## Global Constraints

- Hook `timeout` values are **seconds** in both hosts; never milliseconds. Codex caps most events at 600.
- `${CLAUDE_PLUGIN_ROOT}` must not appear in any file under `skills/**/*.md`. `tests/test_portability.py` enforces this.
- The legacy pointer path `~/.claude/mythras-gm/engine-root` must keep being written. Campaign plugins already installed read only that path, and a campaign is a separately versioned plugin that may not be updated for months.
- Nothing in `scripts/verify-install.sh` may change state: no installs, downloads, config edits or database writes.
- `init-db` must stay idempotent and must not fail because a pointer could not be written. A sandboxed host may permit one location and refuse the other.
- Coverage floor is 74% (`pyproject.toml`). The suite must stay above it.

## Review Focus

Five conditions this change implies that no task's happy path exercises. Each has its test placed in the task that owns the code.

1. **Both pointer locations unwritable** — a read-only home directory. `init-db` must still report `Ready.` and not raise; the pointer is a convenience, not a precondition. *(Task 1)*
2. **A stale host-neutral pointer naming a directory that no longer holds the CLI** — a plugin upgrade moves the engine. The reader must skip it and fall through, never return a path with no engine at it. *(Task 2)*
3. **Both pointers present and disagreeing** — the host-neutral one is newer, so it must win; whichever is checked first must be the one written most recently. *(Task 2)*
4. **`$HOME` unset entirely** — cron, a bare container. `os.path.expanduser` yields a relative-ish path and the shell reader's `${HOME:-}` is empty; neither may crash or write into the working directory. *(Task 1)*
5. **The pointer file exists but is empty or whitespace** — an interrupted write. The reader must treat it as absent rather than resolving `/skills/mythras-gm/mythras_gm.py`. *(Task 2)*

---

### Task 1: The engine writes both pointers, and survives either failing

**Files:**
- Modify: `skills/mythras-gm/mythras_gm.py:4267` (the `ENGINE_POINTER` constant)
- Modify: `skills/mythras-gm/mythras_gm.py:4787-4796` (the write site inside `cmd_init_db`)
- Test: `tests/test_portability.py` (append)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `ENGINE_POINTERS: tuple[str, ...]` — pointer paths, host-neutral first; `ENGINE_POINTER: str` — retained alias for the legacy path, still referenced by docs; `_write_engine_pointers(root: str, paths: tuple[str, ...] = ENGINE_POINTERS) -> list[tuple[str, bool, str]]` returning `(path, ok, detail)` per location. Task 2 consumes `ENGINE_POINTERS` as the list of paths its shell reader must check, in the same order.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_portability.py`:

```python


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run -q --project skills/mythras-gm --with pytest pytest tests/test_portability.py -k pointer -v`

Expected: FAIL — `AttributeError: module 'mythras_gm' has no attribute '_write_engine_pointers'` on the first three, and `AttributeError: ... 'ENGINE_POINTERS'` on the ordering test.

- [ ] **Step 3: Replace the constant**

In `skills/mythras-gm/mythras_gm.py`, replace line 4267:

```python
ENGINE_POINTER = os.path.expanduser("~/.claude/mythras-gm/engine-root")
```

with:

```python
# A plugin cannot resolve a sibling plugin's root, so a campaign package finds
# this engine by reading a pointer file rather than by searching for it. Two
# locations, written in this order and read in this order:
#
#   ~/.mythras-gm/engine-root        host-neutral; what a campaign should read
#   ~/.claude/mythras-gm/engine-root the original; what every campaign already
#                                    shipped reads, and the only one they read
#
# The second is not a statement that Claude Code is installed -- it is simply
# where this was first put, and it keeps working under Codex untouched. But a
# campaign author reading that path cannot know it is host-neutral, and a
# campaign is a separately versioned plugin that may not be updated for
# months, so both are written until the campaigns have moved.
ENGINE_POINTERS = (
    os.path.expanduser("~/.mythras-gm/engine-root"),
    os.path.expanduser("~/.claude/mythras-gm/engine-root"),
)
ENGINE_POINTER = ENGINE_POINTERS[1]   # cited in docs and by installed campaigns
```

- [ ] **Step 4: Add the writer**

Immediately below that block, add:

```python
def _write_engine_pointers(root, paths=ENGINE_POINTERS):
    """Record this engine's location at every pointer path.

    Returns a list of (path, ok, detail). Each location is attempted
    independently and a failure is reported rather than raised: a sandboxed
    host may permit one and refuse the other, and `init-db` must still come up
    either way. The pointer is how a campaign avoids searching -- it is a
    convenience, never a precondition.
    """
    results = []
    for path in paths:
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w") as fh:
                fh.write(root + "\n")
            results.append((path, True, ""))
        except Exception as e:
            results.append((path, False, str(e)[:120]))
    return results
```

- [ ] **Step 5: Rewrite the call site**

Replace `skills/mythras-gm/mythras_gm.py:4790-4796`:

```python
    try:
        os.makedirs(os.path.dirname(ENGINE_POINTER), exist_ok=True)
        with open(ENGINE_POINTER, "w") as fh:
            fh.write(_PROJECT_ROOT + "\n")
        note("engine pointer", True, ENGINE_POINTER)
    except Exception as e:
        note("engine pointer", False, str(e)[:120])
```

with:

```python
    for path, ok, detail in _write_engine_pointers(_PROJECT_ROOT):
        note(f"engine pointer {path}", ok, detail)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run -q --project skills/mythras-gm --with pytest pytest tests/test_portability.py -k pointer -v`
Expected: PASS, 5 tests.

- [ ] **Step 7: Confirm `init-db` still comes up and reports both pointers**

Run: `uv run -q --project skills/mythras-gm python skills/mythras-gm/mythras_gm.py init-db | python3 -m json.tool | grep -A2 "engine pointer"`

Expected: two `engine pointer …` steps, both `"ok": true`, and the command's `verdict` is `Ready.`

- [ ] **Step 8: Run the full suite**

Run: `MYTHRAS_REQUIRE_DB=1 uv run -q --project skills/mythras-gm --with pytest --with pytest-cov pytest tests/ -p no:warnings --cov --cov-report=term`
Expected: exit 0, coverage above the 74% floor.

- [ ] **Step 9: Commit**

```bash
git add skills/mythras-gm/mythras_gm.py tests/test_portability.py
git commit -m "fix(engine): write the campaign pointer somewhere a campaign can trust

~/.claude/mythras-gm/engine-root is where this was first put, not a statement
about which agent is installed -- it works under Codex unchanged. But a
campaign reading that path cannot know that, and a campaign is a separately
versioned plugin. So the engine writes a host-neutral location too and keeps
the original, which is the only one every campaign shipped so far reads.

Extracted to _write_engine_pointers so each location is attempted
independently: a sandboxed host can permit one and refuse the other, and
init-db must come up either way."
```

---

### Task 2: The install check reads either pointer, and distrusts a bad one

**Files:**
- Modify: `scripts/verify-install.sh:71-76` (the breadcrumb probe inside `find_engine`)
- Test: `tests/test_portability.py` (append)

**Interfaces:**
- Consumes: `ENGINE_POINTERS` from Task 1 — the shell probe must check the same two paths in the same order.
- Produces: nothing later tasks rely on.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_portability.py`:

```python


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run -q --project skills/mythras-gm --with pytest pytest tests/test_portability.py -k "pointer and check or stale or disagree or empty_pointer" -v`

Expected: `test_the_check_finds_the_engine_from_the_host_neutral_pointer` FAILS (the script checks only `~/.claude/...`), `test_the_check_still_reads_the_legacy_pointer` PASSES already, and the stale / disagree / empty tests FAIL or pass accidentally — note which, because only the first is proof the probe is wrong.

- [ ] **Step 3: Replace the probe**

In `scripts/verify-install.sh`, replace these lines inside `find_engine()`:

```bash
  # The breadcrumb the engine drops when it first starts. Host-neutral.
  local pointer="${HOME}/.claude/mythras-gm/engine-root"
  if [ -f "$pointer" ]; then
    local p; p=$(head -1 "$pointer" 2>/dev/null)
    [ -n "$p" ] && [ -f "${p}/${GM_REL}" ] && { printf '%s' "$p"; return 0; }
  fi
```

with:

```bash
  # The breadcrumb the engine drops when it first starts, host-neutral location
  # first. Each is CHECKED before it is trusted: a plugin upgrade can leave a
  # pointer naming a directory that no longer holds the CLI, and reporting that
  # path as the engine sends somebody to debug the wrong directory. An empty or
  # whitespace-only file (an interrupted write) must read as absent, not as "/".
  local pointer p
  for pointer in "${HOME:-}/.mythras-gm/engine-root" \
                 "${HOME:-}/.claude/mythras-gm/engine-root"; do
    [ -f "$pointer" ] || continue
    p=$(head -1 "$pointer" 2>/dev/null | tr -d '[:space:]')
    [ -n "$p" ] && [ -f "${p}/${GM_REL}" ] && { printf '%s' "$p"; return 0; }
  done
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run -q --project skills/mythras-gm --with pytest pytest tests/test_portability.py -v`
Expected: PASS, all of them.

- [ ] **Step 5: Confirm the check still passes on this machine**

Run: `bash scripts/verify-install.sh; echo "EXIT=$?"`
Expected: every row `ok`, `EXIT=0`.

- [ ] **Step 6: Document the pointer in the Codex guide**

Append to `docs/CODEX.md`, under the existing "Checking a machine where it will not start" section:

```markdown
### How a campaign finds the engine

A campaign plugin (Purewater, Veilwrack) cannot resolve a sibling plugin's
root — no host provides a variable for it — so it reads a pointer file the
engine writes on first run:

| Path | Read by |
| --- | --- |
| `~/.mythras-gm/engine-root` | current campaigns, any host |
| `~/.claude/mythras-gm/engine-root` | every campaign shipped so far |

Both are written, and both are checked before being trusted: a plugin upgrade
can leave one naming a directory that no longer holds the engine. If a campaign
reports the engine as missing on a machine where `verify-install.sh` finds it,
that pointer is the first thing to look at — and `MYTHRAS_GM_ROOT` overrides
the lot.
```

- [ ] **Step 7: Run the full suite**

Run: `MYTHRAS_REQUIRE_DB=1 uv run -q --project skills/mythras-gm --with pytest --with pytest-cov pytest tests/ -p no:warnings --cov --cov-report=term`
Expected: exit 0, coverage above 74%.

- [ ] **Step 8: Commit**

```bash
git add scripts/verify-install.sh tests/test_portability.py docs/CODEX.md
git commit -m "fix(check): read either engine pointer, and distrust a stale one

The install check knew only the legacy pointer path, so on a machine running a
current engine it fell through to searching the install trees. It now reads the
host-neutral location first, strips whitespace so an interrupted write reads as
absent rather than as \"/\", and verifies the CLI is actually at the path before
reporting it -- a stale pointer sent people to debug a directory that was not
the problem."
```

---

## Self-Review

**Spec coverage.** The contract in `docs/CODEX.md` says a campaign finds the engine by reading a breadcrumb. Task 1 writes it in both places; Task 2 reads both and documents the table. No other part of that document touches the pointer.

**Placeholders.** None: every step carries the code or the exact command.

**Type consistency.** `_write_engine_pointers(root, paths)` returns `list[tuple[str, bool, str]]`; Task 1's call site unpacks three values, and its tests assert on three. `ENGINE_POINTERS` is a 2-tuple, host-neutral first, in both the Python constant and the shell loop. `ENGINE_POINTER` keeps naming the legacy path, which is what `docs/CODEX.md` and installed campaigns cite.

**Review Focus coverage.** 1 → Task 1 Step 1 (`test_every_pointer_unwritable_is_survivable`). 2 → Task 2 (`test_a_stale_pointer_is_skipped_rather_than_reported`). 3 → Task 2 (`test_the_newer_pointer_wins_when_the_two_disagree`). 4 → Task 1 (`test_the_pointer_paths_survive_no_home`). 5 → Task 2 (`test_an_empty_pointer_file_is_treated_as_absent`).

**Not in scope.** `NATIVE_HOME` (`~/.claude/mythras-gm/typedb`) is a different concern — it is already overridable with `MYTHRAS_TYPEDB_HOME`, and moving the save location is a migration, not a rename. Leave it.
