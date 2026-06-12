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
