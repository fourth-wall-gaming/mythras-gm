"""Combat special effects — the table the engine never had.

`differential_roll` has always returned a COUNT of special effects and the name
of whoever earned them. Which effects those could be, what they require, and
what they do has lived only in markdown, which meant the most tactical decision
in Mythras combat was a number the GM narrated past.

This module is the single vocabulary. The ids here are the same strings used as
`effect=` facet values in the rules graph, so `query-rules --facet effect=impale`
and `--effect impale` cannot drift apart (there is a doctor check for that).

Nothing here touches the database or rolls dice; it is a table and some
predicates, so it can be tested on its own.
"""

# phase decides WHEN an effect has to be applied, which is the whole reason
# attack resolution had to be split in two:
#   pre-damage  -- changes the damage roll, the armour, or the parry. Must be
#                  chosen before any dice are rolled for damage.
#   post-damage -- changes the world after the wound is worked out.
#   followup    -- needs a contest the defender gets a say in; never resolved
#                  silently, always handed back as a roll to make.
EFFECTS = [
    # --- offensive -------------------------------------------------------
    dict(id="choose-location", name="Choose Location", side="offense",
         requires=None, phase="pre-damage",
         one_line="put it where you want it"),
    dict(id="maximize-damage", name="Maximize Damage", side="offense",
         requires="critical", phase="pre-damage", stackable=True,
         one_line="one die does the worst it can"),
    dict(id="bypass-armor", name="Bypass Armor", side="offense",
         requires="critical", phase="pre-damage",
         one_line="straight through the armour as if it were not there"),
    dict(id="circumvent-parry", name="Circumvent Parry", side="both",
         requires="critical", phase="pre-damage",
         one_line="round the guard entirely"),
    dict(id="impale", name="Impale", side="offense",
         requires=None, phase="pre-damage", weapon="impaling",
         one_line="drive it home so it sticks"),
    dict(id="force-failure", name="Force Failure", side="defense",
         requires="opponent-fumble", phase="pre-damage",
         one_line="turn the blow into nothing at all"),
    dict(id="select-target", name="Select Target", side="defense",
         requires="opponent-fumble", phase="pre-damage",
         one_line="send it into somebody else"),
    dict(id="enhance-parry", name="Enhance Parry", side="defense",
         requires="critical", phase="pre-damage",
         one_line="take all of it on the block"),

    dict(id="sunder", name="Sunder", side="offense",
         requires=None, phase="post-damage", weapon="two-handed",
         one_line="ruin the armour itself"),
    dict(id="damage-weapon", name="Damage Weapon", side="both",
         requires=None, phase="post-damage",
         one_line="wreck the thing in their hand"),
    dict(id="bash", name="Bash", side="offense",
         requires=None, phase="post-damage", weapon="bludgeoning",
         one_line="knock them off it"),
    dict(id="scar-foe", name="Scar Foe", side="defense",
         requires=None, phase="post-damage",
         one_line="leave a mark they keep"),
    dict(id="prepare-counter", name="Prepare Counter", side="defense",
         requires=None, phase="post-damage",
         one_line="set up the answer"),
    dict(id="withdraw", name="Withdraw", side="defense",
         requires=None, phase="post-damage",
         one_line="break off clean"),
    dict(id="arise", name="Arise", side="defense",
         requires=None, phase="post-damage", needs_prone=True,
         one_line="get back on your feet for free"),
    dict(id="slip-free", name="Slip Free", side="defense",
         requires="critical", phase="post-damage",
         one_line="out of the hold entirely"),

    # --- contested: handed back as a roll, never resolved silently --------
    dict(id="trip", name="Trip", side="both",
         requires=None, phase="followup",
         contest="Brawn or Evade or Acrobatics",
         one_line="take their legs"),
    dict(id="disarm", name="Disarm", side="both",
         requires=None, phase="followup",
         contest="Combat Style",
         one_line="knock it out of their hand"),
    dict(id="bleed", name="Bleed", side="offense",
         requires=None, phase="followup", weapon="cutting",
         contest="Endurance",
         one_line="open them so it keeps running"),
    dict(id="stun-location", name="Stun Location", side="offense",
         requires=None, phase="followup", weapon="bludgeoning",
         contest="Endurance",
         one_line="deaden the limb"),
    dict(id="grip", name="Grip", side="offense",
         requires=None, phase="followup", weapon="unarmed",
         contest="Brawn",
         one_line="take hold and keep hold"),
    dict(id="blind-opponent", name="Blind Opponent", side="defense",
         requires="critical", phase="followup",
         contest="Endurance",
         one_line="go for the eyes"),
]

BY_ID = {e["id"]: e for e in EFFECTS}

# Weapon trait words as they appear in sheets. Equipment carries traits in free
# text (`notes`, occasionally the name), so we sniff rather than demand schema.
_TRAIT_WORDS = {
    "impaling": ("impale", "impaling"),
    "cutting": ("bleed", "cutting", "slash"),
    "bludgeoning": ("stun location", "bludgeon", "crush", "bash"),
    "two-handed": ("2h", "two-handed", "two handed"),
    "unarmed": ("unarmed", "fist", "brawl"),
}


def weapon_traits(weapon):
    """Best-effort read of what a weapon can do.

    An explicit `traits` list wins. Otherwise scan the name and notes, which is
    where sheets in this campaign actually record it ("Impale (damage not
    filled on sheet)", "Stun Location").
    """
    if not weapon:
        return set()
    explicit = weapon.get("traits")
    if explicit:
        return {str(t).lower() for t in explicit}
    hay = " ".join(str(weapon.get(k) or "") for k in ("name", "notes", "size", "type")).lower()
    found = {trait for trait, words in _TRAIT_WORDS.items() if any(w in hay for w in words)}
    # A weapon with no stated traits can still do the trait-free effects.
    return found


def available(side, level, opponent_level, weapon=None, prone=False):
    """Which effects this winner may actually choose.

    side            'offense' | 'defense' -- who won the differential
    level           the winner's success level ('critical'|'success'|...)
    opponent_level  the loser's level, for the fumble-triggered effects
    weapon          the winner's weapon dict, for trait gating
    prone           whether the winner is currently prone (gates Arise)
    """
    traits = weapon_traits(weapon)
    is_crit = level == "critical"
    opp_fumbled = opponent_level == "fumble"
    out = []
    for e in EFFECTS:
        if e["side"] not in (side, "both"):
            continue
        req = e.get("requires")
        if req == "critical" and not is_crit:
            continue
        if req == "opponent-fumble" and not opp_fumbled:
            continue
        need = e.get("weapon")
        if need and need not in traits:
            continue
        if e.get("needs_prone") and not prone:
            continue
        out.append({k: e[k] for k in ("id", "name", "phase", "one_line")
                    if k in e} | ({"contest": e["contest"]} if e.get("contest") else {}))
    return out


def validate(chosen, side, level, opponent_level, count, weapon=None, prone=False):
    """Return an error string, or None if the selection is legal."""
    if len(chosen) > count:
        return f"{len(chosen)} effects chosen but only {count} earned"
    ok = {e["id"] for e in available(side, level, opponent_level, weapon, prone)}
    for c in chosen:
        if c not in BY_ID:
            near = [i for i in BY_ID if i.startswith(c[:4])]
            hint = f" -- did you mean {near[0]}?" if near else ""
            return f"unknown effect '{c}'{hint}"
        if c not in ok:
            e = BY_ID[c]
            why = (f"requires a {e['requires']}" if e.get("requires")
                   else f"requires a {e['weapon']} weapon" if e.get("weapon")
                   else f"is a {e['side']} effect")
            return f"'{c}' not available here: it {why}"
    # Only Maximize Damage may be taken more than once.
    for c in set(chosen):
        if chosen.count(c) > 1 and not BY_ID[c].get("stackable"):
            return f"'{c}' cannot be taken more than once"
    return None
