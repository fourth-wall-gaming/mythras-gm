#!/usr/bin/env python3
"""
campaign_io.py -- serialize a campaign to a publishable file tree and back.

Export writes a human-readable directory (markdown for prose, JSON for
mechanics) that can be committed to a GitHub repo and published on the web.
Import reads that tree and rebuilds the full campaign graph in TypeDB,
including relations (presence, faction membership, template instances,
lore-about links, event involvement).

Layout:
    campaign.yaml                 manifest
    README.md                     generated overview
    lore/<category>/<slug>.md     frontmatter + full text
    characters/{pcs,npcs,creatures}/<slug>.json
    templates/<slug>.json
    locations/<slug>.md
    factions/<slug>.md
    encounters/<slug>.json
    journal/events.json

All entity ids are preserved for lossless round-trips. `--new-ids` remaps
every id on import so a published campaign loads cleanly into any database.
"""

from __future__ import annotations

import json
import os
import re
import sys

import mythras_engine as eng
import mythras_gm as gm

FORMAT_VERSION = "1.1"


# ---------------------------------------------------------------------------
# Slugs, frontmatter, small-file helpers
# ---------------------------------------------------------------------------

def _slugify(name, used):
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "untitled").lower()).strip("-") or "untitled"
    base, n = slug, 2
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


def _emit_frontmatter(meta):
    """Minimal YAML frontmatter; every value is JSON-encoded (valid YAML)."""
    lines = ["---"]
    for k, v in meta.items():
        if v is None:
            continue
        lines.append(f"{k}: {json.dumps(v)}")
    lines.append("---")
    return "\n".join(lines)


def _parse_md(path):
    """Return (meta dict, body) from a frontmatter markdown file."""
    text = open(path).read()
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    meta = {}
    body = text
    if m:
        body = text[m.end():]
        for line in m.group(1).splitlines():
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            try:
                meta[k.strip()] = json.loads(v.strip())
            except (json.JSONDecodeError, ValueError):
                meta[k.strip()] = v.strip()
    return meta, body.strip()


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text if text.endswith("\n") else text + "\n")


def _write_json(path, obj):
    _write(path, json.dumps(obj, indent=2, default=str))


def _ts(value):
    """Normalize a datetime value to TypeDB literal form: 2026-06-03T12:00:00."""
    s = str(value).replace(" ", "T")[:19]
    return s if len(s) == 19 else gm.get_timestamp()


# ---------------------------------------------------------------------------
# Export: DB -> file tree
# ---------------------------------------------------------------------------

def _member_ids(driver, campaign_id, etype):
    rows = gm._fetch(driver, f'''
        match
          $camp isa myth-campaign, has id "{gm.escape_string(campaign_id)}";
          (campaign: $camp, element: $e) isa myth-campaign-membership;
          $e isa {etype}, has id $i;
        fetch {{ "i": $i }};''')
    return [r["i"] for r in rows]


def _relation_pairs(driver, campaign_id, rel, role_a, role_b, type_a, type_b):
    """All (a-id, b-id) pairs of `rel` where the role_a player is a campaign member."""
    rows = gm._fetch(driver, f'''
        match
          $camp isa myth-campaign, has id "{gm.escape_string(campaign_id)}";
          (campaign: $camp, element: $a) isa myth-campaign-membership;
          $a isa {type_a}, has id $ai;
          ({role_a}: $a, {role_b}: $b) isa {rel};
          $b isa {type_b}, has id $bi;
        fetch {{ "a": $ai, "b": $bi }};''')
    return [(r["a"], r["b"]) for r in rows]


def export_campaign(campaign_id, outdir):
    with gm.get_driver() as driver:
        camp = gm._get_entity(driver, "myth-campaign", campaign_id,
                              ["description", "content", "myth-game-date",
                               "myth-current-scene", "myth-session-number",
                               "myth-time-index", "created-at"])
        if not camp:
            gm.fail(f"No campaign '{campaign_id}'")

        # --- relations (gathered up front, attached to records below)
        presence = dict(_relation_pairs(driver, campaign_id, "myth-presence",
                                        "located", "location",
                                        "myth-character", "myth-location"))
        factions_of = {}
        for c, f in _relation_pairs(driver, campaign_id, "myth-faction-membership",
                                    "member", "faction", "myth-character", "myth-faction"):
            factions_of.setdefault(c, []).append(f)
        template_of = {c: t for t, c in _relation_pairs(
            driver, campaign_id, "myth-template-instance",
            "template", "instance", "myth-creature-template", "myth-character")}

        # --- characters
        characters = []
        for cid in _member_ids(driver, campaign_id, "myth-character"):
            c = gm._load_character(driver, cid)
            extra = gm._get_entity(driver, "myth-character", cid, ["created-at"]) or {}
            characters.append({
                "id": c["id"], "name": c["name"],
                "type": c.get("myth-char-type"), "status": c.get("myth-status"),
                "description": c.get("description"), "narrative": c.get("content"),
                "characteristics": c.get("myth-characteristics-json"),
                "attributes": c.get("myth-attributes-json"),
                "skills": c.get("myth-skills-json"),
                "hit_locations": c.get("myth-hit-locations-json"),
                "equipment": c.get("myth-equipment-json"),
                "passions": c.get("myth-passions-json"),
                "combat_styles": c.get("myth-combat-styles-json"),
                "spells": c.get("myth-spells-json"),
                "powers": c.get("myth-powers-json"),
                "extras": c.get("myth-extras-json"),
                "actor_notes": c.get("myth-actor-notes"),
                "fatigue": c.get("myth-fatigue"),
                "luck_current": c.get("myth-luck-current"),
                "magic_current": c.get("myth-magic-current"),
                "experience_rolls": c.get("myth-experience-rolls"),
                "location": presence.get(cid),
                "factions": factions_of.get(cid, []),
                "from_template": template_of.get(cid),
                "created_at": _ts(extra.get("created-at") or gm.get_timestamp()),
            })

        # --- templates
        templates = []
        for tid in _member_ids(driver, campaign_id, "myth-creature-template"):
            t = gm._get_entity(driver, "myth-creature-template", tid,
                               ["description", "content", "myth-characteristics-json",
                                "myth-attributes-json", "myth-skills-json",
                                "myth-hit-locations-json", "myth-equipment-json",
                                "myth-combat-styles-json", "created-at"])
            templates.append({
                "id": t["id"], "name": t["name"],
                "description": t.get("description"), "narrative": t.get("content"),
                "characteristics": json.loads(t.get("myth-characteristics-json") or "{}"),
                "attributes": json.loads(t.get("myth-attributes-json") or "{}"),
                "skills": json.loads(t.get("myth-skills-json") or "{}"),
                "hit_locations": json.loads(t.get("myth-hit-locations-json") or "[]"),
                "equipment": json.loads(t.get("myth-equipment-json") or "[]"),
                "combat_styles": json.loads(t.get("myth-combat-styles-json") or "{}"),
                "created_at": _ts(t.get("created-at") or gm.get_timestamp()),
            })

        # --- locations / factions (markdown records)
        locations = []
        for lid in _member_ids(driver, campaign_id, "myth-location"):
            l = gm._get_entity(driver, "myth-location", lid,
                               ["description", "content", "myth-location-type", "created-at"])
            locations.append(l)
        faction_records = []
        for fid in _member_ids(driver, campaign_id, "myth-faction"):
            f = gm._get_entity(driver, "myth-faction", fid,
                               ["description", "content", "created-at"])
            faction_records.append(f)

        # --- lore (with about-links)
        lore_entries = []
        for lid in _member_ids(driver, campaign_id, "myth-lore"):
            l = gm._get_entity(driver, "myth-lore", lid,
                               ["description", "content", "myth-lore-category",
                                "myth-lore-visibility", "created-at"])
            subjects = gm._fetch(driver, f'''
                match
                  $l isa myth-lore, has id "{gm.escape_string(lid)}";
                  (lore: $l, subject: $s) isa myth-lore-about;
                  $s has id $si;
                fetch {{ "si": $si }};''')
            l["about"] = sorted(r["si"] for r in subjects)
            lore_entries.append(l)

        # --- living world: agendas and beats (with holder/target/cast links)
        agendas = []
        for aid in _member_ids(driver, campaign_id, "myth-agenda"):
            a = gm._get_entity(driver, "myth-agenda", aid,
                               ["description", "content", "myth-agenda-status",
                                "myth-agenda-clock-size", "myth-agenda-clock-filled",
                                "myth-agenda-priority", "created-at"])
            holders = gm._fetch(driver, f'''
                match
                  $a isa myth-agenda, has id "{gm.escape_string(aid)}";
                  (agenda: $a, holder: $h) isa myth-agenda-holder;
                  $h has id $hi;
                fetch {{ "hi": $hi }};''')
            targets = gm._fetch(driver, f'''
                match
                  $a isa myth-agenda, has id "{gm.escape_string(aid)}";
                  (agenda: $a, target: $t) isa myth-agenda-target;
                  $t has id $ti;
                fetch {{ "ti": $ti }};''')
            a["holder"] = holders[0]["hi"] if holders else None
            a["targets"] = sorted(r["ti"] for r in targets)
            agendas.append(a)

        beats = []
        for bid in _member_ids(driver, campaign_id, "myth-beat"):
            b = gm._get_entity(driver, "myth-beat", bid,
                               ["description", "content", "myth-beat-status",
                                "myth-beat-when", "myth-beat-trigger",
                                "myth-beat-onscreen-if", "myth-time-index",
                                "created-at"])
            of = gm._fetch(driver, f'''
                match
                  $b isa myth-beat, has id "{gm.escape_string(bid)}";
                  (beat: $b, agenda: $a) isa myth-beat-of;
                  $a has id $ai;
                fetch {{ "ai": $ai }};''')
            at = gm._fetch(driver, f'''
                match
                  $b isa myth-beat, has id "{gm.escape_string(bid)}";
                  (beat: $b, place: $p) isa myth-beat-at;
                  $p has id $pi;
                fetch {{ "pi": $pi }};''')
            cast = gm._fetch(driver, f'''
                match
                  $b isa myth-beat, has id "{gm.escape_string(bid)}";
                  (beat: $b, member: $m) isa myth-beat-cast;
                  $m has id $mi;
                fetch {{ "mi": $mi }};''')
            b["agenda"] = of[0]["ai"] if of else None
            b["place"] = at[0]["pi"] if at else None
            b["cast"] = sorted(r["mi"] for r in cast)
            beats.append(b)

        # --- facts, knowledge edges, and agenda requirements
        facts = []
        for fid in _member_ids(driver, campaign_id, "myth-fact"):
            f = gm._get_entity(driver, "myth-fact", fid,
                               ["description", "content", "myth-fact-status",
                                "myth-fact-truth", "myth-time-index", "created-at"])
            about = gm._fetch(driver, f'''
                match
                  $f isa myth-fact, has id "{gm.escape_string(fid)}";
                  (fact: $f, subject: $s) isa myth-fact-about;
                  $s has id $si;
                fetch {{ "si": $si }};''')
            origin = gm._fetch(driver, f'''
                match
                  $f isa myth-fact, has id "{gm.escape_string(fid)}";
                  (fact: $f, origin: $o) isa myth-fact-from;
                  $o has id $oi;
                fetch {{ "oi": $oi }};''')
            f["about"] = sorted(r["si"] for r in about)
            f["origin"] = origin[0]["oi"] if origin else None
            facts.append(f)

        knowledge = gm._flatten_edges(gm._knowledge_edges(driver, campaign_id))
        requirements = gm._agenda_requirements(driver, campaign_id)
        consequences = []
        for c in gm._consequences(driver, campaign_id):
            amt = c.get("amount")
            consequences.append({"fact": c["fact"], "agenda": c["agenda"],
                                 "effect": c["effect"],
                                 "amount": (amt[0] if isinstance(amt, list) and amt
                                            else (None if isinstance(amt, list) else amt))})
        supersedes = gm._fetch(driver, f'''
            match
              $camp isa myth-campaign, has id "{gm.escape_string(campaign_id)}";
              (campaign: $camp, element: $new) isa myth-campaign-membership;
              $new isa myth-fact, has id $ni;
              (superseding: $new, superseded: $old) isa myth-fact-supersedes;
              $old has id $oi;
            fetch {{ "superseding": $ni, "superseded": $oi }};''')

        # --- encounters
        encounters = []
        for eid in _member_ids(driver, campaign_id, "myth-encounter"):
            e = gm._get_entity(driver, "myth-encounter", eid,
                               ["description", "content", "myth-encounter-status",
                                "myth-round", "myth-combatants-json", "created-at"])
            encounters.append({
                "id": e["id"], "name": e["name"],
                "description": e.get("description"), "summary": e.get("content"),
                "status": e.get("myth-encounter-status"),
                "round": e.get("myth-round"),
                "combatants": json.loads(e.get("myth-combatants-json") or "[]"),
                "created_at": _ts(e.get("created-at") or gm.get_timestamp()),
            })

        # --- journal events (with involvement links)
        events = []
        for eid in _member_ids(driver, campaign_id, "myth-game-event"):
            e = gm._get_entity(driver, "myth-game-event", eid,
                               ["description", "content", "myth-event-type",
                                "myth-session-number", "created-at"])
            involved = gm._fetch(driver, f'''
                match
                  $e isa myth-game-event, has id "{gm.escape_string(eid)}";
                  (event: $e, participant: $p) isa myth-event-involvement;
                  $p has id $pi;
                fetch {{ "pi": $pi }};''')
            events.append({
                "id": e["id"], "type": e.get("myth-event-type"),
                "summary": e.get("description"), "narrative": e.get("content"),
                "session": e.get("myth-session-number"),
                "involves": sorted(r["pi"] for r in involved),
                "at": _ts(e.get("created-at") or gm.get_timestamp()),
            })
        events.sort(key=lambda r: r["at"])

    # ------------------------------------------------------------------
    # Write the tree
    # ------------------------------------------------------------------
    os.makedirs(outdir, exist_ok=True)

    manifest = {
        "format": "mythras-gm-campaign",
        "format_version": FORMAT_VERSION,
        "id": camp["id"],
        "name": camp["name"],
        "description": camp.get("description"),
        "game_date": camp.get("myth-game-date"),
        "current_scene": camp.get("myth-current-scene"),
        "time_index": camp.get("myth-time-index"),
        "session_number": camp.get("myth-session-number"),
        "created_at": _ts(camp.get("created-at") or gm.get_timestamp()),
        "exported_at": gm.get_timestamp(),
    }
    _write(os.path.join(outdir, "campaign.yaml"),
           "\n".join(f"{k}: {json.dumps(v)}" for k, v in manifest.items() if v is not None))
    if camp.get("content"):
        _write(os.path.join(outdir, "campaign.md"), camp["content"])

    counts = {}

    used = set()
    lore_index = []  # (category, name, visibility, relpath) for the README
    for l in lore_entries:
        cat = l.get("myth-lore-category") or "uncategorized"
        slug = _slugify(l["name"], used)
        vis = l.get("myth-lore-visibility", "player")
        meta = {"id": l["id"], "title": l["name"], "category": cat,
                "visibility": vis,
                "summary": l.get("description"), "about": l.get("about") or None,
                "created_at": _ts(l.get("created-at") or gm.get_timestamp())}
        _write(os.path.join(outdir, "lore", cat, slug + ".md"),
               _emit_frontmatter(meta) + "\n\n" + (l.get("content") or ""))
        lore_index.append((cat, l["name"], vis, f"lore/{cat}/{slug}.md"))
    counts["lore"] = len(lore_entries)

    used = set()
    agenda_index = []  # (title, holder, clock, relpath) for the README
    for a in agendas:
        slug = _slugify(a["name"], used)
        size = a.get("myth-agenda-clock-size") or 0
        filled = a.get("myth-agenda-clock-filled") or 0
        meta = {"id": a["id"], "title": a["name"],
                "goal": a.get("description"),
                "status": a.get("myth-agenda-status") or "active",
                "clock_size": size, "clock_filled": filled,
                "priority": a.get("myth-agenda-priority") or 3,
                "holder": a.get("holder"),
                "targets": a.get("targets") or None,
                "created_at": _ts(a.get("created-at") or gm.get_timestamp())}
        _write(os.path.join(outdir, "agendas", slug + ".md"),
               _emit_frontmatter(meta) + "\n\n" + (a.get("content") or ""))
        agenda_index.append((a["name"], a.get("holder"), f"{filled}/{size}",
                             f"agendas/{slug}.md"))
    counts["agendas"] = len(agendas)

    used = set()
    for b in beats:
        slug = _slugify(b["name"], used)
        meta = {"id": b["id"], "title": b["name"],
                "summary": b.get("description"),
                "status": b.get("myth-beat-status") or "pending",
                "when": b.get("myth-beat-when"),
                "time_index": b.get("myth-time-index"),
                "trigger": b.get("myth-beat-trigger") or "time",
                "onscreen_if": b.get("myth-beat-onscreen-if"),
                "agenda": b.get("agenda"), "place": b.get("place"),
                "cast": b.get("cast") or None,
                "created_at": _ts(b.get("created-at") or gm.get_timestamp())}
        _write(os.path.join(outdir, "beats", slug + ".md"),
               _emit_frontmatter(meta) + "\n\n" + (b.get("content") or ""))
    counts["beats"] = len(beats)

    used = set()
    for f in facts:
        slug = _slugify(f["name"], used)
        meta = {"id": f["id"], "title": f["name"],
                "statement": f.get("description"),
                "status": f.get("myth-fact-status") or "established",
                "truth": f.get("myth-fact-truth") or "true",
                "time_index": f.get("myth-time-index"),
                "about": f.get("about") or None, "origin": f.get("origin"),
                "created_at": _ts(f.get("created-at") or gm.get_timestamp())}
        _write(os.path.join(outdir, "facts", slug + ".md"),
               _emit_frontmatter(meta) + "\n\n" + (f.get("content") or ""))
    counts["facts"] = len(facts)

    # Knowledge is a set of edges, not documents: one file keeps it diffable.
    _write_json(os.path.join(outdir, "knowledge.json"),
                {"knows": sorted(knowledge, key=lambda e: (e["fact"], e["knower"])),
                 "agenda_requires": sorted(requirements,
                                           key=lambda r: (r["agenda"], r["fact"])),
                 "consequences": sorted(consequences,
                                        key=lambda c: (c["fact"], c["agenda"])),
                 "supersedes": sorted(supersedes,
                                      key=lambda s: (s["superseding"], s["superseded"]))})
    counts["knowledge"] = len(knowledge)

    used = set()
    subdir = {"pc": "pcs", "npc": "npcs", "creature": "creatures"}
    char_index = []  # (type, name, description, relpath)
    for c in characters:
        d = subdir.get(c["type"], "npcs")
        slug = _slugify(c["name"], used)
        _write_json(os.path.join(outdir, "characters", d, slug + ".json"), c)
        char_index.append((c["type"], c["name"], c.get("description") or "",
                           f"characters/{d}/{slug}.json"))
    counts["characters"] = len(characters)

    used = set()
    for t in templates:
        _write_json(os.path.join(outdir, "templates",
                                 _slugify(t["name"], used) + ".json"), t)
    counts["templates"] = len(templates)

    used = set()
    for l in locations:
        meta = {"id": l["id"], "name": l["name"],
                "type": l.get("myth-location-type"),
                "summary": l.get("description"),
                "created_at": _ts(l.get("created-at") or gm.get_timestamp())}
        _write(os.path.join(outdir, "locations", _slugify(l["name"], used) + ".md"),
               _emit_frontmatter(meta) + "\n\n" + (l.get("content") or ""))
    counts["locations"] = len(locations)

    used = set()
    for f in faction_records:
        meta = {"id": f["id"], "name": f["name"], "summary": f.get("description"),
                "created_at": _ts(f.get("created-at") or gm.get_timestamp())}
        _write(os.path.join(outdir, "factions", _slugify(f["name"], used) + ".md"),
               _emit_frontmatter(meta) + "\n\n" + (f.get("content") or ""))
    counts["factions"] = len(faction_records)

    used = set()
    for e in encounters:
        _write_json(os.path.join(outdir, "encounters",
                                 _slugify(e["name"], used) + ".json"), e)
    counts["encounters"] = len(encounters)

    _write_json(os.path.join(outdir, "journal", "events.json"), events)
    counts["events"] = len(events)

    pcs = [c["name"] for c in characters if c["type"] == "pc"]

    # Worldbook index: lore grouped by category
    by_cat = {}
    for cat, name, vis, rel in lore_index:
        by_cat.setdefault(cat, []).append((name, vis, rel))
    lore_md = []
    for cat in sorted(by_cat):
        lore_md.append(f"**{cat}**")
        for name, vis, rel in by_cat[cat]:
            mark = " *(GM only)*" if vis == "gm" else ""
            lore_md.append(f"- [{name}]({rel}){mark}")
        lore_md.append("")
    lore_section = "\n".join(lore_md).rstrip()

    holder_names = {r["id"]: r["name"] for r in characters}
    holder_names.update({f["id"]: f["name"] for f in faction_records})
    agenda_md = []
    for title, holder, clock, rel in sorted(agenda_index):
        who = holder_names.get(holder, "unattributed")
        agenda_md.append(f"- [{title}]({rel}) -- *{who}* ({clock})")
    agenda_section = "\n".join(agenda_md) or "_None._"

    # Dramatis personae
    type_label = {"pc": "Player characters", "npc": "NPCs", "creature": "Creatures"}
    people_md = []
    for t in ("pc", "npc", "creature"):
        group = [(n, d, rel) for ct, n, d, rel in char_index if ct == t]
        if not group:
            continue
        people_md.append(f"**{type_label[t]}**")
        for n, d, rel in group:
            people_md.append(f"- [{n}]({rel})" + (f" — {d}" if d else ""))
        people_md.append("")
    people_section = "\n".join(people_md).rstrip()

    factions_section = "\n".join(
        f"- [{f['name']}](factions/{_slugify(f['name'], set())}.md)"
        + (f" — {f['description']}" if f.get("description") else "")
        for f in faction_records) or "none"

    novels_row = ""
    novels_section = ""
    novels_dir = os.path.join(outdir, "novels")
    if os.path.isdir(novels_dir):
        novel_entries = []
        for slug in sorted(os.listdir(novels_dir)):
            book_yaml = os.path.join(novels_dir, slug, "book.yaml")
            if not os.path.isfile(book_yaml):
                continue
            meta = {}
            for line in open(book_yaml):
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip().strip("'\"")
            pdf_rel = f"novels/{slug}/{slug}.pdf"
            link = (pdf_rel if os.path.isfile(os.path.join(outdir, pdf_rel))
                    else f"novels/{slug}/")
            entry = (f"- [{meta.get('title', slug)}]({link}) — "
                     f"{slug.replace('-', ' ').title()}'s run")
            if meta.get("style"):
                entry += f", in the style of {meta['style'].title()}"
            novel_entries.append(entry)
        if novel_entries:
            novels_row = ("\n| `novels/` | Novelizations of actual play, "
                          "one directory per protagonist/party |")
            novels_section = ("\n## Novels\n\n"
                              "Actual play at the table, retold as fiction — "
                              "one play session per chapter, drafted from the "
                              "campaign journal via the mythras-gm "
                              "novelization workflow.\n\n"
                              + "\n".join(novel_entries) + "\n")

    setting_note = ""
    if os.path.isdir(os.path.join(outdir, "setting")):
        setting_note = ("\nThe canonical full-prose worldbook sources live in "
                        "[`setting/`](setting/) — see its README for the book "
                        "list and audience guide. The `lore/` files below are "
                        "the same material sliced into database-ready entries.\n")

    readme = f"""# {camp['name']}

{camp.get('description') or ''}

A **Mythras Imperative** campaign in the
[mythras-gm](https://github.com/fourth-wall-gaming/mythras-gm) publishable
campaign format (v{FORMAT_VERSION}).

| Contents | Count |
|---|---|
| Lore entries | {counts['lore']} |
| Characters | {counts['characters']} (PCs: {', '.join(pcs) or 'none'}) |
| Creature templates | {counts['templates']} |
| Locations | {counts['locations']} |
| Factions | {counts['factions']} |
| Encounters | {counts['encounters']} |
| Journal events | {counts['events']} |
| Agendas | {counts['agendas']} |
| Beats | {counts['beats']} |
| Facts | {counts['facts']} |
| Knowledge edges | {counts['knowledge']} |

## Repository layout

| Directory | Contents |
|---|---|
| `lore/` | The worldbook, one markdown file per entry, grouped by category |
| `characters/` | PCs, NPCs, and creatures (full sheets + GM narratives, JSON) |
| `templates/` | Reusable creature/NPC stat blocks (JSON) |
| `locations/` | Places (markdown + frontmatter) |
| `factions/` | Factions and organizations (markdown + frontmatter) |
| `encounters/` | Combat encounter state (JSON) |
| `journal/` | The campaign event log (JSON) |
| `agendas/` | What each NPC and faction wants, on a progress clock |
| `beats/` | What happens next if nobody interferes, scheduled in world time |
| `facts/` | Situational truth: one proposition per file, with when it became true |
| `knowledge.json` | Who knows which fact, how, and since when |{novels_row}
{setting_note}
## The living world (agendas)

What the world is doing while the PCs are elsewhere. Each agenda is a goal held
by a character or faction, tracked on a clock; the `beats/` directory holds the
concrete things those goals produce, scheduled against the world clock. Run
`tick` between scenes to find out what has come due.

{agenda_section}

## The worldbook (lore index)

{lore_section}

## Dramatis personae

{people_section}

## Factions

{factions_section}
{novels_section}
## Loading this campaign

```bash
python skills/mythras-gm/mythras_gm.py import-campaign --path <this-directory> --new-ids
```

Then resume play with `get-context --campaign <new-id>`.

> Lore files marked `visibility: "gm"` contain spoilers. Players: browse
> `lore/` but skip anything GM-marked, and stay out of `encounters/` and
> `journal/` if you want to avoid table history.

Based on Mythras Imperative, Written by Pete Nash and Lawrence Whitaker,
published by The Design Mechanism, Copyright 2023, used under the ORC License.
"""
    _write(os.path.join(outdir, "README.md"), readme)

    gm.out({"success": True, "campaign": camp["name"], "output": outdir, **counts})


# ---------------------------------------------------------------------------
# Import: file tree -> DB
# ---------------------------------------------------------------------------

def _read_tree(path):
    """Parse the campaign directory back into record lists."""
    manifest = {}
    for line in open(os.path.join(path, "campaign.yaml")):
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        try:
            manifest[k.strip()] = json.loads(v.strip())
        except (json.JSONDecodeError, ValueError):
            manifest[k.strip()] = v.strip()
    camp_md = os.path.join(path, "campaign.md")
    manifest["content"] = open(camp_md).read().strip() if os.path.exists(camp_md) else None

    def md_records(subdir):
        records = []
        root = os.path.join(path, subdir)
        if not os.path.isdir(root):
            return records
        for dirpath, _, files in os.walk(root):
            for fn in sorted(files):
                if fn.endswith(".md"):
                    meta, body = _parse_md(os.path.join(dirpath, fn))
                    meta["content"] = body
                    records.append(meta)
        return records

    def json_records(subdir):
        records = []
        root = os.path.join(path, subdir)
        if not os.path.isdir(root):
            return records
        for dirpath, _, files in os.walk(root):
            for fn in sorted(files):
                if fn.endswith(".json"):
                    records.append(json.load(open(os.path.join(dirpath, fn))))
        return records

    events_path = os.path.join(path, "journal", "events.json")
    events = json.load(open(events_path)) if os.path.exists(events_path) else []

    return {
        "manifest": manifest,
        "lore": md_records("lore"),
        "agendas": md_records("agendas"),
        "beats": md_records("beats"),
        "facts": md_records("facts"),
        "knowledge": (json.load(open(os.path.join(path, "knowledge.json")))
                      if os.path.exists(os.path.join(path, "knowledge.json"))
                      else {"knows": [], "agenda_requires": []}),
        "locations": md_records("locations"),
        "factions": md_records("factions"),
        "characters": json_records("characters"),
        "templates": json_records("templates"),
        "encounters": json_records("encounters"),
        "events": events,
    }


def _opt(attr, value, quote=True):
    if isinstance(value, list):          # optional-attribute fetches come back as lists
        value = value[0] if value else None
    if value is None or value == "":
        return ""
    if quote:
        return f', has {attr} "{gm.escape_string(str(value))}"'
    return f", has {attr} {value}"


def import_campaign(path, new_name=None, new_ids=False):
    tree = _read_tree(path)
    man = tree["manifest"]

    # --- id mapping
    all_ids = ([man["id"]]
               + [r["id"] for key in ("lore", "locations", "factions",
                                      "characters", "templates", "encounters",
                                      "agendas", "beats", "facts")
                  for r in tree[key]]
               + [e["id"] for e in tree["events"]])
    if new_ids:
        idmap = {old: gm.generate_id("-".join(old.split("-")[:-1])) for old in all_ids}
    else:
        idmap = {old: old for old in all_ids}

    def rid(old):
        """Remap an id; ids referencing entities outside the export pass through."""
        return idmap.get(old, old) if old else old

    with gm.get_driver() as driver:
        cid = rid(man["id"])
        if gm._fetch(driver, f'''
                match $c isa myth-campaign, has id "{gm.escape_string(cid)}";
                fetch {{ "i": $c.id }};'''):
            gm.fail(f"Campaign id '{cid}' already exists -- use --new-ids to remap")

        # --- campaign
        name = new_name or man["name"]
        q = (f'insert $c isa myth-campaign, has id "{cid}", '
             f'has name "{gm.escape_string(name)}", '
             f'has myth-session-number {man.get("session_number") or 0}, '
             f'has created-at {_ts(man.get("created_at") or gm.get_timestamp())}'
             + _opt("description", man.get("description"))
             + _opt("content", man.get("content"))
             + _opt("myth-game-date", man.get("game_date"))
             + _opt("myth-current-scene", man.get("current_scene"))
             + _opt("myth-time-index", man.get("time_index"), quote=False) + ";")
        gm._write(driver, q)

        def link(eid, etype):
            gm._link_to_campaign(driver, cid, eid, etype)

        # --- locations
        for l in tree["locations"]:
            lid = rid(l["id"])
            gm._write(driver, f'insert $e isa myth-location, has id "{lid}", '
                      f'has name "{gm.escape_string(l["name"])}", '
                      f'has created-at {_ts(l.get("created_at"))}'
                      + _opt("myth-location-type", l.get("type"))
                      + _opt("description", l.get("summary"))
                      + _opt("content", l.get("content")) + ";")
            link(lid, "myth-location")

        # --- factions
        for f in tree["factions"]:
            fid = rid(f["id"])
            gm._write(driver, f'insert $e isa myth-faction, has id "{fid}", '
                      f'has name "{gm.escape_string(f["name"])}", '
                      f'has created-at {_ts(f.get("created_at"))}'
                      + _opt("description", f.get("summary"))
                      + _opt("content", f.get("content")) + ";")
            link(fid, "myth-faction")

        # --- templates
        for t in tree["templates"]:
            tid = rid(t["id"])
            gm._write(driver, f'insert $e isa myth-creature-template, has id "{tid}", '
                      f'has name "{gm.escape_string(t["name"])}", '
                      f'has myth-characteristics-json "{gm.escape_string(json.dumps(t.get("characteristics") or {}))}", '
                      f'has myth-attributes-json "{gm.escape_string(json.dumps(t.get("attributes") or {}))}", '
                      f'has myth-skills-json "{gm.escape_string(json.dumps(t.get("skills") or {}))}", '
                      f'has myth-hit-locations-json "{gm.escape_string(json.dumps(t.get("hit_locations") or []))}", '
                      f'has myth-equipment-json "{gm.escape_string(json.dumps(t.get("equipment") or []))}", '
                      f'has myth-combat-styles-json "{gm.escape_string(json.dumps(t.get("combat_styles") or {}))}", '
                      f'has created-at {_ts(t.get("created_at"))}'
                      + _opt("description", t.get("description"))
                      + _opt("content", t.get("narrative")) + ";")
            link(tid, "myth-creature-template")

        # --- characters
        for c in tree["characters"]:
            ccid = rid(c["id"])
            q = (f'insert $e isa myth-character, has id "{ccid}", '
                 f'has name "{gm.escape_string(c["name"])}", '
                 f'has myth-char-type "{gm.escape_string(c.get("type") or "npc")}", '
                 f'has myth-status "{gm.escape_string(c.get("status") or "active")}", '
                 f'has myth-characteristics-json "{gm.escape_string(json.dumps(c.get("characteristics") or {}))}", '
                 f'has myth-attributes-json "{gm.escape_string(json.dumps(c.get("attributes") or {}))}", '
                 f'has myth-skills-json "{gm.escape_string(json.dumps(c.get("skills") or {}))}", '
                 f'has myth-hit-locations-json "{gm.escape_string(json.dumps(c.get("hit_locations") or []))}", '
                 f'has myth-equipment-json "{gm.escape_string(json.dumps(c.get("equipment") or []))}", '
                 f'has myth-passions-json "{gm.escape_string(json.dumps(c.get("passions") or {}))}", '
                 f'has myth-combat-styles-json "{gm.escape_string(json.dumps(c.get("combat_styles") or {}))}", '
                 f'has myth-fatigue "{gm.escape_string(c.get("fatigue") or "Fresh")}", '
                 f'has myth-luck-current {c.get("luck_current") if c.get("luck_current") is not None else 2}, '
                 f'has myth-magic-current {c.get("magic_current") if c.get("magic_current") is not None else 10}, '
                 f'has myth-experience-rolls {c.get("experience_rolls") or 0}, '
                 f'has created-at {_ts(c.get("created_at"))}')
            if c.get("spells"):
                q += f', has myth-spells-json "{gm.escape_string(json.dumps(c["spells"]))}"'
            if c.get("powers"):
                q += f', has myth-powers-json "{gm.escape_string(json.dumps(c["powers"]))}"'
            if c.get("extras"):
                q += f', has myth-extras-json "{gm.escape_string(json.dumps(c["extras"]))}"'
            if c.get("actor_notes"):
                q += f', has myth-actor-notes "{gm.escape_string(c["actor_notes"])}"'
            q += _opt("description", c.get("description"))
            q += _opt("content", c.get("narrative")) + ";"
            gm._write(driver, q)
            link(ccid, "myth-character")
            if c.get("location"):
                gm._write(driver, f'''
                    match
                      $c isa myth-character, has id "{ccid}";
                      $l isa myth-location, has id "{rid(c["location"])}";
                    insert (located: $c, location: $l) isa myth-presence;''')
            for fac in c.get("factions") or []:
                gm._write(driver, f'''
                    match
                      $c isa myth-character, has id "{ccid}";
                      $f isa myth-faction, has id "{rid(fac)}";
                    insert (faction: $f, member: $c) isa myth-faction-membership;''')
            if c.get("from_template") and c["from_template"] in idmap:
                gm._write(driver, f'''
                    match
                      $t isa myth-creature-template, has id "{rid(c["from_template"])}";
                      $c isa myth-character, has id "{ccid}";
                    insert (template: $t, instance: $c) isa myth-template-instance;''')

        # --- lore (+ about-links, deferred until all subjects exist)
        for l in tree["lore"]:
            lid = rid(l["id"])
            gm._write(driver, f'insert $e isa myth-lore, has id "{lid}", '
                      f'has name "{gm.escape_string(l["title"])}", '
                      f'has myth-lore-category "{gm.escape_string(l.get("category") or "uncategorized")}", '
                      f'has myth-lore-visibility "{gm.escape_string(l.get("visibility") or "player")}", '
                      f'has created-at {_ts(l.get("created_at"))}'
                      + _opt("description", l.get("summary"))
                      + _opt("content", l.get("content")) + ";")
            link(lid, "myth-lore")
        for l in tree["lore"]:
            for sid in l.get("about") or []:
                gm._link_lore_about(driver, rid(l["id"]), rid(sid))

        # --- living world: agendas then beats (relations deferred until
        #     holders, places and cast all exist)
        for a in tree["agendas"]:
            aid = rid(a["id"])
            gm._write(driver, f'insert $e isa myth-agenda, has id "{aid}", '
                      f'has name "{gm.escape_string(a["title"])}", '
                      f'has myth-agenda-status "{gm.escape_string(a.get("status") or "active")}", '
                      f'has myth-agenda-clock-size {a.get("clock_size") or 0}, '
                      f'has myth-agenda-clock-filled {a.get("clock_filled") or 0}, '
                      f'has myth-agenda-priority {a.get("priority") or 3}, '
                      f'has created-at {_ts(a.get("created_at"))}'
                      + _opt("description", a.get("goal"))
                      + _opt("content", a.get("content")) + ";")
            link(aid, "myth-agenda")

        for b in tree["beats"]:
            bid = rid(b["id"])
            # `when` is what a human authors; the index is derived from it. A
            # beat file that carries only `when` must still be schedulable --
            # otherwise it imports clean, reads correctly in every listing, and
            # silently never fires, because due-ness is decided on the index.
            # `when` is authored and the index is derived from it, so the
            # index is never trusted over the string. Two beats survived a
            # calendar change carrying indices from the old one: they read
            # correctly everywhere and would have fired two days early.
            if b.get("when"):
                try:
                    b["time_index"] = eng.parse_time_key(b["when"])
                except ValueError:
                    # Refuse rather than store it. A `when` that does not parse
                    # imports clean, reads correctly in every listing, and then
                    # never fires -- the worst failure this format has, because
                    # nothing looks wrong until a scene silently does not happen.
                    gm.fail(f"beat {b.get('title')!r}: cannot read when "
                            f"{b['when']!r}. Expected '<day>/<watch>', e.g. "
                            f"'d-3/night'. A trailing comment on the line will "
                            f"do this -- the front matter reader is not YAML.")
            q = (f'insert $e isa myth-beat, has id "{bid}", '
                 f'has name "{gm.escape_string(b["title"])}", '
                 f'has myth-beat-status "{gm.escape_string(b.get("status") or "pending")}", '
                 f'has myth-beat-trigger "{gm.escape_string(b.get("trigger") or "time")}", '
                 f'has created-at {_ts(b.get("created_at"))}'
                 + _opt("myth-beat-when", b.get("when"))
                 + _opt("myth-time-index", b.get("time_index"), quote=False)
                 + _opt("myth-beat-onscreen-if", b.get("onscreen_if"))
                 + _opt("description", b.get("summary"))
                 + _opt("content", b.get("content")) + ";")
            gm._write(driver, q)
            link(bid, "myth-beat")

        for a in tree["agendas"]:
            if a.get("holder"):
                gm._link_relation(driver, "myth-agenda-holder", "agenda",
                                  "myth-agenda", rid(a["id"]), "holder",
                                  gm.AGENDA_HOLDER_TYPES, rid(a["holder"]))
            for tid in a.get("targets") or []:
                gm._link_relation(driver, "myth-agenda-target", "agenda",
                                  "myth-agenda", rid(a["id"]), "target",
                                  gm.AGENDA_TARGET_TYPES, rid(tid))
        for b in tree["beats"]:
            if b.get("agenda"):
                gm._link_relation(driver, "myth-beat-of", "beat", "myth-beat",
                                  rid(b["id"]), "agenda", ["myth-agenda"],
                                  rid(b["agenda"]))
            if b.get("place"):
                gm._link_relation(driver, "myth-beat-at", "beat", "myth-beat",
                                  rid(b["id"]), "place", ["myth-location"],
                                  rid(b["place"]))
            for member_id in b.get("cast") or []:
                gm._link_relation(driver, "myth-beat-cast", "beat", "myth-beat",
                                  rid(b["id"]), "member", gm.AGENDA_HOLDER_TYPES,
                                  rid(member_id))

        # --- facts, then the knowledge edges over them (deferred: knowers,
        #     subjects and origins must all exist first)
        for f in tree["facts"]:
            fid = rid(f["id"])
            q = (f'insert $e isa myth-fact, has id "{fid}", '
                 f'has name "{gm.escape_string(f["title"])}", '
                 f'has myth-fact-status "{gm.escape_string(f.get("status") or "established")}", '
                 f'has myth-fact-truth "{gm.escape_string(f.get("truth") or "true")}", '
                 f'has created-at {_ts(f.get("created_at"))}'
                 + _opt("description", f.get("statement"))
                 + _opt("myth-time-index", f.get("time_index"), quote=False)
                 + _opt("content", f.get("content")) + ";")
            gm._write(driver, q)
            link(fid, "myth-fact")
        for f in tree["facts"]:
            for sid in f.get("about") or []:
                gm._link_relation(driver, "myth-fact-about", "fact", "myth-fact",
                                  rid(f["id"]), "subject", gm.FACT_SUBJECT_TYPES,
                                  rid(sid))
            if f.get("origin"):
                gm._link_relation(driver, "myth-fact-from", "fact", "myth-fact",
                                  rid(f["id"]), "origin", gm.FACT_ORIGIN_TYPES,
                                  rid(f["origin"]))

        know = tree.get("knowledge") or {}
        for e in know.get("knows") or []:
            ktype = None
            for kt in gm.KNOWER_TYPES:
                if gm._fetch(driver, f'''
                        match $k isa {kt}, has id "{gm.escape_string(rid(e["knower"]))}";
                        fetch {{ "i": $k.id }};'''):
                    ktype = kt
                    break
            if not ktype:
                continue
            q = (f'match $k isa {ktype}, has id "{gm.escape_string(rid(e["knower"]))}"; '
                 f'$f isa myth-fact, has id "{gm.escape_string(rid(e["fact"]))}"; '
                 f'insert $r isa myth-knows (knower: $k, fact: $f), '
                 f'has myth-knowledge-certainty "{gm.escape_string(e.get("certainty") or "knows")}"'
                 + _opt("myth-knowledge-source", e.get("source"))
                 + _opt("myth-knowledge-since", e.get("since"), quote=False) + ";")
            gm._write(driver, q)
        for c in know.get("consequences") or []:
            q = (f'match $f isa myth-fact, has id "{gm.escape_string(rid(c["fact"]))}"; '
                 f'$a isa myth-agenda, has id "{gm.escape_string(rid(c["agenda"]))}"; '
                 f'insert $r isa myth-consequence (fact: $f, agenda: $a), '
                 f'has myth-consequence-effect "{gm.escape_string(c["effect"])}"'
                 + _opt("myth-consequence-amount", c.get("amount"), quote=False) + ";")
            gm._write(driver, q)
        for s in know.get("supersedes") or []:
            gm._write(driver, f'''
                match
                  $new isa myth-fact, has id "{gm.escape_string(rid(s["superseding"]))}";
                  $old isa myth-fact, has id "{gm.escape_string(rid(s["superseded"]))}";
                insert (superseding: $new, superseded: $old) isa myth-fact-supersedes;''')
        for r in know.get("agenda_requires") or []:
            gm._write(driver, f'''
                match
                  $a isa myth-agenda, has id "{gm.escape_string(rid(r["agenda"]))}";
                  $f isa myth-fact, has id "{gm.escape_string(rid(r["fact"]))}";
                insert (agenda: $a, fact: $f) isa myth-agenda-requires;''')

        # --- encounters (+ participation, combatant ids remapped)
        for e in tree["encounters"]:
            eid = rid(e["id"])
            combatants = e.get("combatants") or []
            for cb in combatants:
                cb["id"] = rid(cb.get("id"))
            gm._write(driver, f'insert $e isa myth-encounter, has id "{eid}", '
                      f'has name "{gm.escape_string(e["name"])}", '
                      f'has myth-encounter-status "{gm.escape_string(e.get("status") or "resolved")}", '
                      f'has myth-round {e.get("round") or 1}, '
                      f'has myth-combatants-json "{gm.escape_string(json.dumps(combatants))}", '
                      f'has created-at {_ts(e.get("created_at"))}'
                      + _opt("description", e.get("description"))
                      + _opt("content", e.get("summary")) + ";")
            link(eid, "myth-encounter")
            for cb in combatants:
                if cb.get("id"):
                    gm._write(driver, f'''
                        match
                          $e isa myth-encounter, has id "{eid}";
                          $c isa myth-character, has id "{cb["id"]}";
                        insert (encounter: $e, combatant: $c) isa myth-participation;''')

        # --- journal events (+ involvement)
        participant_types = ["myth-character", "myth-location", "myth-faction",
                             "myth-encounter"]
        for ev in tree["events"]:
            evid = rid(ev["id"])
            gm._write(driver, f'insert $e isa myth-game-event, has id "{evid}", '
                      f'has name "{gm.escape_string((ev.get("summary") or "")[:80])}", '
                      f'has description "{gm.escape_string(ev.get("summary") or "")}", '
                      f'has myth-event-type "{gm.escape_string(ev.get("type") or "gm-note")}", '
                      f'has created-at {_ts(ev.get("at"))}'
                      + _opt("content", ev.get("narrative"))
                      + (f', has myth-session-number {ev["session"]}'
                         if ev.get("session") is not None else "") + ";")
            link(evid, "myth-game-event")
            for pid in ev.get("involves") or []:
                pid = rid(pid)
                for ptype in participant_types:
                    if gm._fetch(driver, f'''
                            match $p isa {ptype}, has id "{gm.escape_string(pid)}";
                            fetch {{ "i": $p.id }};'''):
                        gm._write(driver, f'''
                            match
                              $e isa myth-game-event, has id "{evid}";
                              $p isa {ptype}, has id "{gm.escape_string(pid)}";
                            insert (event: $e, participant: $p) isa myth-event-involvement;''')
                        break

    gm.out({"success": True, "id": cid, "name": name,
            "imported": {k: len(tree[k]) for k in
                         ("lore", "locations", "factions", "characters",
                          "templates", "encounters", "events",
                          "agendas", "beats", "facts")},
            "knowledge_edges": len((tree.get("knowledge") or {}).get("knows") or []),
            "consequences": len((tree.get("knowledge") or {}).get("consequences") or []),
            "new_ids": new_ids})


# CLI adapters (called from mythras_gm.py)

def cmd_export(args):
    export_campaign(args.campaign, args.output)


def cmd_import(args):
    import_campaign(args.path, new_name=args.name, new_ids=args.new_ids)
