"""Pure helpers for world state: liveness, attribution, and forward state.

Free of TypeDB imports so the logic is unit-testable without a database, in the
same spirit as score_tools.py. See WORLD-STATE.md for the design.

Three axes:
  liveness    -- is this still true?        (canon status; absent means live)
  attribution -- who was there, who knows?  (participants + camera position)
  forward     -- what happens next?         (the `doing` block on an NPC)
"""

CANON_STATUSES = ("live", "superseded", "retracted")

# Where the camera was. Absent means "played", so existing records need no
# backfill. Orthogonal to event type: an offscreen event can still be a combat.
#   meta is bookkeeping ABOUT the campaign rather than an event IN it -- GM
#   corrections, adopted conventions. It names the whole cast and so would
#   otherwise poison both knowledge scoping and the recent-events window.
EVENT_VISIBILITIES = ("played", "reported", "offscreen", "meta")

# What a PC could actually know about. Offscreen is GM-side; meta is not fiction.
KNOWABLE_VISIBILITIES = ("played", "reported")

# What belongs in the running journal at all.
FICTION_VISIBILITIES = ("played", "reported", "offscreen")


# What an NPC is currently up to. `score` is who they are; `doing` is what they
# are occupied with on the days the party is not standing in front of them.
#
# ANTI-GOALS, named so they stay out: there is no progress, no segments, no
# clock, no deadline, no eta, no threat level. Each is a rejected subsystem in
# disguise. goal + next is a sentence, not a meter. `as_of_session` is a
# staleness LABEL so a reader can see a line is three sessions old -- nothing
# ticks, and nothing advances unless the GM said it did.
DOING_SLOTS = ("goal", "next", "where", "with", "blocked_by",
               "as_of_session", "log")


def build_doing(session=None, **slots):
    """Assemble a doing block, keeping known slots with a value."""
    out = {}
    for k in DOING_SLOTS:
        v = slots.get(k)
        if v not in (None, "", [], {}):
            out[k] = v
    if session is not None:
        out["as_of_session"] = session
    return out


def validate_doing(doing):
    """Return warnings about a doing block. Never raises, never blocks a write."""
    if not isinstance(doing, dict):
        return ["doing is not an object"]
    warnings = []
    goal, nxt = doing.get("goal"), doing.get("next")
    if not nxt:
        warnings.append(
            "no 'next' -- a goal with no next action is a wish, not an agenda")
    elif goal and str(nxt).strip().lower() == str(goal).strip().lower():
        warnings.append("'next' merely restates 'goal'; next is the concrete "
                        "thing they do, not the thing they want")
    if doing.get("as_of_session") is None:
        warnings.append("no 'as_of_session' -- staleness cannot be seen")
    return warnings


def doing_line(doing, current_session=None, width=140):
    """One-line render for the context save file, with a staleness label."""
    if not isinstance(doing, dict) or not doing:
        return ""
    parts = []
    if doing.get("goal"):
        parts.append(str(doing["goal"]))
    if doing.get("next"):
        parts.append("next: " + str(doing["next"]))
    line = "; ".join(parts)
    since = doing.get("as_of_session")
    if current_session is not None and since is not None:
        gap = current_session - since
        if gap > 0:
            line += f"  [s{since}, {gap} session{'s' if gap != 1 else ''} stale]"
    return line if len(line) <= width else line[:width - 1].rstrip() + "…"


def is_live(canon_status):
    """Absent or 'live' means the record is still true."""
    return canon_status in (None, "", "live")


def _visibility(event):
    return event.get("visibility") or "played"


def _participant_ids(event):
    """Accept either [(id, name)] pairs or a bare list of ids."""
    out = []
    for p in event.get("who") or []:
        out.append(p[0] if isinstance(p, (tuple, list)) else p)
    return out


def is_known_to(event, char_id):
    """Could this character know this happened?

    They must have been a participant, and the camera must not have been
    elsewhere. This is the check behind the rule that character knowledge is
    per-character rather than per-campaign.
    """
    if _visibility(event) not in KNOWABLE_VISIBILITIES:
        return False
    return char_id in _participant_ids(event)


def count_unattributed(events):
    """Events carrying no participants at all.

    An event with no participants is UNATTRIBUTED -- we do not know who was
    there -- which is a different thing from an event nobody attended. Any
    filter keyed on participation silently drops these, so callers must be able
    to tell "this character knows nothing" from "we never recorded who was
    present". Getting that wrong is how a GM concludes a PC is ignorant of
    their own history.
    """
    return sum(1 for e in events if not _participant_ids(e))


def is_fiction(event):
    """Did this happen in the world, as opposed to being a note about the game."""
    return _visibility(event) in FICTION_VISIBILITIES


def filter_log(events, involving=None, known_to=None, visibility=None,
               since_session=None, include_retired=False, fiction_only=False):
    """Filter a list of event dicts. Never mutates the input.

    involving      -- list of entity ids; OR semantics (was anyone here present)
    known_to       -- one character id; involving AND the camera was not elsewhere
    visibility     -- exact camera position; 'played' also matches absent
    since_session  -- session number >= this
    include_retired-- keep superseded/retracted records
    """
    out = []
    for e in events:
        if not include_retired and not is_live(e.get("canon")):
            continue
        if visibility is not None and _visibility(e) != visibility:
            continue
        if fiction_only and not is_fiction(e):
            continue
        if since_session is not None and (e.get("session") or 0) < since_session:
            continue
        if involving:
            if not set(involving) & set(_participant_ids(e)):
                continue
        if known_to is not None and not is_known_to(e, known_to):
            continue
        out.append(e)
    return out


# --- character-centred knowledge ----------------------------------------
#
# The journal is the store of facts. Participation in an event already means
# "was there, saw it". These are the edges for everything else: told, shown,
# inferred -- and, crucially, what the knower thinks it MEANT. Perspective
# lives on the edge, so two characters can hold the same event and read it
# incompatibly without either reading changing the journal.

KNOWLEDGE_DEPTHS = ("glimpsed", "knows", "can-prove")
KNOWLEDGE_ROUTES = ("witnessed", "told", "shown", "inferred", "bought", "rumour")

# The living world reads certainty and source, not depth and route. Both
# vocabularies live on the same myth-knows edge and both are written on every
# set-knowledge, so a GM-facing annotation is never invisible to require-fact,
# forecast, tick or check-consistency.
#
# The mapping is lossy in one direction on purpose. `wrong` has no depth: being
# mistaken is not a degree of knowing, it is recorded in the note, which is
# where a false reading belongs. Everything else lines up:
#   glimpsed  -> suspects    seen but not understood
#   knows     -> believes    held as true, not demonstrable
#   can-prove -> knows       can put it in front of someone
DEPTH_TO_CERTAINTY = {"glimpsed": "suspects", "knows": "believes",
                      "can-prove": "knows"}
# `shown` and `bought` both end in the knower having been handed it by someone
# else, which is `told` as far as the engine is concerned; `rumour` keeps the
# American spelling the fact graph has always used.
ROUTE_TO_SOURCE = {"witnessed": "witnessed", "told": "told", "shown": "told",
                   "inferred": "deduced", "bought": "told", "rumour": "rumor"}


def as_certainty(depth):
    """The engine-facing certainty implied by a GM-facing depth, or None."""
    return DEPTH_TO_CERTAINTY.get(depth)


def as_source(route):
    """The engine-facing source implied by a GM-facing route, or None."""
    return ROUTE_TO_SOURCE.get(route)


def validate_knowledge(k):
    """Warnings about one knowledge edge. Never raises, never blocks a write."""
    if not isinstance(k, dict):
        return ["knowledge is not an object"]
    warnings = []
    depth = k.get("depth")
    if depth is not None and depth not in KNOWLEDGE_DEPTHS:
        warnings.append(f"depth '{depth}' not one of {', '.join(KNOWLEDGE_DEPTHS)}")
    route = k.get("route")
    if route is not None and route not in KNOWLEDGE_ROUTES:
        warnings.append(f"route '{route}' not one of {', '.join(KNOWLEDGE_ROUTES)}")
    if not k.get("note") and not k.get("attitude"):
        warnings.append(
            "no note and no attitude -- an edge with neither says only THAT they "
            "know, which participation already told you. The value is in what "
            "they think it meant and how they feel about it")
    if route == "witnessed" and depth == "glimpsed":
        warnings.append("witnessed but only glimpsed -- deliberate? say so in the note")
    return warnings


def knowledge_line(k, width=150):
    """One-line render of an edge for a brief or a report."""
    if not isinstance(k, dict):
        return ""
    bits = []
    head = " ".join(x for x in (k.get("depth"), k.get("route")) if x)
    if head:
        bits.append(head)
    if k.get("note"):
        bits.append(f'"{k["note"]}"')
    if k.get("attitude"):
        bits.append(f"-- {k['attitude']}")
    line = "  ".join(bits)
    return line if len(line) <= width else line[:width - 1].rstrip() + "…"
