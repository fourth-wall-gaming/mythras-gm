# Storage backend switch: TypeDB in Code, JSON files in Chat / Cowork

**Status:** design approved, not implemented
**Date:** 2026-09-20
**Branch:** `feat/storage-backend-switch`

## Problem

`mythras-gm` persists every campaign in TypeDB. That works in Claude Code,
where a SessionStart hook can provision a native TypeDB server on port 1730.
It cannot work in Claude Chat or Cowork: no hook runs, no server can be
started, and `mythras_gm.py` hard-exits at import time when `typedb-driver`
is missing:

```python
try:
    from typedb.driver import Credentials, DriverOptions, TransactionType, TypeDB
except ImportError:
    print(json.dumps({"success": False, "error": "typedb-driver not installed"}))
    sys.exit(1)
```

The game needs a second storage backend — a tree of JSON files on disk — and
a switch that picks the right one without ever putting the Gamesmaster in
front of the wrong save file.

## What the survey found

Two findings reframed the work, and both are load-bearing for everything
below.

**There is no single query interface to divert.** `_fetch(driver, query)` and
`_write(driver, *queries)` are transaction wrappers that take *raw TypeQL
strings*. Those strings are hand-written at roughly 137 call sites in
`mythras_gm.py` (6,252 lines, 185 top-level functions, 88 subcommands) and 49
more in `campaign_io.py`. There is a layer of genuinely semantic helpers —
`_set_attr` (90 uses), `_get_entity` (44), `_load_character`,
`_link_to_campaign` — and those are portable as they stand. The raw-TypeQL
sites are not. Building the interface *is* the work.

**Nothing in the codebase uses TypeDB as a graph database.** Across all 137
sites there are no aggregates, no `sort`, no `limit` or `offset` pushed into
TypeQL — every ranking and truncation happens in Python after the fetch. There
are four negations, all four inside a single legacy-rules migration in
`load-rules`. Every relation traversal is one hop over one relation, and 23 of
them are the same campaign-membership pattern. No rule inference is defined or
used.

Five query shapes cover essentially the whole surface: get entity by id, set
one attribute, list entities of a type, walk one relation one hop, insert an
entity or a relation. A JSON backend therefore gives up nothing — there is no
join or inference to lose. The port is mechanical rather than a redesign of
query semantics.

A third finding is a free win: `_get_entity` issues **one query per
attribute**. Loading a character with its 19 attributes costs 20 round trips.
The JSON store answers the same call with one file read.

## Decisions

| Question | Decision |
|---|---|
| Where Chat/Cowork campaigns live | Cowork's persistent workspace. A real save file, no upload/download ritual. |
| Command parity | All 88. The backend is invisible to `SKILL.md`, `TABLE.md` and the agents. |
| LinkML's role | Readable source for the model; generates the JSON side; a parity test holds `schema.tql` to it. |
| Backend selection | Detection picks the *default*; explicit override wins; **never a silent fallback**. |
| On-disk layout | Purpose-built, id-addressed store. The v1.1 publish tree stays a separate, readable snapshot format. |

## Section 1 — The seam: a `CampaignStore` repository interface

The abstraction goes at the **semantic** level, not the query-string level.
Abstracting TypeQL strings would mean writing a TypeQL interpreter over JSON;
abstracting the five shapes means writing fourteen methods.

New package `skills/mythras-gm/store/`:

```
store/
  __init__.py        resolve_store() -- the switch
  base.py            CampaignStore ABC
  typedb_store.py    TypeDBStore
  json_store.py      JsonStore
  model.py           generated from LinkML; checked in
```

### The interface

```python
class CampaignStore(ABC):
    # entities
    def get_entity(self, etype, eid, attrs) -> dict | None
    def put_entity(self, etype, eid, attrs) -> None
    def set_attr(self, etype, eid, attr, value) -> None
    def delete_entity(self, etype, eid) -> None
    def list_entities(self, etype, where=None) -> list[dict]

    # relations
    def link(self, relation, roles: dict, attrs=None) -> None
    def unlink(self, relation, roles: dict) -> None
    def related(self, relation, from_role, eid, to_role, to_type=None) -> list[str]
    def relation_pairs(self, relation, role_a, role_b, type_a=None, type_b=None) -> list[tuple]

    # campaign membership -- the 23-site pattern, named
    def members(self, campaign_id, etype) -> list[str]
    def add_member(self, campaign_id, eid, etype) -> None

    # meta
    def declared(self, *type_names) -> list[str]
    def transaction(self) -> ContextManager
    def describe(self) -> dict   # backend name, location, health -- for doctor
```

`get_entity` keeps today's contract exactly: listed attributes come back, and
optional ones the store has never heard of come back `None` rather than
exploding.

### What changes at the call sites

The 134 `_set_attr` / `_get_entity` / `_link_to_campaign` call sites **do not
change at all** — those helpers keep their signatures and delegate to the
active store. The ~137 raw-TypeQL sites become calls on the fourteen methods.
`mythras_gm.py` stops importing `typedb.driver` entirely; that import moves
inside `typedb_store.py`, where an `ImportError` is a backend-unavailable
condition rather than a process-wide suicide.

`TypeDBStore` is not a rewrite — today's queries move into it close to
verbatim, including the `declared()` / `_opt()` / `_optf()` machinery that
lets a database older than the schema still be read.

### Consequences worth naming

This refactor touches a 6,252-line file and is the bulk of the work. It is
also the refactor that file already needed: a single interface is what makes
the second backend a few hundred lines rather than a second codebase.

The `JsonStore` needs no `_opt`/`_optf` equivalent. An attribute in a JSON
document is present or absent; there is no type inference to fail. The
schema-drift problem those helpers exist to solve does not arise, and
`declared()` answers from the generated model.

## Section 2 — The JSON store on disk

Purpose-built and id-addressed, because a live store's job is correct
random-access mutation. `campaign_io.py`'s v1.1 tree keeps its own job —
readable, publishable, git-committable snapshots — and `SKILL.md`'s rule that
"a published file tree is a snapshot, not the live game" survives untouched.

```
<store-root>/
  store.json                             manifest: format version, backend marker,
                                         schema version, generated-by
  entities/
    myth-campaign/<id>.json
    myth-character/<id>.json
    myth-location/<id>.json
    myth-game-event/<id>.json
    ...one directory per entity type
  relations/
    myth-campaign-membership.jsonl
    myth-presence.jsonl
    myth-knows.jsonl
    ...one file per relation type
  oplog.jsonl                            append-only; one line per committed
                                         transaction
```

An entity file is a flat JSON object: `{"id": ..., "name": ..., "myth-char-type":
"pc", ...}`. Attribute names are the schema's names verbatim, so a document is
recognisably the same thing the TypeDB backend holds.

A relation line is `{"roles": {"campaign": "<id>", "element": "<id>"}, "attrs":
{}}`. One file per relation type keeps the scan narrow.

**No index files.** A campaign runs to a few hundred entities and a couple of
thousand relation rows; a directory listing and a linear scan answer every one
of the five shapes in microseconds. Indexes would be state that can disagree
with the data, bought with nothing. If a campaign ever outgrows this, shard
`myth-game-event` by session number — the interface hides it.

### Atomicity

Each file is written temp-then-`os.replace`, which is atomic on POSIX, so no
file is ever torn. `transaction()` buffers mutations in memory and flushes on
commit.

A multi-file commit is **not** atomic across files, and the spec says so
rather than implying a guarantee that isn't there. `oplog.jsonl` closes the
gap: one appended line per committed transaction listing the files it touched
and their post-state hashes. A commit interrupted mid-flush is therefore
*detectable* — `doctor` compares the last oplog entry against what is on disk
and reports the discrepancy instead of the game quietly running on a
half-written save. This is proportionate for a single-player save file written
by one CLI process at a time; full WAL recovery is not.

### Where the root lives

Resolution order for `<store-root>`:

1. `MYTHRAS_STORE` if set
2. `<dir>/campaigns/` for the first `<dir>` in a probe list that exists and is
   writable. The list is a small, ordered set of known workspace roots,
   defined in one place in `store/__init__.py` so it can be corrected in a
   single edit when a host's layout turns out to differ.
3. `./campaigns/` relative to the working directory

The probe list is a guess about someone else's runtime, so it is arranged to
fail safely: a wrong entry is skipped rather than used, and if nothing matches
the CWD-relative default applies and `doctor` reports exactly which path was
chosen and why. **Confirm the real Cowork workspace path before implementing
step 2** — until that is verified, step 2 is an empty list and steps 1 and 3
carry the feature.

`init-db` under the JSON backend creates the root and writes `store.json`; it
starts no server. `stop-db` is a no-op that says so.

## Section 3 — LinkML

`schema/mythras.linkml.yaml` becomes the readable definition of the model: 13
entity classes, 21 relation classes with their roles (and, for `myth-knows` and `myth-consequence`, the attributes the relation itself owns), and every attribute as a
slot carrying its type and the description currently living in a `schema.tql`
comment.

It is a **build-time** tool, not a runtime dependency. It generates
`store/model.py` — plain dataclasses and dicts, no Pydantic — and that file is
**checked into the repo**. Two reasons: the Cowork sandbox may not be able to
install anything, and the JSON backend must therefore be **pure stdlib**.
LinkML stays in the dev dependency group.

`schema.tql` remains hand-written and battle-tested; it is not regenerated. A
LinkML→TypeQL generator would have to reproduce the existing schema byte-exact
or every live database stops loading, and that is a subproject that buys
little here.

What prevents drift is a test, not a generator. `tests/test_schema_parity.py`
parses both `schema.tql` and the LinkML model and asserts:

- the same set of entity types, with the same supertypes
- the same set of relation types, with the same role names
- the same set of attributes, with matching value types
- every attribute owned by the same entity types in both

Adding an attribute to one and not the other fails CI. This is the mechanism
that keeps the two backends describing one game rather than two.

## Section 4 — The switch

### Resolution order

1. **`MYTHRAS_BACKEND`** (`typedb` | `json`) — explicit always wins.
2. **Store marker** — if `MYTHRAS_STORE` names a directory containing
   `store.json`, the backend is `json`. A store that exists is evidence about
   where a save lives, and it outranks a guess about the environment.
3. **Environment detection** — `CLAUDECODE` in the environment means Claude
   Code, so `typedb`. Absent, the default is `json`.
4. **Default** — `json`, because the failure mode is benign: a JSON store that
   does not exist yet is a loud, informative error, while a wrongly-attempted
   TypeDB connection is a confusing one.

Detection only ever selects a *default*, and `CLAUDECODE` is an undocumented
internal, so being wrong about it must stay cheap. It is: an explicit override
outranks it, a store marker outranks it, and neither branch can silently open
the wrong save.

### Never a silent fallback

This is the rule the whole design is arranged around. The skill's entire
discipline rests on the Gamesmaster never narrating into a save that isn't the
player's.

- Backend resolves to `typedb`, server unreachable → today's loud `fail()`,
  verbatim. **Not** a quiet switch to an empty JSON store.
- Backend resolves to `json`, store root absent → fail, naming every path
  searched. A store is created only by `init-db`, `create-campaign` or
  `import-campaign` — never as a side effect of a read.
- Backend resolves to `json`, store present but schema version ahead of this
  build → fail with the version mismatch.

### `doctor` and the preflight

`doctor` reports the active backend, why it was chosen, the store location or
server address, and the oplog consistency check. `hooks/session-start.sh` gets
the same treatment: under the JSON backend it validates the store and reports
"database" in terms the model reads the same way, so the preflight's refusal
language keeps working unchanged.

## Testing

**A conformance suite is the core guarantee.** `tests/test_store_conformance.py`
runs one set of assertions against *both* implementations through a
parametrized fixture. Every one of the fourteen methods, every one of the five
query shapes, absent-attribute behaviour, relation round-trips, and
transaction rollback. Behaviour that isn't in the conformance suite isn't
guaranteed to match.

TypeDB-backed parameters skip cleanly when no server is reachable, so the
suite stays runnable in Cowork.

**Round-trip equivalence.** `export-campaign` from a TypeDB campaign, import
into a JSON store, export again — the two v1.1 trees must be identical. This
is the test that proves the backends hold the same game.

**Existing tests.** `tests/` is mostly DB-free already; only `conftest.py`,
`test_cli_ergonomics.py` and `test_novelist.py` touch a driver. Those move to
the store interface and gain a JSON-backed parameter, which makes them
runnable without a server for the first time.

## Migration between backends

No new tool. `export-campaign` and `import-campaign` already move a campaign
losslessly through the v1.1 tree with ids preserved, and once both backends
implement the same interface those commands work in both directions. Moving a
game from Code to Cowork is: export, copy the folder into the workspace,
import.

## Out of scope

- A LinkML→TypeQL generator (see Section 3).
- Multi-process or concurrent-writer support for the JSON store. One CLI
  invocation at a time is the actual usage.
- Any change to the rules engine, the dice, or the TABLE.md voice work. This
  is a storage change and must be invisible at the table.
- Changing the v1.1 publish format.

## Risks

**The refactor's blast radius.** 137 call sites in a file that is the whole
game. Mitigated by porting shape-by-shape rather than command-by-command
(§Section 1), by the conformance suite, and by `TypeDBStore` keeping today's
queries verbatim so the Code path is behaviour-preserving by construction.

**Two backends drifting.** Mitigated by the parity test and the conformance
suite. Neither is optional.

**`CLAUDECODE` changing or being absent.** Mitigated by making detection
choose only a default, behind two higher-priority signals, with no silent
fallback on either branch.
