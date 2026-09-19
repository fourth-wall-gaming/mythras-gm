#!/usr/bin/env python3
"""GLAV migration between two TypeDB databases.

Modelled on skillful-alhazen's `schema_mapper.py`: declarative YAML rules,
each a paired (source_match, target_insert) TypeQL fragment, dependency
ordered, idempotent, dry-runnable. The orchestrator is mechanical and holds
no domain knowledge -- everything that is specific to a migration lives in
its rules directory.

One deliberate difference from the alhazen mapper. That one *skolemises*: it
mints a fresh deterministic id from a set of key values, because it is mapping
one domain's entities onto another's. This is a **schema migration of the same
entities** -- the rows on both sides are the same rows -- so identity is the
existing `id`, preserved. Minting new ids here would break every reference
held outside the database: the campaign package on disk, the session journal,
and anything a GM has written down.

Rule format (YAML, one per file):

    name: character
    description: Characters, re-parented onto the alh-* base hierarchy
    depends_on: [campaign]
    identity: [id]              # defaults to [id]
    source_match: |
      match $c isa myth-character, has id $i, has name $n;
      fetch { "id": $i, "name": $n };
    target_insert: |
      insert $c isa myth-character, has id $id, has name $name;

Variables in `target_insert` are substituted from the fetched row by name.
A `?var` is optional: the whole line it appears on is dropped when the value
is missing, which is how optional attributes survive a schema that does not
require them.

Usage:
    glav_migrate.py plan     --source-db X --target-db Y --rules-dir D
    glav_migrate.py run      --source-db X --target-db Y --rules-dir D [--dry-run]
    glav_migrate.py verify   --source-db X --target-db Y --rules-dir D
"""

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from typedb.driver import Credentials, DriverOptions, TransactionType, TypeDB

TYPEDB_HOST = os.getenv("TYPEDB_HOST", "localhost")
TYPEDB_USERNAME = os.getenv("TYPEDB_USERNAME", "admin")
TYPEDB_PASSWORD = os.getenv("TYPEDB_PASSWORD", "password")


def driver_for(port):
    return TypeDB.driver(f"{TYPEDB_HOST}:{port}",
                         Credentials(TYPEDB_USERNAME, TYPEDB_PASSWORD),
                         DriverOptions(is_tls_enabled=False))


def escape_string(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

@dataclass
class Rule:
    name: str
    description: str
    source_match: str
    target_insert: str
    identity: list = field(default_factory=lambda: ["id"])
    depends_on: list = field(default_factory=list)
    idempotent: bool = True
    kind: str = "entity"          # entity | relation
    verify_match: str = ""        # target-side count when source_match will not port
    notes: str = ""               # migration decisions, printed in the report
    derive: dict = field(default_factory=dict)


REQUIRED = {"name", "source_match", "target_insert"}


def load_rules(rules_dir):
    path = Path(rules_dir)
    if not path.is_dir():
        raise FileNotFoundError(f"no rules directory: {path}")
    rules = []
    for f in sorted(path.glob("*.y*ml")):
        data = yaml.safe_load(f.read_text())
        if not data:
            continue
        missing = REQUIRED - set(data)
        if missing:
            raise ValueError(f"{f.name}: missing {', '.join(sorted(missing))}")
        rules.append(Rule(
            name=data["name"],
            description=data.get("description", ""),
            source_match=data["source_match"].strip(),
            target_insert=data["target_insert"].strip(),
            identity=data.get("identity") or ["id"],
            depends_on=data.get("depends_on") or [],
            idempotent=data.get("idempotent", True),
            kind=data.get("kind", "entity"),
            notes=data.get("notes", ""),
            verify_match=(data.get("verify_match") or "").strip(),
            derive=data.get("derive") or {},
        ))
    return rules


def topological_sort(rules):
    """Dependency order, Kahn's algorithm. Raises on a cycle or unknown dep."""
    by_name = {r.name: r for r in rules}
    for r in rules:
        for dep in r.depends_on:
            if dep not in by_name:
                raise ValueError(f"rule '{r.name}' depends on unknown '{dep}'")
    indeg = {r.name: 0 for r in rules}
    adj = {r.name: [] for r in rules}
    for r in rules:
        for dep in r.depends_on:
            adj[dep].append(r.name)
            indeg[r.name] += 1
    queue = sorted(n for n, d in indeg.items() if d == 0)
    ordered = []
    while queue:
        queue.sort()
        n = queue.pop(0)
        ordered.append(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    if len(ordered) != len(rules):
        stuck = sorted(set(by_name) - set(ordered))
        raise ValueError(f"cycle among rules: {', '.join(stuck)}")
    return [by_name[n] for n in ordered]


# ---------------------------------------------------------------------------
# Substitution
# ---------------------------------------------------------------------------

VAR = re.compile(r"\$([A-Za-z_][A-Za-z0-9_-]*)")
OPTIONAL_VAR = re.compile(r"\?([A-Za-z_][A-Za-z0-9_-]*)")
# !var inserts the value unquoted. Needed for type labels: a relation's
# roleplayer has to be matched at its concrete type, and "myth-character"
# as a quoted string is not a type.
RAW_VAR = re.compile(r"!([A-Za-z_][A-Za-z0-9_-]*)")


# TypeQL datetimes are bare literals, not quoted strings, and the driver hands
# them back as ISO text. Quoting them is a type error at insert time.
ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$")


def format_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    text = str(v)
    if ISO_DATETIME.match(text):
        # trailing zeros in the fraction are legal but noisy; keep it simple
        return text.rstrip("0").rstrip(".") if "." in text else text
    return f'"{escape_string(text)}"'


def apply_derive(row, derive):
    """Compute extra fields from a row using format strings.

    Deliberately format strings and not eval: a migration rule should be able
    to say "prefix the description" without the orchestrator growing the
    ability to run arbitrary code over a live database.
    """
    if not derive:
        return row
    out = dict(row)
    for key, template in derive.items():
        try:
            out[key] = template.format(**{k: ("" if v is None else v) for k, v in row.items()})
        except (KeyError, IndexError):
            out[key] = row.get(key)
    return out


def substitute(template, row):
    """Fill $vars from the row; drop any line whose ?var is absent.

    The optional form is what lets one rule cover rows that do and do not
    carry an optional attribute, instead of needing a rule per combination.
    """
    lines = []
    for line in template.splitlines():
        opts = OPTIONAL_VAR.findall(line)
        if opts and any(row.get(o) in (None, "") for o in opts):
            continue
        line = OPTIONAL_VAR.sub(lambda m: format_value(row[m.group(1)]), line)
        lines.append(line)
    out = "\n".join(lines)
    out = RAW_VAR.sub(
        lambda m: str(row[m.group(1)]) if m.group(1) in row else m.group(0), out)
    out = VAR.sub(
        lambda m: format_value(row[m.group(1)]) if m.group(1) in row else m.group(0),
        out)
    # Dropping the last optional line takes the statement terminator with it,
    # and a trailing comma before one is a syntax error. Both are silent until
    # TypeDB rejects the query, so repair them here rather than asking every
    # rule author to order their optional attributes defensively.
    out = out.rstrip()
    out = re.sub(r",(\s*;)", r"\1", out)
    if not out.endswith(";"):
        out = out.rstrip().rstrip(",") + ";"
    return out


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def normalise(value):
    """TypeDB hands a fetched type variable back as {"label": ..., "kind": ...}.

    A rule that wants a roleplayer's concrete type wants the label and nothing
    else, so flatten it here rather than in every rule.
    """
    if isinstance(value, dict) and "label" in value:
        return value["label"]
    return value


def fetch_rows(src, source_db, query):
    with src.transaction(source_db, TransactionType.READ) as tx:
        return [{k: normalise(v) for k, v in row.items()}
                for row in tx.query(query).resolve()]


def existing_ids(tgt, target_db, ids, chunk=400):
    """Which of these ids the target already holds."""
    found = set()
    ids = [i for i in ids if i]
    for i in range(0, len(ids), chunk):
        part = ids[i:i + chunk]
        with tgt.transaction(target_db, TransactionType.READ) as tx:
            for one in part:
                q = f'match $x isa $t, has id "{escape_string(one)}"; fetch {{ "id": $x.id }};'
                try:
                    if list(tx.query(q).resolve()):
                        found.add(one)
                except Exception:
                    pass
    return found


def run(source_port, source_db, target_port, target_db, rules,
        dry_run=False, only=None, log=print):
    rules = topological_sort(rules)
    if only:
        rules = [r for r in rules if r.name in only]
    report = {"rules": [], "dry_run": dry_run}
    src, tgt = driver_for(source_port), driver_for(target_port)
    try:
        for rule in rules:
            t0 = time.time()
            rows = fetch_rows(src, source_db, rule.source_match)
            skipped = inserted = failed = no_match = 0
            errors = []

            if rule.idempotent and rule.kind == "entity" and not dry_run:
                ids = [r.get(rule.identity[0]) for r in rows]
                already = existing_ids(tgt, target_db, ids)
            else:
                already = set()

            if not dry_run:
                for raw in rows:
                    row = apply_derive(raw, rule.derive)
                    key = row.get(rule.identity[0])
                    if key in already:
                        skipped += 1
                        continue
                    q = substitute(rule.target_insert, row)
                    try:
                        with tgt.transaction(target_db, TransactionType.WRITE) as tx:
                            answer = tx.query(q).resolve()
                            # An insert whose match matches nothing writes
                            # nothing and raises nothing. Counting that as a
                            # success is how a migration reports 100% and
                            # leaves an empty database.
                            try:
                                wrote = len(list(answer))
                            except Exception:
                                wrote = 1
                            tx.commit()
                        if wrote:
                            inserted += 1
                        else:
                            no_match += 1
                    except Exception as e:
                        failed += 1
                        if len(errors) < 3:
                            errors.append(f"{key}: {str(e)[:160]}")
            entry = {"name": rule.name, "source_rows": len(rows),
                     "inserted": inserted, "skipped_existing": skipped,
                     "no_match": no_match, "failed": failed,
                     "seconds": round(time.time() - t0, 2)}
            if errors:
                entry["errors"] = errors
            if rule.notes:
                entry["notes"] = rule.notes
            report["rules"].append(entry)
            log(f"  {rule.name:<26} source {len(rows):>5}  inserted {inserted:>5}"
                f"  existing {skipped:>5}  no-match {no_match:>5}  failed {failed:>4}")
    finally:
        src.close()
        tgt.close()
    report["totals"] = {
        k: sum(r[k] for r in report["rules"])
        for k in ("source_rows", "inserted", "skipped_existing", "no_match", "failed")}
    return report


def verify(source_port, source_db, target_port, target_db, rules, log=print):
    """Count the same source_match on both sides. A migration that cannot be
    counted afterwards is a migration nobody should trust."""
    src, tgt = driver_for(source_port), driver_for(target_port)
    out = {"rules": [], "ok": True}
    try:
        for rule in topological_sort(rules):
            s = len(fetch_rows(src, source_db, rule.source_match))
            # A rule whose source_match filters on a legacy-only type cannot be
            # run against the target at all -- that is the point of migrating.
            # Such a rule declares verify_match instead.
            target_query = rule.verify_match or rule.source_match
            try:
                t = len(fetch_rows(tgt, target_db, target_query))
                err = ""
            except Exception as e:
                t, err = -1, str(e).split("\n")[0][:70]
            ok = t >= s
            row = {"name": rule.name, "source": s, "target": t, "ok": ok}
            if rule.verify_match:
                row["via"] = "verify_match"
            if err:
                row["error"] = err
            out["rules"].append(row)
            out["ok"] &= ok
            log(f"  {rule.name:<26} source {s:>5}  target {t:>5}  "
                f"{'ok' if ok else 'SHORT'}{'  (verify_match)' if rule.verify_match else ''}")
    finally:
        src.close()
        tgt.close()
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=["plan", "run", "verify"])
    p.add_argument("--source-db", required=True)
    p.add_argument("--target-db", required=True)
    p.add_argument("--source-port", default="1729")
    p.add_argument("--target-port", default="1729")
    p.add_argument("--rules-dir", required=True)
    p.add_argument("--rule", action="append", help="run only these rules")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()

    rules = load_rules(a.rules_dir)

    if a.action == "plan":
        ordered = topological_sort(rules)
        print(f"{len(ordered)} rules, in dependency order:\n")
        for r in ordered:
            print(f"  {r.name:<26} {r.kind:<9} {r.description}")
            if r.notes:
                for line in r.notes.strip().splitlines():
                    print(f"      note: {line}")
        return

    fn = run if a.action == "run" else verify
    kwargs = dict(dry_run=a.dry_run, only=a.rule) if a.action == "run" else {}
    log = (lambda *x: None) if a.json else print
    if not a.json:
        print(f"{a.action}: {a.source_db}@{a.source_port} -> {a.target_db}@{a.target_port}\n")
    result = fn(a.source_port, a.source_db, a.target_port, a.target_db, rules,
                log=log, **kwargs)
    if a.json:
        print(json.dumps(result, indent=2))
    else:
        print()
        if a.action == "run":
            print("  totals:", result["totals"])
        else:
            print("  ok" if result["ok"] else "  SHORT -- target is missing rows")
    if a.action == "verify" and not result["ok"]:
        sys.exit(1)
    if a.action == "run" and result["totals"]["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
