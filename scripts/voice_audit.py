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
    ("antithesis-dash",
     re.compile(r"\bnot\s+(?:a|an|the)\s+\w+\s*[—–-]{1,2}\s*(?:a|an|the)\s+\w+", re.I)),
    ("raised-finger",
     re.compile(r"\b(?:holds?|held|raises?|raised|puts?|put)\s+(?:up\s+)?"
                r"(?:one|a|his|her|their)\s+finger\b", re.I)),
    ("punctuation-gesture",
     re.compile(r"\b(tilts? (his|her|their) head|something shifts? in (his|her|their) face|"
                r"lets? the silence do the work)\b", re.I)),
    ("narrated-emotional-price",
     re.compile(r"\bit (?:costs?|cost) (?:him|her|them|\w+) something\b", re.I)),
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
    n = 0

    for body in turns(path):
        prose = strip_noise(body)
        if not prose.strip():
            continue
        n += 1
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
    }


# TABLE.md targets. A session is "passing" when every one of these holds.
TARGETS = {
    "words_per_turn.median": ("<=", 120),
    "words_per_turn.p90": ("<=", 250),
    "words_per_turn.over_400": ("==", 0),
    "quoted_line_words.p90": ("<=", 25),
    "quoted_line_words.over_60": ("==", 0),
    "turns_ending_in_question": ("==", 0),
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
