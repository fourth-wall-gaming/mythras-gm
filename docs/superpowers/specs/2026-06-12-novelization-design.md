# Novelization Feature — Design Spec

**Date:** 2026-06-12
**Status:** Approved by user
**Repo:** fourth-wall-gaming/mythras-gm

## Purpose

Turn the journaled events of a Mythras campaign into a typeset novel (PDF).
Claude reads the campaign's event journal and supporting canon from TypeDB,
drafts chapters in a requested author style (Hemingway, Tolkien, Moorcock,
or any freeform description), and a deterministic CLI renders the manuscript
to a print-style PDF via pandoc → Typst.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Who writes the prose? | Claude, in-session. No API calls in the CLI. |
| PDF toolchain | pandoc → Typst → PDF. Single-binary brew installs, custom book template we own. |
| Style parameter | Curated style cards in `styles/` + freeform descriptions (pinned into the manuscript as a one-off card). |
| Novel structure | Claude proposes a chapter outline grouped by narrative beat; user approves before drafting. |
| Packaging | Inside the mythras-gm plugin (not a separate plugin, not a campaign_io flag). |
| Where manuscripts live | In the exported campaign repo under `novels/<slug>/` — a derived artifact, never imported back into TypeDB. |

## Architecture

```
skills/mythras-gm/
  novelist.py              # CLI: extract + build (deterministic plumbing only)
  NOVELIZATION.md          # workflow doc Claude follows in-session
  styles/
    hemingway.md           # style cards: diction, rhythm, POV habits, avoid-list
    tolkien.md
    moorcock.md
    _template.md           # scaffold for user-authored cards
  book_template/
    novel.typ              # Typst book template: title page, chapter openers,
                           # running headers, scene-break ornament (⁂),
                           # drop caps, 5.5in × 8.5in trim
```

### Manuscript layout (in the campaign repo)

```
<campaign-repo>/
  campaign.yaml, lore/, characters/, journal/events.json   # existing export tree
  novels/
    <book-slug>/
      book.yaml            # title, author, style name, source campaign id,
                           # journal high-water mark (last event id novelized)
      source.md            # extracted raw material (regenerable)
      style.md             # pinned copy of the style card used
      chapters/
        01-<slug>.md
        02-<slug>.md
      <book-slug>.pdf      # built artifact, committed
```

## Components

### 1. `novelist.py` CLI

Two subcommands. No LLM calls; testable without a Claude session. Reuses
`mythras_gm.py` driver helpers (`get_driver`, `_fetch`, `escape_string`).

**`extract --campaign <id> [--out <dir>]`**
- Pulls from TypeDB: all `myth-game-event`s for the campaign ordered by
  `created-at` (id, type, summary, narrative content, session number,
  participants via `myth-event-involvement`); all involved characters
  (name, description, backstory content); locations; factions;
  player-visible lore (`myth-lore-visibility != "gm-only"`).
- Writes `source.md`: events in order as sections, metadata (event id, type,
  session, participants) in HTML comments so prose drafting can cite them.
- Writes `book.yaml` with `status: outline-pending`, `style: null`,
  `high_water_mark: <last event id>`.
- `--out` defaults to `<cwd>/novels/<campaign-slug>/`; re-running refreshes
  `source.md` and updates the high-water mark without touching `chapters/`.

**`build --manuscript <dir> [--pdf-only]`**
- Validates: `chapters/` non-empty, no unresolved `[TODO]` markers, no gaps
  in chapter numbering, `pandoc` and `typst` on PATH (friendly brew-install
  hints on failure).
- Concatenates `chapters/*.md` in filename order, prepends title metadata
  from `book.yaml`, runs `pandoc -t typst` with `book_template/novel.typ`,
  then `typst compile` → `<book-slug>.pdf` in the manuscript dir.
- Exit non-zero with a JSON error payload on any validation failure
  (consistent with mythras_gm.py output conventions).

### 2. `NOVELIZATION.md` (Claude workflow)

1. Run `extract`; read `source.md` end to end.
2. Resolve the style: a named card from `styles/`, or a freeform description
   — in the freeform case, write a one-off style card to the manuscript dir.
   Either way copy the card to `style.md` so the style is pinned and
   reproducible across sessions.
3. Propose a chapter outline grouped by **narrative beat** (not session
   boundaries); present to the user for approval before drafting.
4. Draft chapters one at a time to `chapters/NN-<slug>.md`, each starting
   with `# Chapter N — Title`. Scene breaks within a chapter are `---`
   (rendered as ⁂ by the template).
5. Canon rules: journal events are plot truth; lore/characters/locations
   give texture; connective tissue (interior monologue, transitions, minor
   sensory detail) may be invented but must never contradict the journal or
   player-visible lore. GM-only lore is excluded from extraction and must
   not leak into prose.
6. Run `build`; report the PDF path.
7. Incremental novelization: when the campaign has advanced past the
   high-water mark, `extract` refreshes `source.md`; draft only new
   chapters and update `book.yaml`.

### 3. Style cards

Each ~30 lines covering: sentence rhythm, diction register, dialogue habits,
description density, default POV/tense, signature moves, and a "never do"
list. Shipped: `hemingway.md`, `tolkien.md`, `moorcock.md`. `_template.md`
documents the card format for user additions.

### 4. Typst book template (`novel.typ`)

5.5in × 8.5in trim, justified serif body, title page from metadata, chapter
opener pages (number + title, drop cap on first paragraph), running headers
(book title verso / chapter title recto), page numbers, ⁂ scene breaks,
widow/orphan control.

## Data flow

```
TypeDB (journal + canon)
   │  novelist.py extract
   ▼
source.md + book.yaml ──► Claude (style card + outline + chapter drafts)
   │                              │
   │                              ▼
   │                      chapters/NN-*.md
   │  novelist.py build           │
   └──────────────────────────────┘
   ▼
pandoc -t typst → typst compile → <book-slug>.pdf
```

Canon flows one way: nothing under `novels/` is ever imported back into
TypeDB. `campaign_io.py` import ignores `novels/` (no code change needed —
it only reads its known directories). Multiple novelizations of the same
campaign coexist as sibling dirs.

## Error handling

- `extract` with unknown campaign id → JSON error, exit 1.
- `extract` with zero events → JSON error advising to play first.
- `build` with missing tools → names the tool and prints the brew command.
- `build` with `[TODO]` markers or numbering gaps → lists the offending
  files, exit 1.
- pandoc/typst subprocess failures → surface stderr in the JSON payload.

## Testing

- Unit tests (pytest, alongside existing `tests/test_engine.py`):
  - `extract` event ordering, participant resolution, gm-only lore exclusion
    (against a seeded test campaign in TypeDB; skipped if TypeDB is down).
  - `build` validation: empty chapters dir, `[TODO]` detection, numbering
    gap detection, missing-tool message (PATH manipulation).
- Golden path: a committed 2-chapter fixture manuscript renders to PDF;
  test skipped when `typst`/`pandoc` are not installed.

## Dependencies

- `pandoc` and `typst` (brew). Checked at `build` time, documented in
  README and the plugin's `system` requirements in
  `.claude-plugin/plugin.json`.
- No new Python dependencies (PyYAML and typedb-driver already in
  `pyproject.toml`).

## Out of scope (YAGNI)

- EPUB/print-on-demand output formats.
- Cover art generation.
- Automatic re-drafting of existing chapters when canon changes.
- A generic standalone book-builder plugin.
