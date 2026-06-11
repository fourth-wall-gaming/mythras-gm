"""
mythras_engine.py -- pure Mythras Imperative rules engine.

No TypeDB, no I/O: dice, success levels, opposed/differential resolution,
derived attributes, hit location tables, and damage application. The CLI
(mythras_gm.py) wraps this with persistence.

Rules source: Mythras Imperative SRD (https://github.com/raleel/mythras-srd).
"""

from __future__ import annotations

import math
import random
import re

# ---------------------------------------------------------------------------
# Dice
# ---------------------------------------------------------------------------

_DICE_TERM = re.compile(r"([+-]?)\s*(?:(\d*)d(\d+)|(\d+))")


def roll_dice(expr: str, rng: random.Random | None = None) -> dict:
    """Roll a dice expression like '1d8+1', '2d6', '1d10+1d8', '-1d4', '3'.

    Returns {"expr", "rolls": [per-die results], "total"}.
    """
    rng = rng or random
    expr = expr.strip()
    if not expr or expr in ("+0", "0", "-0"):
        return {"expr": expr or "+0", "rolls": [], "total": 0}

    total = 0
    rolls: list[int] = []
    pos = 0
    matched_any = False
    for m in _DICE_TERM.finditer(expr.replace(" ", "")):
        if m.start() != pos:
            raise ValueError(f"Bad dice expression: {expr!r}")
        pos = m.end()
        matched_any = True
        sign = -1 if m.group(1) == "-" else 1
        if m.group(3):  # NdM
            n = int(m.group(2) or 1)
            sides = int(m.group(3))
            these = [rng.randint(1, sides) for _ in range(n)]
            rolls.extend(sign * r for r in these)
            total += sign * sum(these)
        else:  # constant
            total += sign * int(m.group(4))
    if not matched_any or pos != len(expr.replace(" ", "")):
        raise ValueError(f"Bad dice expression: {expr!r}")
    return {"expr": expr, "rolls": rolls, "total": total}


# ---------------------------------------------------------------------------
# Skill checks
# ---------------------------------------------------------------------------

DIFFICULTY_GRADES = {
    "veryeasy":   lambda s: s * 2,
    "easy":       lambda s: math.ceil(s * 1.5),
    "standard":   lambda s: s,
    "hard":       lambda s: math.ceil(s * 2 / 3),
    "formidable": lambda s: math.ceil(s / 2),
    "herculean":  lambda s: math.ceil(s / 5),
}

SUCCESS_LEVELS = {"critical": 3, "success": 2, "failure": 1, "fumble": 0}


def effective_skill(skill: int, difficulty: str = "standard") -> int:
    key = difficulty.lower().replace("-", "").replace("_", "").replace(" ", "")
    if key not in DIFFICULTY_GRADES:
        raise ValueError(f"Unknown difficulty grade: {difficulty}")
    return DIFFICULTY_GRADES[key](skill)


def skill_check(skill: int, difficulty: str = "standard",
                rng: random.Random | None = None, roll: int | None = None) -> dict:
    """Roll 1d100 vs a (possibly graded) skill. Returns full result dict."""
    rng = rng or random
    eff = effective_skill(skill, difficulty)
    if roll is None:
        roll = rng.randint(1, 100)

    crit_range = math.ceil(eff / 10)
    fumble_floor = 100 if eff > 100 else 99  # 99-00 fumbles; only 00 if skill>100

    if roll >= fumble_floor:
        level = "fumble"
    elif roll <= 5:
        level = "critical" if roll <= crit_range else "success"
    elif roll >= 96:
        level = "failure"
    elif roll <= crit_range:
        level = "critical"
    elif roll <= eff:
        level = "success"
    else:
        level = "failure"

    return {"roll": roll, "skill": skill, "difficulty": difficulty,
            "effective": eff, "critical_range": crit_range, "level": level}


def _over_100_adjust(a_skill: int, b_skill: int) -> tuple[int, int]:
    """Opposed contests: highest skill over 100 subtracts the excess from all."""
    high = max(a_skill, b_skill)
    if high > 100:
        excess = high - 100
        return a_skill - excess, b_skill - excess
    return a_skill, b_skill


def opposed_roll(a_skill: int, b_skill: int,
                 a_difficulty: str = "standard", b_difficulty: str = "standard",
                 rng: random.Random | None = None) -> dict:
    """Win/lose opposed contest. Higher success level wins; tie -> higher roll
    within skill range wins; both fail -> 'none'."""
    rng = rng or random
    a_eff = effective_skill(a_skill, a_difficulty)
    b_eff = effective_skill(b_skill, b_difficulty)
    a_adj, b_adj = _over_100_adjust(a_eff, b_eff)
    a = skill_check(a_adj, "standard", rng)
    b = skill_check(b_adj, "standard", rng)
    la, lb = SUCCESS_LEVELS[a["level"]], SUCCESS_LEVELS[b["level"]]

    if la <= 1 and lb <= 1:
        winner = "none"
    elif la > lb:
        winner = "a"
    elif lb > la:
        winner = "b"
    else:  # same success level, both succeeded
        winner = "a" if a["roll"] >= b["roll"] else "b"
    return {"a": a, "b": b, "winner": winner}


def differential_roll(a_skill: int, b_skill: int,
                      a_difficulty: str = "standard", b_difficulty: str = "standard",
                      rng: random.Random | None = None,
                      b_auto_fail: bool = False) -> dict:
    """Combat-style differential: returns each side's result plus the number
    of special effects and who receives them ('a', 'b', or None)."""
    rng = rng or random
    a_eff = effective_skill(a_skill, a_difficulty)
    b_eff = effective_skill(b_skill, b_difficulty)
    a_adj, b_adj = _over_100_adjust(a_eff, b_eff)
    a = skill_check(a_adj, "standard", rng)
    if b_auto_fail:
        b = {"roll": None, "skill": b_skill, "difficulty": b_difficulty,
             "effective": b_adj, "critical_range": 0, "level": "failure"}
    else:
        b = skill_check(b_adj, "standard", rng)
    la, lb = SUCCESS_LEVELS[a["level"]], SUCCESS_LEVELS[b["level"]]
    diff = la - lb
    # No effects unless at least one side achieved Standard success or better
    if max(la, lb) < 2:
        diff = 0
    beneficiary = "a" if diff > 0 else ("b" if diff < 0 else None)
    return {"a": a, "b": b, "special_effects": abs(diff), "beneficiary": beneficiary}


# ---------------------------------------------------------------------------
# Derived attributes
# ---------------------------------------------------------------------------

def damage_modifier(str_val: int, siz_val: int) -> str:
    total = str_val + siz_val
    table = [
        (5, "-1d8"), (10, "-1d6"), (15, "-1d4"), (20, "-1d2"), (25, "+0"),
        (30, "+1d2"), (35, "+1d4"), (40, "+1d6"), (45, "+1d8"), (50, "+1d10"),
        (60, "+1d12"), (70, "+2d6"), (80, "+1d8+1d6"), (90, "+2d8"),
        (100, "+1d10+1d8"), (110, "+2d10"), (120, "+2d10+1d2"),
    ]
    for ceiling, mod in table:
        if total <= ceiling:
            return mod
    return "+2d10+1d2"  # beyond table: GM extends progression manually


def _step_table(value: int) -> int:
    """Shared progression for Healing Rate / Luck Points / Exp Modifier."""
    if value <= 6:
        return 1
    return 2 + (value - 7) // 6


def derive_attributes(chars: dict, species: str = "avian") -> dict:
    """Compute all derived attributes from a characteristics dict."""
    str_v, con, siz = chars["STR"], chars["CON"], chars["SIZ"]
    dex, int_v, pow_v, cha = chars["DEX"], chars["INT"], chars["POW"], chars["CHA"]
    move = {"avian": "4m walk / 12m fly", "humanoid": "6m"}.get(species, "6m")
    return {
        "action_points": 2,
        "damage_modifier": damage_modifier(str_v, siz),
        "experience_modifier": (-1 if cha <= 6 else 0 if cha <= 12 else _step_table(cha) - 1),
        "healing_rate": _step_table(con),
        "initiative_bonus": (dex + int_v) // 2,
        "luck_points": _step_table(pow_v),
        "magic_points": pow_v,
        "movement": move,
    }


def hp_for_location(con_plus_siz: int, location: str) -> int:
    """Hit points by location from CON+SIZ."""
    band = max(0, (con_plus_siz - 1) // 5)  # 0 for 1-5, 1 for 6-10, ...
    base = {"head": 1, "chest": 3, "abdomen": 2, "arm": 1, "leg": 1, "wing": 1}
    key = location.lower()
    for k in base:
        if k in key:
            b = base[k]
            # arms lag one band: 1,1,2,3...
            if k == "arm":
                return max(1, b + max(0, band - 1))
            return b + band
    return 2 + band  # default to abdomen-like


# Hit location tables: list of (lo, hi, name)
HIT_TABLES = {
    "humanoid": [
        (1, 3, "Right Leg"), (4, 6, "Left Leg"), (7, 9, "Abdomen"),
        (10, 12, "Chest"), (13, 15, "Right Arm"), (16, 18, "Left Arm"),
        (19, 20, "Head"),
    ],
    "avian": [  # winged Alar / avianoid
        (1, 2, "Right Leg"), (3, 4, "Left Leg"), (5, 7, "Abdomen"),
        (8, 10, "Chest"), (11, 12, "Right Wing"), (13, 14, "Left Wing"),
        (15, 16, "Right Arm"), (17, 18, "Left Arm"), (19, 20, "Head"),
    ],
    "winged-quadruped": [  # sky-drakes etc.
        (1, 2, "Right Hind Leg"), (3, 4, "Left Hind Leg"), (5, 7, "Hindquarters"),
        (8, 10, "Forequarters"), (11, 12, "Right Wing"), (13, 14, "Left Wing"),
        (15, 16, "Right Front Leg"), (17, 18, "Left Front Leg"), (19, 20, "Head"),
    ],
}


def build_hit_locations(chars: dict, species: str = "avian",
                        armor: dict | None = None) -> list[dict]:
    """Build the hit-location list for a new character.
    armor: optional {"Chest": 4, "Head": 2, ...} AP map."""
    armor = armor or {}
    cs = chars["CON"] + chars["SIZ"]
    table = HIT_TABLES.get(species, HIT_TABLES["humanoid"])
    out = []
    for lo, hi, name in table:
        hp = hp_for_location(cs, name)
        out.append({"name": name, "range": [lo, hi], "ap": armor.get(name, 0),
                    "hp": hp, "current_hp": hp})
    return out


def roll_hit_location(locations: list[dict], rng: random.Random | None = None,
                      roll: int | None = None) -> dict:
    rng = rng or random
    if roll is None:
        roll = rng.randint(1, 20)
    for loc in locations:
        if loc["range"][0] <= roll <= loc["range"][1]:
            return {"roll": roll, "location": loc["name"]}
    return {"roll": roll, "location": locations[-1]["name"]}


# ---------------------------------------------------------------------------
# Base skills
# ---------------------------------------------------------------------------

STANDARD_SKILL_BASES = {
    "Athletics": ("STR", "DEX"), "Boating": ("STR", "CON"), "Brawn": ("STR", "SIZ"),
    "Conceal": ("DEX", "POW"), "Dance": ("DEX", "CHA"), "Deceit": ("INT", "CHA"),
    "Drive": ("DEX", "POW"), "Endurance": ("CON", "CON"), "Evade": ("DEX", "DEX"),
    "First Aid": ("DEX", "INT"), "Influence": ("CHA", "CHA"), "Insight": ("INT", "POW"),
    "Locale": ("INT", "INT"), "Perception": ("INT", "POW"), "Ride": ("DEX", "POW"),
    "Sing": ("POW", "CHA"), "Stealth": ("DEX", "INT"), "Swim": ("STR", "CON"),
    "Unarmed": ("STR", "DEX"), "Willpower": ("POW", "POW"),
    # Setting addition: Flight is a standard skill for winged species
    "Flight": ("STR", "DEX"),
}
PLUS_40 = {"Customs": ("INT", "INT"), "Native Tongue": ("INT", "CHA")}


def base_skills(chars: dict, species: str = "avian") -> dict:
    skills = {}
    for name, (a, b) in STANDARD_SKILL_BASES.items():
        if name == "Flight" and species not in ("avian", "winged-quadruped"):
            continue
        if name == "Swim" and species == "avian":
            continue  # Alar sink like stones; Swim is professional for them
        skills[name] = chars[a] + chars[b]
    for name, (a, b) in PLUS_40.items():
        skills[name] = chars[a] + chars[b] + 40
    return skills


def roll_characteristics(species: str = "avian", rng: random.Random | None = None) -> dict:
    """3d6 for STR/CON/DEX/POW/CHA, 2d6+6 for SIZ/INT, plus species mods."""
    rng = rng or random
    d3 = lambda: sum(rng.randint(1, 6) for _ in range(3))
    d2p6 = lambda: sum(rng.randint(1, 6) for _ in range(2)) + 6
    chars = {"STR": d3(), "CON": d3(), "SIZ": d2p6(), "DEX": d3(),
             "INT": d2p6(), "POW": d3(), "CHA": d3()}
    if species == "avian":  # Alar: hollow-boned, quick, slight
        chars["SIZ"] = max(4, chars["SIZ"] - 3)
        chars["DEX"] = chars["DEX"] + 2
    return chars


# ---------------------------------------------------------------------------
# Damage application
# ---------------------------------------------------------------------------

WEAPON_SIZES = ["S", "M", "L", "H", "E"]


def parry_reduction(damage: int, attack_size: str, parry_size: str) -> int:
    """Damage remaining after a successful parry, by comparative weapon size."""
    ai = WEAPON_SIZES.index(attack_size.upper()[0])
    pi = WEAPON_SIZES.index(parry_size.upper()[0])
    if pi >= ai:
        return 0
    if pi == ai - 1:
        return damage // 2
    return damage


def apply_damage(locations: list[dict], location_name: str, damage: int,
                 ignore_armor: bool = False) -> dict:
    """Mutates the locations list; returns wound report."""
    for loc in locations:
        if loc["name"].lower() == location_name.lower():
            ap = 0 if ignore_armor else loc.get("ap", 0)
            net = max(0, damage - ap)
            loc["current_hp"] -= net
            cur, start = loc["current_hp"], loc["hp"]
            if net == 0:
                wound = "none"
            elif cur > 0:
                wound = "minor"
            elif cur > -start:
                wound = "serious"
            else:
                wound = "major"
            return {"location": loc["name"], "raw_damage": damage, "armor": ap,
                    "net_damage": net, "current_hp": cur, "starting_hp": start,
                    "wound": wound}
    raise ValueError(f"No such hit location: {location_name}")


FATIGUE_LEVELS = ["Fresh", "Winded", "Tired", "Wearied", "Exhausted",
                  "Debilitated", "Incapacitated", "Semi-Conscious", "Comatose", "Dead"]
