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

3. **Outline.** **Chapters are driven by story beats, not by sessions.** Cut
   the book where the *story* turns — a day closing, a plan being made, a
   thing being found out, somebody deciding something they cannot undo — and
   ignore where play happened to stop for the night. A session boundary is an
   accident of somebody's evening and has no meaning to a reader.

   In practice a chapter is usually one movement of the story: a stretch that
   has one question in it and answers it. Beats inside that movement become
   scene breaks. A session that ran long becomes several chapters; three thin
   sessions that were all one manoeuvre become one.

   Watch the shape rather than the clock: if a chapter is running past roughly
   5,000 words it is carrying more than one turn and wants splitting, and if
   two adjacent chapters are answering the same question they want merging.

   One line per chapter: working title + which journal events it covers (cite
   event ids from the source.md comments). Present the outline to the user and
   wait for approval before drafting.

4. **Draft.** One chapter at a time to `chapters/NN-<slug>.md`, starting each
   file with `# Chapter N — Title`. Scene breaks within a chapter are a line
   containing only `---` (typeset as ⁂). Set `status: drafted` in `book.yaml`
   when the outline is fully drafted.

   *Front matter (optional):* a `front-matter.md` in the manuscript root is
   built in before chapter one -- use it for a prelude/preface that orients a
   reader to the world. Give it its own page and title with a raw `{=typst}`
   block (e.g. `#pagebreak(weak: true)` + a centered `smallcaps[Prelude]`),
   **not** a `# heading`, so it does not register as a chapter (keeps chapter
   numbering and figure placement intact). Player-visible lore only.

5. **Write it the way it was played.** This is the first rule, not a footnote.

   **The dialogue in the novel must be the dialogue from the table.** Find the
   session transcript and use it. The player's own lines are the least
   negotiable thing in the book — they chose those words, in character, under
   pressure, and they are the reason the scene went the way it did. Put them on
   the page as close to verbatim as prose will carry, and put the NPCs' answers
   there the same way.

   `source.md` is **not** enough for this and will quietly betray you. Journal
   events are summaries written after the fact; they carry what happened and
   almost none of what was said. A chapter drafted off a summary will be
   fluent, plausible, and wrong — you will invent a confrontation where there
   was a friendly conversation, put four men on a bridge where there were two,
   and lose every real line in the scene. That has happened, to this book, in
   this repo.

   So before drafting any chapter, go and read the actual play for it. The
   transcript lives in the campaign's `session-logs/`, or in the harness's own
   `.jsonl` for the session. Pull the scene, read the whole exchange, and keep:
   - **every line the player spoke**, and their phrasing, including the
     profanity and the hesitations and the bad jokes;
   - **the NPC lines that landed** — the ones that got a reaction;
   - **the names** that came up at the table, even for walk-ons, and
     **the numbers** exactly as they were said;
   - **who was actually present**, and how many of them.

   You may cut, compress, reorder within a scene, and write the connective
   tissue — that is the job. You may not replace a line that was said with a
   better one you thought of afterwards.

   **Where the dice did something dramatic, translate it, never report it.** A
   failed roll is not "she failed"; it is what failing looked like in that room.

6. **Canon rules.** Journal events are plot truth -- never contradict them.
   Characters, locations, factions, and player-visible lore give texture.
   You may invent connective tissue: interiority, transitions, minor sensory
   detail, unnamed bystanders. Invention flows one way only: embellishments
   created for the novel must never be written back into the journal, lore,
   or any game record. GM-only lore is excluded from `source.md` and
   must never leak into the prose. Leave `[TODO: ...]` markers for anything
   you need the user to decide; `build` refuses to run until they're resolved.

7. **Illustrate (optional).** Add engraving-style plates (or any look) to the
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

8. **Build.** `build --manuscript <dir>`. Report the PDF path. Commit the
   manuscript directory (including the PDF and `illustrations/`) to the
   campaign repo if it's one.

9. **Continue later.** When the campaign has advanced past `high_water_mark`
   in `book.yaml`, re-run `extract` (it refreshes `source.md` and the mark
   without touching `chapters/`), outline the new material, and draft only
   the new chapters.
