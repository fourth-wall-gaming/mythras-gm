# Migrating the legacy `mythras` database

The `mythras` database on `mythras-typedb:1730` was built before this skill's
types were re-parented onto alhazen-core's base hierarchy. It has
`myth-campaign sub myth-collection`; the current schema says `sub alh-collection`.
TypeDB will not accept a supertype change by `define`, so the current schema
cannot be loaded into it and the ordinary `export-campaign` cannot read it —
it queries `myth-time-index`, which that schema does not have.

So the data has to be *mapped* across rather than dumped and reloaded. These
are GLAV rules in the style of skillful-alhazen's `schema_mapper.py`, run by
`scripts/glav_migrate.py`.

**Identity is the existing `id`, preserved.** The alhazen mapper skolemises,
because it maps one domain's entities onto another's. Here the rows on both
sides are the same rows, and minting new ids would break every reference held
outside the database — the campaign package on disk, the journal, and anything
a GM has written down.

## What the source actually contains

Measured, not assumed:

| legacy-only attribute | rows | decision |
|---|---|---|
| `myth-rule-system` | 101 entities, all `"mythras"` | **dropped** — constant, and the whole database is Mythras |
| `myth-event-visibility` | 7 events, `meta` / `offscreen` | `meta` is **dropped** (those events already carry `event-type: gm-note`); `offscreen` is **preserved** into the description |
| `myth-canon-status`, `myth-superseded-by`, `myth-attitude`, `myth-system`, `myth-knowledge-*` | **0 rows** | nothing to carry |
| `myth-knowledge` (relation) | **0 rows** | superseded by `myth-knows`; nothing to carry |

`myth-agenda`, `myth-beat` and `myth-fact` do not exist in the legacy schema,
so the living-world layer starts empty for these campaigns. That is correct:
they were played before it existed.

## Running it

```bash
S=scripts/glav_migrate.py
R=migrations/legacy-mythras

python3 $S plan   --source-db mythras --target-db mythras_v2 --rules-dir $R \
                  --source-port 1730 --target-port 1730
python3 $S run    --source-db mythras --target-db mythras_v2 --rules-dir $R \
                  --source-port 1730 --target-port 1730 --dry-run
python3 $S run    --source-db mythras --target-db mythras_v2 --rules-dir $R \
                  --source-port 1730 --target-port 1730
python3 $S verify --source-db mythras --target-db mythras_v2 --rules-dir $R \
                  --source-port 1730 --target-port 1730
```

The target must already have the current schema loaded. Every rule is
idempotent on `id`, so a re-run inserts nothing and reports what it skipped.

**The legacy database is never written to.** It is the source, it stays as it
is, and there is a full native export of it under `~/mythras-backups/`.
