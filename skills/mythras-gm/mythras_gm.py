#!/usr/bin/env python3
"""
mythras_gm.py -- Gamesmaster CLI for Mythras Imperative with TypeDB persistence.

All campaign state lives in TypeDB (namespace: myth-). The pure rules engine
is in mythras_engine.py. Every command prints a single JSON object.

Campaign:
    create-campaign --name N [--description D] [--game-date D]
    get-campaign --campaign ID
    set-scene --campaign ID --scene TEXT [--game-date D]
    list-campaigns

Characters:
    create-character --campaign ID --name N [--type pc|npc|creature]
        [--species avian|humanoid|winged-quadruped] [--stats JSON] [--roll]
        [--skills JSON] [--combat-styles JSON] [--equipment JSON]
        [--passions JSON] [--armor JSON] [--description D] [--narrative TEXT]
    get-character --id ID [--compact]
    list-characters --campaign ID [--type pc|npc]
    update-character --id ID [--skills JSON] [--equipment JSON] [--passions JSON]
        [--fatigue LEVEL] [--luck N] [--status S]
    apply-damage --id ID --location NAME --damage N [--ignore-armor]
    heal --id ID --location NAME --amount N

Dice & checks:
    roll --dice EXPR
    roll-skill --id ID --skill NAME [--difficulty GRADE] [--augment PASSION]
    roll-opposed --id-a ID --skill-a NAME --id-b ID --skill-b NAME
        [--difficulty-a G] [--difficulty-b G]

Combat:
    start-encounter --campaign ID --name N [--description D]
    add-combatant --encounter ID --character ID
    roll-initiative --encounter ID
    resolve-attack --encounter ID --attacker ID --defender ID
        [--weapon NAME] [--style NAME] [--defense parry|evade|none]
        [--parry-weapon NAME] [--attacker-difficulty G] [--defender-difficulty G]
        [--location NAME] [--no-ap]
    next-round --encounter ID
    get-encounter --encounter ID
    end-encounter --encounter ID [--summary TEXT]

World:
    add-location --campaign ID --name N [--type T] [--description D] [--narrative TEXT]
    add-faction --campaign ID --name N [--description D] [--narrative TEXT]
    add-template --campaign ID --name N --stats JSON [--species S] [--skills JSON]
        [--combat-styles JSON] [--equipment JSON] [--armor JSON] [--description D]
    spawn --template ID --name N [--campaign ID]
    move-character --id ID --location ID
    join-faction --id ID --faction ID

Journal:
    log-event --campaign ID --type T --summary TEXT [--narrative TEXT]
        [--session N] [--involves ID,ID,...]
    get-log --campaign ID [--session N] [--type T] [--limit N]
    get-context --campaign ID [--compact]   # everything needed to resume play

Publishing:
    export-campaign --campaign ID --output DIR   # DB -> publishable file tree
    import-campaign --path DIR [--name N] [--new-ids]   # file tree -> DB

Novelization (see NOVELIZATION.md; separate CLI novelist.py):
    novelist.py extract --campaign ID [--out DIR]
    novelist.py build --manuscript DIR
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import mythras_engine as eng
import mythras_effects as fx

try:
    from typedb.driver import Credentials, DriverOptions, TransactionType, TypeDB
except ImportError:
    print(json.dumps({"success": False, "error": "typedb-driver not installed"}))
    sys.exit(1)

try:
    _SKILL_DIR = os.path.dirname(os.path.realpath(__file__))
    _PROJECT_ROOT = os.path.abspath(os.path.join(_SKILL_DIR, "..", ".."))
    sys.path.insert(0, _PROJECT_ROOT)
    from src.skillful_alhazen.utils.skill_helpers import escape_string, generate_id, get_timestamp
except ImportError:
    import uuid
    from datetime import datetime, timezone

    def escape_string(s):
        if s is None:
            return ""
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")

    def generate_id(prefix):
        return f"{prefix}-{uuid.uuid4().hex[:12]}"

    def get_timestamp():
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

TYPEDB_HOST = os.getenv("TYPEDB_HOST", "localhost")
TYPEDB_PORT = int(os.getenv("TYPEDB_PORT", "1729"))
# One database per repo, per the alhazen convention: this repo owns
# alh_mythras. The old shared "alhazen_notebook" is retired. Anything
# still living there is reachable with TYPEDB_DATABASE=alhazen_notebook.
TYPEDB_DATABASE = os.getenv("TYPEDB_DATABASE", "alh_mythras")
TYPEDB_USERNAME = os.getenv("TYPEDB_USERNAME", "admin")
TYPEDB_PASSWORD = os.getenv("TYPEDB_PASSWORD", "password")


def get_driver():
    return TypeDB.driver(
        f"{TYPEDB_HOST}:{TYPEDB_PORT}",
        Credentials(TYPEDB_USERNAME, TYPEDB_PASSWORD),
        DriverOptions(is_tls_enabled=False),
    )


def out(obj):
    print(json.dumps(obj, default=str))


def fail(msg):
    out({"success": False, "error": msg})
    sys.exit(1)


# ---------------------------------------------------------------------------
# Generic TypeDB helpers
# ---------------------------------------------------------------------------

def _fetch(driver, query):
    with driver.transaction(TYPEDB_DATABASE, TransactionType.READ) as tx:
        return list(tx.query(query).resolve())


def _write(driver, *queries):
    with driver.transaction(TYPEDB_DATABASE, TransactionType.WRITE) as tx:
        for q in queries:
            tx.query(q).resolve()
        tx.commit()


def _set_attr(driver, entity_type, entity_id, attr, value, quote=True):
    """Delete-then-insert an attribute value on an entity (TypeDB 3.x update)."""
    eid = escape_string(entity_id)
    existing = _fetch(driver, f'''
        match $e isa {entity_type}, has id "{eid}", has {attr} $v;
        fetch {{ "v": $v }};''')
    if existing:
        _write(driver, f'''
            match $e isa {entity_type}, has id "{eid}", has {attr} $v;
            delete has $v of $e;''')
    val = f'"{escape_string(str(value))}"' if quote else value
    _write(driver, f'''
        match $e isa {entity_type}, has id "{eid}";
        insert $e has {attr} {val};''')


def _get_entity(driver, entity_type, entity_id, attrs):
    """Fetch listed attributes for one entity; optional attrs come back None."""
    eid = escape_string(entity_id)
    rows = _fetch(driver, f'''
        match $e isa {entity_type}, has id "{eid}";
        fetch {{ "id": $e.id, "name": $e.name }};''')
    if not rows:
        return None
    result = dict(rows[0])
    for a in attrs:
        r = _fetch(driver, f'''
            match $e isa {entity_type}, has id "{eid}", has {a} $v;
            fetch {{ "v": $v }};''')
        result[a] = r[0]["v"] if r else None
    return result


def _link_to_campaign(driver, campaign_id, element_id, element_type):
    _write(driver, f'''
        match
          $c isa myth-campaign, has id "{escape_string(campaign_id)}";
          $e isa {element_type}, has id "{escape_string(element_id)}";
        insert (campaign: $c, element: $e) isa myth-campaign-membership;''')


CHAR_ATTRS = ["description", "content", "myth-char-type", "myth-status",
              "myth-characteristics-json", "myth-attributes-json", "myth-skills-json",
              "myth-hit-locations-json", "myth-equipment-json", "myth-passions-json",
              "myth-combat-styles-json", "myth-spells-json", "myth-extras-json",
              "myth-actor-notes",
              "myth-fatigue", "myth-luck-current",
              "myth-magic-current", "myth-experience-rolls"]


def _load_character(driver, char_id):
    c = _get_entity(driver, "myth-character", char_id, CHAR_ATTRS)
    if not c:
        fail(f"No myth-character with id '{char_id}'")
    for k in list(c):
        if k.endswith("-json") and c[k]:
            c[k] = json.loads(c[k])
    return c


# Attribute keys worth keeping on a combat card (derived stats the GM needs
# mid-fight). Everything else in myth-attributes-json is omitted.
_CARD_ATTR_KEYS = ["action_points", "damage_modifier", "initiative_bonus",
                   "initiative", "movement", "healing_rate"]


def _combat_card(c):
    """Compact projection of a character for in-play context.

    Keeps live combat STATE (hit locations w/ current HP, fatigue, luck, AP,
    damage modifier, combat styles, passions, characteristics) and drops the
    bulky reference data (full skills dict, equipment, spells, extras, prose).
    roll-skill/resolve-attack look skills up from the DB on demand, so the GM
    does not need the skill list in context to adjudicate.
    """
    attrs = c.get("myth-attributes-json") or {}
    card = {
        "id": c.get("id"),
        "name": c.get("name"),
        "type": c.get("myth-char-type"),
        "status": c.get("myth-status"),
        "characteristics": c.get("myth-characteristics-json") or {},
        "attributes": {k: attrs[k] for k in _CARD_ATTR_KEYS if k in attrs},
        "fatigue": c.get("myth-fatigue"),
        "luck_current": c.get("myth-luck-current"),
        "magic_current": c.get("myth-magic-current"),
        "hit_locations": c.get("myth-hit-locations-json") or [],
        "combat_styles": c.get("myth-combat-styles-json") or {},
        "passions": c.get("myth-passions-json") or {},
    }
    return card


# ---------------------------------------------------------------------------
# Campaign commands
# ---------------------------------------------------------------------------

def cmd_create_campaign(args):
    cid = generate_id("myth-campaign")
    ts = get_timestamp()
    q = f'''insert $c isa myth-campaign,
        has id "{cid}", has name "{escape_string(args.name)}",
        has myth-session-number 0, has created-at {ts}'''
    if args.description:
        q += f', has description "{escape_string(args.description)}"'
    if args.game_date:
        q += f', has myth-game-date "{escape_string(args.game_date)}"'
    q += ";"
    with get_driver() as driver:
        _write(driver, q)
    out({"success": True, "id": cid})


def cmd_get_campaign(args):
    with get_driver() as driver:
        c = _get_entity(driver, "myth-campaign", args.campaign,
                        ["description", "content", "myth-game-date",
                         "myth-current-scene", "myth-session-number",
                         "myth-time-index"])
    if not c:
        fail(f"No campaign '{args.campaign}'")
    out({"success": True, "campaign": c})


def cmd_update_campaign(args):
    """Edit campaign-level state. `set-scene` covers the scene; this covers the
    rest -- including the session number and the prose game-date, both of which
    drift away from the numeric world clock if nothing can write them."""
    with get_driver() as driver:
        if not _get_entity(driver, "myth-campaign", args.campaign, []):
            fail(f"No campaign '{args.campaign}'")
        if args.name is not None:
            _set_attr(driver, "myth-campaign", args.campaign, "name", args.name)
        if args.description is not None:
            _set_attr(driver, "myth-campaign", args.campaign, "description", args.description)
        if args.game_date is not None:
            _set_attr(driver, "myth-campaign", args.campaign, "myth-game-date", args.game_date)
        if args.session_number is not None:
            _set_attr(driver, "myth-campaign", args.campaign, "myth-session-number",
                      args.session_number, quote=False)
        if args.time_index is not None:
            _set_attr(driver, "myth-campaign", args.campaign, "myth-time-index",
                      args.time_index, quote=False)
    out({"success": True, "id": args.campaign})


def cmd_set_scene(args):
    with get_driver() as driver:
        _set_attr(driver, "myth-campaign", args.campaign, "myth-current-scene", args.scene)
        if args.game_date:
            _set_attr(driver, "myth-campaign", args.campaign, "myth-game-date", args.game_date)
    out({"success": True})


def cmd_list_campaigns(args):
    with get_driver() as driver:
        rows = _fetch(driver, '''
            match $c isa myth-campaign, has id $i, has name $n;
            fetch { "id": $i, "name": $n };''')
    out({"success": True, "campaigns": rows})


# ---------------------------------------------------------------------------
# Character commands
# ---------------------------------------------------------------------------

def cmd_create_character(args):
    species = args.species
    if args.stats:
        chars = json.loads(args.stats)
    elif args.roll:
        chars = eng.roll_characteristics(species)
    else:
        fail("Provide --stats JSON or --roll")

    attrs = eng.derive_attributes(chars, species)
    skills = eng.base_skills(chars, species)
    if args.skills:
        skills.update(json.loads(args.skills))
    armor = json.loads(args.armor) if args.armor else {}
    locations = eng.build_hit_locations(chars, species, armor)
    equipment = json.loads(args.equipment) if args.equipment else []
    passions = json.loads(args.passions) if args.passions else {}
    styles = json.loads(args.combat_styles) if args.combat_styles else {}

    cid = generate_id("myth-char")
    ts = get_timestamp()
    q = f'''insert $c isa myth-character,
        has id "{cid}",
        has name "{escape_string(args.name)}",
        has myth-char-type "{escape_string(args.type)}",
        has myth-status "active",
        has myth-characteristics-json "{escape_string(json.dumps(chars))}",
        has myth-attributes-json "{escape_string(json.dumps(attrs))}",
        has myth-skills-json "{escape_string(json.dumps(skills))}",
        has myth-hit-locations-json "{escape_string(json.dumps(locations))}",
        has myth-equipment-json "{escape_string(json.dumps(equipment))}",
        has myth-passions-json "{escape_string(json.dumps(passions))}",
        has myth-combat-styles-json "{escape_string(json.dumps(styles))}",
        has myth-fatigue "Fresh",
        has myth-luck-current {attrs["luck_points"]},
        has myth-magic-current {attrs["magic_points"]},
        has myth-experience-rolls 0,
        has created-at {ts}'''
    if args.description:
        q += f', has description "{escape_string(args.description)}"'
    if args.narrative:
        q += f', has content "{escape_string(args.narrative)}"'
    q += ";"

    with get_driver() as driver:
        _write(driver, q)
        if args.campaign:
            _link_to_campaign(driver, args.campaign, cid, "myth-character")

    out({"success": True, "id": cid, "characteristics": chars,
         "attributes": attrs, "skills": skills, "hit_locations": locations})


def cmd_get_character(args):
    with get_driver() as driver:
        c = _load_character(driver, args.id)
    if getattr(args, "compact", False):
        c = _combat_card(c)
    out({"success": True, "character": c})


# ---------------------------------------------------------------------------
# Character import (Mythras-family JSON sheet files)
# ---------------------------------------------------------------------------

def _flatten_kv_list(lst):
    """[{'STR': 14}, {'CON': 13}] -> {'STR': 14, 'CON': 13}. Accepts flat dicts too."""
    if isinstance(lst, dict):
        return dict(lst)
    flat = {}
    for item in lst or []:
        flat.update(item)
    return flat


def _parse_range(rng):
    """'01-03' / '19-20' / '07' / [1,3] -> [lo, hi]."""
    if isinstance(rng, (list, tuple)):
        return [int(rng[0]), int(rng[-1])]
    parts = str(rng).split("-")
    lo = int(parts[0])
    hi = int(parts[-1])
    return [lo, hi]


def _transform_sheet(sheet, char_type):
    """Convert an external Mythras-family character sheet (e.g. the
    stats/skills-as-list-of-dicts format) into our storage shape.
    Preserves source values verbatim where given; derives only what is absent."""
    chars = _flatten_kv_list(sheet["stats"])

    # Skills: flatten, then drop entries duplicated in combat_styles
    skills = _flatten_kv_list(sheet.get("skills"))
    styles = {}
    for cs in sheet.get("combat_styles") or []:
        styles[cs.get("name", "Combat Style")] = cs.get("value", 0)
    for style_name in styles:
        skills.pop(style_name, None)

    # Hit locations: honor the file's hp/ap exactly (different Mythras
    # flavors compute HP differently); add current_hp.
    locations = []
    for loc in sheet.get("hit_locations") or []:
        locations.append({
            "name": loc["name"].title(),
            "range": _parse_range(loc.get("range", "01-20")),
            "ap": loc.get("ap", 0),
            "hp": loc["hp"],
            "current_hp": loc.get("current_hp", loc["hp"]),
        })
    if not locations:
        locations = eng.build_hit_locations(chars, "humanoid")

    # Attributes: keep source values, fill gaps from the eng.
    derived = eng.derive_attributes(chars, "humanoid")
    src_attrs = dict(sheet.get("attributes") or {})
    strike_rank = src_attrs.pop("strike_rank", None)
    if strike_rank and "initiative_bonus" not in src_attrs:
        digits = "".join(ch for ch in str(strike_rank).split("(")[0] if ch.isdigit())
        if digits:
            src_attrs["initiative_bonus"] = int(digits)
    attrs = {**derived, **src_attrs}

    # Equipment: combat style weapons (strings or dicts) + explicit equipment
    equipment = []
    for cs in sheet.get("combat_styles") or []:
        for w in cs.get("weapons") or []:
            equipment.append(w if isinstance(w, dict) else {"name": w})
    for w in sheet.get("equipment") or []:
        equipment.append(w if isinstance(w, dict) else {"name": w})

    # Spells by tradition
    spells = {}
    for trad in ("folk", "theism", "sorcery", "mysticism", "windworking"):
        key = f"{trad}_spells"
        if sheet.get(key):
            spells[trad] = sheet[key]

    # Everything else rides along losslessly
    consumed = {"name", "stats", "skills", "combat_styles", "hit_locations",
                "attributes", "equipment", "notes", "passions",
                "folk_spells", "theism_spells", "sorcery_spells",
                "mysticism_spells", "windworking_spells"}
    extras = {k: v for k, v in sheet.items() if k not in consumed}
    if strike_rank:
        extras["strike_rank"] = strike_rank

    return {
        "name": sheet["name"],
        "type": char_type,
        "characteristics": chars,
        "attributes": attrs,
        "skills": skills,
        "combat_styles": styles,
        "hit_locations": locations,
        "equipment": equipment,
        "passions": _flatten_kv_list(sheet.get("passions")),
        "spells": spells,
        "extras": extras,
        "notes": sheet.get("notes", ""),
    }



def _to_roll20_sheet(c):
    """Convert a stored character back to the Roll20-upload JSON format
    (stats/skills as lists of single-key dicts, zero-padded range strings)."""
    chars = c.get("myth-characteristics-json") or {}
    skills = dict(c.get("myth-skills-json") or {})
    styles = c.get("myth-combat-styles-json") or {}
    extras = c.get("myth-extras-json") or {}
    spells = c.get("myth-spells-json") or {}
    attrs = c.get("myth-attributes-json") or {}
    equipment = c.get("myth-equipment-json") or []

    stat_order = ["STR", "CON", "SIZ", "DEX", "INT", "POW", "CHA"]
    stats_list = [{k: chars[k]} for k in stat_order if k in chars]

    # Roll20 format carries styles inside skills too
    merged_skills = dict(skills)
    merged_skills.update(styles)
    skills_list = [{k: v} for k, v in merged_skills.items()]

    hit_locations = []
    for loc in c.get("myth-hit-locations-json") or []:
        lo, hi = loc.get("range", [1, 20])
        hit_locations.append({
            "name": loc["name"],
            "range": f"{lo:02d}-{hi:02d}",
            "hp": loc["hp"],
            "ap": loc.get("ap", 0),
        })

    weapon_names = [w.get("name", "") for w in equipment if w.get("name")]
    combat_styles = [{"name": n, "value": v, "weapons": weapon_names}
                     for n, v in styles.items()] or                     [{"name": "Combat Style", "value": 0, "weapons": weapon_names}]

    ib = attrs.get("initiative_bonus", 0)
    strike_rank = extras.get("strike_rank", f"{ib}({ib}-0)")

    return {
        "name": c.get("name", ""),
        "cult_rank": extras.get("cult_rank", "None"),
        "stats": stats_list,
        "skills": skills_list,
        "folk_spells": spells.get("folk", []),
        "theism_spells": spells.get("theism", []),
        "sorcery_spells": spells.get("sorcery", []),
        "mysticism_spells": spells.get("mysticism", []),
        "hit_locations": hit_locations,
        "combat_styles": combat_styles,
        "attributes": {
            "action_points": attrs.get("action_points", 2),
            "damage_modifier": attrs.get("damage_modifier", "+0"),
            "magic_points": attrs.get("magic_points", 0),
            "strike_rank": strike_rank,
            "movement": attrs.get("movement", "6m (20')"),
        },
        "notes": c.get("description") or "",
        "features": extras.get("features", []),
        "cults": extras.get("cults", []),
        "spirits": extras.get("spirits", []),
        "natural_armor": extras.get("natural_armor", False),
    }


def cmd_export_characters(args):
    """Export characters to the Roll20-upload JSON format."""
    with get_driver() as driver:
        if args.id:
            ids = [args.id]
        elif args.campaign:
            rows = _fetch(driver, f'''
                match
                  $camp isa myth-campaign, has id "{escape_string(args.campaign)}";
                  (campaign: $camp, element: $c) isa myth-campaign-membership;
                  $c isa myth-character, has id $i, has myth-char-type $t;
                fetch {{ "id": $i, "type": $t }};''')
            ids = [r["id"] for r in rows if not args.type or r["type"] == args.type]
        else:
            fail("Provide --id or --campaign")
        sheets = [_to_roll20_sheet(_load_character(driver, cid)) for cid in ids]

    if args.output:
        with open(args.output, "w") as f:
            json.dump(sheets, f, indent=2)
        out({"success": True, "exported": [s["name"] for s in sheets],
             "file": args.output})
    else:
        print(json.dumps(sheets, indent=2))


def cmd_import_characters(args):
    """Import one or more characters from a Mythras-family JSON sheet file."""
    data = json.load(open(args.file))
    if isinstance(data, dict):
        data = [data]

    imported = []
    with get_driver() as driver:
        for sheet in data:
            t = _transform_sheet(sheet, args.type)
            cid = generate_id("myth-char")
            ts = get_timestamp()
            q = f'''insert $c isa myth-character,
                has id "{cid}",
                has name "{escape_string(t["name"])}",
                has myth-char-type "{escape_string(t["type"])}",
                has myth-status "active",
                has myth-characteristics-json "{escape_string(json.dumps(t["characteristics"]))}",
                has myth-attributes-json "{escape_string(json.dumps(t["attributes"]))}",
                has myth-skills-json "{escape_string(json.dumps(t["skills"]))}",
                has myth-hit-locations-json "{escape_string(json.dumps(t["hit_locations"]))}",
                has myth-equipment-json "{escape_string(json.dumps(t["equipment"]))}",
                has myth-passions-json "{escape_string(json.dumps(t["passions"]))}",
                has myth-combat-styles-json "{escape_string(json.dumps(t["combat_styles"]))}",
                has myth-spells-json "{escape_string(json.dumps(t["spells"]))}",
                has myth-extras-json "{escape_string(json.dumps(t["extras"]))}",
                has myth-fatigue "Fresh",
                has myth-luck-current {t["attributes"].get("luck_points", 2)},
                has myth-magic-current {t["attributes"].get("magic_points", 10)},
                has myth-experience-rolls 0,
                has created-at {ts}'''
            if t["notes"]:
                q += f', has description "{escape_string(t["notes"])}"'
            q += ";"
            _write(driver, q)
            if args.campaign:
                _link_to_campaign(driver, args.campaign, cid, "myth-character")
            imported.append({"id": cid, "name": t["name"]})
    out({"success": True, "imported": imported})


def cmd_list_characters(args):
    with get_driver() as driver:
        rows = _fetch(driver, f'''
            match
              $camp isa myth-campaign, has id "{escape_string(args.campaign)}";
              (campaign: $camp, element: $c) isa myth-campaign-membership;
              $c isa myth-character, has id $i, has name $n,
                 has myth-char-type $t, has myth-status $s;
            fetch {{ "id": $i, "name": $n, "type": $t, "status": $s }};''')
    chars = rows
    if args.type:
        chars = [r for r in rows if r["type"] == args.type]
    out({"success": True, "characters": chars})


def cmd_brief(args):
    """Everything needed to SPEAK as somebody, and nothing else.

    Read this before an NPC opens their mouth for the first time in a scene.
    ~200 tokens against the ~1.5k of a full sheet, because what you need in
    order to play a person is not their hit locations.

    If actor notes are absent it falls back to the older ad-hoc extras keys
    (`manner`, `tells`) so nothing written before the field existed is lost --
    and it says so, so the gap is visible and gets filled.
    """
    with get_driver() as driver:
        c = _get_entity(driver, "myth-character", args.id,
                        ["description", "myth-status", "myth-actor-notes",
                         "myth-extras-json"])
        if not c:
            fail(f"No myth-character with id '{args.id}'")

        notes = c.get("myth-actor-notes")
        source = "actor-notes"
        if not notes:
            extras = json.loads(c.get("myth-extras-json") or "{}")
            legacy = [extras[k] for k in ("manner", "tells") if extras.get(k)]
            if legacy:
                notes, source = " / ".join(legacy), "legacy extras"
            else:
                notes, source = None, None

        where = _fetch(driver, f"""
            match
              $c isa myth-character, has id "{escape_string(args.id)}";
              (located: $c, location: $l) isa myth-presence;
              $l has name $ln;
            fetch {{ "ln": $ln }};""")
        agendas = _fetch(driver, f"""
            match
              $c isa myth-character, has id "{escape_string(args.id)}";
              (agenda: $a, holder: $c) isa myth-agenda-holder;
              $a has name $an, has myth-agenda-status $as;
            fetch {{ "an": $an, "as": $as }};""")

    out({"success": True, "id": args.id, "name": c["name"],
         "status": c.get("myth-status"),
         "description": c.get("description"),
         "location": where[0]["ln"] if where else None,
         "actor_notes": notes,
         "notes_source": source,
         "agendas": [f"{r['an']} ({r['as']})" for r in agendas],
         "guidance": (None if notes else
                      "NO ACTOR NOTES. Give this character one line of business "
                      "and no dialogue, then write them with "
                      "`update-character --actor-notes` before they speak.")})


def cmd_update_character(args):
    # String-valued attributes.
    updates = {
        "myth-skills-json": args.skills, "myth-equipment-json": args.equipment,
        "myth-passions-json": args.passions, "myth-spells-json": args.spells,
        "myth-fatigue": args.fatigue, "myth-status": args.status,
        "myth-actor-notes": args.actor_notes,
        "description": args.description, "content": args.narrative,
    }
    # Integer-valued ones must be written unquoted. These are the values that
    # change most often in play -- magic points especially, which are spent on
    # every cast -- so leaving them unsettable made the sheet drift from the
    # fiction within one scene.
    numeric = {
        "myth-magic-current": args.magic_current,
        "myth-luck-current": args.luck,
        "myth-experience-rolls": args.experience_rolls,
    }
    with get_driver() as driver:
        for attr, val in updates.items():
            if val is not None:
                _set_attr(driver, "myth-character", args.id, attr, val)
        for attr, val in numeric.items():
            if val is not None:
                _set_attr(driver, "myth-character", args.id, attr, val, quote=False)
        # The extras bag was write-once-at-import, which is why portrayal notes
        # ended up smeared across description/narrative instead of living in it.
        if args.extras is not None:
            incoming = json.loads(args.extras)
            if args.extras_replace:
                merged = incoming
            else:
                cur = _get_entity(driver, "myth-character", args.id, ["myth-extras-json"]) or {}
                existing = json.loads(cur.get("myth-extras-json") or "{}")
                existing.update(incoming)
                merged = existing
            _set_attr(driver, "myth-character", args.id, "myth-extras-json",
                      json.dumps(merged))
    out({"success": True, "id": args.id})


def cmd_apply_damage(args):
    with get_driver() as driver:
        c = _load_character(driver, args.id)
        locations = c["myth-hit-locations-json"]
        report = eng.apply_damage(locations, args.location, args.damage,
                                  ignore_armor=args.ignore_armor)
        _set_attr(driver, "myth-character", args.id,
                  "myth-hit-locations-json", json.dumps(locations))
    out({"success": True, "id": args.id, **report})


def cmd_heal(args):
    with get_driver() as driver:
        c = _load_character(driver, args.id)
        locations = c["myth-hit-locations-json"]
        for loc in locations:
            if loc["name"].lower() == args.location.lower():
                loc["current_hp"] = min(loc["hp"], loc["current_hp"] + args.amount)
                _set_attr(driver, "myth-character", args.id,
                          "myth-hit-locations-json", json.dumps(locations))
                out({"success": True, "location": loc["name"],
                     "current_hp": loc["current_hp"], "max_hp": loc["hp"]})
                return
    fail(f"No hit location '{args.location}'")


# ---------------------------------------------------------------------------
# Dice & check commands
# ---------------------------------------------------------------------------

def cmd_roll(args):
    out({"success": True, **eng.roll_dice(args.dice)})


def _norm_skill(s):
    """Fold a skill name to comparable forms.

    Returns (core, full): the name with parentheticals dropped, and the name
    with the parentheses merely flattened. "Piety (Devotion)" gives
    ("piety", "piety devotion") so that both "Piety" and "Piety (Devotion)"
    find it. Combat styles here carry the whole weapon list in the name --
    "Druid (club, dagger, dart, ...)" -- and nobody at a table retypes that.
    """
    s = s or ""
    core = re.sub(r"\([^)]*\)", " ", s)
    core = re.sub(r"[^a-z0-9 ]+", " ", core.lower())
    full = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    return " ".join(core.split()), " ".join(full.split())


def _resolve_skill(char, skill_name):
    """Find the character's entry for a skill, style or passion.

    Matching, in order: exact, then normalised equality, then prefix in either
    direction, then substring. Ambiguity is reported with the candidates rather
    than guessed at -- silently rolling the wrong skill is worse than an error.
    """
    entries = []
    for pool in ("myth-skills-json", "myth-combat-styles-json", "myth-passions-json"):
        for k, v in (char.get(pool) or {}).items():
            entries.append((k, v))

    want = (skill_name or "").strip()
    for k, v in entries:
        if k.lower() == want.lower():
            return k, v

    qc, qf = _norm_skill(want)
    if qc or qf:
        qs = {x for x in (qc, qf) if x}

        def forms(k):
            c, f = _norm_skill(k)
            return {x for x in (c, f) if x}

        tests = (
            lambda ks: bool(ks & qs),
            # forward first: a longer key completing a shorter query. Reverse
            # only after, or a bare core like "love" swallows every passion
            # that starts with it.
            lambda ks: any(k.startswith(q) for k in ks for q in qs),
            lambda ks: any(q.startswith(k) for k in ks for q in qs),
            lambda ks: any(q in k or k in q for k in ks for q in qs),
        )
        for test in tests:
            hits = [(k, v) for k, v in entries if test(forms(k))]
            if len(hits) == 1:
                return hits[0]
            if len(hits) > 1:
                fail(f"'{skill_name}' is ambiguous on {char['name']}: "
                     + ", ".join(sorted(k for k, _ in hits)))

    fail(f"Character '{char['name']}' has no skill/style/passion '{skill_name}'. "
         "Has: " + ", ".join(sorted(k for k, _ in entries)))


def _skill_value(char, skill_name):
    """Look up a skill (or combat style, or passion) value on a character."""
    return _resolve_skill(char, skill_name)[1]


def cmd_roll_skill(args):
    with get_driver() as driver:
        c = _load_character(driver, args.id)
    name, skill = _resolve_skill(c, args.skill)
    if args.augment:
        _, passion = _resolve_skill(c, args.augment)
        skill += passion // 5  # +20% of passion value
    result = eng.skill_check(skill, args.difficulty)
    out({"success": True, "character": c["name"], "skill_name": name,
         "asked_for": args.skill if args.skill != name else None, **result})


def cmd_roll_opposed(args):
    with get_driver() as driver:
        a = _load_character(driver, args.id_a)
        b = _load_character(driver, args.id_b)
    res = eng.opposed_roll(_skill_value(a, args.skill_a), _skill_value(b, args.skill_b),
                           args.difficulty_a, args.difficulty_b)
    winner_name = {"a": a["name"], "b": b["name"], "none": None}[res["winner"]]
    out({"success": True, "a_name": a["name"], "b_name": b["name"],
         "winner": winner_name, **res})


# ---------------------------------------------------------------------------
# Combat commands
# ---------------------------------------------------------------------------

def cmd_start_encounter(args):
    eid = generate_id("myth-enc")
    ts = get_timestamp()
    q = f'''insert $e isa myth-encounter,
        has id "{eid}", has name "{escape_string(args.name)}",
        has myth-encounter-status "active", has myth-round 1,
        has myth-combatants-json "[]", has created-at {ts}'''
    if args.description:
        q += f', has description "{escape_string(args.description)}"'
    q += ";"
    with get_driver() as driver:
        _write(driver, q)
        _link_to_campaign(driver, args.campaign, eid, "myth-encounter")
    out({"success": True, "id": eid})


def _load_encounter(driver, enc_id):
    e = _get_entity(driver, "myth-encounter", enc_id,
                    ["description", "myth-encounter-status", "myth-round",
                     "myth-combatants-json"])
    if not e:
        fail(f"No encounter '{enc_id}'")
    e["combatants"] = json.loads(e["myth-combatants-json"] or "[]")
    e["round"] = e["myth-round"]
    return e


def _save_combatants(driver, enc_id, combatants):
    _set_attr(driver, "myth-encounter", enc_id, "myth-combatants-json",
              json.dumps(combatants))


def cmd_add_combatant(args):
    with get_driver() as driver:
        e = _load_encounter(driver, args.encounter)
        c = _load_character(driver, args.character)
        ap = c["myth-attributes-json"]["action_points"]
        e["combatants"].append({
            "id": c["id"], "name": c["name"], "initiative": None,
            "ap": ap, "max_ap": ap, "conditions": [],
        })
        _save_combatants(driver, args.encounter, e["combatants"])
        _write(driver, f'''
            match
              $e isa myth-encounter, has id "{escape_string(args.encounter)}";
              $c isa myth-character, has id "{escape_string(c["id"])}";
            insert (encounter: $e, combatant: $c) isa myth-participation;''')
    out({"success": True, "combatants": [x["name"] for x in e["combatants"]]})


def cmd_roll_initiative(args):
    import random as _r
    with get_driver() as driver:
        e = _load_encounter(driver, args.encounter)
        for cb in e["combatants"]:
            c = _load_character(driver, cb["id"])
            ib = c["myth-attributes-json"]["initiative_bonus"]
            # armor penalty: highest worn AP subtracts from initiative
            worn = max((loc.get("ap", 0) for loc in c["myth-hit-locations-json"]), default=0)
            cb["initiative"] = _r.randint(1, 10) + ib - worn
            cb["dex"] = c["myth-characteristics-json"]["DEX"]
        e["combatants"].sort(key=lambda x: (x["initiative"], x["dex"]), reverse=True)
        _save_combatants(driver, args.encounter, e["combatants"])
    out({"success": True, "order": [
        {"name": x["name"], "initiative": x["initiative"], "ap": x["ap"]}
        for x in e["combatants"]]})


def _find_weapon(char, name):
    for w in char.get("myth-equipment-json") or []:
        if w.get("name", "").lower() == (name or "").lower():
            return w
    return None


def _spend_ap(combatants, char_id, n=1):
    for cb in combatants:
        if cb["id"] == char_id:
            if cb["ap"] < n:
                return False
            cb["ap"] -= n
            return True
    return None  # not in encounter


def _attack_setup(driver, args):
    """Shared front half of an attack: skills, weapons, AP, the differential.

    Used by `attack-roll`. `resolve-attack` deliberately keeps its own copy --
    it is the path a live campaign is already using, and it is not worth the
    risk of a shared refactor to save twenty lines.
    """
    e = _load_encounter(driver, args.encounter)
    atk = _load_character(driver, args.attacker)
    dfn = _load_character(driver, args.defender)

    styles = atk.get("myth-combat-styles-json") or {}
    if args.style:
        style_val = _skill_value(atk, args.style)
    elif styles:
        style_val = max(styles.values())
    else:
        style_val = _skill_value(atk, "Unarmed")
    weapon = _find_weapon(atk, args.weapon) if args.weapon else None
    if weapon is None:
        equipment = atk.get("myth-equipment-json") or []
        weapon = equipment[0] if equipment else {"name": "Unarmed", "damage": "1d3", "size": "S"}

    defense = args.defense
    if defense == "parry":
        d_styles = dfn.get("myth-combat-styles-json") or {}
        d_val = _skill_value(dfn, args.defender_skill) if args.defender_skill else (
            max(d_styles.values()) if d_styles else _skill_value(dfn, "Unarmed"))
    elif defense == "evade":
        d_val = _skill_value(dfn, args.defender_skill or "Evade")
    else:
        d_val = 0

    if not args.no_ap:
        if _spend_ap(e["combatants"], atk["id"]) is False:
            fail(f"{atk['name']} has no Action Points left this round")
        if defense != "none" and _spend_ap(e["combatants"], dfn["id"]) is False:
            defense = "none"

    diff = eng.differential_roll(style_val, d_val,
                                 args.attacker_difficulty, args.defender_difficulty,
                                 b_auto_fail=(defense == "none"))
    return e, atk, dfn, weapon, defense, diff


def _die_faces(expr):
    """Largest die size in a damage expression -- '1d8+1' -> 8."""
    sizes = [int(m) for m in re.findall(r"d(\d+)", expr or "")]
    return max(sizes) if sizes else 3


def _dice_bonus(expr):
    """Flat modifier in a damage expression -- '1d8+1' -> 1."""
    stripped = re.sub(r"\d*d\d+", "", (expr or "").replace(" ", ""))
    return sum(int(m.group(1)) for m in re.finditer(r"([+-]\d+)", stripped))


def cmd_attack_roll(args):
    """Roll the exchange and STOP, so the winner can choose their effects.

    The rules require special effects to be chosen BEFORE the damage roll.
    `resolve-attack` rolls damage and writes hit locations in the same call
    that reports how many effects were earned, which makes Maximize Damage,
    Bypass Armour, Impale and Enhance Parry impossible to apply afterwards.

    So this half rolls no damage and touches no hit locations. It freezes the
    dice onto the encounter -- frozen, because a menu you can re-roll is not a
    choice -- and hands back what the winner may pick from.
    """
    with get_driver() as driver:
        e, atk, dfn, weapon, defense, diff = _attack_setup(driver, args)

        winner = diff["beneficiary"]
        count = diff["special_effects"]
        side = "offense" if winner == "a" else ("defense" if winner == "b" else None)
        w_char = atk if winner == "a" else dfn
        w_weapon = weapon if winner == "a" else (
            _find_weapon(dfn, args.parry_weapon) if args.parry_weapon else None)
        w_level = diff["a"]["level"] if winner == "a" else diff["b"]["level"]
        l_level = diff["b"]["level"] if winner == "a" else diff["a"]["level"]

        options = []
        if side and count:
            options = fx.available(side, w_level, l_level, w_weapon, prone=args.prone)

        pending = {
            "attacker": atk["id"], "defender": dfn["id"],
            "weapon": weapon, "defense": defense,
            "parry_weapon": args.parry_weapon,
            "diff": diff, "side": side, "count": count,
            "winner_id": w_char["id"] if side else None,
            "winner_level": w_level, "loser_level": l_level,
            "prone": bool(args.prone),
        }
        _set_attr(driver, "myth-encounter", args.encounter,
                  "myth-pending-attack-json", json.dumps(pending))
        if not args.no_ap:
            _save_combatants(driver, args.encounter, e["combatants"])

        out({"success": True, "attacker": atk["name"], "defender": dfn["name"],
             "weapon": weapon["name"], "attack_roll": diff["a"],
             "defense": defense, "defense_roll": diff["b"],
             "special_effects": count,
             "effects_to": (w_char["name"] if side else None),
             "available_effects": options,
             "ap_remaining": {cb["name"]: cb["ap"] for cb in e["combatants"]},
             "next": "resolve-effects --encounter " + args.encounter +
                     (" [--effect <id> ...]" if count else "")})


def cmd_resolve_effects(args):
    """Apply the chosen effects, then roll damage and settle the wound."""
    with get_driver() as driver:
        enc = _get_entity(driver, "myth-encounter", args.encounter,
                          ["myth-pending-attack-json"])
        if not enc:
            fail(f"No encounter '{args.encounter}'")
        raw = enc.get("myth-pending-attack-json")
        if not raw:
            fail("No attack is waiting on this encounter -- run attack-roll first")
        p = json.loads(raw)

        chosen = [c for c in (args.effect or []) if c != "none"]
        if chosen and not p["side"]:
            fail("nobody won the differential; there are no effects to take")
        if chosen:
            err = fx.validate(chosen, p["side"], p["winner_level"], p["loser_level"],
                              p["count"],
                              p["weapon"] if p["side"] == "offense" else None,
                              prone=p["prone"])
            if err:
                fail(err)

        atk = _load_character(driver, p["attacker"])
        dfn = _load_character(driver, p["defender"])
        diff, weapon, defense = p["diff"], p["weapon"], p["defense"]
        taken = set(chosen)
        by_attacker = p["side"] == "offense"

        result = {"success": True, "attacker": atk["name"], "defender": dfn["name"],
                  "effects_applied": chosen}

        attacker_hit = diff["a"]["level"] in ("success", "critical")
        defender_parried = defense == "parry" and diff["b"]["level"] in ("success", "critical")
        defender_evaded = defense == "evade" and \
            eng.SUCCESS_LEVELS[diff["b"]["level"]] >= eng.SUCCESS_LEVELS[diff["a"]["level"]] and \
            diff["b"]["level"] in ("success", "critical")

        # A defender's pre-damage effects can stop the blow outright.
        if not by_attacker and "force-failure" in taken:
            attacker_hit = False
            result["note"] = "attack forced to a failure"
        if by_attacker and "circumvent-parry" in taken:
            defender_parried = False

        if attacker_hit and not defender_evaded:
            dmg_expr = weapon.get("damage", "1d3")
            dmg_roll = eng.roll_dice(dmg_expr)
            # Impale rolls the weapon twice and keeps the better.
            if by_attacker and "impale" in taken:
                second = eng.roll_dice(dmg_expr)
                result["impale_rolls"] = [dmg_roll, second]
                dmg_roll = max(dmg_roll, second, key=lambda r: r["total"])
            # Maximize Damage sets one die to its face value, once per stack.
            n_max = chosen.count("maximize-damage") if by_attacker else 0
            if n_max and dmg_roll.get("rolls"):
                faces = _die_faces(dmg_expr)
                rolls = sorted(dmg_roll["rolls"])
                for i in range(min(n_max, len(rolls))):
                    rolls[i] = faces
                dmg_roll = {"expr": dmg_roll["expr"], "rolls": rolls,
                            "total": sum(rolls) + _dice_bonus(dmg_expr)}

            dm = atk["myth-attributes-json"]["damage_modifier"]
            dm_roll = eng.roll_dice(dm) if dm not in ("+0", "0") else {"total": 0}
            damage = max(0, dmg_roll["total"] + dm_roll["total"])

            if defender_parried:
                if not by_attacker and "enhance-parry" in taken:
                    damage = 0
                    result["note"] = "parry enhanced -- all of it taken on the block"
                else:
                    pw = _find_weapon(dfn, p.get("parry_weapon")) if p.get("parry_weapon") else None
                    if pw is None:
                        d_equipment = dfn.get("myth-equipment-json") or []
                        pw = d_equipment[0] if d_equipment else {"size": "S"}
                    damage = eng.parry_reduction(damage, weapon.get("size", "M"),
                                                 pw.get("size", "S"))
                    result["parried_with"] = pw.get("name", "Unarmed")

            if by_attacker and "choose-location" in taken:
                if not args.location:
                    fail("choose-location taken but no --location given")
                hit_loc = {"roll": None, "location": args.location}
            else:
                hit_loc = eng.roll_hit_location(dfn["myth-hit-locations-json"])

            result["damage_roll"] = dmg_roll
            result["damage_modifier_roll"] = dm_roll
            result["hit_location"] = hit_loc
            if damage > 0:
                locations = dfn["myth-hit-locations-json"]
                wound = eng.apply_damage(
                    locations, hit_loc["location"], damage,
                    ignore_armor=(by_attacker and "bypass-armor" in taken))
                _set_attr(driver, "myth-character", dfn["id"],
                          "myth-hit-locations-json", json.dumps(locations))
                result["wound"] = wound
            else:
                result["wound"] = {"net_damage": 0, "wound": "none",
                                   "note": result.get("note", "damage fully absorbed")}
        elif defender_evaded:
            result["wound"] = {"net_damage": 0, "wound": "none",
                               "note": "evaded (defender prone)"}
        else:
            result["wound"] = {"net_damage": 0, "wound": "none",
                               "note": result.get("note", "attack missed")}

        # Contested effects are never resolved silently -- the loser's choice of
        # resisting skill is a player decision like any other.
        followups = []
        for c in chosen:
            e_def = fx.BY_ID[c]
            if e_def["phase"] == "followup":
                loser_id = p["defender"] if by_attacker else p["attacker"]
                contest = e_def.get("contest") or "<skill>"
                # Which skill the loser resists with is THEIR call when the
                # loser is a PC -- ask, the same way defence is always asked.
                resist = ("<" + contest.replace(" or ", "|") + ">"
                          if " or " in contest else contest)
                followups.append({
                    "effect": c, "name": e_def["name"], "contest": contest,
                    "defender_chooses": " or " in contest,
                    "command": ("roll-opposed --id-a " + p["winner_id"] +
                                " --skill-a <skill> --id-b " + loser_id +
                                " --skill-b " + resist)})
        if followups:
            result["followups"] = followups

        _clear_pending_attack(driver, args.encounter)
    out(result)


def _clear_pending_attack(driver, encounter_id):
    eid = escape_string(encounter_id)
    rows = _fetch(driver, "match $e isa myth-encounter, has id " + '"' + eid + '"' +
                  ", has myth-pending-attack-json $v; fetch { \"v\": $v };")
    if rows:
        _write(driver, "match $e isa myth-encounter, has id " + '"' + eid + '"' +
               ", has myth-pending-attack-json $v; delete has $v of $e;")


def cmd_resolve_attack(args):
    with get_driver() as driver:
        e = _load_encounter(driver, args.encounter)
        atk = _load_character(driver, args.attacker)
        dfn = _load_character(driver, args.defender)

        # --- attacker skill & weapon
        styles = atk.get("myth-combat-styles-json") or {}
        if args.style:
            style_val = _skill_value(atk, args.style)
        elif styles:
            style_val = max(styles.values())
        else:
            style_val = _skill_value(atk, "Unarmed")
        weapon = _find_weapon(atk, args.weapon) if args.weapon else None
        if weapon is None:
            equipment = atk.get("myth-equipment-json") or []
            weapon = equipment[0] if equipment else {"name": "Unarmed", "damage": "1d3", "size": "S"}

        # --- defender skill
        defense = args.defense
        if defense == "parry":
            d_styles = dfn.get("myth-combat-styles-json") or {}
            d_val = _skill_value(dfn, args.defender_skill) if args.defender_skill else (
                max(d_styles.values()) if d_styles else _skill_value(dfn, "Unarmed"))
        elif defense == "evade":
            d_val = _skill_value(dfn, args.defender_skill or "Evade")
        else:
            d_val = 0

        # --- AP bookkeeping
        if not args.no_ap:
            if _spend_ap(e["combatants"], atk["id"]) is False:
                fail(f"{atk['name']} has no Action Points left this round")
            if defense != "none" and _spend_ap(e["combatants"], dfn["id"]) is False:
                defense = "none"  # cannot afford to defend

        # --- differential roll
        diff = eng.differential_roll(style_val, d_val,
                                     args.attacker_difficulty, args.defender_difficulty,
                                     b_auto_fail=(defense == "none"))
        result = {"success": True, "attacker": atk["name"], "defender": dfn["name"],
                  "weapon": weapon["name"], "attack_roll": diff["a"],
                  "defense": defense, "defense_roll": diff["b"],
                  "special_effects": diff["special_effects"],
                  "effects_to": {"a": atk["name"], "b": dfn["name"], None: None}[diff["beneficiary"]]}

        # --- damage
        attacker_hit = diff["a"]["level"] in ("success", "critical")
        defender_parried = defense == "parry" and diff["b"]["level"] in ("success", "critical")
        defender_evaded = defense == "evade" and \
            eng.SUCCESS_LEVELS[diff["b"]["level"]] >= eng.SUCCESS_LEVELS[diff["a"]["level"]] and \
            diff["b"]["level"] in ("success", "critical")

        if attacker_hit and not defender_evaded:
            dmg_roll = eng.roll_dice(weapon.get("damage", "1d3"))
            dm = atk["myth-attributes-json"]["damage_modifier"]
            dm_roll = eng.roll_dice(dm) if dm not in ("+0", "0") else {"total": 0}
            damage = max(0, dmg_roll["total"] + dm_roll["total"])
            if defender_parried:
                pw = _find_weapon(dfn, args.parry_weapon) if args.parry_weapon else None
                if pw is None:
                    d_equipment = dfn.get("myth-equipment-json") or []
                    pw = d_equipment[0] if d_equipment else {"size": "S"}
                damage = eng.parry_reduction(damage, weapon.get("size", "M"),
                                             pw.get("size", "S"))
                result["parried_with"] = pw.get("name", "Unarmed")
            if args.location:
                hit_loc = {"roll": None, "location": args.location}
            else:
                hit_loc = eng.roll_hit_location(dfn["myth-hit-locations-json"])
            result["damage_roll"] = dmg_roll
            result["damage_modifier_roll"] = dm_roll
            result["hit_location"] = hit_loc
            if damage > 0:
                locations = dfn["myth-hit-locations-json"]
                wound = eng.apply_damage(locations, hit_loc["location"], damage)
                _set_attr(driver, "myth-character", dfn["id"],
                          "myth-hit-locations-json", json.dumps(locations))
                result["wound"] = wound
            else:
                result["wound"] = {"net_damage": 0, "wound": "none",
                                   "note": "damage fully absorbed"}
        elif defender_evaded:
            result["wound"] = {"net_damage": 0, "wound": "none", "note": "evaded (defender prone)"}
        else:
            result["wound"] = {"net_damage": 0, "wound": "none", "note": "attack missed"}

        if not args.no_ap:
            _save_combatants(driver, args.encounter, e["combatants"])
        result["ap_remaining"] = {cb["name"]: cb["ap"] for cb in e["combatants"]}
    out(result)


def cmd_next_round(args):
    with get_driver() as driver:
        e = _load_encounter(driver, args.encounter)
        for cb in e["combatants"]:
            cb["ap"] = cb["max_ap"]
        new_round = (e["round"] or 1) + 1
        _save_combatants(driver, args.encounter, e["combatants"])
        _set_attr(driver, "myth-encounter", args.encounter, "myth-round",
                  new_round, quote=False)
    out({"success": True, "round": new_round,
         "order": [{"name": x["name"], "initiative": x["initiative"], "ap": x["ap"]}
                   for x in e["combatants"]]})


def cmd_get_encounter(args):
    with get_driver() as driver:
        e = _load_encounter(driver, args.encounter)
        # enrich with live HP per combatant
        for cb in e["combatants"]:
            c = _load_character(driver, cb["id"])
            cb["hit_locations"] = [
                {"name": l["name"], "hp": f'{l["current_hp"]}/{l["hp"]}', "ap": l["ap"]}
                for l in c["myth-hit-locations-json"]]
            cb["fatigue"] = c["myth-fatigue"]
    out({"success": True, "encounter": {
        "id": e["id"], "name": e["name"], "status": e["myth-encounter-status"],
        "round": e["round"], "combatants": e["combatants"]}})


def cmd_end_encounter(args):
    with get_driver() as driver:
        _set_attr(driver, "myth-encounter", args.encounter,
                  "myth-encounter-status", "resolved")
        if args.summary:
            _set_attr(driver, "myth-encounter", args.encounter, "content", args.summary)
    out({"success": True, "id": args.encounter, "status": "resolved"})


# ---------------------------------------------------------------------------
# World commands
# ---------------------------------------------------------------------------

def _create_world_entity(args, entity_type, prefix, extra_attrs=""):
    eid = generate_id(prefix)
    ts = get_timestamp()
    q = f'''insert $e isa {entity_type},
        has id "{eid}", has name "{escape_string(args.name)}",
        has created-at {ts}{extra_attrs}'''
    if getattr(args, "description", None):
        q += f', has description "{escape_string(args.description)}"'
    if getattr(args, "narrative", None):
        q += f', has content "{escape_string(args.narrative)}"'
    q += ";"
    with get_driver() as driver:
        _write(driver, q)
        if args.campaign:
            _link_to_campaign(driver, args.campaign, eid, entity_type)
    return eid


def cmd_add_location(args):
    extra = f', has myth-location-type "{escape_string(args.type)}"' if args.type else ""
    eid = _create_world_entity(args, "myth-location", "myth-loc", extra)
    out({"success": True, "id": eid})


def cmd_add_faction(args):
    eid = _create_world_entity(args, "myth-faction", "myth-faction")
    out({"success": True, "id": eid})


def cmd_update_location(args):
    with get_driver() as driver:
        if not _get_entity(driver, "myth-location", args.id, []):
            fail(f"No location '{args.id}'")
        if args.name is not None:
            _set_attr(driver, "myth-location", args.id, "name", args.name)
        if args.summary is not None:
            _set_attr(driver, "myth-location", args.id, "description", args.summary)
        if args.narrative is not None:
            _set_attr(driver, "myth-location", args.id, "content", args.narrative)
        if args.type is not None:
            _set_attr(driver, "myth-location", args.id, "myth-location-type", args.type)
    out({"success": True, "id": args.id})


def cmd_update_faction(args):
    with get_driver() as driver:
        if not _get_entity(driver, "myth-faction", args.id, []):
            fail(f"No faction '{args.id}'")
        if args.name is not None:
            _set_attr(driver, "myth-faction", args.id, "name", args.name)
        if args.summary is not None:
            _set_attr(driver, "myth-faction", args.id, "description", args.summary)
        if args.narrative is not None:
            _set_attr(driver, "myth-faction", args.id, "content", args.narrative)
    out({"success": True, "id": args.id})


def cmd_add_template(args):
    chars = json.loads(args.stats)
    species = args.species
    attrs = eng.derive_attributes(chars, species)
    skills = eng.base_skills(chars, species)
    if args.skills:
        skills.update(json.loads(args.skills))
    armor = json.loads(args.armor) if args.armor else {}
    locations = eng.build_hit_locations(chars, species, armor)
    tid = generate_id("myth-tmpl")
    ts = get_timestamp()
    q = f'''insert $t isa myth-creature-template,
        has id "{tid}", has name "{escape_string(args.name)}",
        has myth-characteristics-json "{escape_string(json.dumps(chars))}",
        has myth-attributes-json "{escape_string(json.dumps(attrs))}",
        has myth-skills-json "{escape_string(json.dumps(skills))}",
        has myth-hit-locations-json "{escape_string(json.dumps(locations))}",
        has myth-equipment-json "{escape_string(args.equipment or "[]")}",
        has myth-combat-styles-json "{escape_string(args.combat_styles or "{}")}",
        has created-at {ts}'''
    if args.description:
        q += f', has description "{escape_string(args.description)}"'
    if args.narrative:
        q += f', has content "{escape_string(args.narrative)}"'
    q += ";"
    with get_driver() as driver:
        _write(driver, q)
        if args.campaign:
            _link_to_campaign(driver, args.campaign, tid, "myth-creature-template")
    out({"success": True, "id": tid})


def cmd_spawn(args):
    """Instantiate a creature template as a live NPC character."""
    with get_driver() as driver:
        t = _get_entity(driver, "myth-creature-template", args.template,
                        ["description", "myth-characteristics-json", "myth-attributes-json",
                         "myth-skills-json", "myth-hit-locations-json",
                         "myth-equipment-json", "myth-combat-styles-json"])
        if not t:
            fail(f"No template '{args.template}'")
        cid = generate_id("myth-char")
        ts = get_timestamp()
        attrs = json.loads(t["myth-attributes-json"])
        q = f'''insert $c isa myth-character,
            has id "{cid}", has name "{escape_string(args.name)}",
            has myth-char-type "npc", has myth-status "active",
            has myth-characteristics-json "{escape_string(t["myth-characteristics-json"])}",
            has myth-attributes-json "{escape_string(t["myth-attributes-json"])}",
            has myth-skills-json "{escape_string(t["myth-skills-json"])}",
            has myth-hit-locations-json "{escape_string(t["myth-hit-locations-json"])}",
            has myth-equipment-json "{escape_string(t["myth-equipment-json"] or "[]")}",
            has myth-passions-json "{{}}",
            has myth-combat-styles-json "{escape_string(t["myth-combat-styles-json"] or "{}")}",
            has myth-fatigue "Fresh",
            has myth-luck-current {attrs.get("luck_points", 2)},
            has myth-magic-current {attrs.get("magic_points", 10)},
            has myth-experience-rolls 0,
            has created-at {ts}'''
        if t.get("description"):
            q += f', has description "{escape_string(t["description"])}"'
        q += ";"
        _write(driver, q)
        _write(driver, f'''
            match
              $t isa myth-creature-template, has id "{escape_string(args.template)}";
              $c isa myth-character, has id "{cid}";
            insert (template: $t, instance: $c) isa myth-template-instance;''')
        if args.campaign:
            _link_to_campaign(driver, args.campaign, cid, "myth-character")
    out({"success": True, "id": cid, "from_template": t["name"]})


def cmd_move_character(args):
    with get_driver() as driver:
        # remove any existing presence
        existing = _fetch(driver, f'''
            match
              $c isa myth-character, has id "{escape_string(args.id)}";
              $r isa myth-presence, links (located: $c);
            fetch {{ "x": $c.id }};''')
        if existing:
            _write(driver, f'''
                match
                  $c isa myth-character, has id "{escape_string(args.id)}";
                  $r isa myth-presence, links (located: $c);
                delete $r;''')
        _write(driver, f'''
            match
              $c isa myth-character, has id "{escape_string(args.id)}";
              $l isa myth-location, has id "{escape_string(args.location)}";
            insert (located: $c, location: $l) isa myth-presence;''')
    out({"success": True})


def cmd_join_faction(args):
    with get_driver() as driver:
        _write(driver, f'''
            match
              $c isa myth-character, has id "{escape_string(args.id)}";
              $f isa myth-faction, has id "{escape_string(args.faction)}";
            insert (faction: $f, member: $c) isa myth-faction-membership;''')
    out({"success": True})


# ---------------------------------------------------------------------------
# Journal commands
# ---------------------------------------------------------------------------

def cmd_log_event(args):
    eid = generate_id("myth-event")
    ts = getattr(args, "at", None) or get_timestamp()
    q = f'''insert $e isa myth-game-event,
        has id "{eid}", has name "{escape_string(getattr(args, 'title', None) or args.summary[:80])}",
        has description "{escape_string(args.summary)}",
        has myth-event-type "{escape_string(args.type)}",
        has created-at {ts}'''
    if args.narrative:
        q += f', has content "{escape_string(args.narrative)}"'
    if args.session is not None:
        q += f', has myth-session-number {args.session}'
    q += ";"
    with get_driver() as driver:
        _write(driver, q)
        _link_to_campaign(driver, args.campaign, eid, "myth-game-event")
        participant_types = ["myth-character", "myth-location", "myth-faction",
                             "myth-encounter"]
        for pid in (args.involves or "").split(","):
            pid = pid.strip()
            if not pid:
                continue
            for ptype in participant_types:
                if _fetch(driver, f'''
                        match $p isa {ptype}, has id "{escape_string(pid)}";
                        fetch {{ "id": $p.id }};'''):
                    _write(driver, f'''
                        match
                          $e isa myth-game-event, has id "{eid}";
                          $p isa {ptype}, has id "{escape_string(pid)}";
                        insert (event: $e, participant: $p) isa myth-event-involvement;''')
                    break
    out({"success": True, "id": eid})


def cmd_get_log(args):
    """The journal.

    --full adds the event name and the narrative. The narrative is the field
    log-event writes with --narrative, and until now nothing selected it, so
    verbatim dialogue written into the journal was unreachable through the CLI
    -- which rather defeated the point of writing it down.
    """
    with get_driver() as driver:
        rows = _fetch(driver, f'''
            match
              $camp isa myth-campaign, has id "{escape_string(args.campaign)}";
              (campaign: $camp, element: $e) isa myth-campaign-membership;
              $e isa myth-game-event, has id $i, has description $d,
                 has myth-event-type $t, has created-at $ts;
            fetch {{ "id": $i, "summary": $d, "type": $t, "at": $ts }};''')
        events = sorted(rows, key=lambda r: str(r["at"]))
        if args.type:
            events = [e for e in events if e["type"] == args.type]
        limit = getattr(args, "limit", None)
        if limit and limit > 0:
            events = events[-limit:]
        want_session = getattr(args, "session", None)
        if want_session is not None or getattr(args, "full", False):
            # content and session are optional, so they are fetched per event
            # rather than matched -- a missing optional attribute in the match
            # would drop the whole row.
            for e in events:
                extra = _get_entity(driver, "myth-game-event", e["id"],
                                    ["content", "myth-session-number"])
                if extra:
                    e["title"] = extra.get("name")
                    e["narrative"] = extra.get("content")
                    e["session"] = extra.get("myth-session-number")
        if want_session is not None:
            # --session was declared from the start and never read. It filters.
            events = [e for e in events if e.get("session") == want_session]
            if not getattr(args, "full", False):
                for e in events:
                    e.pop("title", None)
                    e.pop("narrative", None)
    out({"success": True, "events": events})


# ---------------------------------------------------------------------------
# Lore commands (generic worldbuilding)
# ---------------------------------------------------------------------------

LORE_SUBJECT_TYPES = ["myth-character", "myth-location", "myth-faction",
                      "myth-creature-template", "myth-lore"]


def _link_lore_about(driver, lore_id, subject_id):
    """Link a lore entry to any subject entity, resolving its concrete type."""
    for stype in LORE_SUBJECT_TYPES:
        if _fetch(driver, f'''
                match $s isa {stype}, has id "{escape_string(subject_id)}";
                fetch {{ "id": $s.id }};'''):
            _write(driver, f'''
                match
                  $l isa myth-lore, has id "{escape_string(lore_id)}";
                  $s isa {stype}, has id "{escape_string(subject_id)}";
                insert (lore: $l, subject: $s) isa myth-lore-about;''')
            return stype
    return None


def cmd_add_lore(args):
    lid = generate_id("myth-lore")
    ts = get_timestamp()
    q = f'''insert $l isa myth-lore,
        has id "{lid}",
        has name "{escape_string(args.title)}",
        has myth-lore-category "{escape_string(args.category)}",
        has myth-lore-visibility "{escape_string(args.visibility)}",
        has created-at {ts}'''
    if args.summary:
        q += f', has description "{escape_string(args.summary)}"'
    if args.narrative:
        q += f', has content "{escape_string(args.narrative)}"'
    q += ";"
    with get_driver() as driver:
        _write(driver, q)
        _link_to_campaign(driver, args.campaign, lid, "myth-lore")
        linked = []
        for sid in (args.about or "").split(","):
            sid = sid.strip()
            if sid:
                stype = _link_lore_about(driver, lid, sid)
                linked.append({"id": sid, "type": stype})
    out({"success": True, "id": lid, "linked_subjects": linked})


def cmd_list_lore(args):
    with get_driver() as driver:
        rows = _fetch(driver, f'''
            match
              $camp isa myth-campaign, has id "{escape_string(args.campaign)}";
              (campaign: $camp, element: $l) isa myth-campaign-membership;
              $l isa myth-lore, has id $i, has name $n,
                 has myth-lore-category $c, has myth-lore-visibility $v;
            fetch {{ "id": $i, "title": $n, "category": $c, "visibility": $v }};''')
    if args.category:
        rows = [r for r in rows if r["category"] == args.category]
    if args.visibility:
        rows = [r for r in rows if r["visibility"] == args.visibility]
    out({"success": True, "lore": sorted(rows, key=lambda r: (r["category"], r["title"]))})


def cmd_get_lore(args):
    with get_driver() as driver:
        l = _get_entity(driver, "myth-lore", args.id,
                        ["description", "content", "myth-lore-category",
                         "myth-lore-visibility"])
        if not l:
            fail(f"No lore entry '{args.id}'")
        subjects = _fetch(driver, f'''
            match
              $l isa myth-lore, has id "{escape_string(args.id)}";
              (lore: $l, subject: $s) isa myth-lore-about;
              $s has id $si, has name $sn;
            fetch {{ "id": $si, "name": $sn }};''')
    l["about"] = subjects
    out({"success": True, "lore": l})


def cmd_link_lore(args):
    with get_driver() as driver:
        stype = _link_lore_about(driver, args.id, args.subject)
    if not stype:
        fail(f"No linkable entity with id '{args.subject}'")
    out({"success": True, "lore": args.id, "subject": args.subject,
         "subject_type": stype})


def cmd_update_lore(args):
    with get_driver() as driver:
        if not _get_entity(driver, "myth-lore", args.id, []):
            fail(f"No lore entry '{args.id}'")
        if args.narrative is not None:
            _set_attr(driver, "myth-lore", args.id, "content", args.narrative)
        if args.summary is not None:
            _set_attr(driver, "myth-lore", args.id, "description", args.summary)
        if args.visibility is not None:
            _set_attr(driver, "myth-lore", args.id, "myth-lore-visibility", args.visibility)
    out({"success": True, "id": args.id})


# ---------------------------------------------------------------------------
# Living world: agendas, clocks, beats
#
# What the world is doing while the PCs are elsewhere. An agenda is a goal held
# by a character or faction, tracked on a progress clock; a beat is the next
# concrete thing that agenda produces if nobody interferes. `tick` advances
# world time and reports what has come due, staged against where the PCs
# actually are -- so the same beat plays as a scene or resolves off-camera
# depending only on where the party went.
# ---------------------------------------------------------------------------

AGENDA_ATTRS = ["description", "content", "myth-agenda-status",
                "myth-agenda-clock-size", "myth-agenda-clock-filled",
                "myth-agenda-priority"]
BEAT_ATTRS = ["description", "content", "myth-beat-status", "myth-beat-when",
              "myth-beat-trigger", "myth-beat-onscreen-if", "myth-time-index"]

# Anything that can hold or be targeted by an agenda, or be cast in a beat.
AGENDA_HOLDER_TYPES = ["myth-character", "myth-faction"]
AGENDA_TARGET_TYPES = ["myth-character", "myth-faction", "myth-location"]


def _link_relation(driver, rel, role_a, type_a, id_a, role_b, candidate_types, id_b):
    """Insert a binary relation, resolving the second player's concrete type."""
    for tb in candidate_types:
        if _fetch(driver, f'''
                match $b isa {tb}, has id "{escape_string(id_b)}";
                fetch {{ "id": $b.id }};'''):
            _write(driver, f'''
                match
                  $a isa {type_a}, has id "{escape_string(id_a)}";
                  $b isa {tb}, has id "{escape_string(id_b)}";
                insert ({role_a}: $a, {role_b}: $b) isa {rel};''')
            return tb
    return None


def _agenda_record(driver, aid, holder=True):
    """One agenda as a flat dict: clock, status, priority, and its holder."""
    a = _get_entity(driver, "myth-agenda", aid, AGENDA_ATTRS)
    if not a:
        return None
    rec = {
        "id": a["id"], "title": a["name"], "goal": a.get("description"),
        "status": a.get("myth-agenda-status") or "active",
        "clock": {"filled": a.get("myth-agenda-clock-filled") or 0,
                  "size": a.get("myth-agenda-clock-size") or 0},
        "priority": a.get("myth-agenda-priority") or 3,
        "narrative": a.get("content"),
    }
    if holder:
        rows = _fetch(driver, f'''
            match
              $a isa myth-agenda, has id "{escape_string(aid)}";
              (agenda: $a, holder: $h) isa myth-agenda-holder;
              $h has id $hi, has name $hn;
            fetch {{ "id": $hi, "name": $hn }};''')
        rec["holder"] = rows[0] if rows else None
        targets = _fetch(driver, f'''
            match
              $a isa myth-agenda, has id "{escape_string(aid)}";
              (agenda: $a, target: $t) isa myth-agenda-target;
              $t has id $ti, has name $tn;
            fetch {{ "id": $ti, "name": $tn }};''')
        rec["targets"] = targets
    return rec


def _beat_record(driver, bid):
    """One beat as a flat dict, with its agenda, place and cast resolved."""
    b = _get_entity(driver, "myth-beat", bid, BEAT_ATTRS)
    if not b:
        return None
    agenda = _fetch(driver, f'''
        match
          $b isa myth-beat, has id "{escape_string(bid)}";
          (beat: $b, agenda: $a) isa myth-beat-of;
          $a has id $ai, has name $an, has myth-agenda-priority $ap,
             has myth-agenda-clock-filled $af;
        fetch {{ "id": $ai, "name": $an, "priority": $ap, "filled": $af }};''')
    place = _fetch(driver, f'''
        match
          $b isa myth-beat, has id "{escape_string(bid)}";
          (beat: $b, place: $p) isa myth-beat-at;
          $p has id $pi, has name $pn;
        fetch {{ "id": $pi, "name": $pn }};''')
    cast = _fetch(driver, f'''
        match
          $b isa myth-beat, has id "{escape_string(bid)}";
          (beat: $b, member: $m) isa myth-beat-cast;
          $m has id $mi, has name $mn;
        fetch {{ "id": $mi, "name": $mn }};''')
    ag = agenda[0] if agenda else None
    return {
        "id": b["id"], "title": b["name"], "summary": b.get("description"),
        "status": b.get("myth-beat-status") or "pending",
        "when": b.get("myth-beat-when"),
        "time_index": b.get("myth-time-index"),
        "trigger": b.get("myth-beat-trigger") or "time",
        "onscreen_if": b.get("myth-beat-onscreen-if"),
        "narrative": b.get("content"),
        "agenda": ag["id"] if ag else None,
        "agenda_title": ag["name"] if ag else None,
        "priority": ag["priority"] if ag else 3,
        "place": place[0]["id"] if place else None,
        "place_name": place[0]["name"] if place else None,
        "cast": [c["id"] for c in cast],
        "cast_names": [c["name"] for c in cast],
    }


def _campaign_beats(driver, campaign_id):
    ids = _fetch(driver, f'''
        match
          $camp isa myth-campaign, has id "{escape_string(campaign_id)}";
          (campaign: $camp, element: $b) isa myth-campaign-membership;
          $b isa myth-beat, has id $i;
        fetch {{ "id": $i }};''')
    return [_beat_record(driver, r["id"]) for r in ids]


def _campaign_agendas(driver, campaign_id):
    ids = _fetch(driver, f'''
        match
          $camp isa myth-campaign, has id "{escape_string(campaign_id)}";
          (campaign: $camp, element: $a) isa myth-campaign-membership;
          $a isa myth-agenda, has id $i;
        fetch {{ "id": $i }};''')
    return [_agenda_record(driver, r["id"]) for r in ids]


def _pc_presence(driver, campaign_id):
    """(pc ids, location ids the PCs are standing in) for beat staging."""
    pcs = _fetch(driver, f'''
        match
          $camp isa myth-campaign, has id "{escape_string(campaign_id)}";
          (campaign: $camp, element: $c) isa myth-campaign-membership;
          $c isa myth-character, has id $i, has myth-char-type "pc",
             has myth-status "active";
        fetch {{ "id": $i }};''')
    pc_ids = [r["id"] for r in pcs]
    places = []
    for pid in pc_ids:
        rows = _fetch(driver, f'''
            match
              $c isa myth-character, has id "{escape_string(pid)}";
              (located: $c, location: $l) isa myth-presence;
              $l has id $li;
            fetch {{ "id": $li }};''')
        places.extend(r["id"] for r in rows)
    return pc_ids, places


def cmd_add_agenda(args):
    aid = generate_id("myth-agenda")
    ts = get_timestamp()
    q = f'''insert $a isa myth-agenda,
        has id "{aid}",
        has name "{escape_string(args.title)}",
        has myth-agenda-status "{escape_string(args.status)}",
        has myth-agenda-clock-size {args.clock},
        has myth-agenda-clock-filled {args.filled},
        has myth-agenda-priority {args.priority},
        has created-at {ts}'''
    if args.goal:
        q += f', has description "{escape_string(args.goal)}"'
    if args.narrative:
        q += f', has content "{escape_string(args.narrative)}"'
    q += ";"
    with get_driver() as driver:
        _write(driver, q)
        _link_to_campaign(driver, args.campaign, aid, "myth-agenda")
        holder_type = _link_relation(driver, "myth-agenda-holder", "agenda",
                                     "myth-agenda", aid, "holder",
                                     AGENDA_HOLDER_TYPES, args.holder)
        if not holder_type:
            fail(f"No character or faction with id '{args.holder}'")
        targets = []
        for tid in (args.target or "").split(","):
            tid = tid.strip()
            if tid and _link_relation(driver, "myth-agenda-target", "agenda",
                                      "myth-agenda", aid, "target",
                                      AGENDA_TARGET_TYPES, tid):
                targets.append(tid)
    out({"success": True, "id": aid, "holder": args.holder,
         "holder_type": holder_type, "targets": targets})


def cmd_list_agendas(args):
    with get_driver() as driver:
        agendas = _campaign_agendas(driver, args.campaign)
    if args.status:
        agendas = [a for a in agendas if a["status"] == args.status]
    if args.holder:
        agendas = [a for a in agendas
                   if a.get("holder") and a["holder"]["id"] == args.holder]
    agendas.sort(key=lambda a: (-a["priority"], a["title"]))
    if args.compact:
        agendas = [{"id": a["id"], "title": a["title"],
                    "holder": (a.get("holder") or {}).get("name"),
                    "clock": f'{a["clock"]["filled"]}/{a["clock"]["size"]}',
                    "status": a["status"], "priority": a["priority"]}
                   for a in agendas]
    out({"success": True, "agendas": agendas})


def cmd_get_agenda(args):
    with get_driver() as driver:
        agenda = _agenda_record(driver, args.id)
        if not agenda:
            fail(f"No agenda '{args.id}'")
        beat_ids = _fetch(driver, f'''
            match
              $a isa myth-agenda, has id "{escape_string(args.id)}";
              (beat: $b, agenda: $a) isa myth-beat-of;
              $b has id $bi;
            fetch {{ "id": $bi }};''')
        agenda["beats"] = sorted(
            [_beat_record(driver, r["id"]) for r in beat_ids],
            key=lambda b: (b["time_index"] if b["time_index"] is not None else 1 << 30))
    out({"success": True, "agenda": agenda})


def cmd_advance_agenda(args):
    with get_driver() as driver:
        agenda = _agenda_record(driver, args.id, holder=False)
        if not agenda:
            fail(f"No agenda '{args.id}'")
        filled, completed = eng.advance_clock(
            agenda["clock"]["filled"], agenda["clock"]["size"], args.by)
        _set_attr(driver, "myth-agenda", args.id,
                  "myth-agenda-clock-filled", filled, quote=False)
        if completed and args.complete_status:
            _set_attr(driver, "myth-agenda", args.id,
                      "myth-agenda-status", args.complete_status)
        # Beats gated on this agenda's clock may now be due.
        beat_ids = _fetch(driver, f'''
            match
              $a isa myth-agenda, has id "{escape_string(args.id)}";
              (beat: $b, agenda: $a) isa myth-beat-of;
              $b has id $bi;
            fetch {{ "id": $bi }};''')
        beats = [_beat_record(driver, r["id"]) for r in beat_ids]
        triggered = [b for b in beats
                     if eng.beat_is_due(b, 1 << 30, clock_filled=filled)
                     and str(b["trigger"]).lower().startswith("clock")]
        if args.note and args.campaign:
            _log_world_note(driver, args.campaign, args.note)
    out({"success": True, "id": args.id,
         "clock": {"filled": filled, "size": agenda["clock"]["size"]},
         "completed": completed, "triggered_beats": triggered})


def _log_world_note(driver, campaign_id, text):
    """A gm-note journal entry recording an off-camera world movement."""
    eid = generate_id("myth-event")
    _write(driver, f'''insert $e isa myth-game-event,
        has id "{eid}", has name "World note",
        has description "{escape_string(text)}",
        has myth-event-type "gm-note",
        has created-at {get_timestamp()};''')
    _link_to_campaign(driver, campaign_id, eid, "myth-game-event")
    return eid


def cmd_update_agenda(args):
    """Edit an agenda in place. Clocks and status have their own verbs
    (advance-agenda, set-agenda-status); this is for everything else -- what
    they want, how they pursue it, how big the clock is, how loudly they act."""
    with get_driver() as driver:
        if not _get_entity(driver, "myth-agenda", args.id, []):
            fail(f"No agenda '{args.id}'")
        if args.title is not None:
            _set_attr(driver, "myth-agenda", args.id, "name", args.title)
        if args.goal is not None:
            _set_attr(driver, "myth-agenda", args.id, "description", args.goal)
        if args.narrative is not None:
            _set_attr(driver, "myth-agenda", args.id, "content", args.narrative)
        if args.clock is not None:
            _set_attr(driver, "myth-agenda", args.id, "myth-agenda-clock-size",
                      args.clock, quote=False)
        if args.filled is not None:
            _set_attr(driver, "myth-agenda", args.id, "myth-agenda-clock-filled",
                      args.filled, quote=False)
        if args.priority is not None:
            _set_attr(driver, "myth-agenda", args.id, "myth-agenda-priority",
                      args.priority, quote=False)
    out({"success": True, "id": args.id})


def cmd_set_agenda_status(args):
    with get_driver() as driver:
        if not _get_entity(driver, "myth-agenda", args.id, []):
            fail(f"No agenda '{args.id}'")
        _set_attr(driver, "myth-agenda", args.id,
                  "myth-agenda-status", args.status)
        if args.note and args.campaign:
            _log_world_note(driver, args.campaign, args.note)
    out({"success": True, "id": args.id, "status": args.status})


def cmd_add_beat(args):
    bid = generate_id("myth-beat")
    ts = get_timestamp()
    time_index = None
    if args.when:
        try:
            time_index = eng.parse_time_key(args.when)
        except ValueError as e:
            fail(str(e))
    trigger = args.trigger or "time"
    if trigger == "time" and time_index is None:
        fail("A time-triggered beat needs --when (e.g. 'd-3/night')")
    q = f'''insert $b isa myth-beat,
        has id "{bid}",
        has name "{escape_string(args.title)}",
        has myth-beat-status "{escape_string(args.status)}",
        has myth-beat-trigger "{escape_string(trigger)}",
        has created-at {ts}'''
    if args.when:
        q += f', has myth-beat-when "{escape_string(args.when)}"'
        q += f', has myth-time-index {time_index}'
    if args.summary:
        q += f', has description "{escape_string(args.summary)}"'
    if args.onscreen_if:
        q += f', has myth-beat-onscreen-if "{escape_string(args.onscreen_if)}"'
    if args.narrative:
        q += f', has content "{escape_string(args.narrative)}"'
    q += ";"
    with get_driver() as driver:
        agenda = _get_entity(driver, "myth-agenda", args.agenda, [])
        if not agenda:
            fail(f"No agenda '{args.agenda}'")
        _write(driver, q)
        _link_to_campaign(driver, args.campaign, bid, "myth-beat")
        _write(driver, f'''
            match
              $b isa myth-beat, has id "{bid}";
              $a isa myth-agenda, has id "{escape_string(args.agenda)}";
            insert (beat: $b, agenda: $a) isa myth-beat-of;''')
        if args.at:
            if not _link_relation(driver, "myth-beat-at", "beat", "myth-beat",
                                  bid, "place", ["myth-location"], args.at):
                fail(f"No location '{args.at}'")
        cast = []
        for cid in (args.cast or "").split(","):
            cid = cid.strip()
            if cid and _link_relation(driver, "myth-beat-cast", "beat", "myth-beat",
                                      bid, "member", AGENDA_HOLDER_TYPES, cid):
                cast.append(cid)
    out({"success": True, "id": bid, "when": args.when,
         "time_index": time_index, "cast": cast})


def cmd_list_beats(args):
    with get_driver() as driver:
        beats = _campaign_beats(driver, args.campaign)
        camp = _get_entity(driver, "myth-campaign", args.campaign, ["myth-time-index"])
        now = camp.get("myth-time-index") if camp else None
        clocks = {a["id"]: a["clock"]["filled"]
                  for a in _campaign_agendas(driver, args.campaign)}
    if args.pending:
        beats = [b for b in beats if b["status"] == "pending"]
    if args.at:
        beats = [b for b in beats if b["place"] == args.at]
    if args.involving:
        beats = [b for b in beats if args.involving in b["cast"]]
    if args.due:
        if now is None:
            fail("Campaign has no world clock yet -- run `tick` first")
        beats = [b for b in beats
                 if eng.beat_is_due(b, now, clocks.get(b["agenda"]))]
    beats.sort(key=lambda b: (b["time_index"] if b["time_index"] is not None else 1 << 30,
                              -b["priority"]))
    out({"success": True, "now": eng.format_time_key(now) if now is not None else None,
         "beats": beats})


def cmd_revise_beat(args):
    """Bend a planned beat to match what play has made true."""
    with get_driver() as driver:
        if not _get_entity(driver, "myth-beat", args.id, []):
            fail(f"No beat '{args.id}'")
        if args.when is not None:
            try:
                idx = eng.parse_time_key(args.when)
            except ValueError as e:
                fail(str(e))
            _set_attr(driver, "myth-beat", args.id, "myth-beat-when", args.when)
            _set_attr(driver, "myth-beat", args.id, "myth-time-index", idx, quote=False)
        if args.title is not None:
            _set_attr(driver, "myth-beat", args.id, "name", args.title)
        if args.summary is not None:
            _set_attr(driver, "myth-beat", args.id, "description", args.summary)
        if args.narrative is not None:
            _set_attr(driver, "myth-beat", args.id, "content", args.narrative)
        if args.onscreen_if is not None:
            _set_attr(driver, "myth-beat", args.id,
                      "myth-beat-onscreen-if", args.onscreen_if)
        if args.trigger is not None:
            _set_attr(driver, "myth-beat", args.id, "myth-beat-trigger", args.trigger)
        if args.status is not None:
            _set_attr(driver, "myth-beat", args.id, "myth-beat-status", args.status)
        if args.at is not None:
            _write(driver, f'''
                match
                  $b isa myth-beat, has id "{escape_string(args.id)}";
                  $r isa myth-beat-at (beat: $b);
                delete $r;''')
            if args.at and not _link_relation(driver, "myth-beat-at", "beat",
                                              "myth-beat", args.id, "place",
                                              ["myth-location"], args.at):
                fail(f"No location '{args.at}'")
        if args.cast is not None:
            _write(driver, f'''
                match
                  $b isa myth-beat, has id "{escape_string(args.id)}";
                  $r isa myth-beat-cast (beat: $b);
                delete $r;''')
            for cid in args.cast.split(","):
                cid = cid.strip()
                if cid:
                    _link_relation(driver, "myth-beat-cast", "beat", "myth-beat",
                                   args.id, "member", AGENDA_HOLDER_TYPES, cid)
        beat = _beat_record(driver, args.id)
    out({"success": True, "beat": beat})


def cmd_fire_beat(args):
    """Resolve a beat: mark how it went and, with --log, journal it."""
    with get_driver() as driver:
        beat = _beat_record(driver, args.id)
        if not beat:
            fail(f"No beat '{args.id}'")
        _set_attr(driver, "myth-beat", args.id, "myth-beat-status", args.outcome)
        event_id = None
        if args.log:
            summary = args.summary or beat["summary"] or beat["title"]
            eid = generate_id("myth-event")
            q = (f'insert $e isa myth-game-event, has id "{eid}", '
                 f'has name "{escape_string(beat["title"])}", '
                 f'has description "{escape_string(summary)}", '
                 f'has myth-event-type "{escape_string(args.type)}", '
                 f'has created-at {get_timestamp()}')
            if args.narrative:
                q += f', has content "{escape_string(args.narrative)}"'
            if args.session is not None:
                q += f', has myth-session-number {args.session}'
            q += ";"
            _write(driver, q)
            _link_to_campaign(driver, args.campaign, eid, "myth-game-event")
            _write(driver, f'''
                match
                  $b isa myth-beat, has id "{escape_string(args.id)}";
                  $e isa myth-game-event, has id "{eid}";
                insert (beat: $b, event: $e) isa myth-beat-outcome;''')
            # Everyone in the beat's cast took part in the event it became.
            for cid in beat["cast"]:
                for ptype in AGENDA_HOLDER_TYPES:
                    if _fetch(driver, f'''
                            match $p isa {ptype}, has id "{escape_string(cid)}";
                            fetch {{ "id": $p.id }};'''):
                        _write(driver, f'''
                            match
                              $e isa myth-game-event, has id "{eid}";
                              $p isa {ptype}, has id "{escape_string(cid)}";
                            insert (event: $e, participant: $p) isa myth-event-involvement;''')
                        break
            event_id = eid
        # The beat is what makes its facts true -- or what makes them
        # impossible. Either way its futures stop being pending here.
        beat_facts = _fetch(driver, f'''
            match
              $b isa myth-beat, has id "{escape_string(args.id)}";
              (fact: $f, origin: $b) isa myth-fact-from;
              $f has id $fi, has myth-fact-status $fs;
            fetch {{ "id": $fi, "status": $fs }};''')
        established_now, retired_now = [], []
        if not args.no_facts:
            camp = _get_entity(driver, "myth-campaign", args.campaign,
                               ["myth-time-index"]) if args.campaign else None
            now = camp.get("myth-time-index") if camp else None
            for bf in beat_facts:
                if bf["status"] != "not-yet-true":
                    continue
                if args.outcome in ("played", "narrated"):
                    _set_attr(driver, "myth-fact", bf["id"],
                              "myth-fact-status", "established")
                    if now is not None:
                        _set_attr(driver, "myth-fact", bf["id"],
                                  "myth-time-index", now, quote=False)
                    established_now.append(bf["id"])
                else:
                    _supersede_fact(driver, bf["id"])
                    retired_now.append(bf["id"])
            # whoever was there to see it now knows it
            for wid in (args.witnesses or "").split(","):
                wid = wid.strip()
                if not wid or not established_now:
                    continue
                for kt in KNOWER_TYPES:
                    if _fetch(driver, f'''
                            match $k isa {kt}, has id "{escape_string(wid)}";
                            fetch {{ "id": $k.id }};'''):
                        for fid in established_now:
                            q = (f'match $k isa {kt}, has id "{escape_string(wid)}"; '
                                 f'$f isa myth-fact, has id "{escape_string(fid)}"; '
                                 f'insert $r isa myth-knows (knower: $k, fact: $f), '
                                 f'has myth-knowledge-certainty "knows", '
                                 f'has myth-knowledge-source "witnessed"')
                            if now is not None:
                                q += f", has myth-knowledge-since {now}"
                            _write(driver, q + ";")
                        break

        clock = None
        if args.advance and beat["agenda"]:
            agenda = _agenda_record(driver, beat["agenda"], holder=False)
            filled, completed = eng.advance_clock(agenda["clock"]["filled"],
                                                  agenda["clock"]["size"], args.advance)
            _set_attr(driver, "myth-agenda", beat["agenda"],
                      "myth-agenda-clock-filled", filled, quote=False)
            clock = {"agenda": beat["agenda"], "filled": filled,
                     "size": agenda["clock"]["size"], "completed": completed}
        cascade = _cascade(driver, args.campaign,
                           established=established_now) if args.campaign else {}
    out({"success": True, "id": args.id, "outcome": args.outcome,
         "event": event_id, "clock": clock,
         "facts_established": established_now, "facts_retired": retired_now,
         "cascade": cascade})


def cmd_tick(args):
    """Advance world time and report what has come due, staged against the PCs.

    This is the GM's between-scenes move: the world does not wait for the
    party. Every beat whose trigger has been met comes back flagged `onscreen`
    (the PCs are there to witness or interrupt it) or `offscreen` (it happens
    regardless, and becomes something they may discover later).
    """
    with get_driver() as driver:
        camp = _get_entity(driver, "myth-campaign", args.campaign,
                           ["myth-time-index", "myth-game-date"])
        if not camp:
            fail(f"No campaign '{args.campaign}'")
        was = camp.get("myth-time-index")
        try:
            now = eng.parse_time_key(args.to)
        except ValueError as e:
            fail(str(e))
        if was is not None and now < was and not args.rewind:
            fail(f"Refusing to move the clock backwards "
                 f"({eng.format_time_key(was)} -> {args.to}); pass --rewind to force")
        _set_attr(driver, "myth-campaign", args.campaign,
                  "myth-time-index", now, quote=False)
        if args.set_date:
            _set_attr(driver, "myth-campaign", args.campaign,
                      "myth-game-date", args.set_date)

        agendas = _campaign_agendas(driver, args.campaign)

        # Re-settle the world before reading it: wake knowledge-gated agendas,
        # cancel beats whose agenda has died, retire futures that cannot happen.
        settle = _cascade(driver, args.campaign)
        activated = settle["activated_agendas"]
        if (settle["activated_agendas"] or settle["cancelled_beats"]
                or settle["retired_facts"]):
            agendas = _campaign_agendas(driver, args.campaign)

        clocks = {a["id"]: a["clock"]["filled"] for a in agendas}
        active = {a["id"] for a in agendas
                  if a["status"] in ("active", "pending")}
        beats = [b for b in _campaign_beats(driver, args.campaign)
                 if b["agenda"] is None or b["agenda"] in active]
        due = eng.due_beats(beats, now, clocks)
        pc_ids, pc_places = _pc_presence(driver, args.campaign)
        for b in due:
            b["staging"] = eng.beat_staging(b, pc_places, pc_ids)

    out({"success": True,
         "from": eng.format_time_key(was) if was is not None else None,
         "now": args.to, "time_index": now,
         "activated_agendas": activated,
         "cancelled_beats": settle["cancelled_beats"],
         "retired_facts": settle["retired_facts"],
         "pc_locations": pc_places,
         "due_beats": due,
         "onscreen": [b["id"] for b in due if b["staging"] == "onscreen"],
         "offscreen": [b["id"] for b in due if b["staging"] == "offscreen"]})


# ---------------------------------------------------------------------------
# Epistemics: facts, knowledge, and reconciliation
#
# Situational truth lives in ONE place -- the fact graph -- and what a character
# knows is a projection of it (myth-knows edges), never a separate store. That
# is what makes per-character knowledge reconcilable: two views cannot disagree
# when there is only one source and everything else is a query into it.
#
# Character prose describes CHARACTER. Facts carry SITUATION.
# ---------------------------------------------------------------------------

FACT_ATTRS = ["description", "content", "myth-fact-status", "myth-fact-truth",
              "myth-time-index"]
FACT_SUBJECT_TYPES = ["myth-character", "myth-location", "myth-faction",
                      "myth-agenda", "myth-beat"]
KNOWER_TYPES = ["myth-character", "myth-faction"]
FACT_ORIGIN_TYPES = ["myth-beat", "myth-game-event"]


def _fact_record(driver, fid):
    f = _get_entity(driver, "myth-fact", fid, FACT_ATTRS)
    if not f:
        return None
    about = _fetch(driver, f'''
        match
          $f isa myth-fact, has id "{escape_string(fid)}";
          (fact: $f, subject: $s) isa myth-fact-about;
          $s has id $si, has name $sn;
        fetch {{ "id": $si, "name": $sn }};''')
    origin = _fetch(driver, f'''
        match
          $f isa myth-fact, has id "{escape_string(fid)}";
          (fact: $f, origin: $o) isa myth-fact-from;
          $o has id $oi, has name $on;
        fetch {{ "id": $oi, "name": $on }};''')
    return {
        "id": f["id"], "title": f["name"], "statement": f.get("description"),
        "status": f.get("myth-fact-status") or "established",
        "truth": f.get("myth-fact-truth") or "true",
        "time_index": f.get("myth-time-index"),
        "when": (eng.format_time_key(f["myth-time-index"])
                 if f.get("myth-time-index") is not None else None),
        "narrative": f.get("content"),
        "about": [a["id"] for a in about], "about_names": [a["name"] for a in about],
        "from": origin[0]["id"] if origin else None,
        "from_name": origin[0]["name"] if origin else None,
    }


def _campaign_facts(driver, campaign_id):
    rows = _fetch(driver, f'''
        match
          $camp isa myth-campaign, has id "{escape_string(campaign_id)}";
          (campaign: $camp, element: $f) isa myth-campaign-membership;
          $f isa myth-fact, has id $i;
        fetch {{ "id": $i }};''')
    return [_fact_record(driver, r["id"]) for r in rows]


def _knowledge_edges(driver, campaign_id):
    """Every (knower, fact) edge in the campaign, with how and when."""
    return _fetch(driver, f'''
        match
          $camp isa myth-campaign, has id "{escape_string(campaign_id)}";
          (campaign: $camp, element: $f) isa myth-campaign-membership;
          $f isa myth-fact, has id $fi;
          $r isa myth-knows (knower: $k, fact: $f);
          $k has id $ki, has name $kn;
          $r has myth-knowledge-certainty $c;
        fetch {{
          "knower": $ki, "knower_name": $kn, "fact": $fi, "certainty": $c,
          "source": [ $r.myth-knowledge-source ],
          "since": [ $r.myth-knowledge-since ]
        }};''')


def _flatten_edges(rows):
    """The fetch above returns list-valued optional attributes; flatten them."""
    out = []
    for r in rows:
        e = dict(r)
        for k in ("source", "since"):
            v = e.get(k)
            e[k] = (v[0] if isinstance(v, list) and v else (None if isinstance(v, list) else v))
        out.append(e)
    return out


def _agenda_requirements(driver, campaign_id):
    return _fetch(driver, f'''
        match
          $camp isa myth-campaign, has id "{escape_string(campaign_id)}";
          (campaign: $camp, element: $a) isa myth-campaign-membership;
          $a isa myth-agenda, has id $ai;
          (agenda: $a, fact: $f) isa myth-agenda-requires;
          $f has id $fi;
        fetch {{ "agenda": $ai, "fact": $fi }};''')


def cmd_add_fact(args):
    fid = generate_id("myth-fact")
    ts = get_timestamp()
    time_index = None
    if args.when:
        try:
            time_index = eng.parse_time_key(args.when)
        except ValueError as e:
            fail(str(e))
    if args.status == "established" and time_index is None:
        fail("An established fact needs --when (when it became true)")
    q = f'''insert $f isa myth-fact,
        has id "{fid}",
        has name "{escape_string(args.title or args.statement[:60])}",
        has description "{escape_string(args.statement)}",
        has myth-fact-status "{escape_string(args.status)}",
        has myth-fact-truth "{escape_string(args.truth)}",
        has created-at {ts}'''
    if time_index is not None:
        q += f", has myth-time-index {time_index}"
    if args.narrative:
        q += f', has content "{escape_string(args.narrative)}"'
    q += ";"
    with get_driver() as driver:
        _write(driver, q)
        _link_to_campaign(driver, args.campaign, fid, "myth-fact")
        about = []
        for sid in (args.about or "").split(","):
            sid = sid.strip()
            if sid and _link_relation(driver, "myth-fact-about", "fact", "myth-fact",
                                      fid, "subject", FACT_SUBJECT_TYPES, sid):
                about.append(sid)
        origin = None
        if args.origin:
            origin = _link_relation(driver, "myth-fact-from", "fact", "myth-fact",
                                    fid, "origin", FACT_ORIGIN_TYPES, args.origin)
            if not origin:
                fail(f"No beat or event with id '{args.origin}'")
        learned = _ids(getattr(args, "learned_by", None))
        if learned and args.status != "established":
            fail("--learned-by needs --status established: nobody can know a "
                 "fact that has not happened yet")
        for kid in learned:
            _write_knowledge(driver, kid, fid, args.certainty, args.source, time_index)
    out({"success": True, "id": fid, "status": args.status, "truth": args.truth,
         "when": args.when, "about": about, "from": args.origin,
         "learned_by": learned})


def cmd_list_facts(args):
    with get_driver() as driver:
        facts = _campaign_facts(driver, args.campaign)
        edges = _flatten_edges(_knowledge_edges(driver, args.campaign))
    if args.status:
        facts = [f for f in facts if f["status"] == args.status]
    if args.truth:
        facts = [f for f in facts if f["truth"] == args.truth]
    if args.about:
        facts = [f for f in facts if args.about in f["about"]]
    if args.known_by:
        known = {e["fact"] for e in edges if e["knower"] == args.known_by}
        facts = [f for f in facts if f["id"] in known]
    knowers = {}
    for e in edges:
        knowers.setdefault(e["fact"], []).append(e["knower_name"])
    for f in facts:
        f["known_by"] = sorted(knowers.get(f["id"], []))
    facts.sort(key=lambda f: (f["time_index"] if f["time_index"] is not None else 1 << 30))
    out({"success": True, "facts": facts})


def cmd_get_fact(args):
    with get_driver() as driver:
        f = _fact_record(driver, args.id)
        if not f:
            fail(f"No fact '{args.id}'")
        edges = _flatten_edges(_knowledge_edges(driver, args.campaign)) if args.campaign else []
        f["known_by"] = [e for e in edges if e["fact"] == args.id]
    out({"success": True, "fact": f})


def cmd_establish_fact(args):
    """Flip a fact from not-yet-true to established at a point in world time."""
    with get_driver() as driver:
        f = _fact_record(driver, args.id)
        if not f:
            fail(f"No fact '{args.id}'")
        try:
            idx = eng.parse_time_key(args.when)
        except ValueError as e:
            fail(str(e))
        _set_attr(driver, "myth-fact", args.id, "myth-fact-status", "established")
        _set_attr(driver, "myth-fact", args.id, "myth-time-index", idx, quote=False)
        if args.truth:
            _set_attr(driver, "myth-fact", args.id, "myth-fact-truth", args.truth)
        # A fact landing can change what people are trying to do, which can
        # cancel futures that were only ever going to happen because of them.
        report = _cascade(driver, args.campaign, established=[args.id]) if args.campaign else {}
    out({"success": True, "id": args.id, "status": "established", "when": args.when,
         "cascade": report})


def _consequences(driver, campaign_id):
    return _fetch(driver, f'''
        match
          $camp isa myth-campaign, has id "{escape_string(campaign_id)}";
          (campaign: $camp, element: $a) isa myth-campaign-membership;
          $a isa myth-agenda, has id $ai;
          $r isa myth-consequence (fact: $f, agenda: $a);
          $f has id $fi;
          $r has myth-consequence-effect $e;
        fetch {{ "fact": $fi, "agenda": $ai, "effect": $e,
                 "amount": [ $r.myth-consequence-amount ] }};''')


def _supersede_fact(driver, fid, by=None):
    """Retire a future that can no longer happen, keeping the trail."""
    _set_attr(driver, "myth-fact", fid, "myth-fact-status", "superseded")
    if by:
        _write(driver, f'''
            match
              $new isa myth-fact, has id "{escape_string(by)}";
              $old isa myth-fact, has id "{escape_string(fid)}";
            insert (superseding: $new, superseded: $old) isa myth-fact-supersedes;''')


def _cascade(driver, campaign_id, established=()):
    """Propagate an event through intentions and the futures they promised.

        fact established
          -> consequences change agendas      (thwart/abandon/stall/advance)
          -> dead agendas cancel their beats  (the future is rewritten)
          -> those beats' futures are retired (no orphaned not-yet-true facts)
          -> knowledge-gated agendas activate
          -> and any agenda that just died cancels its beats too

    Everything except the consequence step is convergent, so this is safe to
    run on every tick. Consequences fire only for facts named in `established`
    -- the moment of transition -- because stall/advance are not idempotent.
    """
    report = {"agenda_changes": [], "cancelled_beats": [], "retired_facts": [],
              "activated_agendas": []}

    agendas = _campaign_agendas(driver, campaign_id)
    flat = [{"id": a["id"], "title": a["title"], "status": a["status"],
             "clock": dict(a["clock"]), "priority": a["priority"],
             "holder": (a.get("holder") or {}).get("id")} for a in agendas]

    if established:
        cons = []
        for c in _consequences(driver, campaign_id):
            amount = c.get("amount")
            cons.append({"fact": c["fact"], "agenda": c["agenda"],
                         "effect": c["effect"],
                         "amount": (amount[0] if isinstance(amount, list) and amount
                                    else amount)})
        for ch in eng.apply_consequences(established, cons, flat):
            if ch["to_status"] != ch["from_status"]:
                _set_attr(driver, "myth-agenda", ch["agenda"],
                          "myth-agenda-status", ch["to_status"])
            if ch["clock_to"] != ch["clock_from"]:
                _set_attr(driver, "myth-agenda", ch["agenda"],
                          "myth-agenda-clock-filled", ch["clock_to"], quote=False)
            report["agenda_changes"].append(ch)

    # knowledge-gated activations (idempotent)
    edges = _flatten_edges(_knowledge_edges(driver, campaign_id))
    reqs = _agenda_requirements(driver, campaign_id)
    for a in eng.agendas_to_activate(flat, reqs, edges):
        _set_attr(driver, "myth-agenda", a["id"], "myth-agenda-status", "active")
        for f in flat:
            if f["id"] == a["id"]:
                f["status"] = "active"
        report["activated_agendas"].append({"id": a["id"], "title": a["title"]})

    # dead agendas cancel the beats they were going to produce
    beats = _campaign_beats(driver, campaign_id)
    for b in eng.beats_to_cancel(flat, beats):
        _set_attr(driver, "myth-beat", b["id"], "myth-beat-status", "cancelled")
        b["status"] = "cancelled"
        report["cancelled_beats"].append({"id": b["id"], "title": b["title"]})

    # and futures no live beat will ever make true are retired
    facts = _campaign_facts(driver, campaign_id)
    for f in eng.orphaned_futures(facts, beats):
        _supersede_fact(driver, f["id"])
        report["retired_facts"].append({"id": f["id"], "statement": f["statement"]})
    return report


def cmd_add_consequence(args):
    """Say what an established fact does to somebody's intentions."""
    with get_driver() as driver:
        if not _get_entity(driver, "myth-fact", args.fact, []):
            fail(f"No fact '{args.fact}'")
        if not _get_entity(driver, "myth-agenda", args.agenda, []):
            fail(f"No agenda '{args.agenda}'")
        q = (f'match $f isa myth-fact, has id "{escape_string(args.fact)}"; '
             f'$a isa myth-agenda, has id "{escape_string(args.agenda)}"; '
             f'insert $r isa myth-consequence (fact: $f, agenda: $a), '
             f'has myth-consequence-effect "{escape_string(args.effect)}"')
        if args.amount is not None:
            q += f", has myth-consequence-amount {args.amount}"
        q += ";"
        _write(driver, q)
    out({"success": True, "fact": args.fact, "agenda": args.agenda,
         "effect": args.effect, "amount": args.amount})


def cmd_supersede_fact(args):
    with get_driver() as driver:
        if not _fact_record(driver, args.id):
            fail(f"No fact '{args.id}'")
        if args.by and not _fact_record(driver, args.by):
            fail(f"No fact '{args.by}'")
        _supersede_fact(driver, args.id, args.by)
        report = _cascade(driver, args.campaign) if args.campaign else {}
    out({"success": True, "id": args.id, "superseded_by": args.by,
         "cascade": report})


def cmd_cascade(args):
    """Re-settle the world: cancel dead futures, wake what should be awake."""
    with get_driver() as driver:
        report = _cascade(driver, args.campaign)
    out({"success": True, **report})


def cmd_revise_fact(args):
    """Correct a fact's wording, truth or subjects.

    A proposition must never assert who knows it -- ignorance lives in the
    myth-knows edges. Restating a fact keeps its id, so agenda gates and
    knowledge edges pointing at it stay valid.
    """
    with get_driver() as driver:
        if not _get_entity(driver, "myth-fact", args.id, []):
            fail(f"No fact '{args.id}'")
        if args.statement is not None:
            _set_attr(driver, "myth-fact", args.id, "description", args.statement)
        if args.title is not None:
            _set_attr(driver, "myth-fact", args.id, "name", args.title)
        if args.truth is not None:
            _set_attr(driver, "myth-fact", args.id, "myth-fact-truth", args.truth)
        if args.status is not None:
            _set_attr(driver, "myth-fact", args.id, "myth-fact-status", args.status)
        if args.narrative is not None:
            _set_attr(driver, "myth-fact", args.id, "content", args.narrative)
        if args.about is not None:
            _write(driver, f'''
                match
                  $f isa myth-fact, has id "{escape_string(args.id)}";
                  $r isa myth-fact-about (fact: $f);
                delete $r;''')
            for sid in args.about.split(","):
                sid = sid.strip()
                if sid:
                    _link_relation(driver, "myth-fact-about", "fact", "myth-fact",
                                   args.id, "subject", FACT_SUBJECT_TYPES, sid)
        fact = _fact_record(driver, args.id)
    out({"success": True, "fact": fact})


def _write_knowledge(driver, knower_id, fact_id, certainty, source, since):
    """One edge per (knower, fact) -- replace rather than duplicate."""
    ktype = None
    for kt in KNOWER_TYPES:
        if _fetch(driver, 'match $k isa %s, has id "%s"; fetch { "id": $k.id };'
                  % (kt, escape_string(knower_id))):
            ktype = kt
            break
    if not ktype:
        fail("No character or faction with id '%s'" % knower_id)
    _write(driver, '''
        match
          $k isa %s, has id "%s";
          $f isa myth-fact, has id "%s";
          $r isa myth-knows (knower: $k, fact: $f);
        delete $r;''' % (ktype, escape_string(knower_id), escape_string(fact_id)))
    q = ('match $k isa %s, has id "%s"; $f isa myth-fact, has id "%s"; '
         'insert $r isa myth-knows (knower: $k, fact: $f), '
         'has myth-knowledge-certainty "%s"'
         % (ktype, escape_string(knower_id), escape_string(fact_id),
            escape_string(certainty)))
    if source:
        q += ', has myth-knowledge-source "%s"' % escape_string(source)
    if since is not None:
        q += ", has myth-knowledge-since %d" % since
    q += ";"
    _write(driver, q)
    return ktype


def _ids(raw):
    """Split a comma-separated id list. Writing one edge should not need a
    shell loop -- that is how edges end up not written at all."""
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


def cmd_learn(args):
    """Record that someone learned something -- the knowledge edge.

    --knower takes a list, because tonight's session wrote five of these in a
    shell loop and the sixth never got written at all.
    """
    knowers = _ids(args.knower)
    if not knowers:
        fail("--knower needs at least one character or faction id")
    with get_driver() as driver:
        f = _fact_record(driver, args.fact)
        if not f:
            fail(f"No fact '{args.fact}'")
        if f["status"] == "not-yet-true" and not args.force:
            fail(f"Fact '{args.fact}' has not happened yet "
                 f"(status not-yet-true) -- establish it first, or pass --force")
        since = None
        if args.at:
            try:
                since = eng.parse_time_key(args.at)
            except ValueError as e:
                fail(str(e))
        elif getattr(args, "campaign", None):
            camp = _get_entity(driver, "myth-campaign", args.campaign, ["myth-time-index"])
            since = camp.get("myth-time-index") if camp else None
        for kid in knowers:
            _write_knowledge(driver, kid, args.fact, args.certainty, args.source, since)
    out({"success": True, "knowers": knowers, "fact": args.fact,
         "certainty": args.certainty, "source": args.source, "since": since})


def cmd_forget(args):
    with get_driver() as driver:
        for kt in KNOWER_TYPES:
            _write(driver, f'''
                match
                  $k isa {kt}, has id "{escape_string(args.knower)}";
                  $f isa myth-fact, has id "{escape_string(args.fact)}";
                  $r isa myth-knows (knower: $k, fact: $f);
                delete $r;''')
    out({"success": True, "knower": args.knower, "fact": args.fact, "forgotten": True})


def cmd_who_knows(args):
    with get_driver() as driver:
        edges = _flatten_edges(_knowledge_edges(driver, args.campaign))
    rows = [e for e in edges if e["fact"] == args.fact]
    for e in rows:
        e["since_key"] = (eng.format_time_key(e["since"]) if e.get("since") is not None else None)
    rows.sort(key=lambda e: (e["since"] if e.get("since") is not None else 1 << 30))
    out({"success": True, "fact": args.fact, "knowers": rows})


def cmd_character_view(args):
    """Everything this character can legitimately act on. A projection."""
    with get_driver() as driver:
        camp_id = args.campaign
        facts = _campaign_facts(driver, camp_id)
        edges = _flatten_edges(_knowledge_edges(driver, camp_id))
        who = _get_entity(driver, "myth-character", args.id, ["myth-char-type"])
    view = eng.character_view(facts, edges, args.id)
    for f in view:
        f["since_key"] = (eng.format_time_key(f["since"]) if f.get("since") is not None else None)
    if args.compact:
        view = [{"statement": f["statement"], "certainty": f["certainty"],
                 "source": f.get("source"), "since": f.get("since_key"),
                 "truth": f["truth"]} for f in view]
    out({"success": True, "character": args.id,
         "name": who["name"] if who else None, "knows": view})


def cmd_require_fact(args):
    """Gate an agenda on its holder knowing something."""
    with get_driver() as driver:
        if not _get_entity(driver, "myth-agenda", args.agenda, []):
            fail(f"No agenda '{args.agenda}'")
        if not _get_entity(driver, "myth-fact", args.fact, []):
            fail(f"No fact '{args.fact}'")
        _write(driver, f'''
            match
              $a isa myth-agenda, has id "{escape_string(args.agenda)}";
              $f isa myth-fact, has id "{escape_string(args.fact)}";
            insert (agenda: $a, fact: $f) isa myth-agenda-requires;''')
    out({"success": True, "agenda": args.agenda, "requires": args.fact})


def cmd_check_consistency(args):
    """Reconcile the knowledge graph against the fact graph and the agendas."""
    with get_driver() as driver:
        facts = _campaign_facts(driver, args.campaign)
        edges = _flatten_edges(_knowledge_edges(driver, args.campaign))
        agendas = _campaign_agendas(driver, args.campaign)
        reqs = _agenda_requirements(driver, args.campaign)
        all_beats = _campaign_beats(driver, args.campaign)
        camp = _get_entity(driver, "myth-campaign", args.campaign, ["myth-time-index"])
    now = camp.get("myth-time-index") if camp else None
    problems = eng.knowledge_violations(facts, edges)
    # a fact scheduled in the past that never got established
    for f in facts:
        if (f["status"] == "not-yet-true" and f["time_index"] is not None
                and now is not None and f["time_index"] <= now):
            problems.append({"kind": "overdue-fact", "fact": f["id"],
                             "statement": f["statement"],
                             "detail": "due by the world clock but still not-yet-true"})
    # An established fact nobody holds is usually a missed edge rather than a
    # secret: the graph only knows what the GM remembered to write, and after
    # a long scene that is not everything. Reported separately from problems,
    # because GM-side truths that genuinely nobody has discovered are legal.
    known_fact_ids = {e.get("fact") for e in edges}
    unheld = [f for f in facts
              if f["status"] == "established" and f["id"] not in known_fact_ids]

    beats = all_beats
    for f in eng.orphaned_futures(facts, beats):
        problems.append({"kind": "orphaned-future", "fact": f["id"],
                         "statement": f["statement"],
                         "detail": "no live beat will ever establish this -- "
                                   "run `cascade` to retire it"})
    for b in eng.beats_to_cancel(
            [{"id": a["id"], "status": a["status"]} for a in agendas], beats):
        problems.append({"kind": "beat-on-dead-agenda", "beat": b["id"],
                         "statement": b["title"],
                         "detail": "still pending, but its agenda is no longer "
                                   "being pursued -- run `cascade`"})
    holders = {a["id"]: (a.get("holder") or {}).get("id") for a in agendas}
    for a in agendas:
        a["holder_id"] = holders.get(a["id"])
    ready = eng.agendas_to_activate(
        [{"id": a["id"], "title": a["title"], "status": a["status"],
          "holder": a["holder_id"], "priority": a["priority"]} for a in agendas],
        reqs, edges)
    out({"success": True, "facts": len(facts), "knowledge_edges": len(edges),
         "problems": problems, "ok": not problems,
         "established_but_unheld": [{"id": f["id"], "statement": f["statement"]}
                                    for f in unheld],
         "agendas_ready_to_activate": [{"id": a["id"], "title": a["title"]} for a in ready]})


# ---------------------------------------------------------------------------
# Rules graph (global, faceted, queryable -- mirrors the lore pattern)
# ---------------------------------------------------------------------------

RULES_DIR = os.path.join(_SKILL_DIR, "rules")
RULE_ATTRS = ["description", "content", "myth-rule-category", "myth-rule-kind",
              "myth-rule-domain", "myth-rule-topic"]


def _get_or_create_facet(driver, dim, value):
    """Return the id of the myth-rule-facet for (dim, value); create if absent."""
    rows = _fetch(driver, f'''
        match $f isa myth-rule-facet, has name "{escape_string(value)}",
              has myth-facet-dim "{escape_string(dim)}";
        fetch {{ "id": $f.id }};''')
    if rows:
        return rows[0]["id"]
    fid = generate_id("myth-facet")
    _write(driver, f'''insert $f isa myth-rule-facet,
        has id "{fid}", has name "{escape_string(value)}",
        has myth-facet-dim "{escape_string(dim)}";''')
    return fid


def _rule_facets(driver, rule_id):
    """All (dim, value) facets tagged on a rule."""
    return _fetch(driver, f'''
        match
          $r isa myth-rule, has id "{escape_string(rule_id)}";
          $rel isa myth-rule-tagged, links (rule: $r, facet: $f);
          $f has myth-facet-dim $d, has name $v;
        fetch {{ "dim": $d, "value": $v }};''')


def _rule_links(driver, rule_id):
    """One hop of linked rules in both directions (id + title)."""
    fwd = _fetch(driver, f'''
        match
          $r isa myth-rule, has id "{escape_string(rule_id)}";
          $rel isa myth-rule-link, links (rule: $r, linked: $o);
          $o has id $i, has name $n;
        fetch {{ "id": $i, "title": $n }};''')
    rev = _fetch(driver, f'''
        match
          $r isa myth-rule, has id "{escape_string(rule_id)}";
          $rel isa myth-rule-link, links (rule: $o, linked: $r);
          $o has id $i, has name $n;
        fetch {{ "id": $i, "title": $n }};''')
    seen, out_links = set(), []
    for r in fwd + rev:
        if r["id"] not in seen:
            seen.add(r["id"])
            out_links.append(r)
    return out_links


def cmd_load_rules(args):
    """Walk rules/<domain>/*.md (frontmatter + body), (re)build the rules graph.

    Idempotent: clears all myth-rule / facets / tag / link relations, then
    reloads from disk. Rules are GLOBAL (no campaign membership).
    """
    import campaign_io
    rules_dir = args.dir or RULES_DIR
    if not os.path.isdir(rules_dir):
        fail(f"No rules directory: {rules_dir}")

    # Gather every markdown file that carries a frontmatter `id`.
    pieces = []
    for root, _dirs, files in os.walk(rules_dir):
        for fn in sorted(files):
            if not fn.endswith(".md"):
                continue
            meta, body = campaign_io._parse_md(os.path.join(root, fn))
            if not meta.get("id"):
                continue
            meta["content"] = body
            pieces.append(meta)

    if not pieces:
        fail(f"No rule files with frontmatter `id` under {rules_dir}")

    with get_driver() as driver:
        # Clear the existing graph (data matches with bound vars -- safe).
        for rel in ("myth-rule-tagged", "myth-rule-link"):
            _write(driver, f"match $x isa {rel}; delete $x;")
        for ent in ("myth-rule", "myth-rule-facet"):
            _write(driver, f"match $x isa {ent}; delete $x;")

        ts = get_timestamp()
        for p in pieces:
            rid = p["id"]
            q = f'''insert $r isa myth-rule,
                has id "{escape_string(rid)}",
                has name "{escape_string(p.get("title", rid))}",
                has myth-rule-category "{escape_string(p.get("category", p.get("domain", "core")))}",
                has myth-rule-kind "{escape_string(p.get("kind", "reference"))}",
                has myth-rule-domain "{escape_string(p.get("domain", p.get("category", "core")))}",
                has myth-rule-topic "{escape_string(p.get("topic", ""))}",
                has created-at {ts}'''
            if p.get("summary"):
                q += f', has description "{escape_string(p["summary"])}"'
            if p.get("content"):
                q += f', has content "{escape_string(p["content"])}"'
            q += ";"
            _write(driver, q)

            for dim, values in (p.get("facets") or {}).items():
                for value in (values if isinstance(values, list) else [values]):
                    fid = _get_or_create_facet(driver, dim, str(value))
                    _write(driver, f'''
                        match
                          $r isa myth-rule, has id "{escape_string(rid)}";
                          $f isa myth-rule-facet, has id "{escape_string(fid)}";
                        insert (rule: $r, facet: $f) isa myth-rule-tagged;''')

        # Links in a second pass, once every rule exists.
        link_count = 0
        for p in pieces:
            rid = p["id"]
            for target in (p.get("links") or []):
                if _fetch(driver, f'''
                        match $t isa myth-rule, has id "{escape_string(target)}";
                        fetch {{ "id": $t.id }};'''):
                    _write(driver, f'''
                        match
                          $r isa myth-rule, has id "{escape_string(rid)}";
                          $t isa myth-rule, has id "{escape_string(target)}";
                        insert (rule: $r, linked: $t) isa myth-rule-link;''')
                    link_count += 1

    out({"success": True, "rules_loaded": len(pieces), "links_loaded": link_count})


def cmd_list_rules(args):
    """Lean rule index -- a TOC by domain/topic. Cheap; load once for orientation.

    By default each entry is just id/title/domain/topic/kind (no facets), so the
    whole 100+-piece index stays small (~1k tokens). Pass --facets to include
    each piece's facet tags (heavier), or --dim/--value to filter by a facet.
    """
    want_facets = args.facets or (args.dim and args.value)
    with get_driver() as driver:
        rows = _fetch(driver, '''
            match $r isa myth-rule, has id $i, has name $n,
                  has myth-rule-domain $dm,
                  has myth-rule-topic $tp, has myth-rule-kind $k;
            fetch { "id": $i, "title": $n,
                    "domain": $dm, "topic": $tp, "kind": $k };''')
        # category == domain by construction, so it isn't emitted; filter on domain.
        if args.category:
            rows = [r for r in rows if r["domain"] == args.category]
        if want_facets:
            for r in rows:
                facets = {}
                for f in _rule_facets(driver, r["id"]):
                    facets.setdefault(f["dim"], []).append(f["value"])
                r["facets"] = facets
    if args.dim and args.value:
        rows = [r for r in rows
                if args.value in (r["facets"].get(args.dim) or [])]
    out({"success": True, "count": len(rows),
         "rules": sorted(rows, key=lambda r: (r["domain"], r["topic"], r["title"]))})


def cmd_get_rule(args):
    """One rule piece in full; with --linked, append its linked neighbours."""
    with get_driver() as driver:
        r = _get_entity(driver, "myth-rule", args.id, RULE_ATTRS)
        if not r:
            fail(f"No rule '{args.id}'")
        facets = {}
        for f in _rule_facets(driver, args.id):
            facets.setdefault(f["dim"], []).append(f["value"])
        r["facets"] = facets
        if args.linked:
            neighbours = []
            for nb in _rule_links(driver, args.id):
                full = _get_entity(driver, "myth-rule", nb["id"], RULE_ATTRS)
                if full:
                    neighbours.append(full)
            r["linked"] = neighbours
    out({"success": True, "rule": r})


def _facet_vocabulary(driver):
    """Every facet dimension in the rules graph and the values it takes."""
    vocab = {}
    for row in _fetch(driver, 'match $f isa myth-rule-facet, has myth-facet-dim $d, '
                              'has name $v; fetch { "dim": $d, "value": $v };'):
        vocab.setdefault(row["dim"], set()).add(row["value"])
    return {d: sorted(vs) for d, vs in sorted(vocab.items())}


def cmd_list_facets(args):
    """The facet vocabulary, so a query can be composed without guessing.

    query-rules used to accept any dim=value at all: an unknown facet simply
    matched nothing and the call returned success with an empty list, which
    reads exactly like "no such rule exists" and is how `effect=bypass-armour`
    (with a u) looked like a settled question for a while.
    """
    with get_driver() as driver:
        vocab = _facet_vocabulary(driver)
    if getattr(args, "dim", None):
        if args.dim not in vocab:
            fail("No facet dimension '%s'. Dimensions: %s"
                 % (args.dim, ", ".join(vocab)))
        out({"success": True, "dim": args.dim, "values": vocab[args.dim]})
    out({"success": True,
         "dimensions": {d: len(v) for d, v in vocab.items()},
         "facets": vocab})


def cmd_query_rules(args):
    """Live faceted fetch: pass --facet dim=value (repeatable). Rules matching
    more of the situation's facets rank first; --linked adds one link hop."""
    wanted = []
    for spec in (args.facet or []):
        if "=" not in spec:
            fail(f"Bad --facet '{spec}' (expected dim=value)")
        dim, _, value = spec.partition("=")
        wanted.append((dim.strip(), value.strip()))
    if not wanted:
        fail("Provide at least one --facet dim=value")

    with get_driver() as driver:
        # An unknown dim or value used to match nothing and return success,
        # which is indistinguishable from "there is no such rule". Check the
        # vocabulary first and say which half was wrong.
        vocab = _facet_vocabulary(driver)
        for dim, value in wanted:
            if dim not in vocab:
                fail("No facet dimension '%s'. Dimensions: %s"
                     % (dim, ", ".join(vocab)))
            if value not in vocab[dim]:
                fail("No value '%s' in facet dimension '%s'. Values: %s"
                     % (value, dim, ", ".join(vocab[dim])))

        scores = {}
        for dim, value in wanted:
            for row in _fetch(driver, f'''
                    match
                      $f isa myth-rule-facet, has name "{escape_string(value)}",
                          has myth-facet-dim "{escape_string(dim)}";
                      $rel isa myth-rule-tagged, links (rule: $r, facet: $f);
                      $r has id $i;
                    fetch {{ "id": $i }};'''):
                scores[row["id"]] = scores.get(row["id"], 0) + 1

        # Matching is ANY by default, ranked by how many facets a rule hits --
        # which is what the code has always done, whatever the docs said.
        # --match all narrows it to rules carrying every facet asked for.
        if getattr(args, "match", "any") == "all":
            scores = {rid: n for rid, n in scores.items() if n == len(wanted)}
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        if args.limit and args.limit > 0:
            ranked = ranked[:args.limit]

        results = []
        seen = set(rid for rid, _ in ranked)
        for rid, score in ranked:
            full = _get_entity(driver, "myth-rule", rid, RULE_ATTRS)
            if not full:
                continue
            full["match_score"] = score
            facets = {}
            for f in _rule_facets(driver, rid):
                facets.setdefault(f["dim"], []).append(f["value"])
            full["facets"] = facets
            results.append(full)

        linked = []
        if args.linked:
            for rid, _ in ranked:
                for nb in _rule_links(driver, rid):
                    if nb["id"] not in seen:
                        seen.add(nb["id"])
                        full = _get_entity(driver, "myth-rule", nb["id"], RULE_ATTRS)
                        if full:
                            linked.append(full)

    out({"success": True, "facets": [f"{d}={v}" for d, v in wanted],
         "match": getattr(args, "match", "any"),
         "count": len(results), "rules": results, "linked": linked})


def cmd_get_context(args):
    """Everything needed to resume a campaign: campaign state, PCs (full sheets),
    NPCs (names), locations, factions, active encounters, recent events."""
    with get_driver() as driver:
        camp = _get_entity(driver, "myth-campaign", args.campaign,
                           ["description", "content", "myth-game-date",
                            "myth-current-scene", "myth-session-number",
                            "myth-time-index"])
        if not camp:
            fail(f"No campaign '{args.campaign}'")

        def members(entity_type, extra=""):
            return _fetch(driver, f'''
                match
                  $camp isa myth-campaign, has id "{escape_string(args.campaign)}";
                  (campaign: $camp, element: $e) isa myth-campaign-membership;
                  $e isa {entity_type}, has id $i, has name $n{extra};
                fetch {{ "id": $i, "name": $n }};''')

        chars = _fetch(driver, f'''
            match
              $camp isa myth-campaign, has id "{escape_string(args.campaign)}";
              (campaign: $camp, element: $c) isa myth-campaign-membership;
              $c isa myth-character, has id $i, has name $n,
                 has myth-char-type $t, has myth-status $s;
            fetch {{ "id": $i, "name": $n, "type": $t, "status": $s }};''')
        compact = getattr(args, "compact", False)
        active_pcs = [r for r in chars if r["type"] == "pc" and r["status"] == "active"]
        if compact:
            pcs = [_combat_card(_load_character(driver, r["id"])) for r in active_pcs]
        else:
            pcs = [_load_character(driver, r["id"]) for r in active_pcs]

        # Where each PC is standing. Carried on the combat card because staging
        # is decided by presence: a PC whose location never changes is a PC the
        # GM has stopped running, and that has to be visible every scene rather
        # than discoverable only by asking.
        for card in pcs:
            rows = _fetch(driver, f"""
                match
                  $c isa myth-character, has id "{escape_string(card['id'])}";
                  (located: $c, location: $l) isa myth-presence;
                  $l has id $li, has name $ln;
                fetch {{ "id": $li, "name": $ln }};""")
            card["location"] = rows[0]["id"] if rows else None
            card["location_name"] = rows[0]["name"] if rows else None
        npcs = [r for r in chars if r["type"] != "pc"]

        encounters = _fetch(driver, f'''
            match
              $camp isa myth-campaign, has id "{escape_string(args.campaign)}";
              (campaign: $camp, element: $e) isa myth-campaign-membership;
              $e isa myth-encounter, has id $i, has name $n, has myth-encounter-status $s;
            fetch {{ "id": $i, "name": $n, "status": $s }};''')

        events = _fetch(driver, f'''
            match
              $camp isa myth-campaign, has id "{escape_string(args.campaign)}";
              (campaign: $camp, element: $e) isa myth-campaign-membership;
              $e isa myth-game-event, has id $i, has description $d,
                 has myth-event-type $t, has created-at $ts;
            fetch {{ "id": $i, "summary": $d, "type": $t, "at": $ts }};''')
        recent_n = 5 if compact else 15
        recent = sorted(events, key=lambda r: str(r["at"]))[-recent_n:]

        result = {"success": True, "campaign": camp, "player_characters": pcs,
                  "npcs": npcs, "locations": members("myth-location"),
                  "factions": members("myth-faction"),
                  "encounters": [e for e in encounters if e["status"] == "active"],
                  "recent_events": recent}

        # The living world: what is in motion, and what is already due. Kept
        # small enough for compact mode -- a resumed session must know what the
        # world is mid-way through doing, not just where the party is standing.
        agendas = [a for a in _campaign_agendas(driver, args.campaign)
                   if a["status"] in ("active", "pending")]
        agendas.sort(key=lambda a: (-a["priority"], a["title"]))
        result["agendas"] = [
            {"id": a["id"], "title": a["title"],
             "holder": (a.get("holder") or {}).get("name"),
             "clock": f'{a["clock"]["filled"]}/{a["clock"]["size"]}',
             "priority": a["priority"], "status": a["status"]}
            for a in agendas]
        now = camp.get("myth-time-index")
        if now is not None:
            clocks = {a["id"]: a["clock"]["filled"] for a in agendas}
            active_ids = {a["id"] for a in agendas}
            pending = [b for b in _campaign_beats(driver, args.campaign)
                       if b["agenda"] is None or b["agenda"] in active_ids]
            pc_ids, pc_places = _pc_presence(driver, args.campaign)
            result["world_clock"] = eng.format_time_key(now)
            result["due_beats"] = [
                {"id": b["id"], "title": b["title"], "when": b["when"],
                 "place": b["place_name"], "agenda": b["agenda_title"],
                 "staging": eng.beat_staging(b, pc_places, pc_ids)}
                for b in eng.due_beats(pending, now, clocks)]

        # The lore index is a big static block. In compact mode skip it
        # entirely (use list-lore on demand); only emit it for full context.
        if not compact:
            lore = _fetch(driver, f'''
                match
                  $camp isa myth-campaign, has id "{escape_string(args.campaign)}";
                  (campaign: $camp, element: $l) isa myth-campaign-membership;
                  $l isa myth-lore, has id $i, has name $n,
                     has myth-lore-category $c, has myth-lore-visibility $v;
                fetch {{ "id": $i, "title": $n, "category": $c, "visibility": $v }};''')
            result["lore_index"] = sorted(lore, key=lambda r: (r["category"], r["title"]))

    out(result)


# ---------------------------------------------------------------------------
# Campaign publishing (export / import file trees) -- see campaign_io.py
# ---------------------------------------------------------------------------

def cmd_export_campaign(args):
    import campaign_io
    campaign_io.cmd_export(args)


def cmd_import_campaign(args):
    import campaign_io
    campaign_io.cmd_import(args)


# Everything linked into a campaign by myth-campaign-membership. Deleting these
# also removes the relations they play a role in, since a relation with no
# remaining roleplayers does not survive.
CAMPAIGN_MEMBER_TYPES = [
    "myth-game-event", "myth-encounter", "myth-beat", "myth-agenda", "myth-fact",
    "myth-lore", "myth-character", "myth-creature-template", "myth-location",
    "myth-faction",
]


def cmd_delete_campaign(args):
    """Permanently remove a campaign and everything linked to it."""
    with get_driver() as driver:
        camp = _get_entity(driver, "myth-campaign", args.campaign,
                           ["myth-game-date", "myth-session-number"])
        if not camp:
            fail(f"No campaign '{args.campaign}'")

        cid = escape_string(args.campaign)
        counts = {}
        for etype in CAMPAIGN_MEMBER_TYPES:
            rows = _fetch(driver, f"""
                match
                  $c isa myth-campaign, has id "{cid}";
                  (campaign: $c, element: $e) isa myth-campaign-membership;
                  $e isa {etype}, has id $ei;
                fetch {{ "ei": $ei }};""")
            counts[etype] = len(rows)

        if not args.yes:
            fail(f"Refusing to delete '{camp['name']}' ({sum(counts.values())} elements, "
                 f"{counts.get('myth-game-event', 0)} journal events) without --yes")

        for etype in CAMPAIGN_MEMBER_TYPES:
            if not counts[etype]:
                continue
            _write(driver, f"""
                match
                  $c isa myth-campaign, has id "{cid}";
                  (campaign: $c, element: $e) isa myth-campaign-membership;
                  $e isa {etype};
                delete $e;""")
        _write(driver, f'match $c isa myth-campaign, has id "{cid}"; delete $c;')

    out({"success": True, "deleted": args.campaign, "name": camp["name"],
         "elements": {k: v for k, v in counts.items() if v}})


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Flag ergonomics
# ---------------------------------------------------------------------------
# The CLI grew one command at a time and the flag names drifted: a fact is
# --id in get-fact and --fact in who-knows; a location is --location in
# move-character and --at in add-beat; and --at means an ISO timestamp in
# log-event but a location id in list-beats. Rather than rename anything and
# break the campaign package, every canonical flag gains the alias somebody
# will actually reach for, and the alias is folded onto the canonical name
# before dispatch.

ALIASES = {
    # command: {alias: canonical dest}
    "get-character":     {"--character": "id"},
    "update-character":  {"--character": "id"},
    "brief":             {"--character": "id"},
    "roll-skill":        {"--character": "id"},
    "apply-damage":      {"--character": "id"},
    "heal":              {"--character": "id"},
    "move-character":    {"--character": "id", "--to": "location"},
    "character-view":    {"--character": "id"},
    "join-faction":      {"--character": "id"},
    "get-fact":          {"--fact": "id"},
    "establish-fact":    {"--fact": "id"},
    "supersede-fact":    {"--fact": "id"},
    "revise-fact":       {"--fact": "id"},
    "get-agenda":        {"--agenda": "id"},
    "advance-agenda":    {"--agenda": "id"},
    "update-agenda":     {"--agenda": "id"},
    "set-agenda-status": {"--agenda": "id"},
    "revise-beat":       {"--beat": "id", "--place": "at"},
    "fire-beat":         {"--beat": "id"},
    "add-beat":          {"--place": "at"},
    "list-beats":        {"--place": "at"},
    "get-lore":          {"--lore": "id"},
    "link-lore":         {"--lore": "id"},
    "update-lore":       {"--lore": "id"},
    "update-location":   {"--location": "id"},
    "update-faction":    {"--faction": "id"},
    "log-event":         {"--when": "at"},
    "learn":             {"--character": "knower"},
    "forget":            {"--character": "knower"},
    "who-knows":         {"--id": "fact"},
    "add-consequence":   {"--id": "fact"},
    "require-fact":      {"--id": "fact"},
    "tick":              {"--when": "to"},
}

# Commands that genuinely need a campaign. Held as a set rather than
# required=True on each parser, so that inference gets a chance to run first.
NEEDS_CAMPAIGN = {
    "get-campaign", "set-scene", "update-campaign", "create-character",
    "import-characters", "export-characters", "list-characters", "add-location",
    "add-faction", "add-template", "spawn", "log-event", "add-lore", "list-lore",
    "add-agenda", "list-agendas", "advance-agenda", "set-agenda-status",
    "add-beat", "list-beats", "fire-beat", "tick", "add-fact", "list-facts",
    "get-fact", "establish-fact", "who-knows", "character-view", "supersede-fact",
    "cascade", "check-consistency", "get-log", "get-context", "export-campaign",
    "delete-campaign", "start-encounter",
}


# Canonical flags relaxed from required=True because an alias may supply them.
# main() enforces them again once aliases have been folded in.
RELAXED_REQUIRED = {}


def _install_aliases(sub):
    """Add the alias flags, hidden from --help so the canonical name stays the
    one people learn.

    Adding an alias means the canonical flag can no longer be required by
    argparse -- it would reject the call before the alias is ever read -- so
    it is relaxed here and re-enforced after resolution.
    """
    for cmd, mapping in ALIASES.items():
        parser = sub.choices.get(cmd)
        if parser is None:
            continue
        existing = {o for a in parser._actions for o in a.option_strings}
        for alias, canonical in mapping.items():
            if alias in existing:
                continue
            parser.add_argument(alias, dest="_alias_" + canonical.replace("-", "_"),
                                help=argparse.SUPPRESS)
            for action in parser._actions:
                if action.dest == canonical and action.required:
                    action.required = False
                    RELAXED_REQUIRED.setdefault(cmd, set()).add(canonical)


def _resolve_aliases(args):
    """Fold any alias value onto its canonical attribute, and complain if both
    were given and disagree."""
    for key in [k for k in vars(args) if k.startswith("_alias_")]:
        canonical = key[len("_alias_"):]
        val = getattr(args, key)
        delattr(args, key)
        if val is None:
            continue
        current = getattr(args, canonical, None)
        if current is not None and current != val:
            fail("--%s and its alias were both given and they disagree: %r vs %r"
                 % (canonical, current, val))
        setattr(args, canonical, val)


CAMPAIGN_LIST_QUERY = (
    "match $c isa myth-campaign, has id $i, has name $n; "
    'fetch { "id": $i, "name": $n };'
)


def _resolve_campaign(args):
    """Fill --campaign in from MYTH_CAMPAIGN, or from the only campaign there
    is. A GM running one game should never have to type the id."""
    if not hasattr(args, "campaign") or getattr(args, "campaign", None):
        return
    env = os.environ.get("MYTH_CAMPAIGN")
    if env:
        args.campaign = env
        return
    with get_driver() as driver:
        rows = _fetch(driver, CAMPAIGN_LIST_QUERY)
    if len(rows) == 1:
        args.campaign = rows[0]["id"]
        return
    if not rows:
        fail("--campaign is required and there are no campaigns yet")
    listing = "; ".join("%s (%s)" % (r["id"], r["name"]) for r in rows)
    fail("--campaign is required. Set MYTH_CAMPAIGN, or pass one of: " + listing)



def build_parser():
    p = argparse.ArgumentParser(prog="mythras-gm",
                                description="Mythras Imperative GM engine with TypeDB persistence")
    sub = p.add_subparsers(dest="command")

    s = sub.add_parser("create-campaign")
    s.add_argument("--name", required=True)
    s.add_argument("--description")
    s.add_argument("--game-date")

    s = sub.add_parser("get-campaign")
    s.add_argument("--campaign", required=True)

    s = sub.add_parser("set-scene")
    s.add_argument("--campaign", required=True)
    s.add_argument("--scene", required=True)
    s.add_argument("--game-date")

    s = sub.add_parser("update-campaign",
                       help="Edit campaign name, description, game-date, session number or world clock")
    s.add_argument("--campaign", required=True)
    s.add_argument("--name")
    s.add_argument("--description")
    s.add_argument("--game-date", help="prose date shown at the top of the save")
    s.add_argument("--session-number", type=int)
    s.add_argument("--time-index", type=int, help="numeric world clock; prefer tick in play")

    sub.add_parser("list-campaigns")

    s = sub.add_parser("create-character")
    s.add_argument("--campaign")
    s.add_argument("--name", required=True)
    s.add_argument("--type", default="pc", choices=["pc", "npc", "creature"])
    s.add_argument("--species", default="avian",
                   choices=["avian", "humanoid", "winged-quadruped"])
    s.add_argument("--stats", help='JSON {"STR":11,...}')
    s.add_argument("--roll", action="store_true")
    s.add_argument("--skills", help="JSON skill overrides/additions")
    s.add_argument("--combat-styles", help='JSON {"Style name": value}')
    s.add_argument("--equipment", help="JSON weapon/gear list")
    s.add_argument("--passions", help="JSON passions")
    s.add_argument("--armor", help='JSON {"Chest":4,...} AP by location')
    s.add_argument("--description")
    s.add_argument("--narrative")

    s = sub.add_parser("get-character")
    s.add_argument("--id", required=True)
    s.add_argument("--compact", action="store_true",
                   help="Combat-card projection (state only; omits skills, "
                        "equipment, spells, prose)")

    s = sub.add_parser("import-characters",
                       help="Import characters from a Mythras-family JSON sheet file")
    s.add_argument("--file", required=True,
                   help="JSON file: a sheet object or list of sheets "
                        "(stats/skills as list-of-dicts or flat dicts)")
    s.add_argument("--campaign")
    s.add_argument("--type", default="pc", choices=["pc", "npc", "creature"])

    s = sub.add_parser("export-characters",
                       help="Export characters to Roll20-upload JSON format")
    s.add_argument("--id", help="single character id")
    s.add_argument("--campaign", help="export all characters in a campaign")
    s.add_argument("--type", help="filter by pc/npc/creature when exporting a campaign")
    s.add_argument("--output", help="write to file instead of stdout")

    s = sub.add_parser("list-characters")
    s.add_argument("--campaign", required=True)
    s.add_argument("--type")

    s = sub.add_parser("brief",
                       help="How to play an NPC: bearing, speech, tell, wants. Read before they speak.")
    s.add_argument("--id", required=True)

    s = sub.add_parser("update-character")
    s.add_argument("--id", required=True)
    s.add_argument("--skills")
    s.add_argument("--equipment")
    s.add_argument("--passions")
    s.add_argument("--fatigue")
    s.add_argument("--luck", type=int)
    s.add_argument("--magic-current", type=int, help="current magic points")
    s.add_argument("--experience-rolls", type=int)
    s.add_argument("--actor-notes",
                   help="how to PLAY them: bearing, speech, tell | wants, won't, because")
    s.add_argument("--extras", help="JSON merged into the extras bag")
    s.add_argument("--extras-replace", action="store_true",
                   help="replace the extras bag instead of merging into it")
    s.add_argument("--status")
    s.add_argument("--description", help="one-line description (e.g. pronouns, role)")
    s.add_argument("--narrative", help="full rich-text backstory (stored as content)")
    s.add_argument("--spells", help="JSON spell lists, e.g. {\"binding\": [...], \"arcane\": [...]}")

    s = sub.add_parser("apply-damage")
    s.add_argument("--id", required=True)
    s.add_argument("--location", required=True)
    s.add_argument("--damage", type=int, required=True)
    s.add_argument("--ignore-armor", action="store_true")

    s = sub.add_parser("heal")
    s.add_argument("--id", required=True)
    s.add_argument("--location", required=True)
    s.add_argument("--amount", type=int, required=True)

    s = sub.add_parser("roll")
    s.add_argument("--dice", required=True)

    s = sub.add_parser("roll-skill")
    s.add_argument("--id", required=True)
    s.add_argument("--skill", required=True)
    s.add_argument("--difficulty", default="standard")
    s.add_argument("--augment", help="passion name to augment with (+20%% of value)")

    s = sub.add_parser("roll-opposed")
    s.add_argument("--id-a", required=True)
    s.add_argument("--skill-a", required=True)
    s.add_argument("--id-b", required=True)
    s.add_argument("--skill-b", required=True)
    s.add_argument("--difficulty-a", default="standard")
    s.add_argument("--difficulty-b", default="standard")

    s = sub.add_parser("start-encounter")
    s.add_argument("--campaign", required=True)
    s.add_argument("--name", required=True)
    s.add_argument("--description")

    s = sub.add_parser("add-combatant")
    s.add_argument("--encounter", required=True)
    s.add_argument("--character", required=True)

    s = sub.add_parser("roll-initiative")
    s.add_argument("--encounter", required=True)

    s = sub.add_parser("resolve-attack")
    s.add_argument("--encounter", required=True)
    s.add_argument("--attacker", required=True)
    s.add_argument("--defender", required=True)
    s.add_argument("--weapon")
    s.add_argument("--style")
    s.add_argument("--defense", default="parry", choices=["parry", "evade", "none"])
    s.add_argument("--defender-skill")
    s.add_argument("--parry-weapon")
    s.add_argument("--attacker-difficulty", default="standard")
    s.add_argument("--defender-difficulty", default="standard")
    s.add_argument("--location", help="override hit location (Choose Location effect)")
    s.add_argument("--no-ap", action="store_true", help="skip Action Point accounting")

    s = sub.add_parser("attack-roll",
                       help="Roll an attack and STOP so the winner can choose special effects")
    s.add_argument("--encounter", required=True)
    s.add_argument("--attacker", required=True)
    s.add_argument("--defender", required=True)
    s.add_argument("--weapon")
    s.add_argument("--style")
    s.add_argument("--defense", default="parry", choices=["parry", "evade", "none"])
    s.add_argument("--defender-skill")
    s.add_argument("--parry-weapon")
    s.add_argument("--attacker-difficulty", default="standard")
    s.add_argument("--defender-difficulty", default="standard")
    s.add_argument("--prone", action="store_true", help="winner is prone (gates Arise)")
    s.add_argument("--no-ap", action="store_true")

    s = sub.add_parser("resolve-effects",
                       help="Apply the chosen special effects, then roll damage")
    s.add_argument("--encounter", required=True)
    s.add_argument("--effect", action="append",
                   help="effect id; repeat for each taken ('none' for no effects)")
    s.add_argument("--location", help="required when choose-location is taken")

    s = sub.add_parser("next-round")
    s.add_argument("--encounter", required=True)

    s = sub.add_parser("get-encounter")
    s.add_argument("--encounter", required=True)

    s = sub.add_parser("end-encounter")
    s.add_argument("--encounter", required=True)
    s.add_argument("--summary")

    s = sub.add_parser("add-location")
    s.add_argument("--campaign", required=True)
    s.add_argument("--name", required=True)
    s.add_argument("--type")
    s.add_argument("--description")
    s.add_argument("--narrative")

    s = sub.add_parser("add-faction")
    s.add_argument("--campaign", required=True)
    s.add_argument("--name", required=True)
    s.add_argument("--description")
    s.add_argument("--narrative")

    s = sub.add_parser("update-location", help="Update a location's text, name or type")
    s.add_argument("--id", required=True)
    s.add_argument("--name")
    s.add_argument("--summary")
    s.add_argument("--narrative")
    s.add_argument("--type")

    s = sub.add_parser("update-faction", help="Update a faction's text or name")
    s.add_argument("--id", required=True)
    s.add_argument("--name")
    s.add_argument("--summary")
    s.add_argument("--narrative")

    s = sub.add_parser("add-template")
    s.add_argument("--campaign")
    s.add_argument("--name", required=True)
    s.add_argument("--stats", required=True)
    s.add_argument("--species", default="avian",
                   choices=["avian", "humanoid", "winged-quadruped"])
    s.add_argument("--skills")
    s.add_argument("--combat-styles")
    s.add_argument("--equipment")
    s.add_argument("--armor")
    s.add_argument("--description")
    s.add_argument("--narrative")

    s = sub.add_parser("spawn")
    s.add_argument("--template", required=True)
    s.add_argument("--name", required=True)
    s.add_argument("--campaign")

    s = sub.add_parser("move-character")
    s.add_argument("--id", required=True)
    s.add_argument("--location", required=True)

    s = sub.add_parser("join-faction")
    s.add_argument("--id", required=True)
    s.add_argument("--faction", required=True)

    s = sub.add_parser("log-event")
    s.add_argument("--campaign", required=True)
    s.add_argument("--type", required=True,
                   choices=["scene", "combat", "skill-roll", "decision",
                            "gm-note", "session-start", "session-end"])
    s.add_argument("--summary", required=True)
    s.add_argument("--title", help="event name; defaults to the first 80 "
                                   "characters of --summary")
    s.add_argument("--narrative")
    s.add_argument("--session", type=int)
    s.add_argument("--involves", help="comma-separated entity ids")
    s.add_argument("--at", help="ISO timestamp (YYYY-MM-DDTHH:MM:SS) to record the "
                               "event at; defaults to now. Use to place an event in "
                               "story order rather than wall-clock order.")

    s = sub.add_parser("add-lore", help="Add a worldbuilding lore entry to a campaign")
    s.add_argument("--campaign", required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--category", required=True,
                   help="free-form: cosmology, species, culture, magic-system, careers, "
                        "history, religion, economy, bestiary, house-rules, ...")
    s.add_argument("--summary", help="one-line description")
    s.add_argument("--narrative", help="full rich-text content (markdown welcome)")
    s.add_argument("--visibility", default="player", choices=["player", "gm"])
    s.add_argument("--about", help="comma-separated entity ids this lore concerns")

    s = sub.add_parser("list-lore", help="Index of lore entries for a campaign")
    s.add_argument("--campaign", required=True)
    s.add_argument("--category")
    s.add_argument("--visibility", choices=["player", "gm"])

    s = sub.add_parser("get-lore", help="Full text of one lore entry")
    s.add_argument("--id", required=True)

    s = sub.add_parser("link-lore", help="Link a lore entry to another entity")
    s.add_argument("--id", required=True)
    s.add_argument("--subject", required=True)

    s = sub.add_parser("update-lore", help="Update a lore entry's text or visibility")
    s.add_argument("--id", required=True)
    s.add_argument("--narrative")
    s.add_argument("--summary")
    s.add_argument("--visibility", choices=["player", "gm"])

    # --- Living world (agendas, clocks, beats) ---
    s = sub.add_parser("add-agenda",
                       help="Create a goal held by an NPC or faction, with a progress clock")
    s.add_argument("--campaign", required=True)
    s.add_argument("--holder", required=True,
                   help="character or faction id that wants this")
    s.add_argument("--title", required=True)
    s.add_argument("--goal", help="one-line statement of what they want")
    s.add_argument("--clock", type=int, default=6, help="segments to completion")
    s.add_argument("--filled", type=int, default=0, help="segments already filled")
    s.add_argument("--priority", type=int, default=3,
                   help="1-5; who acts first when agendas collide")
    s.add_argument("--status", default="active",
                   choices=["pending", "active", "achieved", "thwarted",
                            "abandoned", "dormant"])
    s.add_argument("--target", help="comma-separated ids this agenda is aimed at")
    s.add_argument("--narrative",
                   help="how they pursue it, and what would change their mind")

    s = sub.add_parser("list-agendas", help="Who wants what, and how close they are")
    s.add_argument("--campaign", required=True)
    s.add_argument("--holder")
    s.add_argument("--status")
    s.add_argument("--compact", action="store_true")

    s = sub.add_parser("get-agenda", help="One agenda in full, with its beats")
    s.add_argument("--id", required=True)

    s = sub.add_parser("advance-agenda", help="Fill clock segments toward completion")
    s.add_argument("--id", required=True)
    s.add_argument("--by", type=int, default=1)
    s.add_argument("--campaign", help="required with --note")
    s.add_argument("--note", help="journal a gm-note recording the movement")
    s.add_argument("--complete-status", default="achieved",
                   help="status to set when the clock fills (default: achieved)")

    s = sub.add_parser("update-agenda",
                       help="Edit an agenda's text, clock size or priority")
    s.add_argument("--id", required=True)
    s.add_argument("--title")
    s.add_argument("--goal", help="one-line statement of what they want")
    s.add_argument("--narrative", help="how they pursue it, and what would change their mind")
    s.add_argument("--clock", type=int, help="new clock size")
    s.add_argument("--filled", type=int, help="new filled segments")
    s.add_argument("--priority", type=int, help="1-5; who acts first when agendas collide")

    s = sub.add_parser("set-agenda-status", help="Mark an agenda achieved/thwarted/etc")
    s.add_argument("--id", required=True)
    s.add_argument("--status", required=True,
                   choices=["pending", "active", "achieved", "thwarted",
                            "abandoned", "dormant"])
    s.add_argument("--campaign", help="required with --note")
    s.add_argument("--note")

    s = sub.add_parser("add-beat",
                       help="Schedule the next concrete thing an agenda produces")
    s.add_argument("--campaign", required=True)
    s.add_argument("--agenda", required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--when", help="time key, e.g. 'd-3/night' (day/watch)")
    s.add_argument("--trigger", default="time",
                   help="'time' (default) or 'clock>=N' to fire on agenda progress")
    s.add_argument("--at", help="location id where it happens")
    s.add_argument("--cast", help="comma-separated character/faction ids involved")
    s.add_argument("--onscreen-if", dest="onscreen_if",
                   help="prose note on what would put the PCs in the scene")
    s.add_argument("--summary")
    s.add_argument("--narrative")
    s.add_argument("--status", default="pending",
                   choices=["pending", "played", "narrated", "preempted",
                            "rewritten", "cancelled"])

    s = sub.add_parser("list-beats", help="What is about to happen, and where")
    s.add_argument("--campaign", required=True)
    s.add_argument("--pending", action="store_true")
    s.add_argument("--due", action="store_true", help="only beats already triggered")
    s.add_argument("--at", help="filter by location id")
    s.add_argument("--involving", help="filter by character id in the cast")

    s = sub.add_parser("revise-beat",
                       help="Bend a planned beat to match what play has made true")
    s.add_argument("--id", required=True)
    s.add_argument("--title")
    s.add_argument("--when")
    s.add_argument("--trigger")
    s.add_argument("--at", help="new location id ('' to clear)")
    s.add_argument("--cast", help="replacement cast ids ('' to clear)")
    s.add_argument("--onscreen-if", dest="onscreen_if")
    s.add_argument("--summary")
    s.add_argument("--narrative")
    s.add_argument("--status",
                   choices=["pending", "played", "narrated", "preempted",
                            "rewritten", "cancelled"])

    s = sub.add_parser("fire-beat", help="Resolve a beat and optionally journal it")
    s.add_argument("--id", required=True)
    s.add_argument("--outcome", required=True,
                   choices=["played", "narrated", "preempted", "rewritten",
                            "cancelled"])
    s.add_argument("--campaign", help="required with --log")
    s.add_argument("--log", action="store_true",
                   help="write a linked journal event for what happened")
    s.add_argument("--type", default="scene",
                   help="event type for --log (default: scene)")
    s.add_argument("--summary")
    s.add_argument("--narrative")
    s.add_argument("--session", type=int)
    s.add_argument("--advance", type=int,
                   help="also fill N segments on the parent agenda's clock")
    s.add_argument("--witnesses",
                   help="comma-separated ids who saw it and now know its facts")
    s.add_argument("--no-facts", dest="no_facts", action="store_true",
                   help="do not establish or retire this beat's facts")

    s = sub.add_parser("tick",
                       help="Advance world time; report what came due, onscreen or off")
    s.add_argument("--campaign", required=True)
    s.add_argument("--to", required=True, help="time key, e.g. 'd-2/dawn'")
    s.add_argument("--set-date", dest="set_date",
                   help="also update the campaign's prose game-date")
    s.add_argument("--rewind", action="store_true",
                   help="allow moving the world clock backwards")

    # --- Epistemics (facts, knowledge, reconciliation) ---
    s = sub.add_parser("add-fact",
                       help="Record one proposition about the world")
    s.add_argument("--campaign", required=True)
    s.add_argument("--statement", required=True,
                   help="the proposition, e.g. 'Santo carved Emmeralda'")
    s.add_argument("--title", help="short label (defaults to the statement)")
    s.add_argument("--status", default="not-yet-true",
                   choices=["not-yet-true", "established", "superseded"])
    s.add_argument("--truth", default="true", choices=["true", "false", "partial"],
                   help="a believed falsehood is still a fact node")
    s.add_argument("--when", help="time key it became true, e.g. 'd-3/night'")
    s.add_argument("--about", help="comma-separated ids this fact is about")
    s.add_argument("--origin", dest="origin",
                   help="id of the beat or event that produces it")
    s.add_argument("--narrative")
    s.add_argument("--learned-by", dest="learned_by",
                   help="comma-separated knower ids; only valid with "
                        "--status established, since nobody can know a future")
    s.add_argument("--certainty", default="knows",
                   choices=["knows", "believes", "suspects", "wrong"],
                   help="certainty for --learned-by")
    s.add_argument("--source", choices=["witnessed", "told", "deduced", "rumor"],
                   help="source for --learned-by")

    s = sub.add_parser("list-facts", help="The fact graph: what is true, and who knows")
    s.add_argument("--campaign", required=True)
    s.add_argument("--status")
    s.add_argument("--truth")
    s.add_argument("--about", help="filter to facts about this entity id")
    s.add_argument("--known-by", dest="known_by", help="filter to what this id knows")

    s = sub.add_parser("get-fact", help="One fact, with its knowers")
    s.add_argument("--id", required=True)
    s.add_argument("--campaign", help="include the list of who knows it")

    s = sub.add_parser("establish-fact",
                       help="Flip a fact from not-yet-true to established")
    s.add_argument("--id", required=True)
    s.add_argument("--campaign", help="run the consequence cascade after establishing")
    s.add_argument("--when", required=True, help="time key it became true")
    s.add_argument("--truth", choices=["true", "false", "partial"])
    s.add_argument("--learned-by", dest="learned_by",
                   help="comma-separated knower ids who learn this the moment "
                        "it becomes true -- the edge belongs in this call, not "
                        "a later one")
    s.add_argument("--certainty", default="knows",
                   choices=["knows", "believes", "suspects", "wrong"],
                   help="certainty for --learned-by")
    s.add_argument("--source", choices=["witnessed", "told", "deduced", "rumor"],
                   help="source for --learned-by")

    s = sub.add_parser("revise-fact",
                       help="Correct a fact's wording, truth or subjects (keeps its id)")
    s.add_argument("--id", required=True)
    s.add_argument("--statement")
    s.add_argument("--title")
    s.add_argument("--truth", choices=["true", "false", "partial"])
    s.add_argument("--status", choices=["not-yet-true", "established", "superseded"])
    s.add_argument("--narrative")
    s.add_argument("--about", help="replacement comma-separated subject ids")

    s = sub.add_parser("learn", help="Record that someone learned something")
    s.add_argument("--knower", required=True,
                   help="character or faction id, or a comma-separated list")
    s.add_argument("--fact", required=True)
    s.add_argument("--certainty", default="knows",
                   choices=["knows", "believes", "suspects", "wrong"])
    s.add_argument("--source", choices=["witnessed", "told", "deduced", "rumor"])
    s.add_argument("--at", help="time key learned (defaults to the world clock)")
    s.add_argument("--campaign", help="used to default --at to the world clock")
    s.add_argument("--force", action="store_true",
                   help="allow knowing a fact that has not been established")

    s = sub.add_parser("forget", help="Remove a knowledge edge")
    s.add_argument("--knower", required=True)
    s.add_argument("--fact", required=True)

    s = sub.add_parser("who-knows", help="Everyone who holds a given fact")
    s.add_argument("--campaign", required=True)
    s.add_argument("--fact", required=True)

    s = sub.add_parser("character-view",
                       help="What one character can legitimately act on")
    s.add_argument("--campaign", required=True)
    s.add_argument("--id", required=True)
    s.add_argument("--compact", action="store_true")

    s = sub.add_parser("add-consequence",
                       help="What an established fact does to somebody's intentions")
    s.add_argument("--fact", required=True)
    s.add_argument("--agenda", required=True)
    s.add_argument("--effect", required=True,
                   choices=list(eng.CONSEQUENCE_EFFECTS))
    s.add_argument("--amount", type=int, help="clock segments for stall/advance")

    s = sub.add_parser("supersede-fact",
                       help="Retire a fact, optionally naming what replaced it")
    s.add_argument("--id", required=True)
    s.add_argument("--by", help="id of the fact that replaces it")
    s.add_argument("--campaign", help="run the cascade afterwards")

    s = sub.add_parser("cascade",
                       help="Re-settle intentions and futures without moving time")
    s.add_argument("--campaign", required=True)

    s = sub.add_parser("require-fact",
                       help="Gate an agenda on its holder knowing something")
    s.add_argument("--agenda", required=True)
    s.add_argument("--fact", required=True)

    s = sub.add_parser("check-consistency",
                       help="Reconcile knowledge against facts, agendas and the clock")
    s.add_argument("--campaign", required=True)

    # --- Rules graph (global, faceted) ---
    s = sub.add_parser("load-rules",
                       help="(Re)build the global rules graph from rules/<domain>/*.md")
    s.add_argument("--dir", help="rules directory (default: skill's rules/)")

    s = sub.add_parser("list-rules",
                       help="Lean rule index (id/title/domain/topic); the orientation TOC")
    s.add_argument("--category")
    s.add_argument("--facets", action="store_true",
                   help="include each piece's facet tags (heavier output)")
    s.add_argument("--dim", help="filter by facet dimension (with --value)")
    s.add_argument("--value", help="filter by facet value (with --dim)")

    s = sub.add_parser("get-rule", help="Full text of one rule piece")
    s.add_argument("--id", required=True)
    s.add_argument("--linked", action="store_true",
                   help="also return one hop of linked rule pieces")

    s = sub.add_parser("list-facets",
                       help="The facet vocabulary: every dimension and its values")
    s.add_argument("--dim", help="just this dimension's values")

    s = sub.add_parser("query-rules",
                       help="Live faceted fetch: --facet dim=value (repeatable)")
    s.add_argument("--facet", action="append",
                   help="dim=value; repeat to AND/rank across facets")
    s.add_argument("--linked", action="store_true",
                   help="append one hop of myth-rule-link neighbours")
    s.add_argument("--limit", type=int, default=0,
                   help="cap the number of ranked rules returned (0 = all)")
    s.add_argument("--match", choices=["any", "all"], default="any",
                   help="any (default): rules matching at least one facet, "
                        "ranked by how many they hit. all: only rules "
                        "carrying every facet asked for")

    s = sub.add_parser("get-log")
    s.add_argument("--campaign", required=True)
    s.add_argument("--session", type=int)
    s.add_argument("--type")
    s.add_argument("--limit", type=int, default=15,
                   help="Return only the last N events (default 15; 0 = all)")
    s.add_argument("--full", action="store_true",
                   help="include the event name and the narrative "
                        "(verbatim dialogue), not just the summary")

    s = sub.add_parser("get-context")
    s.add_argument("--campaign", required=True)
    s.add_argument("--compact", action="store_true",
                   help="Combat cards instead of full PC sheets, drop lore "
                        "index, last 5 events. ~13k -> ~1.5k tokens.")

    s = sub.add_parser("export-campaign",
                       help="Export a campaign to a publishable file tree")
    s.add_argument("--campaign", required=True)
    s.add_argument("--output", required=True, help="directory to write")

    s = sub.add_parser("import-campaign",
                       help="Load a published campaign file tree into the database")
    s.add_argument("--path", required=True, help="campaign directory")
    s.add_argument("--name", help="override the campaign name")
    s.add_argument("--new-ids", action="store_true",
                   help="remap all entity ids (load alongside the original)")

    s = sub.add_parser("delete-campaign",
                       help="Permanently delete a campaign and everything in it")
    s.add_argument("--campaign", required=True)
    s.add_argument("--yes", action="store_true",
                   help="required; without it the command reports what would be lost and stops")

    for name, parser_ in sub.choices.items():
        if name not in NEEDS_CAMPAIGN:
            continue
        for action in parser_._actions:
            if "--campaign" in action.option_strings:
                action.required = False
    _install_aliases(sub)
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    _resolve_aliases(args)
    for dest in RELAXED_REQUIRED.get(args.command, ()):
        if getattr(args, dest, None) is None:
            alternatives = " or ".join(sorted(
                a for a, c in ALIASES.get(args.command, {}).items() if c == dest))
            fail("%s needs --%s (or %s)" % (args.command, dest, alternatives))
    if args.command in NEEDS_CAMPAIGN:
        _resolve_campaign(args)
    fn = globals().get("cmd_" + args.command.replace("-", "_"))
    if fn is None:
        fail(f"Unknown command: {args.command}")
    fn(args)


if __name__ == "__main__":
    main()
