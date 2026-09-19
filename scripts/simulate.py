#!/usr/bin/env python3
"""Step a campaign package watch by watch and report what the GM would have.

This is a harness for testing the STORY STRUCTURE, not the fiction. It cannot
tell you whether a scene is good. It can tell you whether, at 07:00 on day two,
there is anything at all for a particular character to do -- which is the defect
that actually kills sessions, and the one that is invisible while reading a plan
top to bottom because reading a plan never puts you inside a single watch.

Run it once per PC. A structure that works for Magda and strands Randall for
nine watches is not a working structure.
"""
import argparse
import json
import pathlib
import re
import sys

WATCHES = ["dawn", "day", "dusk", "night"]


def _fm(text):
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    return m.group(1) if m else ""


def load_beats(pkg):
    out = []
    for f in sorted((pkg / "beats").glob("*.md")):
        raw = f.read_text()
        fm = _fm(raw)
        body = raw[len(fm) + 8:] if fm else raw

        def g(k):
            m = re.search(rf'^{k}:\s*"?([^"\n]*)"?', fm, re.M)
            return (m.group(1).strip() or None) if m else None

        out.append({
            "slug": f.stem,
            "title": g("title") or f.stem,
            "when": g("when"),
            "summary": g("summary") or "",
            "onscreen_if": g("onscreen_if") or "",
            "place": g("place"),
            "cast": re.findall(r"myth-char-[0-9a-f]+", (g("cast") or "")),
            "needs": re.findall(r"played:\s*([a-z0-9\-]+)", fm),
            "body": body,
        })
    return out


def load_names(pkg):
    names = {}
    for f in (pkg / "characters").rglob("*.json"):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        for r in d if isinstance(d, list) else [d]:
            if isinstance(r, dict) and r.get("id"):
                names[r["id"]] = r.get("name", "?")
    for f in (pkg / "locations").glob("*.md"):
        t = f.read_text()
        i = re.search(r'^id:\s*"([^"]*)"', t, re.M)
        n = re.search(r'^name:\s*"([^"]*)"', t, re.M)
        if i and n:
            names[i.group(1)] = n.group(1)
    return names


def pcs(pkg):
    out = {}
    for f in (pkg / "characters" / "pcs").glob("*.json"):
        d = json.loads(f.read_text())
        for r in d if isinstance(d, list) else [d]:
            out[r["name"]] = r["id"]
    return out


def timeline(beats):
    days, seen = [], set()
    for b in beats:
        if b["when"]:
            seen.add(b["when"].split("/")[0])
    def daykey(d):
        return int(d[1:])
    for d in sorted(seen, key=daykey):
        for w in WATCHES:
            days.append(f"{d}/{w}")
    return days


# -- the four things that can be wrong with a watch -------------------------
#
# ENGAGED    a beat this PC is cast in, or is the obvious subject of
# WITNESS    a beat they could reach but that is not about them
# OFFSTAGE   beats fire, none of them reachable
# EMPTY      nothing scheduled at all

def classify(b, pc_id, pc_name):
    if pc_id in b["cast"]:
        return "ENGAGED"
    osi = b["onscreen_if"].lower()
    if pc_name.split()[0].lower() in osi:
        return "ENGAGED"
    if "any pc" in osi or "anyone" in osi or "always" in osi:
        return "WITNESS"
    return "OFFSTAGE"


DECISION = re.compile(
    r"\broll\b|\bthe dice decide\b|\bthe choice\b|\bdecides\b|\bopposed\b"
    r"|\bwillpower\b|\binsight\b|\bcombat\b|\bwhat the dice\b", re.I)


def run(pkg, pc_name, verbose=True):
    beats = load_beats(pkg)
    names = load_names(pkg)
    allpc = pcs(pkg)
    if pc_name not in allpc:
        sys.exit(f"No PC {pc_name!r}. Have: {', '.join(sorted(allpc))}")
    pc_id = allpc[pc_name]

    by_watch = {}
    for b in beats:
        by_watch.setdefault(b["when"], []).append(b)
    available = by_watch.pop(None, [])

    trace, findings = [], []
    dry = 0            # consecutive watches with nothing for this PC
    no_decision = 0    # consecutive watches with no decision offered
    concluded = None

    for w in timeline(beats):
        here = by_watch.get(w, [])
        rows = [(classify(b, pc_id, pc_name), b) for b in here]
        engaged = [b for k, b in rows if k == "ENGAGED"]
        witness = [b for k, b in rows if k == "WITNESS"]
        reach = engaged + witness

        if not here:
            state = "EMPTY"
        elif not reach:
            state = "OFFSTAGE"
        elif engaged:
            state = "ENGAGED"
        else:
            state = "WITNESS"

        decides = any(DECISION.search(b["body"]) for b in reach)
        dry = dry + 1 if state in ("EMPTY", "OFFSTAGE") else 0
        no_decision = no_decision + 1 if not decides else 0

        trace.append({"watch": w, "state": state, "decides": decides,
                      "beats": [(k, b["title"]) for k, b in rows],
                      "dry": dry, "no_decision": no_decision})

        # --- stop conditions, checked in the order a player would hit them
        if dry >= 3:
            findings.append({"condition": "C", "watch": w,
                             "detail": f"{dry} consecutive watches with nothing "
                                       f"{pc_name} can reach -- it is not obvious "
                                       "what to do next"})
        if no_decision >= 4:
            findings.append({"condition": "B", "watch": w,
                             "detail": f"{no_decision} consecutive watches in "
                                       "which nothing asks for a decision -- "
                                       "this is exposition"})
        if any(b["slug"] == "the-boy" for b in here):
            concluded = w
            break

    return {"pc": pc_name, "trace": trace, "findings": findings,
            "concluded": concluded, "available": available, "names": names}


def report(r, verbose):
    print(f"\n{'='*72}\n  SIMULATION — {r['pc']}\n{'='*72}")
    if verbose:
        for t in r["trace"]:
            mark = {"ENGAGED": "**", "WITNESS": " ·", "OFFSTAGE": " ×",
                    "EMPTY": " -"}[t["state"]]
            d = "?" if t["decides"] else " "
            print(f"{mark}{d} {t['watch']:<10} " +
                  ("; ".join(f"{k[0]}:{ti}" for k, ti in t["beats"])[:88] or "—"))
    n = len(r["trace"])
    from collections import Counter
    c = Counter(t["state"] for t in r["trace"])
    print(f"\n  watches: {n}   " + "  ".join(f"{k} {v}" for k, v in c.most_common()))
    print(f"  decisions offered in {sum(1 for t in r['trace'] if t['decides'])} of {n} watches")
    print(f"  concluded: {r['concluded'] or 'NO — ran out of timeline'}")
    if r["findings"]:
        print("\n  STOP CONDITIONS HIT")
        seen = set()
        for f in r["findings"]:
            k = (f["condition"], f["detail"][:20])
            if k in seen:
                continue
            seen.add(k)
            print(f"   [{f['condition']}] {f['watch']:<10} {f['detail']}")
    else:
        print("\n  no stop conditions hit")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", default=".", type=pathlib.Path)
    ap.add_argument("--pc")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    who = sorted(pcs(a.package)) if a.all else [a.pc]
    for name in who:
        report(run(a.package, name), not a.quiet)
