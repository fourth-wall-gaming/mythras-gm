#!/usr/bin/env python
"""Id-preserving copy of a mythras database into another database.

Standalone -- talks to TypeDB directly, depends on nothing in Alhazen. Written
for the August 2026 decouple/rename migration (alh_mythras -> mythras), but it
is a general capability: back a game up into a scratch DB, clone a database
before a risky change, or move data between servers.

It is schema-driven only in the sense that it knows the myth- type inventory
(below). Attribute VALUES are read generically via `has $a`, so adding an
attribute to an existing entity type needs no change here; adding a whole new
entity or relation type does.

    python db_copy.py copy --src alh_mythras --dst mythras [--schema-dir DIR]

The destination is created if absent and loaded from base-schema.tql +
schema.tql (found next to this file, or under --schema-dir). Copy is additive;
run against an empty destination.
"""
import argparse
import os
import sys

from typedb.driver import TypeDB, Credentials, DriverOptions, TransactionType

HERE = os.path.dirname(os.path.abspath(__file__))

# Concrete entity types, in an order safe for foreign-key-free inserts (any
# order works -- entities carry no cross-references except via relations, which
# are copied afterwards).
ENTITY_TYPES = [
    "myth-campaign", "myth-character", "myth-creature-template",
    "myth-location", "myth-faction", "myth-encounter",
    "myth-game-event", "myth-lore", "myth-rule", "myth-rule-facet",
]

# (relation type, [role names], [relation-owned attribute names]).
RELATION_TYPES = [
    ("myth-campaign-membership", ["campaign", "element"], []),
    ("myth-presence", ["located", "location"], []),
    ("myth-participation", ["encounter", "combatant"], []),
    ("myth-event-involvement", ["event", "participant"], []),
    ("myth-faction-membership", ["faction", "member"], []),
    ("myth-template-instance", ["template", "instance"], []),
    ("myth-lore-about", ["lore", "subject"], []),
    ("myth-knowledge", ["knower", "subject"],
     ["myth-knowledge-depth", "myth-knowledge-route", "myth-knowledge-note",
      "myth-attitude", "myth-session-number"]),
    ("myth-rule-tagged", ["rule", "facet"], []),
    ("myth-rule-link", ["rule", "linked"], []),
]


def _driver():
    return TypeDB.driver(
        f"{os.getenv('TYPEDB_HOST', 'localhost')}:{os.getenv('TYPEDB_PORT', '1729')}",
        Credentials(os.getenv("TYPEDB_USERNAME", "admin"),
                    os.getenv("TYPEDB_PASSWORD", "password")),
        DriverOptions(is_tls_enabled=False))


def _esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _literal(attr):
    """TypeQL literal for an attribute concept's value."""
    if attr.is_string():
        return '"' + _esc(attr.try_get_string()) + '"'
    if attr.is_integer():
        return str(attr.try_get_integer())
    if attr.is_boolean():
        return "true" if attr.try_get_boolean() else "false"
    if attr.is_double():
        return str(attr.try_get_double())
    if attr.is_datetime():
        return str(attr.try_get_datetime()).replace(" ", "T")
    if attr.is_date():
        return str(attr.try_get_date())
    raise ValueError(f"unhandled value type for {attr.get_type().get_label()}")


def _count(tx, typ):
    r = list(tx.query(f"match $x isa {typ}; reduce $c = count;").resolve())
    return r[0].get("c").get_integer() if r else 0


def load_schema(driver, db, schema_dir):
    for fname in ("base-schema.tql", "schema.tql"):
        path = os.path.join(schema_dir, fname)
        with open(path, encoding="utf-8") as fh, \
                driver.transaction(db, TransactionType.SCHEMA) as tx:
            tx.query(fh.read()).resolve()
            tx.commit()


def copy_entities(driver, src, dst):
    total = 0
    for typ in ENTITY_TYPES:
        # gather {id: [(attr_label, literal), ...]}
        rows = {}
        with driver.transaction(src, TransactionType.READ) as tx:
            for row in tx.query(f"match $x isa {typ}, has id $id, has $a;").resolve():
                iid = row.get("id").try_get_string()
                a = row.get("a")
                label = str(a.get_type().get_label())
                rows.setdefault(iid, []).append((label, _literal(a)))
        # insert
        with driver.transaction(dst, TransactionType.WRITE) as tx:
            for iid, attrs in rows.items():
                has = ", ".join(f"has {lbl} {lit}" for lbl, lit in attrs)
                tx.query(f"insert $e isa {typ}, {has};").resolve()
            tx.commit()
        print(f"  {typ:26s} {len(rows)}")
        total += len(rows)
    return total


def copy_relations(driver, src, dst):
    total = 0
    for rel, roles, attrs in RELATION_TYPES:
        links = ", ".join(f"{r}: $p{i}" for i, r in enumerate(roles))
        idbind = "; ".join(f"$p{i} has id $i{i}" for i, _ in enumerate(roles))
        abind = "".join(f", has {a} $va{j}" for j, a in enumerate(attrs))
        recs = []
        with driver.transaction(src, TransactionType.READ) as tx:
            q = f"match $r isa {rel}, links ({links}){abind}; {idbind};"
            for row in tx.query(q).resolve():
                ids = [row.get(f"i{i}").try_get_string() for i, _ in enumerate(roles)]
                # pin each player's concrete type so role compatibility resolves
                # (matching by id alone infers the base type and the insert fails)
                ptypes = [str(row.get(f"p{i}").get_type().get_label())
                          for i, _ in enumerate(roles)]
                avals = [(a, _literal(row.get(f"va{j}"))) for j, a in enumerate(attrs)]
                recs.append((ids, ptypes, avals))
        with driver.transaction(dst, TransactionType.WRITE) as tx:
            for ids, ptypes, avals in recs:
                mparts = "; ".join(
                    f'$p{i} isa {ptypes[i]}, has id "{_esc(ids[i])}"'
                    for i, _ in enumerate(roles))
                links_ins = ", ".join(f"{r}: $p{i}" for i, r in enumerate(roles))
                ahas = "".join(f", has {a} {lit}" for a, lit in avals)
                tx.query(f"match {mparts}; "
                         f"insert ({links_ins}) isa {rel}{ahas};").resolve()
            tx.commit()
        print(f"  {rel:26s} {len(recs)}")
        total += len(recs)
    return total


def cmd_copy(args):
    driver = _driver()
    try:
        if not driver.databases.contains(args.src):
            sys.exit(f"source database '{args.src}' does not exist")
        if driver.databases.contains(args.dst):
            if not args.allow_existing:
                sys.exit(f"destination '{args.dst}' already exists "
                         f"(use --allow-existing to copy into it)")
        else:
            driver.databases.create(args.dst)
            load_schema(driver, args.dst, args.schema_dir)
            print(f"created '{args.dst}' and loaded schema")

        print("entities:")
        ne = copy_entities(driver, args.src, args.dst)
        print("relations:")
        nr = copy_relations(driver, args.src, args.dst)
        print(f"copied {ne} entities + {nr} relations = {ne + nr} instances")

        # verify per-type parity
        print("verify (src == dst):")
        ok = True
        with driver.transaction(args.src, TransactionType.READ) as s, \
                driver.transaction(args.dst, TransactionType.READ) as d:
            for typ in ENTITY_TYPES + [r[0] for r in RELATION_TYPES]:
                cs, cd = _count(s, typ), _count(d, typ)
                flag = "OK" if cs == cd else "MISMATCH"
                if cs != cd:
                    ok = False
                print(f"  {typ:26s} src={cs:5d} dst={cd:5d} {flag}")
        sys.exit(0 if ok else 2)
    finally:
        driver.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("copy", help="id-preserving copy src -> dst")
    c.add_argument("--src", required=True)
    c.add_argument("--dst", required=True)
    c.add_argument("--schema-dir", default=HERE)
    c.add_argument("--allow-existing", action="store_true")
    c.set_defaults(func=cmd_copy)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
