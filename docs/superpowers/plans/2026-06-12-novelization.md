# Novelization Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `novelist.py` CLI plus style cards, a Typst book template, and a Claude workflow doc so a Mythras campaign journal in TypeDB can be turned into a typeset PDF novel.

**Architecture:** `novelist.py extract` pulls the journal + player-visible canon from TypeDB into `novels/<slug>/source.md` inside the campaign repo; Claude (per `NOVELIZATION.md`) drafts chapters into `chapters/NN-*.md` guided by a style card; `novelist.py build` validates and renders chapters via `pandoc -t typst` + `typst compile` using `book_template/novel.typ`. Pure helpers are separated from DB/subprocess code so they unit-test without TypeDB or the toolchain.

**Tech Stack:** Python 3.11+ (PyYAML, typedb-driver — both already in `pyproject.toml`), pandoc, Typst, pytest.

**Repo:** `/Users/gullyburns/mythras-gm` (work on `main` unless told otherwise — small repo, single committer). All paths below are relative to repo root.

**Spec:** `docs/superpowers/specs/2026-06-12-novelization-design.md`

**Spec amendments locked in here (the spec is slightly out of date on two details):**
1. Lore visibility values in the schema/CLI are `"player"` and `"gm"` (not `"gm-only"`). Extraction excludes `visibility == "gm"`; missing visibility counts as player-visible.
2. Drop caps are deferred (Typst needs a third-party package); chapter openers use small-caps title + ✦ ornament instead.

**Domain context an engineer needs:**
- `skills/mythras-gm/mythras_gm.py` is the existing GM CLI. It exposes reusable helpers: `get_driver()`, `_fetch(driver, query)`, `_write(driver, *queries)`, `escape_string(s)`, `out(obj)` (prints JSON), `fail(msg)` (prints JSON error, exit 1). Import it as `import mythras_gm as gm`.
- TypeDB 3.x query notes: fetch syntax is `fetch { "key": $var.attr };`; optional attributes must be fetched with a separate per-attribute query (fetching `$e.attr` when absent errors); relation match uses the anonymous form `(role1: $a, role2: $b) isa relation-type;`.
- Events are `myth-game-event` entities: `description` = one-line summary, `content` = optional rich narrative, `myth-event-type`, optional `myth-session-number`, `created-at`. Participants link via `myth-event-involvement (event, participant)`. Everything in a campaign links via `myth-campaign-membership (campaign, element)`.
- Tests live in `tests/` and run with `cd /Users/gullyburns/mythras-gm && python -m pytest tests/ -v`. Existing `tests/test_engine.py` shows the import pattern (`sys.path.insert` to the skill dir).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `skills/mythras-gm/novelist.py` | Create | extract + build CLI; pure helpers at top, DB/subprocess below |
| `tests/test_novelist.py` | Create | unit tests for pure helpers + golden-path build |
| `tests/fixtures/sample-manuscript/` | Create | 2-chapter fixture manuscript for the build test |
| `skills/mythras-gm/book_template/novel.typ` | Create | Typst book interior template |
| `skills/mythras-gm/styles/{hemingway,tolkien,moorcock,_template}.md` | Create | style cards |
| `skills/mythras-gm/NOVELIZATION.md` | Create | Claude workflow doc |
| `skills/mythras-gm/SKILL.md` | Modify | add novelize trigger + pointer |
| `skills/mythras-gm/mythras_gm.py:55-61` | Modify | mention novelist.py in the usage docstring |
| `.claude-plugin/plugin.json` | Modify | add pandoc/typst to system bins note |
| `README.md` | Modify | document the feature |

---

### Task 1: Pure helpers — slugify, lore filter, source.md renderer

**Files:**
- Create: `skills/mythras-gm/novelist.py`
- Create: `tests/test_novelist.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_novelist.py`:

```python
"""Unit tests for novelist.py pure helpers (no TypeDB, no pandoc/typst)."""

import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "mythras-gm"))
import novelist as nov


# --- slugify ---------------------------------------------------------------

def test_slugify():
    assert nov.slugify("The Stilling!") == "the-stilling"
    assert nov.slugify("") == "untitled"
    assert nov.slugify(None) == "untitled"


# --- lore filtering ----------------------------------------------------------

def test_filter_player_lore_excludes_gm():
    rows = [
        {"id": "a", "name": "Public", "visibility": "player"},
        {"id": "b", "name": "Secret", "visibility": "gm"},
        {"id": "c", "name": "Unset", "visibility": None},
    ]
    kept = nov.filter_player_lore(rows)
    assert [r["id"] for r in kept] == ["a", "c"]


# --- source.md rendering ------------------------------------------------------

CAMPAIGN = {"id": "myth-camp-1", "name": "The Stilling"}
EVENTS = [
    {"id": "ev-1", "type": "scene", "at": "2026-06-01T10:00:00",
     "summary": "Esk reaches the chart-room.", "narrative": "Wind hissed in the spars.",
     "session": 1, "participants": [{"id": "ch-1", "name": "Esk"}]},
    {"id": "ev-2", "type": "combat", "at": "2026-06-01T11:00:00",
     "summary": "Skirmish on the windlane.", "narrative": None,
     "session": None, "participants": []},
]
CHARS = [{"id": "ch-1", "name": "Esk", "description": "A wary navigator.", "content": "Born aloft."}]


def test_render_source_md_structure():
    md = nov.render_source_md(CAMPAIGN, EVENTS, CHARS, [], [], [])
    assert md.startswith("# Source Material — The Stilling")
    assert "## Dramatis Personae" in md
    assert "### Esk <!-- id: ch-1 -->" in md
    assert "Born aloft." in md
    # events in order, with metadata comments
    i1 = md.index("Esk reaches the chart-room.")
    i2 = md.index("Skirmish on the windlane.")
    assert i1 < i2
    assert "id: ev-1, type: scene" in md
    assert "session: 1" in md
    assert "involves: Esk" in md
    assert "Wind hissed in the spars." in md


def test_render_source_md_omits_empty_sections():
    md = nov.render_source_md(CAMPAIGN, EVENTS, [], [], [], [])
    assert "## Dramatis Personae" not in md
    assert "## Locations" not in md
    assert "## Journal" in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/gullyburns/mythras-gm && python -m pytest tests/test_novelist.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'novelist'`

- [ ] **Step 3: Write the implementation**

Create `skills/mythras-gm/novelist.py`:

```python
#!/usr/bin/env python3
"""novelist.py -- campaign journal -> manuscript -> typeset PDF.

Usage:
    extract --campaign ID [--out DIR]     # TypeDB -> novels/<slug>/source.md + book.yaml
    build --manuscript DIR                # chapters/*.md -> pandoc -> typst -> <slug>.pdf

The CLI is deterministic plumbing only -- Claude writes the prose between
`extract` and `build` (see NOVELIZATION.md). Pure helpers live at the top of
this file so they can be unit-tested without TypeDB or the toolchain.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import mythras_gm as gm  # driver, _fetch, escape_string, out, fail

import yaml

SKILL_DIR = os.path.dirname(os.path.realpath(__file__))
TEMPLATE_PATH = os.path.join(SKILL_DIR, "book_template", "novel.typ")

TOOL_HINTS = {"pandoc": "brew install pandoc", "typst": "brew install typst"}


class BuildError(Exception):
    pass


# ---------------------------------------------------------------------------
# Pure helpers (no DB, no subprocess)
# ---------------------------------------------------------------------------

def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", (name or "untitled").lower()).strip("-") or "untitled"


def filter_player_lore(rows):
    """Drop GM-only lore; missing visibility counts as player-visible."""
    return [r for r in rows if (r.get("visibility") or "player") != "gm"]


def render_source_md(campaign, events, characters, locations, factions, lore):
    """Render extracted campaign data as the manuscript's raw-material file."""
    lines = [f"# Source Material — {campaign['name']}", ""]

    def section(title, items, body_keys):
        if not items:
            return
        lines.append(f"## {title}")
        lines.append("")
        for it in items:
            lines.append(f"### {it['name']} <!-- id: {it['id']} -->")
            for key in body_keys:
                if it.get(key):
                    lines.append("")
                    lines.append(str(it[key]))
            lines.append("")

    section("Dramatis Personae", characters, ["description", "content"])
    section("Locations", locations, ["description", "content"])
    section("Factions", factions, ["description", "content"])
    section("Lore (player-visible)", lore, ["description", "content"])

    lines.append("## Journal")
    lines.append("")
    for n, e in enumerate(events, 1):
        meta = f"id: {e['id']}, type: {e['type']}, at: {e['at']}"
        if e.get("session") is not None:
            meta += f", session: {e['session']}"
        if e.get("participants"):
            meta += ", involves: " + ", ".join(p["name"] for p in e["participants"])
        lines.append(f"### Event {n} <!-- {meta} -->")
        lines.append("")
        lines.append(e["summary"])
        if e.get("narrative"):
            lines.append("")
            lines.append(e["narrative"])
        lines.append("")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/gullyburns/mythras-gm && python -m pytest tests/test_novelist.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/gullyburns/mythras-gm
git add skills/mythras-gm/novelist.py tests/test_novelist.py
git commit -m "feat(novelist): pure helpers -- slugify, lore filter, source.md renderer"
```

---

### Task 2: Manuscript validation + tool checks

**Files:**
- Modify: `skills/mythras-gm/novelist.py` (append after `render_source_md`)
- Modify: `tests/test_novelist.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_novelist.py`:

```python
# --- manuscript validation ----------------------------------------------------

def _make_manuscript(tmp_path, chapters):
    mdir = tmp_path / "ms"
    (mdir / "chapters").mkdir(parents=True)
    (mdir / "book.yaml").write_text(
        'title: "Sample Book"\nauthor: "FWG"\nslug: "sample-book"\n', encoding="utf-8")
    for fname, text in chapters.items():
        (mdir / "chapters" / fname).write_text(text, encoding="utf-8")
    return str(mdir)


def test_validate_ok(tmp_path):
    mdir = _make_manuscript(tmp_path, {
        "01-dawn.md": "# Chapter 1 — Dawn\n\nProse.\n",
        "02-dusk.md": "# Chapter 2 — Dusk\n\nMore prose.\n",
    })
    assert nov.validate_manuscript(mdir) == []


def test_validate_empty_chapters(tmp_path):
    mdir = _make_manuscript(tmp_path, {})
    errors = nov.validate_manuscript(mdir)
    assert any("chapters/ is empty" in e for e in errors)


def test_validate_todo_marker(tmp_path):
    mdir = _make_manuscript(tmp_path, {"01-dawn.md": "# Chapter 1\n\n[TODO: fight scene]\n"})
    errors = nov.validate_manuscript(mdir)
    assert any("[TODO]" in e and "01-dawn.md" in e for e in errors)


def test_validate_numbering_gap(tmp_path):
    mdir = _make_manuscript(tmp_path, {
        "01-dawn.md": "# Chapter 1\n\nProse.\n",
        "03-dusk.md": "# Chapter 3\n\nProse.\n",
    })
    errors = nov.validate_manuscript(mdir)
    assert any("gaps or duplicates" in e for e in errors)


def test_validate_bad_filename(tmp_path):
    mdir = _make_manuscript(tmp_path, {"dawn.md": "# Chapter 1\n\nProse.\n"})
    errors = nov.validate_manuscript(mdir)
    assert any("not NN-<slug>.md" in e for e in errors)


def test_validate_missing_book_yaml(tmp_path):
    mdir = tmp_path / "ms"
    (mdir / "chapters").mkdir(parents=True)
    (mdir / "chapters" / "01-a.md").write_text("# Chapter 1\n\nx\n", encoding="utf-8")
    errors = nov.validate_manuscript(str(mdir))
    assert any("book.yaml" in e for e in errors)


# --- tool checks ---------------------------------------------------------------

def test_missing_tools_reports_brew_hints():
    msgs = nov.missing_tools(path="/nonexistent")
    assert any("pandoc" in m and "brew install pandoc" in m for m in msgs)
    assert any("typst" in m and "brew install typst" in m for m in msgs)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/gullyburns/mythras-gm && python -m pytest tests/test_novelist.py -v`
Expected: new tests FAIL with `AttributeError: module 'novelist' has no attribute 'validate_manuscript'`

- [ ] **Step 3: Write the implementation**

Append to `skills/mythras-gm/novelist.py` (after `render_source_md`):

```python
def chapter_files(manuscript_dir):
    """Sorted chapter markdown filenames (not paths)."""
    cdir = os.path.join(manuscript_dir, "chapters")
    if not os.path.isdir(cdir):
        return []
    return sorted(f for f in os.listdir(cdir) if f.endswith(".md"))


def validate_manuscript(manuscript_dir):
    """Return a list of human-readable problems; empty list means buildable."""
    errors = []
    if not os.path.exists(os.path.join(manuscript_dir, "book.yaml")):
        errors.append("book.yaml missing -- run extract first")
    files = chapter_files(manuscript_dir)
    if not files:
        errors.append("chapters/ is empty -- draft chapters first (see NOVELIZATION.md)")
        return errors
    nums = []
    for f in files:
        m = re.match(r"(\d+)-.+\.md$", f)
        if not m:
            errors.append(f"chapter filename not NN-<slug>.md: {f}")
        else:
            nums.append(int(m.group(1)))
    if nums and sorted(nums) != list(range(1, len(nums) + 1)):
        errors.append(f"chapter numbering has gaps or duplicates: {sorted(nums)}")
    for f in files:
        with open(os.path.join(manuscript_dir, "chapters", f), encoding="utf-8") as fh:
            if "[TODO" in fh.read():
                errors.append(f"unresolved [TODO] marker in {f}")
    return errors


def missing_tools(path=None):
    """Names of required binaries not on PATH, with brew install hints."""
    return [f"{tool} not found -- install with: {hint}"
            for tool, hint in TOOL_HINTS.items()
            if shutil.which(tool, path=path) is None]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/gullyburns/mythras-gm && python -m pytest tests/test_novelist.py -v`
Expected: 11 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/gullyburns/mythras-gm
git add skills/mythras-gm/novelist.py tests/test_novelist.py
git commit -m "feat(novelist): manuscript validation and toolchain checks"
```

---

### Task 3: TypeDB extraction + `extract` command

**Files:**
- Modify: `skills/mythras-gm/novelist.py` (append)
- Modify: `tests/test_novelist.py` (append)

- [ ] **Step 1: Write the (skippable) integration test**

Append to `tests/test_novelist.py`:

```python
# --- extract (requires TypeDB; skipped when down) -------------------------------

def _typedb_up():
    try:
        import mythras_gm as gm
        with gm.get_driver() as d:
            d.databases.all()
        return True
    except Exception:
        return False


TYPEDB_UP = _typedb_up()


@pytest.mark.skipif(not TYPEDB_UP, reason="TypeDB not reachable")
def test_extract_unknown_campaign_fails(tmp_path, capsys):
    with pytest.raises(SystemExit):
        nov.fetch_campaign_data("no-such-campaign-id")
    assert "not found" in capsys.readouterr().out


@pytest.mark.skipif(not TYPEDB_UP, reason="TypeDB not reachable")
def test_extract_seeded_campaign(tmp_path):
    """Seed a throwaway campaign via the GM CLI, then extract it."""
    import json
    import subprocess
    cli = os.path.join(os.path.dirname(__file__), "..", "skills", "mythras-gm", "mythras_gm.py")

    def run(*args):
        r = subprocess.run([sys.executable, cli, *args], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        return json.loads(r.stdout)

    camp = run("create-campaign", "--name", "ztest-novelist")["id"]
    run("log-event", "--campaign", camp, "--type", "scene",
        "--summary", "First scene", "--narrative", "It begins.", "--session", "1")
    run("log-event", "--campaign", camp, "--type", "combat", "--summary", "Second scene")
    run("add-lore", "--campaign", camp, "--title", "Open Secret",
        "--category", "history", "--narrative", "Everyone knows.", "--visibility", "player")
    run("add-lore", "--campaign", camp, "--title", "Hidden Truth",
        "--category", "history", "--narrative", "Nobody knows.", "--visibility", "gm")

    campaign, events, chars, locs, facs, lore = nov.fetch_campaign_data(camp)
    assert campaign["name"] == "ztest-novelist"
    assert [e["summary"] for e in events] == ["First scene", "Second scene"]
    assert events[0]["narrative"] == "It begins."
    assert events[0]["session"] == 1
    names = [l["name"] for l in lore]
    assert "Open Secret" in names and "Hidden Truth" not in names
```

- [ ] **Step 2: Run tests to verify the new ones fail (or skip)**

Run: `cd /Users/gullyburns/mythras-gm && python -m pytest tests/test_novelist.py -v`
Expected: if TypeDB is up, the two new tests FAIL with `AttributeError: ... 'fetch_campaign_data'`; if down, they SKIP (then verify locally with TypeDB running before sign-off).

- [ ] **Step 3: Write the implementation**

Append to `skills/mythras-gm/novelist.py`:

```python
# ---------------------------------------------------------------------------
# TypeDB extraction
# ---------------------------------------------------------------------------

def _members(driver, campaign_id, etype, extra_attrs):
    """Campaign members of one type with id+name plus optional extra attrs.

    extra_attrs: list of (typedb_attr, output_key). Optional attributes must be
    fetched one query at a time in TypeDB 3.x (absent attr in fetch = error).
    """
    cid = gm.escape_string(campaign_id)
    rows = gm._fetch(driver, f'''
        match
          $camp isa myth-campaign, has id "{cid}";
          (campaign: $camp, element: $x) isa myth-campaign-membership;
          $x isa {etype}, has id $i, has name $n;
        fetch {{ "id": $i, "name": $n }};''')
    result = []
    for r in rows:
        d = dict(r)
        for attr, key in extra_attrs:
            v = gm._fetch(driver, f'''
                match $x isa {etype}, has id "{gm.escape_string(d["id"])}", has {attr} $v;
                fetch {{ "v": $v }};''')
            d[key] = v[0]["v"] if v else None
        result.append(d)
    return result


def fetch_campaign_data(campaign_id):
    """Everything the novelization needs: (campaign, events, chars, locs, factions, lore)."""
    cid = gm.escape_string(campaign_id)
    with gm.get_driver() as driver:
        camp = gm._fetch(driver, f'''
            match $c isa myth-campaign, has id "{cid}";
            fetch {{ "id": $c.id, "name": $c.name }};''')
        if not camp:
            gm.fail(f"campaign not found: {campaign_id}")
        campaign = dict(camp[0])

        events = [dict(r) for r in gm._fetch(driver, f'''
            match
              $camp isa myth-campaign, has id "{cid}";
              (campaign: $camp, element: $e) isa myth-campaign-membership;
              $e isa myth-game-event, has id $i, has description $d,
                 has myth-event-type $t, has created-at $ts;
            fetch {{ "id": $i, "summary": $d, "type": $t, "at": $ts }};''')]
        events.sort(key=lambda e: (str(e["at"]), e["id"]))
        for e in events:
            eid = gm.escape_string(e["id"])
            for attr, key in (("content", "narrative"), ("myth-session-number", "session")):
                v = gm._fetch(driver, f'''
                    match $e isa myth-game-event, has id "{eid}", has {attr} $v;
                    fetch {{ "v": $v }};''')
                e[key] = v[0]["v"] if v else None
            e["participants"] = [dict(p) for p in gm._fetch(driver, f'''
                match
                  $e isa myth-game-event, has id "{eid}";
                  (event: $e, participant: $p) isa myth-event-involvement;
                  $p has id $pi, has name $pn;
                fetch {{ "id": $pi, "name": $pn }};''')]

        characters = _members(driver, campaign_id, "myth-character",
                              [("description", "description"), ("content", "content")])
        locations = _members(driver, campaign_id, "myth-location",
                             [("description", "description"), ("content", "content")])
        factions = _members(driver, campaign_id, "myth-faction",
                            [("description", "description"), ("content", "content")])
        lore = filter_player_lore(
            _members(driver, campaign_id, "myth-lore",
                     [("description", "description"), ("content", "content"),
                      ("myth-lore-visibility", "visibility")]))
    return campaign, events, characters, locations, factions, lore


def cmd_extract(args):
    campaign, events, chars, locs, facs, lore = fetch_campaign_data(args.campaign)
    if not events:
        gm.fail("campaign has no journal events -- play some sessions first")
    slug = slugify(campaign["name"])
    mdir = args.out or os.path.join(os.getcwd(), "novels", slug)
    os.makedirs(os.path.join(mdir, "chapters"), exist_ok=True)

    with open(os.path.join(mdir, "source.md"), "w", encoding="utf-8") as fh:
        fh.write(render_source_md(campaign, events, chars, locs, facs, lore))

    book_path = os.path.join(mdir, "book.yaml")
    if os.path.exists(book_path):
        with open(book_path, encoding="utf-8") as fh:
            book = yaml.safe_load(fh) or {}
    else:
        book = {"title": campaign["name"], "author": "Fourth Wall Gaming",
                "slug": slug, "campaign_id": campaign["id"],
                "style": None, "status": "outline-pending"}
    book["high_water_mark"] = events[-1]["id"]
    with open(book_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(book, fh, sort_keys=False, allow_unicode=True)

    gm.out({"success": True, "manuscript": os.path.abspath(mdir),
            "events": len(events), "high_water_mark": book["high_water_mark"]})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/gullyburns/mythras-gm && python -m pytest tests/test_novelist.py -v` (with TypeDB up)
Expected: 13 PASS (or 11 PASS + 2 SKIP if TypeDB is down — must see them PASS at least once before sign-off)

- [ ] **Step 5: Commit**

```bash
cd /Users/gullyburns/mythras-gm
git add skills/mythras-gm/novelist.py tests/test_novelist.py
git commit -m "feat(novelist): TypeDB extraction and extract command"
```

---

### Task 4: Typst book template + `build` command + CLI entrypoint

**Files:**
- Create: `skills/mythras-gm/book_template/novel.typ`
- Create: `tests/fixtures/sample-manuscript/book.yaml`, `tests/fixtures/sample-manuscript/chapters/01-the-spire.md`, `tests/fixtures/sample-manuscript/chapters/02-the-stilling.md`
- Modify: `skills/mythras-gm/novelist.py` (append build + main)
- Modify: `tests/test_novelist.py` (append)

- [ ] **Step 1: Create the fixture manuscript**

`tests/fixtures/sample-manuscript/book.yaml`:

```yaml
title: "Sample Book"
author: "Fourth Wall Gaming"
slug: "sample-book"
campaign_id: "myth-camp-test"
style: "moorcock"
status: "drafted"
```

`tests/fixtures/sample-manuscript/chapters/01-the-spire.md`:

```markdown
# Chapter 1 — The Spire

Wind hissed in the spars of the dead leviathan, and Esk counted the gusts
the way other people counted coins. One hundred and eight since dawn. The
number meant something. She was sure of it.

---

Below the chart-room the roost was waking, wings unfolding in the amber
light, and nobody else seemed to notice that the wind was dying.
```

`tests/fixtures/sample-manuscript/chapters/02-the-stilling.md`:

```markdown
# Chapter 2 — The Stilling

The windlane had gone slack overnight. Esk stood at its edge and felt
nothing move against her feathers at all.

"It's spreading," she said, to no one.
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_novelist.py`:

```python
# --- build (golden path; skipped without pandoc+typst) ---------------------------

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample-manuscript")
HAS_TOOLS = shutil.which("pandoc") is not None and shutil.which("typst") is not None


def test_build_refuses_invalid_manuscript(tmp_path):
    mdir = _make_manuscript(tmp_path, {"01-a.md": "# Chapter 1\n\n[TODO: finish]\n"})
    with pytest.raises(nov.BuildError) as exc:
        nov.build_manuscript(mdir)
    assert "[TODO]" in str(exc.value)


@pytest.mark.skipif(not HAS_TOOLS, reason="pandoc/typst not installed")
def test_build_golden_path(tmp_path):
    mdir = str(tmp_path / "ms")
    shutil.copytree(FIXTURE, mdir)
    pdf = nov.build_manuscript(mdir)
    assert os.path.basename(pdf) == "sample-book.pdf"
    assert os.path.getsize(pdf) > 10_000  # a real multi-page PDF, not an error stub
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/gullyburns/mythras-gm && python -m pytest tests/test_novelist.py -v`
Expected: `test_build_refuses_invalid_manuscript` FAILS with `AttributeError: ... 'BuildError'`... actually `BuildError` exists from Task 1; FAILS with `AttributeError: ... 'build_manuscript'`. Golden path SKIPs if tools missing.

- [ ] **Step 4: Create the Typst template**

`skills/mythras-gm/book_template/novel.typ`:

```typst
// Fourth Wall Gaming novel interior -- 5.5in x 8.5in trade style.
// Used via: #import "novel.typ": *  then  #show: novel.with(title: ..., author: ...)

// pandoc -t typst emits #horizontalrule for markdown "---" scene breaks.
#let horizontalrule = align(center, block(above: 1.5em, below: 1.5em,
  text(size: 11pt)[⁂]))

#let novel(title: "Untitled", author: "", body) = {
  set document(title: title, author: author)
  set text(size: 10.5pt, lang: "en")
  set par(justify: true, leading: 0.68em, first-line-indent: 1.2em)

  // Title page (its own page params; no header/footer).
  page(width: 5.5in, height: 8.5in, margin: (x: 0.8in, y: 0.8in),
       header: none, footer: none)[
    #align(center + horizon)[
      #text(size: 25pt)[#smallcaps(title)]
      #v(3em)
      #text(size: 12pt, style: "italic")[#author]
    ]
  ]

  // Interior pages: running headers, page numbers.
  set page(
    width: 5.5in, height: 8.5in,
    margin: (inside: 0.8in, outside: 0.6in, top: 0.75in, bottom: 0.75in),
    numbering: "1",
    header: context {
      let pg = counter(page).get().first()
      if calc.even(pg) {
        align(center, text(size: 8.5pt, smallcaps(title)))
      } else {
        let chapters = query(selector(heading.where(level: 1)).before(here()))
        if chapters.len() > 0 {
          align(center, text(size: 8.5pt, smallcaps(chapters.last().body)))
        }
      }
    },
  )
  counter(page).update(1)

  // Chapter openers: new page, drop, centered small-caps title, ornament.
  show heading.where(level: 1): it => {
    pagebreak(weak: true)
    v(16%)
    align(center, text(size: 17pt, weight: "regular", smallcaps(it.body)))
    v(0.5em)
    align(center, text(size: 11pt)[✦])
    v(2em)
  }

  body
}
```

- [ ] **Step 5: Write the build implementation**

Append to `skills/mythras-gm/novelist.py`:

```python
# ---------------------------------------------------------------------------
# Build: chapters/*.md -> pandoc -> typst -> PDF
# ---------------------------------------------------------------------------

def _run(cmd, cwd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise BuildError(f"{cmd[0]} failed: {r.stderr.strip()[:2000]}")


def build_manuscript(manuscript_dir):
    """Render the manuscript to PDF. Returns the PDF path; raises BuildError."""
    problems = validate_manuscript(manuscript_dir) + missing_tools()
    if problems:
        raise BuildError("; ".join(problems))

    with open(os.path.join(manuscript_dir, "book.yaml"), encoding="utf-8") as fh:
        book = yaml.safe_load(fh) or {}
    title = book.get("title") or "Untitled"
    author = book.get("author") or ""
    slug = book.get("slug") or slugify(title)

    build_dir = os.path.join(manuscript_dir, ".build")
    os.makedirs(build_dir, exist_ok=True)

    chapters = [open(os.path.join(manuscript_dir, "chapters", f), encoding="utf-8").read()
                for f in chapter_files(manuscript_dir)]
    with open(os.path.join(build_dir, "body.md"), "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(chapters))

    _run(["pandoc", "-f", "markdown", "-t", "typst", "body.md", "-o", "body.typ"],
         cwd=build_dir)
    shutil.copy(TEMPLATE_PATH, os.path.join(build_dir, "novel.typ"))

    def typ_str(s):
        return s.replace("\\", "\\\\").replace('"', '\\"')

    with open(os.path.join(build_dir, "main.typ"), "w", encoding="utf-8") as fh:
        fh.write(f'#import "novel.typ": *\n'
                 f'#show: novel.with(title: "{typ_str(title)}", '
                 f'author: "{typ_str(author)}")\n'
                 f'#include "body.typ"\n')

    _run(["typst", "compile", "main.typ", "out.pdf"], cwd=build_dir)
    pdf_path = os.path.join(manuscript_dir, f"{slug}.pdf")
    shutil.move(os.path.join(build_dir, "out.pdf"), pdf_path)
    return pdf_path


def cmd_build(args):
    try:
        pdf = build_manuscript(args.manuscript)
    except BuildError as e:
        gm.fail(str(e))
    gm.out({"success": True, "pdf": os.path.abspath(pdf)})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Campaign journal -> typeset novel PDF")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("extract", help="TypeDB -> novels/<slug>/source.md + book.yaml")
    s.add_argument("--campaign", required=True)
    s.add_argument("--out", help="manuscript dir (default: ./novels/<campaign-slug>/)")
    s.set_defaults(func=cmd_extract)

    s = sub.add_parser("build", help="chapters/*.md -> PDF")
    s.add_argument("--manuscript", required=True)
    s.set_defaults(func=cmd_build)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/gullyburns/mythras-gm && python -m pytest tests/test_novelist.py -v`
Expected: all PASS (golden path SKIPs if pandoc/typst absent — install them with `brew install pandoc typst` and confirm the golden path passes at least once; open the produced `sample-book.pdf` and eyeball title page, chapter openers, ⁂ scene break, running headers, page numbers).

- [ ] **Step 7: Commit**

```bash
cd /Users/gullyburns/mythras-gm
git add skills/mythras-gm/novelist.py skills/mythras-gm/book_template/ tests/
git commit -m "feat(novelist): Typst book template and build command"
```

---

### Task 5: Style cards

**Files:**
- Create: `skills/mythras-gm/styles/hemingway.md`, `tolkien.md`, `moorcock.md`, `_template.md`

No tests — these are prose-guidance documents. Review them for quality instead.

- [ ] **Step 1: Create `skills/mythras-gm/styles/_template.md`**

```markdown
# Style Card: <Author or Style Name>

Used by NOVELIZATION.md step 2. Copy this file to `<your-style>.md`, fill in
every section, keep it under ~40 lines. Be concrete: rhythm and diction rules
Claude can obey, not vibes.

## Sentence rhythm
<Short/long? Periodic or paratactic? Typical paragraph length?>

## Diction
<Register, vocabulary era, concrete vs abstract, Latinate vs Anglo-Saxon.>

## Dialogue
<Tag style, dialect handling, how much subtext, interruption habits.>

## Description density
<How much scene-setting per beat; what senses get priority.>

## POV and tense
<Default narrative distance, head-hopping rules, tense.>

## Signature moves
<3-5 recognizable techniques to deploy sparingly.>

## Never do
<Hard prohibitions -- the fastest way to break the pastiche.>
```

- [ ] **Step 2: Create `skills/mythras-gm/styles/hemingway.md`**

```markdown
# Style Card: Hemingway

## Sentence rhythm
Short declarative sentences. Compound sentences joined with "and," rarely
subordinate clauses. Paragraphs of two to five sentences. Repetition of key
nouns instead of pronoun variety.

## Diction
Plain Anglo-Saxon vocabulary. Concrete nouns: things you can touch, drink,
carry. No abstractions unless a character speaks them. Numbers stated plainly.

## Dialogue
Untagged or "said" only. Long exchanges with no attribution once the rhythm
is set. Characters talk past each other; the real subject is never named.

## Description density
Sparse. One or two physical details per scene, chosen for weight. Weather
and terrain matter. Interior states shown only through action and omission.

## POV and tense
Close third person, past tense. The narrator never explains feelings; the
iceberg stays underwater.

## Signature moves
- The true sentence: open a scene with one flat factual statement.
- Ritual detail: hands doing work (rigging, cleaning, cooking) described step by step.
- The unsaid: end scenes one beat before the emotional payoff.

## Never do
No adverbs of manner. No semicolons. No similes longer than four words.
Never describe a character's emotion by naming it.
```

- [ ] **Step 3: Create `skills/mythras-gm/styles/tolkien.md`**

```markdown
# Style Card: Tolkien

## Sentence rhythm
Long, flowing periodic sentences balanced with short solemn ones at moments
of weight. Inversions for gravity ("Great was the fall of that tower").
Paragraphs breathe; haste is itself a narrative event.

## Diction
Elevated but clear. Archaisms used sparingly and correctly (ere, fell, wrought).
Names matter: places and weapons are named, and the names carry history.
Light/dark, height/depth as moral geography.

## Dialogue
Formal registers that differ by culture and rank. Songs, proverbs, and
recited lore are welcome. Characters speak in complete, considered sentences.

## Description density
Rich for landscape and weather -- the land is a character. Journeys deserve
miles and meals. Battles described at the level of banners and tides, then
a single vivid personal moment.

## POV and tense
Omniscient-leaning third person, past tense, with the narrator permitted a
historian's asides ("It is said that...").

## Signature moves
- Deep time: any ruin or road gets one sentence of its ancient past.
- Eucatastrophe: hope arrives at the darkest moment, earned and sudden.
- The homely interlude: food, firelight, and fellowship between perils.

## Never do
No modern idiom or slang. No irony at the expense of wonder. Never make
evil glamorous; its works are ash and machinery.
```

- [ ] **Step 4: Create `skills/mythras-gm/styles/moorcock.md`**

```markdown
# Style Card: Moorcock

## Sentence rhythm
Swift, vivid, pulpy momentum -- written hot. Medium sentences that lean
forward; short ones for shock. Chapters end on reversals or omens.

## Diction
Lush and baroque for settings and sorcery (chalcedony, lambent, iridescent);
blunt for violence. Invented proper nouns with apostrophes and grandeur.
Physical decadence and beauty described without embarrassment.

## Dialogue
Theatrical and declarative. Villains articulate philosophy; heroes answer
with weary irony. Oaths sworn to gods who are listening.

## Description density
High color, low patience -- one dazzling paragraph per new vista, then on
with the action. Sorcery is sensory overload; combat is fast and grim.

## POV and tense
Close third person on a doomed protagonist, past tense. The narrator knows
fate's shape and lets dread leak in.

## Signature moves
- The melancholy antihero: power that costs; victory that tastes of ash.
- Law and Chaos: frame conflicts as cosmic balance, not good versus evil.
- The sentient burden: weapons, patrons, or gifts with their own hungers.

## Never do
No cozy domesticity without an undertow. No clean triumphs. Never let the
hero be comfortable in his own skin for more than a scene.
```

- [ ] **Step 5: Commit**

```bash
cd /Users/gullyburns/mythras-gm
git add skills/mythras-gm/styles/
git commit -m "feat(novelist): style cards -- hemingway, tolkien, moorcock + template"
```

---

### Task 6: NOVELIZATION.md workflow doc

**Files:**
- Create: `skills/mythras-gm/NOVELIZATION.md`

- [ ] **Step 1: Create `skills/mythras-gm/NOVELIZATION.md`**

```markdown
# Novelization Workflow

Turn a campaign's journal into a typeset novel. You (Claude) are the author;
`novelist.py` is the extractor and the press. Canon flows one way: nothing
you write here goes back into TypeDB.

## CLI

```bash
NOV="${CLAUDE_PLUGIN_ROOT}/skills/mythras-gm/novelist.py"
PRJ="${CLAUDE_PLUGIN_ROOT}/skills/mythras-gm"
uv run --project "$PRJ" python "$NOV" <command> [args] 2>/dev/null
```

Requires `pandoc` and `typst` for `build` (`brew install pandoc typst`).

## Workflow

1. **Extract.** `extract --campaign <id> [--out <dir>]`. Default output is
   `./novels/<campaign-slug>/` -- run it from the campaign's exported repo so
   the manuscript lives alongside `journal/` and `lore/`. Read the produced
   `source.md` end to end before writing anything.

2. **Pin the style.** If the user names a shipped style, read
   `styles/<name>.md`. If they give a freeform description, write a one-off
   card in the same format (use `styles/_template.md`). Either way, copy the
   card to `<manuscript>/style.md` and set `style:` in `book.yaml` -- the
   style must be reproducible in a later session.

3. **Outline.** Propose a chapter outline grouped by narrative beat, not by
   session boundaries. One line per chapter: working title + which journal
   events it covers (cite event ids from the source.md comments). Present it
   to the user and wait for approval before drafting.

4. **Draft.** One chapter at a time to `chapters/NN-<slug>.md`, starting each
   file with `# Chapter N — Title`. Scene breaks within a chapter are a line
   containing only `---` (typeset as ⁂). Set `status: drafted` in `book.yaml`
   when the outline is fully drafted.

5. **Canon rules.** Journal events are plot truth -- never contradict them.
   Characters, locations, factions, and player-visible lore give texture.
   You may invent connective tissue: interiority, transitions, minor sensory
   detail, unnamed bystanders. GM-only lore is excluded from `source.md` and
   must never leak into the prose. Leave `[TODO: ...]` markers for anything
   you need the user to decide; `build` refuses to run until they're resolved.

6. **Build.** `build --manuscript <dir>`. Report the PDF path. Commit the
   manuscript directory (including the PDF) to the campaign repo if it's one.

7. **Continue later.** When the campaign has advanced past `high_water_mark`
   in `book.yaml`, re-run `extract` (it refreshes `source.md` and the mark
   without touching `chapters/`), outline the new material, and draft only
   the new chapters.
```

- [ ] **Step 2: Verify the doc's commands match reality**

Run: `cd /Users/gullyburns/mythras-gm && uv run --project skills/mythras-gm python skills/mythras-gm/novelist.py extract --help && uv run --project skills/mythras-gm python skills/mythras-gm/novelist.py build --help`
Expected: both print help with the flags the doc names (`--campaign`, `--out`, `--manuscript`).

- [ ] **Step 3: Commit**

```bash
cd /Users/gullyburns/mythras-gm
git add skills/mythras-gm/NOVELIZATION.md
git commit -m "docs(novelist): Claude novelization workflow"
```

---

### Task 7: Wire into SKILL.md, CLI docstring, plugin.json, README

**Files:**
- Modify: `skills/mythras-gm/SKILL.md`
- Modify: `skills/mythras-gm/mythras_gm.py` (usage docstring, after the Publishing block ~line 59-61)
- Modify: `.claude-plugin/plugin.json`
- Modify: `README.md`

- [ ] **Step 1: Add trigger + pointer to SKILL.md**

In `skills/mythras-gm/SKILL.md`, change the Triggers line:

```markdown
**Triggers:** play rpg, run campaign, create character, roll dice, start encounter,
continue campaign, mythras, gamesmaster, novelize campaign, write novel
```

and append after the final paragraph (the `**Before executing commands...**` block):

```markdown
**Novelization:** to turn a campaign's journal into a typeset PDF novel
(in a chosen author style -- Hemingway, Tolkien, Moorcock, or freeform),
read `NOVELIZATION.md` and follow it.
```

- [ ] **Step 2: Add novelist to the mythras_gm.py usage docstring**

In `skills/mythras-gm/mythras_gm.py`, the docstring ends with:

```
Publishing:
    export-campaign --campaign ID --output DIR   # DB -> publishable file tree
    import-campaign --path DIR [--name N] [--new-ids]   # file tree -> DB
"""
```

Insert before the closing `"""`:

```
Novelization (see NOVELIZATION.md; separate CLI novelist.py):
    novelist.py extract --campaign ID [--out DIR]
    novelist.py build --manuscript DIR
```

- [ ] **Step 3: Update plugin.json system requirements**

In `.claude-plugin/plugin.json`, the `requires.system` block currently reads:

```json
"system": {
  "bins": ["uv", "docker"],
  "description": "Run /alhazen-core:init first to set up TypeDB and base schema"
}
```

Change to:

```json
"system": {
  "bins": ["uv", "docker"],
  "description": "Run /alhazen-core:init first to set up TypeDB and base schema. Novelization PDF builds additionally need pandoc and typst (brew install pandoc typst)."
}
```

(`pandoc`/`typst` stay out of `bins` — they are optional, only needed for `build`, and checked at runtime with friendly hints.)

- [ ] **Step 4: Add a README section**

In `README.md`, add after the existing feature/usage sections (engineer judgment on exact placement — keep it with other feature docs):

```markdown
## Novelization

Turn a campaign's journal into a typeset PDF novel. Claude reads the event
journal and player-visible canon from TypeDB, drafts chapters in a chosen
author style (Hemingway, Tolkien, Moorcock, or any description you give it),
and `novelist.py` renders the manuscript with pandoc + Typst.

```bash
brew install pandoc typst    # one-time, for PDF builds
```

Then just ask: *"Novelize the Veilwrack campaign in Moorcock's style."*
Claude extracts the journal, proposes a chapter outline for your approval,
drafts the chapters, and builds the PDF. Manuscripts live in the campaign
repo under `novels/<slug>/` and are never imported back into game state --
keep as many parallel novelizations as you like.
```

- [ ] **Step 5: Run the full test suite**

Run: `cd /Users/gullyburns/mythras-gm && python -m pytest tests/ -v`
Expected: all PASS (engine + novelist), with TypeDB-dependent and toolchain-dependent tests passing or cleanly skipping.

- [ ] **Step 6: Commit**

```bash
cd /Users/gullyburns/mythras-gm
git add skills/mythras-gm/SKILL.md skills/mythras-gm/mythras_gm.py .claude-plugin/plugin.json README.md
git commit -m "docs: wire novelization into skill triggers, plugin requirements, README"
```

---

### Task 8: End-to-end smoke test against the Veilwrack campaign

Manual verification — no code.

- [ ] **Step 1: Install the toolchain (if not present)**

Run: `brew install pandoc typst` (skip if `which pandoc typst` finds both).

- [ ] **Step 2: Extract the real campaign**

Run (TypeDB must be up; find the campaign id first):
```bash
cd /Users/gullyburns/mythras-gm
uv run --project skills/mythras-gm python skills/mythras-gm/mythras_gm.py list-campaigns
uv run --project skills/mythras-gm python skills/mythras-gm/novelist.py extract --campaign <veilwrack-id> --out /tmp/novel-smoke
```
Expected: `{"success": true, "manuscript": "/tmp/novel-smoke", "events": N, ...}` with N ≥ 1; `/tmp/novel-smoke/source.md` contains the journal, no GM-only lore.

- [ ] **Step 3: Build the fixture-style smoke book**

Copy the two fixture chapters into the smoke manuscript and build:
```bash
cp tests/fixtures/sample-manuscript/chapters/*.md /tmp/novel-smoke/chapters/
uv run --project skills/mythras-gm python skills/mythras-gm/novelist.py build --manuscript /tmp/novel-smoke
open /tmp/novel-smoke/*.pdf
```
Expected: PDF opens; title page shows the campaign name; chapter openers, ⁂ scene break, running headers, page numbers all present.

- [ ] **Step 4: Push**

```bash
cd /Users/gullyburns/mythras-gm && git push origin main
```

---

## Self-Review (done at plan time)

- **Spec coverage:** extract (Task 3), build + template (Task 4), style cards (Task 5), workflow doc (Task 6), SKILL/plugin/README wiring (Task 7), error handling (validate_manuscript + missing_tools + BuildError + gm.fail paths, Tasks 2-4), testing incl. golden path + TypeDB-skip (Tasks 1-4), one-way canon flow (no campaign_io change needed — documented in NOVELIZATION.md). Two spec deviations are declared in the header (lore visibility value `"gm"`, drop caps deferred).
- **Placeholders:** none — all code, docs, and commands are complete.
- **Type consistency:** `slugify`, `filter_player_lore`, `render_source_md`, `chapter_files`, `validate_manuscript`, `missing_tools`, `fetch_campaign_data`, `build_manuscript`, `BuildError`, `cmd_extract`, `cmd_build`, `main` — names match across tasks and tests.
