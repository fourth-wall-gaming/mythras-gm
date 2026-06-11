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
    get-character --id ID
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
    get-log --campaign ID [--session N] [--type T]
    get-context --campaign ID        # everything needed to resume play
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import mythras_engine as eng

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
TYPEDB_DATABASE = os.getenv("TYPEDB_DATABASE", "alhazen_notebook")
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
              "myth-combat-styles-json", "myth-fatigue", "myth-luck-current",
              "myth-magic-current", "myth-experience-rolls"]


def _load_character(driver, char_id):
    c = _get_entity(driver, "myth-character", char_id, CHAR_ATTRS)
    if not c:
        fail(f"No myth-character with id '{char_id}'")
    for k in list(c):
        if k.endswith("-json") and c[k]:
            c[k] = json.loads(c[k])
    return c


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
                         "myth-current-scene", "myth-session-number"])
    if not c:
        fail(f"No campaign '{args.campaign}'")
    out({"success": True, "campaign": c})


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
    out({"success": True, "character": c})


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


def cmd_update_character(args):
    updates = {
        "myth-skills-json": args.skills, "myth-equipment-json": args.equipment,
        "myth-passions-json": args.passions, "myth-fatigue": args.fatigue,
        "myth-status": args.status,
    }
    with get_driver() as driver:
        for attr, val in updates.items():
            if val is not None:
                _set_attr(driver, "myth-character", args.id, attr, val)
        if args.luck is not None:
            _set_attr(driver, "myth-character", args.id, "myth-luck-current",
                      args.luck, quote=False)
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


def _skill_value(char, skill_name):
    """Look up a skill (or combat style, or passion) value on a character."""
    for pool in ("myth-skills-json", "myth-combat-styles-json", "myth-passions-json"):
        vals = char.get(pool) or {}
        for k, v in vals.items():
            if k.lower() == skill_name.lower():
                return v
    fail(f"Character '{char['name']}' has no skill/style/passion '{skill_name}'")


def cmd_roll_skill(args):
    with get_driver() as driver:
        c = _load_character(driver, args.id)
    skill = _skill_value(c, args.skill)
    if args.augment:
        passion = _skill_value(c, args.augment)
        skill += passion // 5  # +20% of passion value
    result = eng.skill_check(skill, args.difficulty)
    out({"success": True, "character": c["name"], "skill_name": args.skill, **result})


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
    ts = get_timestamp()
    q = f'''insert $e isa myth-game-event,
        has id "{eid}", has name "{escape_string(args.summary[:80])}",
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
    out({"success": True, "events": events})


def cmd_get_context(args):
    """Everything needed to resume a campaign: campaign state, PCs (full sheets),
    NPCs (names), locations, factions, active encounters, recent events."""
    with get_driver() as driver:
        camp = _get_entity(driver, "myth-campaign", args.campaign,
                           ["description", "content", "myth-game-date",
                            "myth-current-scene", "myth-session-number"])
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
        pcs = [_load_character(driver, r["id"]) for r in chars
               if r["type"] == "pc" and r["status"] == "active"]
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
        recent = sorted(events, key=lambda r: str(r["at"]))[-15:]
        result = {"success": True, "campaign": camp, "player_characters": pcs,
                  "npcs": npcs, "locations": members("myth-location"),
                  "factions": members("myth-faction"),
                  "encounters": [e for e in encounters if e["status"] == "active"],
                  "recent_events": recent}

    out(result)


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------

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

    s = sub.add_parser("list-characters")
    s.add_argument("--campaign", required=True)
    s.add_argument("--type")

    s = sub.add_parser("update-character")
    s.add_argument("--id", required=True)
    s.add_argument("--skills")
    s.add_argument("--equipment")
    s.add_argument("--passions")
    s.add_argument("--fatigue")
    s.add_argument("--luck", type=int)
    s.add_argument("--status")

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
    s.add_argument("--narrative")
    s.add_argument("--session", type=int)
    s.add_argument("--involves", help="comma-separated entity ids")

    s = sub.add_parser("get-log")
    s.add_argument("--campaign", required=True)
    s.add_argument("--session", type=int)
    s.add_argument("--type")

    s = sub.add_parser("get-context")
    s.add_argument("--campaign", required=True)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    fn = globals().get("cmd_" + args.command.replace("-", "_"))
    if fn is None:
        fail(f"Unknown command: {args.command}")
    fn(args)


if __name__ == "__main__":
    main()
