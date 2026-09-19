#!/usr/bin/env python3
"""Audit GM table prose for the tics and habits TABLE.md bans.

"Be less verbose" has never once worked as an instruction. This turns the rules
in TABLE.md into numbers you can hold a session against.

Usage:
    voice_audit.py <transcript.md> [--baseline] [--json]

The transcript format is the one produced by the session-log extractor:

    ===== ASSISTANT [2026-09-06T00:59:28.264Z] =====
    ...prose...

Only ASSISTANT turns are measured. Tool-call noise, fenced blocks and mechanics
blocks are stripped first, because none of that is table prose.
"""

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

TURN_RE = re.compile(r"^===== ASSISTANT \[[^\]]*\] =====$", re.M)

# Banned constructions, as classes rather than strings. Each entry is
# (label, compiled pattern). Patterns are deliberately narrow: the aim is
# zero false positives, because an audit nobody trusts gets switched off.
BANNED = [
    ("arithmetic-metaphor",
     re.compile(r"\b(arithmetic|the calculus of it|the math of it|the ledger of it)\b", re.I)),
    ("furniture-metaphor",
     re.compile(r"\b(as though (he|she|they) were furniture|like furniture|"
                r"\bwallpaper\b|part of the room)\b", re.I)),
    ("antithesis-correction",
     # "That's not a monster. That's a prisoner." / "Not grief — policy."
     re.compile(r"(?:that'?s|it'?s|this is)\s+not\s+[^.!?\n]{1,60}[.;]\s*"
                r"(?:that'?s|it'?s|this is)\s+", re.I)),
    # ("antithesis-dash", ...) removed. It only ever fired on appositions --
    # "Not the ledger - a smaller one, canvas-backed" -- which re-specify a
    # noun rather than opposing two things. The real tic is caught by
    # antithesis-correction above, and an audit with false positives in it is
    # an audit somebody switches off.
    ("raised-finger",
     # The rhetorical finger, held up to make a point -- not a finger put down
     # on a page, or laid against something. Requires "up", or a following
     # clause that makes it a gesture at a listener.
     re.compile(r"\b(?:holds?|held|raises?|raised)\s+(?:up\s+)?"
                r"(?:one|a|his|her|their)\s+finger\b"
                r"|\b(?:puts?|put)\s+up\s+(?:one|a|his|her|their)\s+finger\b", re.I)),
    ("punctuation-gesture",
     re.compile(r"\b(tilts? (his|her|their) head|something shifts? in (his|her|their) face|"
                r"lets? the silence do the work)\b", re.I)),
    ("narrated-emotional-price",
     re.compile(r"\bit (?:costs?|cost) (?:him|her|them|\w+) something\b", re.I)),
    ("enumerated-preamble",
     # "Two things." / "Two questions and then you can have mine." / "Three
     # points, and the first is the only one that matters." Counting what is
     # coming before delivering it. The noun varies -- things, questions,
     # reasons, problems, points, parts, ways -- and swapping it does not make
     # it a different habit, which is how it survived the first ban.
     # ~32 hits across two sessions in five characters' mouths: one narrator's
     # lecture-shape wearing everybody's face. "one of them" is excluded; that
     # is ordinary narration.
     re.compile(r"\b(?:two|three|four|five)\s+"
                r"(?:things|questions|reasons|problems|points|parts|ways|rules)\b",
                re.I)),
    ("question-flattery",
     re.compile(r"\b(?:nobody|no one|no-one)\s+(?:has\s+)?ever\s+asked\s+(?:me|us)\b", re.I)),
    ("being-difficult",
     re.compile(r"\bbeing difficult\b|\bI'?m going to be difficult\b", re.I)),
    ("off-camera",
     re.compile(r"\b(meanwhile|somewhere in the city|elsewhere in the city)\b", re.I)),
    ("assistant-register",
     re.compile(r"^(?:###+\s|\s*---\s*$)|here'?s where we are|before I hand you", re.I | re.M)),
]

# A turn that ends by inviting the player to act. TABLE.md §2.4: end on the last
# physical thing that happened.
TRAILING_QUESTION = re.compile(r"[?]\s*$")
INVITATION = re.compile(r"\b(what do you do|what'?s your move|you could\b|"
                        r"you'?ll need to decide|do you want to)\b", re.I)

FENCE = re.compile(r"```.*?```", re.S)
MECH_BLOCK = re.compile(r"^>\s*⟦.*?⟧\s*$", re.M)
QUOTED = re.compile(r"[“\"]([^”\"]{2,})[”\"]")


# --- shoe leather ----------------------------------------------------------
#
# Film calls the connective tissue between scenes shoe leather: the walk across
# the lobby, the parking, the greeting, the hello and goodbye on a phone call.
# TABLE.md section 2a says when to cut it -- when nothing is at risk and nobody
# is exposed -- and that judgement is the GM's and cannot be counted.
#
# So this is NOT a score. It is a flag list: here are the places you narrated
# an arrival, a greeting, a departure; go and look at them and decide whether
# each one earned its place. A regex cannot know whether the gate toll mattered.
# It can only say that you narrated eleven arrivals.

SHOE = [
    ("transit",
     # Going somewhere, with nothing happening on the way. Deliberately narrow:
     # "you cross the floor" in a room with a monster in it is a scene, not
     # transit, so crossing has to be crossing something you travel over, and
     # a walk has to be one that "takes" time.
     re.compile(r"\byou (?:make your way|set off|head (?:back|off|out|over)\b)"
                r"|\byou (?:walk|row|ride|cross) (?:back )?(?:to|towards?|over to|up to) the\b"
                r"|\bthe (?:walk|crossing|row|ride|journey) (?:takes|took) \w+", re.I)),
    ("threshold",
     # Arriving and being admitted, before the scene's question is live.
     re.compile(r"\byou arrive at\b|\byou are shown (?:in|up|through)\b"
                r"|\byou knock\b|\byou (?:push|shoulder) (?:the door )?open\b", re.I)),
    ("greeting",
     re.compile(r"[\u201c\"](?:hello|good (?:morning|evening|day)|welcome"
                r"|can i help you|what can i do for you)\b", re.I)),
    ("leave-taking",
     re.compile(r"[\u201c\"](?:goodbye|good night|farewell|safe travels"
                r"|i'?ll see you|see you (?:then|later|tomorrow))\b", re.I)),
]


def shoe_leather(turns_text):
    """Flag connective tissue, with the turn it appears in. Not a verdict."""
    found = {label: [] for label, _ in SHOE}
    for i, prose in enumerate(turns_text, start=1):
        for label, pat in SHOE:
            for m in pat.finditer(prose):
                snip = prose[max(0, m.start() - 30):m.end() + 40].replace("\n", " ")
                found[label].append({"turn": i, "text": snip.strip()})
    return found


def strip_noise(text: str) -> str:
    """Remove anything that is not table prose."""
    text = FENCE.sub("", text)
    text = MECH_BLOCK.sub("", text)
    return text


def turns(path: Path):
    raw = path.read_text(encoding="utf-8", errors="replace")
    parts = TURN_RE.split(raw)
    # parts[0] is whatever preceded the first ASSISTANT marker
    for chunk in parts[1:]:
        # a turn ends at the next ===== marker of any kind
        end = chunk.find("\n=====")
        body = chunk if end == -1 else chunk[:end]
        yield body.strip()


def audit(path: Path) -> dict:
    hits = {label: [] for label, _ in BANNED}
    words, trailing, invitations, quoted_lens = [], 0, 0, []
    prose_turns = []
    n = 0

    for body in turns(path):
        prose = strip_noise(body)
        if not prose.strip():
            continue
        n += 1
        prose_turns.append(prose)
        w = len(prose.split())
        words.append(w)

        for label, pat in BANNED:
            for m in pat.finditer(prose):
                snippet = prose[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")
                hits[label].append(snippet.strip())

        tail = prose.rstrip().split("\n")[-1] if prose.strip() else ""
        if TRAILING_QUESTION.search(tail) and not QUOTED.search(tail):
            trailing += 1
        if INVITATION.search(prose):
            invitations += 1

        for q in QUOTED.findall(prose):
            quoted_lens.append(len(q.split()))

    shoe = shoe_leather(prose_turns)

    def pct(xs, p):
        if not xs:
            return 0
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(len(xs) * p))]

    return {
        "turns": n,
        "words_total": sum(words),
        "words_per_turn": {
            "median": int(statistics.median(words)) if words else 0,
            "p90": pct(words, 0.90),
            "max": max(words) if words else 0,
            "over_250": sum(1 for w in words if w > 250),
            "over_400": sum(1 for w in words if w > 400),
            "pct_over_250": round(100 * sum(1 for w in words if w > 250) / max(1, n), 1),
        },
        "quoted_line_words": {
            "count": len(quoted_lens),
            "median": int(statistics.median(quoted_lens)) if quoted_lens else 0,
            "p90": pct(quoted_lens, 0.90),
            "max": max(quoted_lens) if quoted_lens else 0,
            "over_60": sum(1 for q in quoted_lens if q > 60),
        },
        "turns_ending_in_question": trailing,
        "turns_containing_invitation": invitations,
        "banned": {k: len(v) for k, v in hits.items()},
        "banned_total": sum(len(v) for v in hits.values()),
        "examples": {k: v[:3] for k, v in hits.items() if v},
        "shoe_leather": {k: len(v) for k, v in shoe.items()},
        "shoe_leather_total": sum(len(v) for v in shoe.values()),
        "shoe_leather_flags": {k: v for k, v in shoe.items() if v},
    }


# TABLE.md targets. A session is "passing" when every one of these holds.
# TABLE.md targets. A session is "passing" when every one of these holds.
#
# The word-count targets that used to live here (median <=120, p90 <=250) came
# from the old section 2.4, which said to end on the last physical thing that
# happened. That rule is gone: turn length now follows where the decision falls
# (section 2.1), so a median is no longer a thing worth failing a session over.
# What survives is the tail -- a turn over 400 words is a lecture whatever the
# rule says -- and the NPC speech cap, which is the one that actually regressed.
TARGETS = {
    "words_per_turn.p90": ("<=", 320),
    "words_per_turn.over_400": ("==", 0),
    "quoted_line_words.p90": ("<=", 40),
    "quoted_line_words.over_60": ("==", 0),
    "turns_containing_invitation": ("==", 0),
    "banned_total": ("==", 0),
}


def dig(d, path):
    for part in path.split("."):
        d = d[part]
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    path = Path(args.transcript)
    if not path.exists():
        sys.exit(f"no such transcript: {path}")

    r = audit(path)

    if args.json:
        print(json.dumps(r, indent=2))
        return

    w = r["words_per_turn"]
    q = r["quoted_line_words"]
    print(f"\n{path.name} — {r['turns']} GM turns, {r['words_total']:,} words\n")
    print("  GM words per turn     median %-5d p90 %-5d max %-5d  (%d over 250, %d over 400)"
          % (w["median"], w["p90"], w["max"], w["over_250"], w["over_400"]))
    print("  Quoted line words     median %-5d p90 %-5d max %-5d  (%d over 60)"
          % (q["median"], q["p90"], q["max"], q["over_60"]))
    print("  Turns ending on a question      %d" % r["turns_ending_in_question"])
    print("  Turns containing an invitation  %d" % r["turns_containing_invitation"])

    print("\n  Shoe leather flagged: %d (a list to look at, not a score)" % r["shoe_leather_total"])
    for label, count in sorted(r["shoe_leather"].items(), key=lambda kv: -kv[1]):
        if count:
            print("    %-28s %d" % (label, count))
            for ex in r["shoe_leather_flags"].get(label, [])[:2]:
                print("        turn %-4d … %s …" % (ex["turn"], ex["text"][:80]))
    print("    (TABLE.md 2a: cut it only where nothing is at risk and nobody is")
    print("     exposed. That judgement is yours; this is only where to look.)")

    print("\n  Banned constructions: %d total" % r["banned_total"])
    for label, count in sorted(r["banned"].items(), key=lambda kv: -kv[1]):
        if count:
            print("    %-28s %d" % (label, count))
            for ex in r["examples"].get(label, [])[:2]:
                print("        … %s …" % ex[:100])

    print("\n  Against TABLE.md targets:")
    failed = 0
    for key, (op, want) in TARGETS.items():
        got = dig(r, key)
        ok = (got <= want) if op == "<=" else (got == want)
        failed += 0 if ok else 1
        print("    %-34s %-6s %-6s %s" % (key, got, f"{op}{want}", "ok" if ok else "FAIL"))
    print()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
