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
EVENT_VISIBILITIES = ("played", "reported", "offscreen")

# What a PC could actually know about. Offscreen is GM-side only.
KNOWABLE_VISIBILITIES = ("played", "reported")


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


def filter_log(events, involving=None, known_to=None, visibility=None,
               since_session=None, include_retired=False):
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
        if since_session is not None and (e.get("session") or 0) < since_session:
            continue
        if involving:
            if not set(involving) & set(_participant_ids(e)):
                continue
        if known_to is not None and not is_known_to(e, known_to):
            continue
        out.append(e)
    return out
