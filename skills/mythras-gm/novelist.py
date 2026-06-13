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
    lines = [f"# Source Material \u2014 {campaign['name']}", ""]

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


# ---------------------------------------------------------------------------
# Illustrations: book.yaml `illustrations:` manifest + Typst figure injection
# ---------------------------------------------------------------------------

def _chapter_paths_by_number(manuscript_dir):
    """Map chapter number -> path, from chapters/NN-*.md."""
    out = {}
    for f in chapter_files(manuscript_dir):
        m = re.match(r"(\d+)-.+\.md$", f)
        if m:
            out[int(m.group(1))] = os.path.join(manuscript_dir, "chapters", f)
    return out


def _count_scene_breaks(path):
    """Number of '---' scene-break lines in a chapter markdown file."""
    with open(path, encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip() == "---")


def validate_illustrations(book, manuscript_dir):
    """Return human-readable problems with the book.yaml `illustrations:` list.

    Each entry: file (required); chapter (an existing chapter number);
    after_scene (0..number of '---' breaks in that chapter); optional caption;
    optional prompt_file (must exist under illustrations/). Empty/absent
    manifest is valid.
    """
    problems = []
    items = book.get("illustrations") or []
    chapters = _chapter_paths_by_number(manuscript_dir)
    idir = os.path.join(manuscript_dir, "illustrations")
    for n, it in enumerate(items, 1):
        if not isinstance(it, dict):
            problems.append(f"illustration {n}: not a mapping")
            continue
        label = it.get("file") or f"#{n}"
        if not it.get("file"):
            problems.append(f"illustration {n}: missing 'file'")
        ch = it.get("chapter")
        if ch not in chapters:
            problems.append(f"illustration {label}: chapter {ch!r} has no chapter file")
        else:
            breaks = _count_scene_breaks(chapters[ch])
            after = it.get("after_scene", 0)
            if not isinstance(after, int) or after < 0 or after > breaks:
                problems.append(
                    f"illustration {label}: after_scene {after!r} out of range "
                    f"(chapter {ch} has {breaks} scene breaks; use 0..{breaks})")
        pf = it.get("prompt_file")
        if pf and not os.path.exists(os.path.join(idir, pf)):
            problems.append(
                f"illustration {label}: prompt_file not found: illustrations/{pf}")
    return problems


def _typ_inline(s):
    """Escape Typst-significant characters for use inside a [content] block."""
    for ch in "\\#[]@$":
        s = s.replace(ch, "\\" + ch)
    return s


def _figure_block(it):
    caption = it.get("caption")
    cap = f", caption: [{_typ_inline(str(caption))}]" if caption else ""
    return f'\n#figure(image("illustrations/{it["file"]}", width: 85%){cap})\n\n'


def inject_figures(body_typ, illustrations, present_files):
    """Insert #figure(image(...)) into pandoc's Typst body at manifest positions.

    Chapters are level-1 headings ('= ...'); scene breaks are '#horizontalrule'
    lines (pandoc renders markdown '---' that way). after_scene 0 places the
    figure right after the chapter heading; k places it right after the k-th
    scene break in that chapter. Entries whose 'file' is not in present_files
    are skipped, so a build never breaks on art that has not been made yet.
    """
    wanted = [it for it in (illustrations or []) if it.get("file") in present_files]
    if not wanted:
        return body_typ

    def figs(chap, scene):
        return [_figure_block(it) for it in wanted
                if it.get("chapter") == chap and it.get("after_scene", 0) == scene]

    out, chap, scene = [], 0, 0
    for line in body_typ.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("= "):
            chap += 1
            scene = 0
            out.append(line)
            out.extend(figs(chap, 0))
        elif stripped == "#horizontalrule":
            scene += 1
            out.append(line)
            out.extend(figs(chap, scene))
        else:
            out.append(line)
    return "".join(out)


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

    # Typst #include files don't inherit the caller's scope, so pandoc's
    # #horizontalrule calls would be unresolved. Prepend an import line.
    body_typ_path = os.path.join(build_dir, "body.typ")
    with open(body_typ_path, encoding="utf-8") as fh:
        body_content = fh.read()
    with open(body_typ_path, "w", encoding="utf-8") as fh:
        fh.write('#import "novel.typ": horizontalrule\n' + body_content)

    # Illustrations: copy generated images into the build dir and inject
    # #figure blocks at the manifest positions. Images not yet generated are
    # skipped, so the build never breaks before the art exists.
    illustrations = book.get("illustrations") or []
    if illustrations:
        present = set()
        src_idir = os.path.join(manuscript_dir, "illustrations")
        if os.path.isdir(src_idir):
            dst_idir = os.path.join(build_dir, "illustrations")
            if os.path.exists(dst_idir):
                shutil.rmtree(dst_idir)
            shutil.copytree(src_idir, dst_idir)
            present = {f for f in os.listdir(dst_idir)
                       if os.path.isfile(os.path.join(dst_idir, f))}
        with open(body_typ_path, encoding="utf-8") as fh:
            injected = inject_figures(fh.read(), illustrations, present)
        with open(body_typ_path, "w", encoding="utf-8") as fh:
            fh.write(injected)

    shutil.copy(TEMPLATE_PATH, os.path.join(build_dir, "novel.typ"))

    def typ_str(s):
        return s.replace("\\", "\\\\").replace('"', '\\"')

    with open(os.path.join(build_dir, "main.typ"), "w", encoding="utf-8") as fh:
        fh.write(f'#import "novel.typ": novel\n'
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


def cmd_illustrate(args):
    mdir = args.manuscript
    book_path = os.path.join(mdir, "book.yaml")
    if not os.path.exists(book_path):
        gm.fail("book.yaml missing -- run extract first")
    with open(book_path, encoding="utf-8") as fh:
        book = yaml.safe_load(fh) or {}
    problems = validate_illustrations(book, mdir)
    scene_breaks = {n: _count_scene_breaks(p)
                    for n, p in _chapter_paths_by_number(mdir).items()}
    idir = os.path.join(mdir, "illustrations")
    present = ({f for f in os.listdir(idir) if os.path.isfile(os.path.join(idir, f))}
               if os.path.isdir(idir) else set())
    figures = [{
        "file": it.get("file"),
        "chapter": it.get("chapter"),
        "after_scene": it.get("after_scene", 0),
        "caption": it.get("caption"),
        "prompt_file": it.get("prompt_file"),
        "status": "present" if it.get("file") in present else "pending",
    } for it in (book.get("illustrations") or [])]
    gm.out({"success": not problems,
            "manuscript": os.path.abspath(mdir),
            "art_style": book.get("art_style"),
            "scene_breaks_per_chapter": scene_breaks,
            "figures": figures,
            "problems": problems})


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

    s = sub.add_parser("illustrate",
                       help="validate/report the book.yaml illustrations manifest")
    s.add_argument("--manuscript", required=True)
    s.set_defaults(func=cmd_illustrate)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
