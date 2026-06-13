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

3. **Outline.** Basic rule: **one session = one chapter.** Each chapter
   covers a full play session's events in order; narrative beats within the
   session become scene breaks, not separate chapters. One line per chapter:
   working title + session number + which journal events it covers (cite
   event ids from the source.md comments). Present it to the user and wait
   for approval before drafting.

4. **Draft.** One chapter at a time to `chapters/NN-<slug>.md`, starting each
   file with `# Chapter N — Title`. Scene breaks within a chapter are a line
   containing only `---` (typeset as ⁂). Set `status: drafted` in `book.yaml`
   when the outline is fully drafted.

5. **Canon rules.** Journal events are plot truth -- never contradict them.
   Characters, locations, factions, and player-visible lore give texture.
   You may invent connective tissue: interiority, transitions, minor sensory
   detail, unnamed bystanders. Invention flows one way only: embellishments
   created for the novel must never be written back into the journal, lore,
   or any game record. GM-only lore is excluded from `source.md` and
   must never leak into the prose. Leave `[TODO: ...]` markers for anything
   you need the user to decide; `build` refuses to run until they're resolved.

6. **Illustrate (optional).** Add engraving-style plates (or any look) to the
   book. Like prose styles, art styles are reproducible cards in
   `styles/art/`. The CLI is plumbing -- you write the prompts.
   1. **Pin an art style.** Copy `styles/art/<name>.md` to
      `<manuscript>/art.md` and set `art_style: <name>` in `book.yaml`. The
      card is the visual preamble for every prompt, so the plates read as one
      set.
   2. **Choose scenes and write prompts.** For each scene to illustrate, write
      a text-to-image prompt (the art-style preamble + the scene's specifics,
      drawn from the *player-visible* journal in `source.md` -- never GM lore)
      to `<manuscript>/illustrations/<NN-slug>.txt`.
   3. **Add the manifest.** For each plate add an entry under `illustrations:`
      in `book.yaml`. Place it either right after the paragraph where the
      action happens (`after_text`, preferred) or coarsely by scene
      (`after_scene`). Omit `caption` for a bare image; include it for a
      "Figure N" caption.
      ```yaml
      illustrations:
        - file: 01-the-dive.png      # the image you will generate
          chapter: 1
          after_text: "drove the point down through the root of its wing"
          # ...or instead: after_scene: 0   # 0 = chapter opener; k = after k-th ⁂
          prompt_file: 01-the-dive.txt
      ```
      `after_text` is a verbatim phrase from the chapter prose; the plate drops
      in right after that paragraph. (`after_text` wins if both are given.)
   4. **Generate and drop in.** Run each prompt through your image model and
      save the result as `<manuscript>/illustrations/<file>`.
   5. **Check.** `illustrate --manuscript <dir>` validates placements and lists
      each plate as `present` or `pending`, with each chapter's scene-break
      count so you can pick `after_scene`. The build injects only the plates
      that exist, so it is safe to run before every image is made.

7. **Build.** `build --manuscript <dir>`. Report the PDF path. Commit the
   manuscript directory (including the PDF and `illustrations/`) to the
   campaign repo if it's one.

8. **Continue later.** When the campaign has advanced past `high_water_mark`
   in `book.yaml`, re-run `extract` (it refreshes `source.md` and the mark
   without touching `chapters/`), outline the new material, and draft only
   the new chapters.
