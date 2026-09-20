# Storage Backend Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `mythras-gm` a second storage backend — a tree of JSON files — so campaigns can run in Claude Chat / Cowork where TypeDB cannot, with all 88 CLI commands working identically on both.

**Architecture:** Introduce a `CampaignStore` repository interface with fourteen semantic methods covering the five query shapes the codebase actually uses. Two implementations — `TypeDBStore` (today's TypeQL moved in verbatim) and `JsonStore` (pure stdlib, id-addressed files) — are held to one parametrized conformance suite. A `resolve_store()` switch picks the backend from an explicit override, then a store marker, then environment detection, and never silently falls back.

**Tech Stack:** Python 3.11–3.13, stdlib only for the JSON backend; `typedb-driver` 3.8.x for the TypeDB backend; LinkML as a dev-only build-time tool; pytest.

**Spec:** [`docs/superpowers/specs/2026-09-20-storage-backend-switch-design.md`](../specs/2026-09-20-storage-backend-switch-design.md)

## Global Constraints

- **The JSON backend is pure stdlib.** No Pydantic, no LinkML at runtime, no third-party imports in `store/json_store.py` or `store/model.py`. The Cowork sandbox may not be able to install anything.
- **LinkML is a dev dependency only** (`[dependency-groups] dev`). `store/model.py` is generated at build time and **checked into the repo**.
- **`schema.tql` is hand-written and is never regenerated.** A parity test holds it and the LinkML model in agreement.
- **Never a silent fallback.** A backend that resolves to `typedb` and cannot reach a server fails loudly. It must never open a JSON store instead.
- **`TypeDBStore` preserves behaviour exactly.** Existing TypeQL moves in verbatim, including the `declared()` / `_opt()` / `_optf()` machinery for databases older than the schema.
- **No changes to the rules engine, dice, or table voice.** `mythras_engine.py`, `mythras_effects.py`, `TABLE.md` and `styles/` are out of scope. This change must be invisible at the table.
- Python floor: `>=3.11,<3.14` (from `skills/mythras-gm/pyproject.toml`).
- Tests must never touch a live database or a live store. `tests/conftest.py` forces `TYPEDB_DATABASE=mythras_pytest`; it must gain the same discipline for `MYTHRAS_STORE`.

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `skills/mythras-gm/schema/mythras.linkml.yaml` | Readable definition of the model: 13 entities, 21 relations, 63 attributes |
| `skills/mythras-gm/scripts/gen_model.py` | Build-time generator: LinkML YAML → `store/model.py` |
| `skills/mythras-gm/store/__init__.py` | `resolve_store()` — the switch, plus store-root resolution |
| `skills/mythras-gm/store/base.py` | `CampaignStore` ABC and `StoreError` |
| `skills/mythras-gm/store/model.py` | Generated, checked in: `ENTITY_TYPES`, `RELATION_TYPES`, `ATTRIBUTE_TYPES`, `BASE_ATTRS` |
| `skills/mythras-gm/store/typedb_store.py` | `TypeDBStore` |
| `skills/mythras-gm/store/json_store.py` | `JsonStore` |
| `tests/test_store_conformance.py` | One suite, both backends, parametrized |
| `tests/test_schema_parity.py` | `schema.tql` ↔ LinkML drift guard |
| `tests/test_backend_switch.py` | Resolution order and the no-silent-fallback rule |
| `tests/test_roundtrip_equivalence.py` | TypeDB → export → JSON → export produces identical trees |

**Modified:**

| Path | Change |
|---|---|
| `skills/mythras-gm/mythras_gm.py` | Helper layer delegates to the store; ~137 raw-TypeQL sites ported; top-level `typedb.driver` import removed |
| `skills/mythras-gm/campaign_io.py` | 49 store-touching sites ported |
| `skills/mythras-gm/novelist.py` | Driver use ported |
| `tests/conftest.py` | Force `MYTHRAS_STORE` to a temp root; add backend fixtures |
| `hooks/session-start.sh` | Backend-aware preflight |
| `skills/mythras-gm/SKILL.md`, `USAGE.md` | Document the two backends |
| `skills/mythras-gm/pyproject.toml` | `typedb-driver` becomes optional; LinkML added to dev group |

---

### Task 1: LinkML model and the generated model module

**Files:**
- Create: `skills/mythras-gm/schema/mythras.linkml.yaml`
- Create: `skills/mythras-gm/scripts/gen_model.py`
- Create: `skills/mythras-gm/store/model.py` (generated output, committed)
- Create: `tests/test_schema_parity.py`
- Modify: `skills/mythras-gm/pyproject.toml`

**Interfaces:**
- Consumes: nothing.
- Produces: `store/model.py` exporting four module-level constants —
  `ENTITY_TYPES: dict[str, dict]` mapping entity name → `{"parent": str, "owns": list[str]}`;
  `RELATION_TYPES: dict[str, dict]` mapping relation name → `{"roles": list[str], "owns": list[str]}` — relations own attributes too (`myth-knows` owns eight), so roles alone cannot describe them;
  `ATTRIBUTE_TYPES: dict[str, str]` mapping attribute name → one of `"string" | "integer" | "datetime"`;
  `BASE_ATTRS: list[str]` = `["id", "name", "description", "content", "created-at"]`.

- [ ] **Step 1: Write the failing parity test**

```python
# tests/test_schema_parity.py
"""The LinkML model and schema.tql must describe one game, not two.

Two backends read from two descriptions of the model. Nothing but this test
stops someone adding an attribute to one and not the other, at which point a
campaign saved in Code stops round-tripping into Cowork -- silently, because
an absent attribute reads as None rather than as an error.
"""
import re
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "mythras-gm"


def _tql_entities(text):
    """{entity_name: (parent, {owned attrs})} from schema.tql."""
    out = {}
    for block in re.finditer(
        r"^entity (\S+?)(?: @abstract)? sub (\S+?),(.*?);$", text, re.S | re.M
    ):
        name, parent, body = block.group(1), block.group(2), block.group(3)
        owns = set(re.findall(r"owns ([a-z0-9-]+)", body))
        out[name] = (parent, owns)
    return out


def _tql_relations(text):
    """{relation_name: {"roles": [...], "owns": {...}}} from schema.tql.

    Roles carry cardinality annotations (`relates fact @card(0..1)`) which the
    name regex stops before, and relations own attributes of their own --
    myth-knows owns eight, which is where knowledge certainty and provenance
    live.
    """
    out = {}
    for block in re.finditer(r"^relation (\S+?),(.*?);$", text, re.S | re.M):
        body = block.group(2)
        out[block.group(1)] = {
            "roles": re.findall(r"relates ([a-z0-9-]+)", body),
            "owns": set(re.findall(r"owns ([a-z0-9-]+)", body)),
        }
    return out


def _tql_attributes(text):
    return {m.group(1): m.group(2)
            for m in re.finditer(r"^attribute ([a-z0-9-]+), value (\w+)", text, re.M)}


def _schema_text():
    return ((SKILL / "schema-base.tql").read_text()
            + "\n" + (SKILL / "schema.tql").read_text())


def test_entity_types_match():
    from store import model
    tql = _tql_entities(_schema_text())
    myth_tql = {k: v for k, v in tql.items() if k.startswith("myth-")}
    assert set(myth_tql) == set(model.ENTITY_TYPES), (
        "entity types differ between schema.tql and the LinkML model"
    )
    for name, (parent, _owns) in myth_tql.items():
        assert model.ENTITY_TYPES[name]["parent"] == parent, f"{name} parent differs"


def test_entity_attribute_ownership_matches():
    from store import model
    tql = _tql_entities(_schema_text())
    for name, (_parent, owns) in tql.items():
        if not name.startswith("myth-"):
            continue
        assert owns == set(model.ENTITY_TYPES[name]["owns"]), (
            f"{name} owns different attributes in schema.tql vs the model"
        )


def test_relation_types_and_roles_match():
    from store import model
    tql = _tql_relations(_schema_text())
    myth_tql = {k: v for k, v in tql.items() if k.startswith("myth-")}
    assert set(myth_tql) == set(model.RELATION_TYPES)
    for name, spec in myth_tql.items():
        assert spec["roles"] == list(model.RELATION_TYPES[name]["roles"]), (
            f"{name} roles differ")


def test_relation_attribute_ownership_matches():
    """myth-knows owns eight attributes and myth-consequence two.

    Miss these and knowledge certainty, provenance and consequence amounts
    survive in TypeDB and vanish in JSON -- silently, because an absent
    attribute reads as None.
    """
    from store import model
    tql = _tql_relations(_schema_text())
    for name, spec in tql.items():
        if not name.startswith("myth-"):
            continue
        assert spec["owns"] == set(model.RELATION_TYPES[name]["owns"]), (
            f"{name} owns different attributes in schema.tql vs the model")


def test_attribute_value_types_match():
    from store import model
    tql = _tql_attributes(_schema_text())
    for attr, value_type in tql.items():
        if not attr.startswith("myth-"):
            continue
        assert attr in model.ATTRIBUTE_TYPES, f"{attr} missing from the model"
        assert model.ATTRIBUTE_TYPES[attr] == value_type, f"{attr} value type differs"


def test_base_attrs_are_the_inherited_ones():
    from store import model
    assert model.BASE_ATTRS == ["id", "name", "description", "content", "created-at"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd /Users/gullyburns/mythras-gm && uv run --project skills/mythras-gm python -m pytest tests/test_schema_parity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'store'`

- [ ] **Step 3: Write the LinkML model**

Create `skills/mythras-gm/schema/mythras.linkml.yaml`. Transcribe every entity, relation and attribute from `schema.tql` and `schema-base.tql`, carrying the existing comments across as `description:`. Shape:

```yaml
id: https://fourth-wall-gaming.github.io/mythras-gm/schema
name: mythras-gm
title: Mythras GM campaign model
description: >-
  The persistent model behind mythras-gm. This is the readable definition of
  the game's state; schema.tql is the TypeDB rendering of the same model and
  tests/test_schema_parity.py holds the two in agreement.
prefixes:
  linkml: https://w3id.org/linkml/
  myth: https://fourth-wall-gaming.github.io/mythras-gm/schema/
default_prefix: myth
default_range: string
imports:
  - linkml:types

classes:
  AlhIdentifiableEntity:
    abstract: true
    description: Base type; everything in the game has these.
    attributes:
      id:
        identifier: true
        description: Stable id; @key in TypeDB, filename in the JSON store.
      name: {}
      description: {}
      content:
        description: Rich narrative text.
      created-at:
        range: datetime

  AlhDomainThing:
    is_a: AlhIdentifiableEntity
    description: A thing in the world.
  AlhCollection:
    is_a: AlhIdentifiableEntity
    description: A container of things.
  AlhNote:
    is_a: AlhIdentifiableEntity
    description: Rich text, via content.

  MythCampaign:
    is_a: AlhCollection
    annotations:
      typedb_name: myth-campaign
    attributes:
      myth-system: {}
      myth-game-date:
        description: In-world calendar date.
      myth-staging-notes:
        description: The world's physical laws; shown with EVERY place brief.
      myth-played-pcs:
        description: >-
          Comma-separated ids of the PCs somebody is actually playing;
          staging counts only these.
      myth-arc-json:
        description: The act skeleton from story.md.
      myth-current-scene: {}
      myth-session-number:
        range: integer
      myth-time-index:
        range: integer

  MythCharacter:
    is_a: AlhDomainThing
    annotations:
      typedb_name: myth-character
    attributes:
      myth-canon-status: {}
      myth-superseded-by: {}
      myth-char-type:
        description: pc | npc | creature
      myth-status:
        description: active | dead | retired | template
      myth-characteristics-json: {}
      myth-attributes-json: {}
      myth-skills-json: {}
      myth-hit-locations-json: {}
      myth-equipment-json: {}
      myth-passions-json: {}
      myth-combat-styles-json: {}
      myth-fatigue: {}
      myth-luck-current:
        range: integer
      myth-magic-current:
        range: integer
      myth-experience-rolls:
        range: integer
      myth-spells-json: {}
      myth-powers-json: {}
      myth-extras-json: {}
      myth-actor-notes:
        description: "How to PLAY them: bearing, speech, tell | wants, won't, because."

  # ...continue for the remaining 11 entity classes, transcribed from
  # schema.tql lines 266-492: MythCreatureTemplate, MythLocation, MythFaction,
  # MythEncounter, MythGameEvent, MythAgenda, MythBeat, MythLore, MythFact,
  # MythRuleFacet, MythRule.

relations:
  myth-campaign-membership:
    roles: [campaign, element]
  myth-presence:
    roles: [located, location]
  myth-participation:
    roles: [encounter, combatant]
  myth-event-involvement:
    roles: [event, participant]
  myth-faction-membership:
    roles: [faction, member]
  myth-template-instance:
    roles: [template, instance]
  myth-lore-about:
    roles: [lore, subject]
  myth-agenda-holder:
    roles: [agenda, holder]
  myth-agenda-target:
    roles: [agenda, target]
  myth-beat-of:
    roles: [beat, agenda]
  myth-beat-at:
    roles: [beat, place]
  myth-beat-cast:
    roles: [beat, member]
  myth-beat-outcome:
    roles: [beat, event]
  myth-fact-from:
    roles: [fact, origin]
  myth-fact-about:
    roles: [fact, subject]
  myth-knows:
    # THREE roles, not two: a knower knows either a fact or a subject, each
    # optional. And eight owned attributes -- this is where knowledge
    # certainty, provenance and attitude live.
    roles: [knower, fact, subject]
    owns:                             # same shape as a class's `attributes:`
      myth-knowledge-certainty: {}    # knows | believes | suspects | wrong
      myth-knowledge-source: {}       # witnessed | told | deduced | rumor
      myth-knowledge-since:
        range: integer                # world-clock index when this knower learned it
      myth-knowledge-depth: {}        # glimpsed | knows | can-prove
      myth-knowledge-route: {}        # witnessed | told | shown | inferred | bought | rumour
      myth-knowledge-note: {}         # THEIR reading of it; may be flatly wrong
      myth-attitude: {}
      myth-session-number:
        range: integer
  myth-agenda-requires:
    roles: [agenda, fact]
  myth-consequence:
    roles: [fact, agenda]
    owns:
      myth-consequence-effect: {}     # thwart | abandon | stall | advance | complete | activate
      myth-consequence-amount:
        range: integer                # clock segments, for stall/advance
  myth-fact-supersedes:
    roles: [superseding, superseded]
  myth-rule-tagged:
    roles: [rule, facet]
  myth-rule-link:
    roles: [rule, linked]
```

The role names above were read out of `schema.tql:139-262`; check any you
change against that file rather than against this excerpt. Note `myth-knows`
and `myth-consequence` — relations owning attributes is the thing easiest to
miss, and the parity test added below is what catches it.

LinkML has no native relation construct with named roles, so relations live
in a top-level `relations:` block that the generator reads directly. It is
plain YAML either way; the LinkML `classes:` section is what LinkML tooling
validates.

- [ ] **Step 4: Write the generator**

```python
#!/usr/bin/env python3
# skills/mythras-gm/scripts/gen_model.py
"""Generate store/model.py from schema/mythras.linkml.yaml.

Build-time only. The output is committed, so the shipped plugin needs neither
LinkML nor PyYAML at runtime and the JSON backend stays pure stdlib.

Run after editing the LinkML model:
    uv run --project skills/mythras-gm python skills/mythras-gm/scripts/gen_model.py
"""
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
SRC = SKILL / "schema" / "mythras.linkml.yaml"
DST = SKILL / "store" / "model.py"

LINKML_TO_TQL = {"string": "string", "integer": "integer", "datetime": "datetime"}


def main():
    doc = yaml.safe_load(SRC.read_text())
    classes = doc["classes"]

    # Resolve each myth- class to its TypeDB name, parent and owned attributes.
    entity_types, attribute_types = {}, {}
    for cls_name, cls in classes.items():
        tql_name = (cls.get("annotations") or {}).get("typedb_name")
        if not tql_name:
            continue                      # an alh- base class; not a myth- entity
        parent_cls = classes[cls["is_a"]]
        parent = (parent_cls.get("annotations") or {}).get("typedb_name") \
            or _alh_name(cls["is_a"])
        owns = list((cls.get("attributes") or {}).keys())
        entity_types[tql_name] = {"parent": parent, "owns": owns}
        for attr, spec in (cls.get("attributes") or {}).items():
            rng = (spec or {}).get("range", doc.get("default_range", "string"))
            attribute_types[attr] = LINKML_TO_TQL[rng]

    # Relations own attributes too -- myth-knows owns eight, myth-consequence
    # two -- and most are declared nowhere else, so this pass types them.
    relation_types = {}
    for name, spec in doc["relations"].items():
        owns = spec.get("owns") or {}
        relation_types[name] = {"roles": list(spec["roles"]),
                                "owns": sorted(owns)}
        for attr, aspec in owns.items():
            rng = (aspec or {}).get("range", doc.get("default_range", "string"))
            existing = attribute_types.get(attr)
            if existing and existing != LINKML_TO_TQL[rng]:
                raise SystemExit(
                    f"{attr} is {existing} on an entity and {rng} on {name}")
            attribute_types[attr] = LINKML_TO_TQL[rng]

    DST.write_text(_render(entity_types, relation_types, attribute_types))
    print(f"wrote {DST} "
          f"({len(entity_types)} entities, {len(relation_types)} relations, "
          f"{len(attribute_types)} attributes)")


def _alh_name(cls_name):
    """AlhDomainThing -> alh-domain-thing."""
    out = []
    for i, ch in enumerate(cls_name):
        if ch.isupper() and i:
            out.append("-")
        out.append(ch.lower())
    return "".join(out)


def _render(entities, relations, attributes):
    return (
        '"""Generated from schema/mythras.linkml.yaml. Do not edit by hand.\n'
        "\n"
        "Regenerate with scripts/gen_model.py after changing the LinkML model,\n"
        "and keep schema.tql in step -- tests/test_schema_parity.py enforces it.\n"
        '"""\n\n'
        f"ENTITY_TYPES = {json.dumps(entities, indent=4, sort_keys=True)}\n\n"
        f"RELATION_TYPES = {json.dumps(relations, indent=4, sort_keys=True)}\n\n"
        f"ATTRIBUTE_TYPES = {json.dumps(attributes, indent=4, sort_keys=True)}\n\n"
        'BASE_ATTRS = ["id", "name", "description", "content", "created-at"]\n'
    )


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Add LinkML to the dev group and generate**

In `skills/mythras-gm/pyproject.toml`:

```toml
[dependency-groups]
dev = [
    "pytest>=9.1.1",
    "linkml>=1.8",
]
```

Run:
```bash
cd /Users/gullyburns/mythras-gm
uv run --project skills/mythras-gm python skills/mythras-gm/scripts/gen_model.py
```
Expected: `wrote .../store/model.py (13 entities, 21 relations, 63 attributes)`

- [ ] **Step 6: Validate the LinkML model is well-formed LinkML**

Run: `uv run --project skills/mythras-gm linkml-lint skills/mythras-gm/schema/mythras.linkml.yaml`
Expected: no errors. Warnings about naming conventions are acceptable — the attribute names must stay `myth-` prefixed to match TypeDB.

- [ ] **Step 7: Run the parity test until it passes**

Run: `uv run --project skills/mythras-gm python -m pytest tests/test_schema_parity.py -v`
Expected: 5 passed. Each failure names the entity, relation or attribute that differs — fix the LinkML model (not the test, and not `schema.tql`) and regenerate.

- [ ] **Step 8: Commit**

```bash
git add skills/mythras-gm/schema/ skills/mythras-gm/scripts/gen_model.py \
        skills/mythras-gm/store/model.py tests/test_schema_parity.py \
        skills/mythras-gm/pyproject.toml
git commit -m "feat(store): LinkML model of the campaign schema, with a drift guard

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: The `CampaignStore` interface and its conformance suite

**Files:**
- Create: `skills/mythras-gm/store/base.py`
- Create: `skills/mythras-gm/store/__init__.py`
- Create: `tests/test_store_conformance.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: `store.model` (Task 1).
- Produces: the `CampaignStore` ABC. Every later task depends on these exact signatures:

```python
get_entity(etype: str, eid: str, attrs: list[str]) -> dict | None
put_entity(etype: str, eid: str, attrs: dict) -> None
set_attr(etype: str, eid: str, attr: str, value) -> None
delete_entity(etype: str, eid: str) -> None
list_entities(etype: str, where: dict | None = None) -> list[dict]
link(relation: str, roles: dict[str, str], attrs: dict | None = None) -> None
unlink(relation: str, roles: dict[str, str]) -> None
related(relation: str, from_role: str, eid: str, to_role: str,
        to_type: str | None = None) -> list[str]
relation_pairs(relation: str, role_a: str, role_b: str,
               type_a: str | None = None,
               type_b: str | None = None) -> list[tuple[str, str, dict]]
members(campaign_id: str, etype: str) -> list[str]
add_member(campaign_id: str, eid: str, etype: str) -> None
declared(*type_names: str) -> list[str]
transaction() -> ContextManager[None]
describe() -> dict
```

  Also produces `StoreError(Exception)` and the conformance fixture
  `store` (parametrized over both backends).

- [ ] **Step 1: Write the conformance suite**

```python
# tests/test_store_conformance.py
"""One suite, both backends.

This is the guarantee that a campaign behaves the same whether it lives in
TypeDB or in a folder of JSON. Behaviour that is not asserted here is not
guaranteed to match, so anything a command relies on belongs in this file.
"""
import pytest

CAMPAIGN = "myth-campaign-conformance"
CHAR = "myth-character-aaa111"
CHAR2 = "myth-character-bbb222"
PLACE = "myth-location-ccc333"


def test_get_missing_entity_returns_none(store):
    assert store.get_entity("myth-character", "nope-not-here", []) is None


def test_put_then_get_roundtrips_attributes(store):
    store.put_entity("myth-character", CHAR, {
        "name": "Magda", "myth-char-type": "pc", "myth-luck-current": 3,
    })
    got = store.get_entity("myth-character", CHAR,
                           ["myth-char-type", "myth-luck-current"])
    assert got["id"] == CHAR
    assert got["name"] == "Magda"
    assert got["myth-char-type"] == "pc"
    assert got["myth-luck-current"] == 3


def test_absent_attribute_reads_as_none_not_error(store):
    """The contract _get_entity has always had: an optional attribute the
    store has never held comes back None rather than killing the read."""
    store.put_entity("myth-character", CHAR, {"name": "Magda"})
    got = store.get_entity("myth-character", CHAR, ["myth-fatigue"])
    assert got["myth-fatigue"] is None


def test_set_attr_overwrites_rather_than_accumulates(store):
    store.put_entity("myth-character", CHAR, {"name": "Magda"})
    store.set_attr("myth-character", CHAR, "myth-fatigue", "Fresh")
    store.set_attr("myth-character", CHAR, "myth-fatigue", "Winded")
    got = store.get_entity("myth-character", CHAR, ["myth-fatigue"])
    assert got["myth-fatigue"] == "Winded"


def test_set_attr_preserves_integer_type(store):
    store.put_entity("myth-character", CHAR, {"name": "Magda"})
    store.set_attr("myth-character", CHAR, "myth-luck-current", 2)
    got = store.get_entity("myth-character", CHAR, ["myth-luck-current"])
    assert got["myth-luck-current"] == 2
    assert isinstance(got["myth-luck-current"], int)


def test_set_attr_survives_quotes_and_newlines(store):
    """Narrative text is full of both, and the TypeQL path escapes them."""
    nasty = 'She said "no" —\nthen left.\\'
    store.put_entity("myth-location", PLACE, {"name": "Roost"})
    store.set_attr("myth-location", PLACE, "content", nasty)
    got = store.get_entity("myth-location", PLACE, ["content"])
    assert got["content"] == nasty


def test_delete_entity_removes_it(store):
    store.put_entity("myth-character", CHAR, {"name": "Magda"})
    store.delete_entity("myth-character", CHAR)
    assert store.get_entity("myth-character", CHAR, []) is None


def test_list_entities_returns_all_of_a_type(store):
    store.put_entity("myth-character", CHAR, {"name": "Magda"})
    store.put_entity("myth-character", CHAR2, {"name": "Toval"})
    ids = {e["id"] for e in store.list_entities("myth-character")}
    assert {CHAR, CHAR2} <= ids


def test_list_entities_filters_on_where(store):
    store.put_entity("myth-character", CHAR,
                     {"name": "Magda", "myth-char-type": "pc"})
    store.put_entity("myth-character", CHAR2,
                     {"name": "Toval", "myth-char-type": "npc"})
    got = store.list_entities("myth-character", where={"myth-char-type": "pc"})
    assert [e["id"] for e in got] == [CHAR]


def test_link_and_related_walk_one_hop(store):
    store.put_entity("myth-character", CHAR, {"name": "Magda"})
    store.put_entity("myth-location", PLACE, {"name": "Roost"})
    store.link("myth-presence", {"located": CHAR, "location": PLACE})
    assert store.related("myth-presence", "located", CHAR, "location") == [PLACE]
    assert store.related("myth-presence", "location", PLACE, "located") == [CHAR]


def test_unlink_removes_only_that_pair(store):
    store.put_entity("myth-character", CHAR, {"name": "Magda"})
    store.put_entity("myth-character", CHAR2, {"name": "Toval"})
    store.put_entity("myth-location", PLACE, {"name": "Roost"})
    store.link("myth-presence", {"located": CHAR, "location": PLACE})
    store.link("myth-presence", {"located": CHAR2, "location": PLACE})
    store.unlink("myth-presence", {"located": CHAR, "location": PLACE})
    assert store.related("myth-presence", "location", PLACE, "located") == [CHAR2]


def test_related_filters_by_target_type(store):
    """myth-agenda-holder points at a character OR a faction; callers ask for one."""
    store.put_entity("myth-agenda", "myth-agenda-x", {"name": "Take the spire"})
    store.put_entity("myth-character", CHAR, {"name": "Magda"})
    store.put_entity("myth-faction", "myth-faction-y", {"name": "The Murmuration"})
    store.link("myth-agenda-holder", {"agenda": "myth-agenda-x", "holder": CHAR})
    store.link("myth-agenda-holder",
               {"agenda": "myth-agenda-x", "holder": "myth-faction-y"})
    got = store.related("myth-agenda-holder", "agenda", "myth-agenda-x",
                        "holder", to_type="myth-character")
    assert got == [CHAR]


def test_link_carries_attributes(store):
    """myth-knows holds confidence/since on the relation itself."""
    store.put_entity("myth-character", CHAR, {"name": "Magda"})
    store.put_entity("myth-fact", "myth-fact-z", {"name": "The wind is dying"})
    store.link("myth-knows", {"knower": CHAR, "subject": "myth-fact-z"},
               attrs={"myth-knowledge-certainty": "certain"})
    pairs = store.relation_pairs("myth-knows", "knower", "subject")
    assert (CHAR, "myth-fact-z", {"myth-knowledge-certainty": "certain"}) in pairs


def test_members_and_add_member(store):
    store.put_entity("myth-campaign", CAMPAIGN, {"name": "Purewater"})
    store.put_entity("myth-character", CHAR, {"name": "Magda"})
    store.add_member(CAMPAIGN, CHAR, "myth-character")
    assert store.members(CAMPAIGN, "myth-character") == [CHAR]
    assert store.members(CAMPAIGN, "myth-location") == []


def test_declared_reports_known_attribute_types(store):
    assert "myth-char-type" in store.declared("myth-char-type")
    assert store.declared("myth-no-such-attribute") == []


def test_transaction_commits_together(store):
    store.put_entity("myth-campaign", CAMPAIGN, {"name": "Purewater"})
    with store.transaction():
        store.put_entity("myth-character", CHAR, {"name": "Magda"})
        store.add_member(CAMPAIGN, CHAR, "myth-character")
    assert store.get_entity("myth-character", CHAR, []) is not None
    assert store.members(CAMPAIGN, "myth-character") == [CHAR]


def test_transaction_rolls_back_on_error(store):
    store.put_entity("myth-campaign", CAMPAIGN, {"name": "Purewater"})
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.put_entity("myth-character", CHAR, {"name": "Magda"})
            raise RuntimeError("boom")
    assert store.get_entity("myth-character", CHAR, []) is None


def test_describe_names_the_backend(store):
    d = store.describe()
    assert d["backend"] in {"typedb", "json"}
    assert d["location"]
```

- [ ] **Step 2: Add the parametrized fixture to conftest**

Append to `tests/conftest.py`:

```python
# --- storage backends -------------------------------------------------------
# Same discipline as TYPEDB_DATABASE above: a test must never be able to open
# a real save. MYTHRAS_STORE is forced to a temp root per-test by the fixture,
# and cleared here so an inherited value cannot leak into a bare import.
os.environ.pop("MYTHRAS_STORE", None)
os.environ["MYTHRAS_BACKEND"] = "json"


def _typedb_reachable():
    try:
        from store.typedb_store import TypeDBStore
        TypeDBStore(database=TEST_DB).describe()
        return True
    except Exception:
        return False


@pytest.fixture(params=["json", "typedb"])
def store(request, tmp_path):
    """Every conformance test runs against both backends.

    TypeDB parameters skip rather than fail when no server is reachable, so
    the suite stays runnable in Cowork and in CI without a database.
    """
    if request.param == "json":
        from store.json_store import JsonStore
        s = JsonStore(root=tmp_path / "campaigns")
        s.initialize()
        yield s
        return

    if not _typedb_reachable():
        pytest.skip("no TypeDB server reachable on this machine")
    from store.typedb_store import TypeDBStore
    s = TypeDBStore(database=TEST_DB)
    s.initialize()
    s.reset()          # conformance tests own the test database
    yield s
    s.close()
```

- [ ] **Step 3: Run the suite to verify it fails**

Run: `uv run --project skills/mythras-gm python -m pytest tests/test_store_conformance.py -v`
Expected: every test ERRORs at fixture setup — `ModuleNotFoundError: No module named 'store.json_store'`

- [ ] **Step 4: Write the ABC**

```python
# skills/mythras-gm/store/base.py
"""The seam between the game and where its state lives.

Fourteen methods, because a survey of every query the CLI makes found five
shapes and no more: get an entity by id, set one attribute, list entities of a
type, walk one relation one hop, insert an entity or a relation. Nothing in
this codebase uses TypeDB as a graph database -- no aggregates, no sorts
pushed into the query, no inference -- so a file-backed store gives up
nothing.

The abstraction is deliberately SEMANTIC rather than at the query-string
level. Abstracting TypeQL would mean writing a TypeQL interpreter over JSON.
"""
from abc import ABC, abstractmethod
from contextlib import contextmanager


class StoreError(Exception):
    """Something went wrong in the storage layer.

    Callers turn this into the CLI's loud JSON refusal. It is never caught
    and turned into a fallback to another backend: opening the wrong save
    file is the one failure this system must not have.
    """


class CampaignStore(ABC):
    # --- lifecycle ---------------------------------------------------------
    @abstractmethod
    def initialize(self) -> None:
        """Create whatever the backend needs to be writable. Idempotent."""

    def close(self) -> None:
        """Release resources. Default: nothing to do."""

    @abstractmethod
    def describe(self) -> dict:
        """{"backend", "location", "healthy", "detail"} -- for `doctor`."""

    # --- entities ----------------------------------------------------------
    @abstractmethod
    def get_entity(self, etype, eid, attrs) -> dict | None:
        """Listed attributes for one entity, or None if it is not there.

        Always includes "id" and "name". An attribute this store has never
        held comes back None -- never an error, because a save written before
        an attribute existed must stay readable.
        """

    @abstractmethod
    def put_entity(self, etype, eid, attrs) -> None:
        """Insert an entity. `attrs` may include base and myth- attributes."""

    @abstractmethod
    def set_attr(self, etype, eid, attr, value) -> None:
        """Set one attribute, replacing any existing value."""

    @abstractmethod
    def delete_entity(self, etype, eid) -> None: ...

    @abstractmethod
    def list_entities(self, etype, where=None) -> list:
        """All entities of a type, optionally filtered by exact attribute match."""

    # --- relations ---------------------------------------------------------
    @abstractmethod
    def link(self, relation, roles, attrs=None) -> None: ...

    @abstractmethod
    def unlink(self, relation, roles) -> None: ...

    @abstractmethod
    def related(self, relation, from_role, eid, to_role, to_type=None) -> list:
        """The ids at `to_role` for relations whose `from_role` is `eid`."""

    @abstractmethod
    def relation_pairs(self, relation, role_a, role_b,
                       type_a=None, type_b=None) -> list:
        """Every (id_a, id_b, attrs) triple of a relation. Bulk read for export."""

    # --- campaign membership -----------------------------------------------
    @abstractmethod
    def members(self, campaign_id, etype) -> list: ...

    @abstractmethod
    def add_member(self, campaign_id, eid, etype) -> None: ...

    # --- meta --------------------------------------------------------------
    @abstractmethod
    def declared(self, *type_names) -> list:
        """Which of these attribute types this store actually knows about."""

    @contextmanager
    def transaction(self):
        """Group writes. Default: no grouping, each write stands alone."""
        yield
```

- [ ] **Step 5: Write the package entry point (switch comes in Task 6)**

```python
# skills/mythras-gm/store/__init__.py
"""Storage backends for mythras-gm."""
from .base import CampaignStore, StoreError

__all__ = ["CampaignStore", "StoreError", "resolve_store"]


def resolve_store(**kwargs):
    raise NotImplementedError("the switch lands in Task 6")
```

- [ ] **Step 6: Run the suite — still failing, but now for the right reason**

Run: `uv run --project skills/mythras-gm python -m pytest tests/test_store_conformance.py -v`
Expected: still `No module named 'store.json_store'`. The ABC has no implementations yet; Tasks 3–5 make it green.

- [ ] **Step 7: Commit**

```bash
git add skills/mythras-gm/store/base.py skills/mythras-gm/store/__init__.py \
        tests/test_store_conformance.py tests/conftest.py
git commit -m "feat(store): CampaignStore interface and a two-backend conformance suite

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `JsonStore` — entities

**Files:**
- Create: `skills/mythras-gm/store/json_store.py`
- Test: `tests/test_store_conformance.py` (existing; the `json` parameter starts passing)

**Interfaces:**
- Consumes: `CampaignStore`, `StoreError` (Task 2); `store.model` (Task 1).
- Produces: `JsonStore(root: Path | str)` with `initialize()`, and the entity half of the interface. Task 4 adds relations to this same class; Task 5 adds transactions.

- [ ] **Step 1: Run the entity conformance tests to confirm they fail**

Run: `uv run --project skills/mythras-gm python -m pytest tests/test_store_conformance.py -k "json and (entity or attr or list_entities)" -v`
Expected: ERROR — `No module named 'store.json_store'`

- [ ] **Step 2: Implement the entity half**

```python
# skills/mythras-gm/store/json_store.py
"""A campaign as a tree of JSON files.

Pure stdlib, deliberately: this is the backend that runs in Claude Chat and
Cowork, where nothing can be installed and no server can be started.

Layout (see the design doc for why):

    <root>/
      store.json                       manifest
      entities/<type>/<id>.json        one flat object per entity
      relations/<relation>.jsonl       one line per link
      oplog.jsonl                      append-only commit log

No index files. A campaign runs to a few hundred entities and a couple of
thousand relation rows, so a directory listing answers every query shape in
microseconds, and an index would be state that can disagree with the data.
"""
import json
import os
import tempfile
from pathlib import Path

from .base import CampaignStore, StoreError
from . import model

FORMAT_VERSION = "1.0"


class JsonStore(CampaignStore):
    def __init__(self, root):
        self.root = Path(root)
        self._pending = None        # set inside transaction(); Task 5

    # --- lifecycle ---------------------------------------------------------
    def initialize(self):
        (self.root / "entities").mkdir(parents=True, exist_ok=True)
        (self.root / "relations").mkdir(parents=True, exist_ok=True)
        manifest = self.root / "store.json"
        if not manifest.exists():
            self._write_json(manifest, {
                "format_version": FORMAT_VERSION,
                "backend": "json",
                "entity_types": sorted(model.ENTITY_TYPES),
                "relation_types": sorted(model.RELATION_TYPES),
            })

    def describe(self):
        manifest = self.root / "store.json"
        return {
            "backend": "json",
            "location": str(self.root),
            "healthy": manifest.exists(),
            "detail": (f"format {self._manifest().get('format_version')}"
                       if manifest.exists() else "no store.json -- not initialized"),
        }

    def _manifest(self):
        try:
            return json.loads((self.root / "store.json").read_text())
        except (OSError, json.JSONDecodeError):
            return {}

    # --- paths -------------------------------------------------------------
    def _entity_dir(self, etype):
        return self.root / "entities" / etype

    def _entity_path(self, etype, eid):
        if "/" in eid or eid.startswith("."):
            raise StoreError(f"unsafe entity id {eid!r}")
        return self._entity_dir(etype) / f"{eid}.json"

    # --- atomic file io ----------------------------------------------------
    @staticmethod
    def _write_json(path, obj):
        """Temp-then-replace: os.replace is atomic on POSIX, so a reader never
        sees a torn file even if this process dies mid-write."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(obj, fh, indent=2, sort_keys=True, default=str)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    @staticmethod
    def _read_json(path):
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as e:
            raise StoreError(f"{path} is not readable JSON: {e}") from e

    # --- entities ----------------------------------------------------------
    def get_entity(self, etype, eid, attrs):
        doc = self._read_json(self._entity_path(etype, eid))
        if doc is None:
            return None
        result = {"id": doc.get("id", eid), "name": doc.get("name")}
        for a in attrs:
            result[a] = doc.get(a)
        return result

    def put_entity(self, etype, eid, attrs):
        if etype not in model.ENTITY_TYPES:
            raise StoreError(f"unknown entity type {etype!r}")
        doc = {"id": eid}
        doc.update({k: v for k, v in (attrs or {}).items() if v is not None})
        self._stage(self._entity_path(etype, eid), doc)

    def set_attr(self, etype, eid, attr, value):
        path = self._entity_path(etype, eid)
        doc = self._read_json(path)
        if doc is None:
            raise StoreError(f"no {etype} '{eid}' to set {attr} on")
        doc[attr] = value
        self._stage(path, doc)

    def delete_entity(self, etype, eid):
        self._stage(self._entity_path(etype, eid), None)

    def list_entities(self, etype, where=None):
        out = []
        d = self._entity_dir(etype)
        if not d.is_dir():
            return out
        for path in sorted(d.glob("*.json")):
            doc = self._read_json(path)
            if doc is None:
                continue
            if where and any(doc.get(k) != v for k, v in where.items()):
                continue
            out.append(doc)
        return out

    # --- meta --------------------------------------------------------------
    def declared(self, *type_names):
        """Every attribute in the model is 'declared'.

        The TypeDB backend needs this because naming an undeclared attribute
        kills type inference and takes the whole query with it. A JSON
        document has no such problem -- an attribute is present or absent --
        so this answers from the model and the N+1 read _get_entity does on
        TypeDB collapses to one file read.
        """
        known = set(model.ATTRIBUTE_TYPES) | set(model.BASE_ATTRS)
        return [t for t in type_names if t in known]

    # --- write staging (completed in Task 5) -------------------------------
    def _stage(self, path, doc):
        """Write now, or buffer if inside a transaction."""
        if self._pending is not None:
            self._pending[path] = doc
            return
        self._commit_one(path, doc)

    def _commit_one(self, path, doc):
        if doc is None:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
        else:
            self._write_json(path, doc)
```

- [ ] **Step 3: Run the entity conformance tests**

Run: `uv run --project skills/mythras-gm python -m pytest tests/test_store_conformance.py -k json -v`
Expected: entity tests PASS (`get_missing`, `put_then_get`, `absent_attribute`, `set_attr_*`, `delete_entity`, `list_entities_*`, `declared`, `describe`). Relation, membership and transaction tests still fail — Tasks 4 and 5.

- [ ] **Step 4: Commit**

```bash
git add skills/mythras-gm/store/json_store.py
git commit -m "feat(store): JsonStore entity operations

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: `JsonStore` — relations and membership

**Files:**
- Modify: `skills/mythras-gm/store/json_store.py`

**Interfaces:**
- Consumes: `JsonStore` entity half (Task 3).
- Produces: `link`, `unlink`, `related`, `relation_pairs`, `members`, `add_member` on `JsonStore`.

- [ ] **Step 1: Run the relation conformance tests to confirm they fail**

Run: `uv run --project skills/mythras-gm python -m pytest tests/test_store_conformance.py -k "json and (link or related or member or relation)" -v`
Expected: FAIL — `TypeError: Can't instantiate abstract class JsonStore` or `NotImplementedError`

- [ ] **Step 2: Implement relations**

Append to `JsonStore`:

```python
    # --- relations ---------------------------------------------------------
    # One JSONL file per relation type keeps every scan narrow. A line is
    # {"roles": {...}, "attrs": {...}}; role names come from the model, so a
    # typo'd role fails here rather than silently matching nothing later.
    def _relation_path(self, relation):
        if relation not in model.RELATION_TYPES:
            raise StoreError(f"unknown relation type {relation!r}")
        return self.root / "relations" / f"{relation}.jsonl"

    def _read_relation(self, relation):
        path = self._relation_path(relation)
        if self._pending is not None and path in self._pending:
            return list(self._pending[path] or [])
        try:
            text = path.read_text()
        except FileNotFoundError:
            return []
        rows = []
        for n, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise StoreError(f"{path}:{n} is not readable JSON: {e}") from e
        return rows

    def _stage_relation(self, relation, rows):
        path = self._relation_path(relation)
        if self._pending is not None:
            self._pending[path] = rows
            return
        self._commit_relation(path, rows)

    @staticmethod
    def _commit_relation(path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(r, sort_keys=True, default=str) + "\n"
                          for r in rows)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(payload)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _check_roles(self, relation, roles):
        known = set(model.RELATION_TYPES[relation]["roles"])
        unknown = set(roles) - known
        if unknown:
            raise StoreError(
                f"{relation} has roles {sorted(known)}, not {sorted(unknown)}")

    def link(self, relation, roles, attrs=None):
        self._check_roles(relation, roles)
        rows = self._read_relation(relation)
        row = {"roles": dict(roles), "attrs": dict(attrs or {})}
        # Re-linking the same pair updates its attributes rather than
        # duplicating the row; TypeDB's insert is likewise idempotent on the
        # role players and the CLI re-links freely.
        for existing in rows:
            if existing["roles"] == row["roles"]:
                existing["attrs"] = row["attrs"]
                break
        else:
            rows.append(row)
        self._stage_relation(relation, rows)

    def unlink(self, relation, roles):
        self._check_roles(relation, roles)
        rows = [r for r in self._read_relation(relation)
                if not all(r["roles"].get(k) == v for k, v in roles.items())]
        self._stage_relation(relation, rows)

    def related(self, relation, from_role, eid, to_role, to_type=None):
        self._check_roles(relation, {from_role: eid, to_role: None})
        out = []
        for r in self._read_relation(relation):
            if r["roles"].get(from_role) != eid:
                continue
            other = r["roles"].get(to_role)
            if other is None:
                continue
            if to_type and not self._is_type(to_type, other):
                continue
            out.append(other)
        return out

    def _is_type(self, etype, eid):
        return self._entity_path(etype, eid).exists()

    def relation_pairs(self, relation, role_a, role_b, type_a=None, type_b=None):
        out = []
        for r in self._read_relation(relation):
            a, b = r["roles"].get(role_a), r["roles"].get(role_b)
            if a is None or b is None:
                continue
            if type_a and not self._is_type(type_a, a):
                continue
            if type_b and not self._is_type(type_b, b):
                continue
            out.append((a, b, dict(r.get("attrs") or {})))
        return out

    # --- campaign membership -----------------------------------------------
    def members(self, campaign_id, etype):
        return self.related("myth-campaign-membership", "campaign", campaign_id,
                            "element", to_type=etype)

    def add_member(self, campaign_id, eid, etype):
        """Refuse to create an unreachable orphan.

        _link_to_campaign has always checked this, because an insert that
        matches nothing reports success while the element dangles -- which has
        cost a whole session's log before.
        """
        if self.get_entity("myth-campaign", campaign_id, []) is None:
            raise StoreError(
                f"No campaign '{campaign_id}' in the store at {self.root}. "
                f"The element was created but is NOT linked.")
        self.link("myth-campaign-membership",
                  {"campaign": campaign_id, "element": eid})
```

- [ ] **Step 3: Run the relation conformance tests**

Run: `uv run --project skills/mythras-gm python -m pytest tests/test_store_conformance.py -k json -v`
Expected: all PASS except `test_transaction_commits_together` and `test_transaction_rolls_back_on_error`.

- [ ] **Step 4: Commit**

```bash
git add skills/mythras-gm/store/json_store.py
git commit -m "feat(store): JsonStore relations and campaign membership

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: `JsonStore` — transactions and the oplog

**Files:**
- Modify: `skills/mythras-gm/store/json_store.py`

**Interfaces:**
- Consumes: `JsonStore` (Tasks 3–4).
- Produces: `transaction()` context manager and `check_oplog() -> list[str]` (returns human-readable discrepancies; empty list means consistent). Task 8's `doctor` calls `check_oplog()`.

- [ ] **Step 1: Write the oplog test**

Add to `tests/test_store_conformance.py`:

```python
# --- JSON-backend specifics -------------------------------------------------
# These assert the file-level guarantees the design doc promises, so they are
# not part of the shared conformance contract.

def test_oplog_records_each_commit(json_store):
    json_store.put_entity("myth-campaign", CAMPAIGN, {"name": "Purewater"})
    with json_store.transaction():
        json_store.put_entity("myth-character", CHAR, {"name": "Magda"})
        json_store.add_member(CAMPAIGN, CHAR, "myth-character")
    lines = (json_store.root / "oplog.jsonl").read_text().splitlines()
    assert len(lines) == 2          # the bare put, then the transaction
    import json as _json
    last = _json.loads(lines[-1])
    assert len(last["files"]) == 2
    assert all("path" in f and "sha256" in f for f in last["files"])


def test_check_oplog_detects_a_torn_commit(json_store):
    json_store.put_entity("myth-character", CHAR, {"name": "Magda"})
    assert json_store.check_oplog() == []
    # Simulate a commit interrupted after the oplog line but before the file
    # landed -- exactly what a crash mid-flush leaves behind.
    (json_store.root / "entities" / "myth-character" / f"{CHAR}.json").unlink()
    problems = json_store.check_oplog()
    assert problems and CHAR in problems[0]
```

And the fixture it needs, in `tests/conftest.py`:

```python
@pytest.fixture
def json_store(tmp_path):
    """The JSON backend alone, for file-level guarantees TypeDB has no analogue of."""
    from store.json_store import JsonStore
    s = JsonStore(root=tmp_path / "campaigns")
    s.initialize()
    return s
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --project skills/mythras-gm python -m pytest tests/test_store_conformance.py -k oplog -v`
Expected: FAIL — `AttributeError: 'JsonStore' object has no attribute 'check_oplog'`

- [ ] **Step 3: Implement transactions and the oplog**

Add to `JsonStore`, and replace the `_stage`/`_commit_one` stubs from Task 3:

```python
    # --- transactions ------------------------------------------------------
    # Each file is written temp-then-replace, so no file is ever torn. A
    # multi-file commit is NOT atomic across files, and the oplog exists
    # because of that: one appended line per commit, listing the files and
    # their post-state hashes, so an interrupted flush is DETECTABLE. `doctor`
    # reports the discrepancy rather than the game running on a half-written
    # save. Full WAL recovery would be out of proportion for a single-player
    # save file written by one process at a time.
    @contextmanager
    def transaction(self):
        if self._pending is not None:
            yield                      # already in one; the outermost commits
            return
        self._pending = {}
        try:
            yield
        except BaseException:
            self._pending = None       # discard every buffered write
            raise
        pending, self._pending = self._pending, None
        self._flush(pending)

    def _flush(self, pending):
        written = []
        for path, doc in pending.items():
            if isinstance(doc, list):
                self._commit_relation(path, doc)
            else:
                self._commit_one(path, doc)
            written.append(path)
        self._append_oplog(written)

    def _stage(self, path, doc):
        if self._pending is not None:
            self._pending[path] = doc
            return
        self._commit_one(path, doc)
        self._append_oplog([path])

    def _stage_relation(self, relation, rows):
        path = self._relation_path(relation)
        if self._pending is not None:
            self._pending[path] = rows
            return
        self._commit_relation(path, rows)
        self._append_oplog([path])

    # --- oplog -------------------------------------------------------------
    def _append_oplog(self, paths):
        entry = {
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "files": [{"path": str(p.relative_to(self.root)),
                       "sha256": self._hash(p)} for p in paths],
        }
        with open(self.root / "oplog.jsonl", "a") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    @staticmethod
    def _hash(path):
        """Hash of the file's current bytes, or None if it was deleted."""
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except FileNotFoundError:
            return None

    def check_oplog(self):
        """Compare the last recorded state of each file against what is on disk.

        Returns a list of human-readable discrepancies; empty means consistent.
        """
        log = self.root / "oplog.jsonl"
        if not log.exists():
            return []
        latest = {}
        for line in log.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                return [f"{log} has an unreadable line; the last commit may be torn"]
            for f in entry["files"]:
                latest[f["path"]] = f["sha256"]
        problems = []
        for rel, expected in latest.items():
            actual = self._hash(self.root / rel)
            if actual != expected:
                problems.append(
                    f"{rel}: oplog expects {expected or 'absent'}, "
                    f"found {actual or 'absent'}")
        return problems
```

Add the imports this needs at the top of the file:

```python
import hashlib
from contextlib import contextmanager
from datetime import datetime, timezone
```

- [ ] **Step 4: Run the whole JSON conformance suite**

Run: `uv run --project skills/mythras-gm python -m pytest tests/test_store_conformance.py -k json -v`
Expected: all PASS, including both transaction tests and both oplog tests.

- [ ] **Step 5: Commit**

```bash
git add skills/mythras-gm/store/json_store.py tests/test_store_conformance.py tests/conftest.py
git commit -m "feat(store): JsonStore transactions with a detectable-torn-commit oplog

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: `TypeDBStore`

**Files:**
- Create: `skills/mythras-gm/store/typedb_store.py`

**Interfaces:**
- Consumes: `CampaignStore`, `StoreError` (Task 2).
- Produces: `TypeDBStore(host=None, port=None, database=None, username=None, password=None)` implementing the full interface, plus `reset()` (deletes and recreates the database — tests only) and `close()`.

**This task is behaviour-preserving.** Every query below already exists in `mythras_gm.py`; move it, do not rewrite it. Read `mythras_gm.py:193-325` for the originals.

- [ ] **Step 1: Run the TypeDB conformance parameter to confirm it fails**

Run: `uv run --project skills/mythras-gm python -m pytest tests/test_store_conformance.py -k typedb -v`
Expected: ERROR — `No module named 'store.typedb_store'` (or SKIP if no server is reachable; start one with `mythras_gm.py init-db` first, since this task needs a live server to verify).

- [ ] **Step 2: Implement**

```python
# skills/mythras-gm/store/typedb_store.py
"""The TypeDB backend -- today's queries, moved rather than rewritten.

Every query in this file came out of mythras_gm.py verbatim, including the
declared()/_opt()/_optf() machinery. That machinery is not incidental: naming
an attribute the database has never declared does not return nothing, it fails
type inference and kills the whole read. A save written before an attribute
existed must stay readable, so optional attributes are filtered through
declared() first and simply come back absent.
"""
import os
from contextlib import contextmanager

from .base import CampaignStore, StoreError
from . import model

try:
    from typedb.driver import Credentials, DriverOptions, TransactionType, TypeDB
    DRIVER_AVAILABLE = True
except ImportError:                     # Cowork: no driver, and that is fine
    DRIVER_AVAILABLE = False


def escape_string(s):
    if s is None:
        return ""
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\n", "\\n").replace("\r", ""))


class TypeDBStore(CampaignStore):
    def __init__(self, host=None, port=None, database=None,
                 username=None, password=None):
        if not DRIVER_AVAILABLE:
            raise StoreError(
                "typedb-driver is not installed, so the TypeDB backend cannot "
                "run here. Set MYTHRAS_BACKEND=json to use a file-backed store.")
        self.host = host or os.getenv("TYPEDB_HOST", "localhost")
        self.port = int(port or os.getenv("TYPEDB_PORT", "1730"))
        self.database = database or os.getenv("TYPEDB_DATABASE", "mythras")
        self.username = username or os.getenv("TYPEDB_USERNAME", "admin")
        self.password = password or os.getenv("TYPEDB_PASSWORD", "password")
        self._driver = None
        self._schema_attrs = None

    # --- lifecycle ---------------------------------------------------------
    @property
    def driver(self):
        if self._driver is None:
            try:
                self._driver = TypeDB.driver(
                    f"{self.host}:{self.port}",
                    Credentials(self.username, self.password),
                    DriverOptions(is_tls_enabled=False),
                )
            except Exception as e:
                raise StoreError(
                    f"cannot reach TypeDB at {self.host}:{self.port} "
                    f"(database {self.database}): {e}") from e
        return self._driver

    def initialize(self):
        if self.database not in [d.name for d in self.driver.databases.all()]:
            self.driver.databases.create(self.database)

    def close(self):
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def reset(self):
        """Tests only. Refuses to touch anything that looks like a real save."""
        LIVE = {"mythras", "alh_mythras", "alhazen_notebook"}
        if self.database in LIVE:
            raise StoreError(f"refusing to reset live database {self.database!r}")
        if self.database in [d.name for d in self.driver.databases.all()]:
            self.driver.databases.get(self.database).delete()
        self.driver.databases.create(self.database)
        self._schema_attrs = None
        self.load_schema()

    def load_schema(self):
        """Apply schema-base.tql (only where absent) then schema.tql."""
        from pathlib import Path
        skill = Path(__file__).resolve().parent.parent
        if not self._declared_types({"alh-identifiable-entity"}):
            self._write((skill / "schema-base.tql").read_text())
        self._write((skill / "schema.tql").read_text())
        self._schema_attrs = None

    def describe(self):
        try:
            names = [d.name for d in self.driver.databases.all()]
            healthy = self.database in names
            detail = ("ok" if healthy
                      else f"database {self.database!r} does not exist")
        except StoreError as e:
            healthy, detail = False, str(e)
        return {"backend": "typedb",
                "location": f"{self.host}:{self.port}/{self.database}",
                "healthy": healthy, "detail": detail}

    # --- raw query helpers (from mythras_gm.py:193-203) ---------------------
    def _fetch(self, query):
        with self.driver.transaction(self.database, TransactionType.READ) as tx:
            return list(tx.query(query).resolve())

    def _write(self, *queries):
        with self.driver.transaction(self.database, TransactionType.WRITE) as tx:
            for q in queries:
                tx.query(q).resolve()
            tx.commit()

    # --- schema introspection (from mythras_gm.py:224-253) -----------------
    def _declared_types(self, wanted):
        if self._schema_attrs is None:
            try:
                text = self.driver.databases.get(self.database).schema()
            except Exception:
                return set(wanted)          # cannot tell; assume present
            self._schema_attrs = {
                ln.split(",")[0].removeprefix("attribute ").strip()
                for ln in text.splitlines() if ln.startswith("attribute ")
            } | {
                ln.split(" ")[1].split(",")[0].strip()
                for ln in text.splitlines() if ln.startswith("entity ")
            }
        return {t for t in wanted if t in self._schema_attrs}

    def declared(self, *type_names):
        have = self._declared_types(set(type_names))
        return [t for t in type_names if t in have]

    # --- entities ----------------------------------------------------------
    def get_entity(self, etype, eid, attrs):
        e = escape_string(eid)
        rows = self._fetch(f'''
            match $e isa {etype}, has id "{e}";
            fetch {{ "id": $e.id, "name": $e.name }};''')
        if not rows:
            return None
        result = dict(rows[0])
        present = set(self.declared(*[a for a in attrs if a.startswith("myth-")]))
        for a in attrs:
            if a.startswith("myth-") and a not in present:
                result[a] = None
                continue
            r = self._fetch(f'''
                match $e isa {etype}, has id "{e}", has {a} $v;
                fetch {{ "v": $v }};''')
            result[a] = r[0]["v"] if r else None
        return result

    def put_entity(self, etype, eid, attrs):
        if etype not in model.ENTITY_TYPES:
            raise StoreError(f"unknown entity type {etype!r}")
        clauses = [f'has id "{escape_string(eid)}"']
        for attr, value in (attrs or {}).items():
            if value is None:
                continue
            clauses.append(f"has {attr} {self._literal(attr, value)}")
        self._write(f"insert $e isa {etype}, " + ", ".join(clauses) + ";")

    @staticmethod
    def _literal(attr, value):
        if model.ATTRIBUTE_TYPES.get(attr) == "integer":
            return str(int(value))
        if model.ATTRIBUTE_TYPES.get(attr) == "datetime":
            return str(value)
        return f'"{escape_string(str(value))}"'

    def set_attr(self, etype, eid, attr, value):
        """Delete-then-insert; TypeDB 3.x has no in-place attribute update."""
        e = escape_string(eid)
        if self._fetch(f'''
                match $e isa {etype}, has id "{e}", has {attr} $v;
                fetch {{ "v": $v }};'''):
            self._write(f'''
                match $e isa {etype}, has id "{e}", has {attr} $v;
                delete has $v of $e;''')
        self._write(f'''
            match $e isa {etype}, has id "{e}";
            insert $e has {attr} {self._literal(attr, value)};''')

    def delete_entity(self, etype, eid):
        self._write(f'''
            match $e isa {etype}, has id "{escape_string(eid)}";
            delete $e;''')

    def list_entities(self, etype, where=None):
        rows = self._fetch(f'''
            match $e isa {etype}, has id $i;
            fetch {{ "id": $i }};''')
        out = []
        attrs = list((where or {}).keys())
        for r in rows:
            doc = self.get_entity(etype, r["id"], attrs + ["description", "content"])
            if doc is None:
                continue
            if where and any(doc.get(k) != v for k, v in where.items()):
                continue
            out.append(doc)
        return out

    # --- relations ---------------------------------------------------------
    def link(self, relation, roles, attrs=None):
        # Re-linking an existing pair must update its attributes rather than
        # add a second instance -- JsonStore.link does exactly that, and the
        # conformance suite holds the two to the same behaviour.
        self.unlink(relation, roles)
        match, players = [], []
        for i, (role, eid) in enumerate(roles.items()):
            match.append(f'$p{i} has id "{escape_string(eid)}";')
            players.append(f"{role}: $p{i}")
        has = "".join(f", has {a} {self._literal(a, v)}"
                      for a, v in (attrs or {}).items())
        self._write(
            f"match {' '.join(match)} "
            f"insert ({', '.join(players)}) isa {relation}{has};")

    def unlink(self, relation, roles):
        match = " ".join(f'$p{i} has id "{escape_string(eid)}";'
                         for i, eid in enumerate(roles.values()))
        players = ", ".join(f"{role}: $p{i}"
                            for i, role in enumerate(roles.keys()))
        self._write(
            f"match {match} $rel isa {relation}, links ({players}); delete $rel;")

    def related(self, relation, from_role, eid, to_role, to_type=None):
        type_clause = f"$o isa {to_type};" if to_type else ""
        rows = self._fetch(f'''
            match
              $s has id "{escape_string(eid)}";
              {type_clause}
              $rel isa {relation}, links ({from_role}: $s, {to_role}: $o);
              $o has id $i;
            fetch {{ "id": $i }};''')
        return [r["id"] for r in rows]

    def relation_pairs(self, relation, role_a, role_b, type_a=None, type_b=None):
        a_clause = f"$a isa {type_a};" if type_a else ""
        b_clause = f"$b isa {type_b};" if type_b else ""
        rows = self._fetch(f'''
            match
              {a_clause} {b_clause}
              $rel isa {relation}, links ({role_a}: $a, {role_b}: $b);
              $a has id $ai; $b has id $bi;
            fetch {{ "a": $ai, "b": $bi }};''')
        return [(r["a"], r["b"], {}) for r in rows]

    # --- campaign membership -----------------------------------------------
    def members(self, campaign_id, etype):
        rows = self._fetch(f'''
            match
              $camp isa myth-campaign, has id "{escape_string(campaign_id)}";
              (campaign: $camp, element: $e) isa myth-campaign-membership;
              $e isa {etype}, has id $i;
            fetch {{ "id": $i }};''')
        return [r["id"] for r in rows]

    def add_member(self, campaign_id, eid, etype):
        if not self._fetch(f'''
                match $c isa myth-campaign, has id "{escape_string(campaign_id)}";
                fetch {{ "id": $c.id }};'''):
            raise StoreError(
                f"No campaign '{campaign_id}' in database '{self.database}'. "
                f"Set TYPEDB_DATABASE to the campaign's database and retry "
                f"(the element was created but is NOT linked).")
        self._write(f'''
            match
              $c isa myth-campaign, has id "{escape_string(campaign_id)}";
              $e isa {etype}, has id "{escape_string(eid)}";
            insert (campaign: $c, element: $e) isa myth-campaign-membership;''')

    # --- transactions ------------------------------------------------------
    @contextmanager
    def transaction(self):
        """Each write already commits on its own, which is what every command
        in this CLI has always relied on. Grouping them into one TypeDB
        transaction is a worthwhile follow-up but would change failure
        behaviour, so it is deliberately not part of this change."""
        yield
```

Note `relation_pairs` returns `{}` for attrs on the TypeDB side. `myth-knows`
carries attributes; extend this method to fetch them when porting
`_subject_knowledge_edges` in Task 9, and make the conformance test
`test_link_carries_attributes` pass for both backends at that point.

- [ ] **Step 3: Start a server and run the TypeDB conformance parameter**

```bash
uv run --project skills/mythras-gm python skills/mythras-gm/mythras_gm.py init-db
uv run --project skills/mythras-gm python -m pytest tests/test_store_conformance.py -k typedb -v
```
Expected: all PASS except `test_link_carries_attributes`, which is xfail until Task 9. Mark it so:

```python
@pytest.mark.xfail(reason="relation attributes land with _subject_knowledge_edges in Task 9",
                   strict=False)
def test_link_carries_attributes(store):
    ...
```

- [ ] **Step 4: Commit**

```bash
git add skills/mythras-gm/store/typedb_store.py tests/test_store_conformance.py
git commit -m "feat(store): TypeDBStore -- today's queries behind the interface

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: The switch

**Files:**
- Modify: `skills/mythras-gm/store/__init__.py`
- Create: `tests/test_backend_switch.py`

**Interfaces:**
- Consumes: `JsonStore` (Tasks 3–5), `TypeDBStore` (Task 6).
- Produces: `resolve_store(create: bool = False) -> CampaignStore` and
  `resolve_backend() -> tuple[str, str]` returning `(backend, reason)`.
  `mythras_gm.py` calls `resolve_store()` in Task 8.

- [ ] **Step 1: Write the switch test**

```python
# tests/test_backend_switch.py
"""The switch must never open the wrong save file.

Everything here exists because of one failure mode: a Gamesmaster narrating a
session into a store that is not the player's. An explicit choice outranks a
marker, a marker outranks a guess about the environment, and no branch is
allowed to fall back silently when the backend it was told to use is
unavailable.
"""
import pytest

from store import resolve_backend, resolve_store, StoreError


def test_explicit_backend_wins_over_everything(monkeypatch, tmp_path):
    monkeypatch.setenv("MYTHRAS_BACKEND", "json")
    monkeypatch.setenv("CLAUDECODE", "1")
    backend, reason = resolve_backend()
    assert backend == "json"
    assert "MYTHRAS_BACKEND" in reason


def test_store_marker_outranks_environment_detection(monkeypatch, tmp_path):
    monkeypatch.delenv("MYTHRAS_BACKEND", raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")          # looks like Claude Code
    root = tmp_path / "campaigns"
    root.mkdir()
    (root / "store.json").write_text('{"backend": "json"}')
    monkeypatch.setenv("MYTHRAS_STORE", str(root))
    backend, reason = resolve_backend()
    assert backend == "json"
    assert "store.json" in reason


def test_claude_code_defaults_to_typedb(monkeypatch):
    monkeypatch.delenv("MYTHRAS_BACKEND", raising=False)
    monkeypatch.delenv("MYTHRAS_STORE", raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")
    backend, reason = resolve_backend()
    assert backend == "typedb"
    assert "CLAUDECODE" in reason


def test_absent_claude_code_defaults_to_json(monkeypatch):
    monkeypatch.delenv("MYTHRAS_BACKEND", raising=False)
    monkeypatch.delenv("MYTHRAS_STORE", raising=False)
    monkeypatch.delenv("CLAUDECODE", raising=False)
    backend, _reason = resolve_backend()
    assert backend == "json"


def test_unreachable_typedb_never_falls_back_to_json(monkeypatch, tmp_path):
    """The rule the whole design is arranged around."""
    monkeypatch.setenv("MYTHRAS_BACKEND", "typedb")
    monkeypatch.setenv("TYPEDB_PORT", "1")         # nothing listens here
    monkeypatch.setenv("MYTHRAS_STORE", str(tmp_path / "campaigns"))
    with pytest.raises(StoreError) as e:
        resolve_store().describe()
    assert "typedb" in str(e.value).lower()
    assert "json" not in str(e.value).lower() or "MYTHRAS_BACKEND=json" in str(e.value)


def test_missing_json_store_fails_naming_paths_searched(monkeypatch, tmp_path):
    monkeypatch.setenv("MYTHRAS_BACKEND", "json")
    monkeypatch.setenv("MYTHRAS_STORE", str(tmp_path / "nowhere"))
    with pytest.raises(StoreError) as e:
        resolve_store()
    assert str(tmp_path / "nowhere") in str(e.value)


def test_create_flag_makes_the_store(monkeypatch, tmp_path):
    monkeypatch.setenv("MYTHRAS_BACKEND", "json")
    monkeypatch.setenv("MYTHRAS_STORE", str(tmp_path / "fresh"))
    s = resolve_store(create=True)
    assert (tmp_path / "fresh" / "store.json").exists()
    assert s.describe()["backend"] == "json"


def test_store_ahead_of_this_build_fails_loudly(monkeypatch, tmp_path):
    monkeypatch.setenv("MYTHRAS_BACKEND", "json")
    root = tmp_path / "campaigns"
    root.mkdir()
    (root / "store.json").write_text('{"backend": "json", "format_version": "99.0"}')
    monkeypatch.setenv("MYTHRAS_STORE", str(root))
    with pytest.raises(StoreError) as e:
        resolve_store()
    assert "99.0" in str(e.value)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --project skills/mythras-gm python -m pytest tests/test_backend_switch.py -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_backend' from 'store'`

- [ ] **Step 3: Implement the switch**

```python
# skills/mythras-gm/store/__init__.py
"""Storage backends for mythras-gm, and the switch that picks one.

Resolution order, strictest evidence first:

  1. MYTHRAS_BACKEND      -- an explicit choice always wins
  2. a store marker       -- MYTHRAS_STORE naming a directory with store.json
                             is EVIDENCE about where a save lives, and it
                             outranks a guess about the environment
  3. CLAUDECODE in env    -- Claude Code, so TypeDB
  4. default              -- json

Detection only ever chooses a DEFAULT, and CLAUDECODE is an undocumented
internal, so being wrong about it must stay cheap: two higher-priority signals
outrank it and neither branch can silently open the wrong save.
"""
import json
import os
from pathlib import Path

from .base import CampaignStore, StoreError

__all__ = ["CampaignStore", "StoreError", "resolve_store", "resolve_backend",
           "resolve_store_root"]

SUPPORTED_FORMAT = "1.0"

# Candidate workspace roots, probed in order. This is a guess about someone
# else's runtime, so it is arranged to fail safely: an entry that is not there
# is skipped, and if none match the CWD-relative default applies.
#
# EMPTY UNTIL THE REAL COWORK WORKSPACE PATH IS CONFIRMED. Steps 1 and 3 of
# resolve_store_root carry the feature until then; adding a path here is a
# one-line change once it is known.
WORKSPACE_ROOTS: list[str] = []


def resolve_store_root():
    """(root: Path, reason: str) for where JSON campaigns live."""
    explicit = os.getenv("MYTHRAS_STORE")
    if explicit:
        return Path(explicit), "MYTHRAS_STORE"
    for candidate in WORKSPACE_ROOTS:
        p = Path(candidate)
        if p.is_dir() and os.access(p, os.W_OK):
            return p / "campaigns", f"workspace root {candidate}"
    return Path.cwd() / "campaigns", "working directory"


def resolve_backend():
    """(backend: str, reason: str). Never raises; never guesses destructively."""
    explicit = os.getenv("MYTHRAS_BACKEND")
    if explicit:
        if explicit not in {"typedb", "json"}:
            raise StoreError(
                f"MYTHRAS_BACKEND={explicit!r} is not a backend. "
                f"Use 'typedb' or 'json'.")
        return explicit, f"MYTHRAS_BACKEND={explicit}"

    root, _why = resolve_store_root()
    if (root / "store.json").is_file():
        return "json", f"found a store.json at {root}"

    if os.getenv("CLAUDECODE"):
        return "typedb", "CLAUDECODE is set, so this is Claude Code"

    return "json", "no CLAUDECODE in the environment, so not Claude Code"


def resolve_store(create=False):
    """The active store. Raises StoreError rather than falling back.

    `create=True` is passed only by init-db, create-campaign and
    import-campaign. A read must never bring a store into existence: an empty
    store that appears on demand is indistinguishable, to the Gamesmaster,
    from a campaign that has lost everything.
    """
    backend, reason = resolve_backend()

    if backend == "typedb":
        from .typedb_store import TypeDBStore
        store = TypeDBStore()
        if create:
            store.initialize()
        # Surface an unreachable server HERE, as itself. Never as a fallback.
        health = store.describe()
        if not health["healthy"] and not create:
            raise StoreError(
                f"The TypeDB backend was selected ({reason}) but "
                f"{health['location']} is not usable: {health['detail']}. "
                f"The save file and the dice tower are both unavailable -- run "
                f"`doctor`. Do NOT continue play from memory, and do not claim "
                f"anything persisted. If this game is meant to run on files "
                f"instead, set MYTHRAS_BACKEND=json.")
        return store

    from .json_store import JsonStore
    root, root_reason = resolve_store_root()
    store = JsonStore(root=root)
    marker = root / "store.json"
    if create:
        store.initialize()
        return store
    if not marker.is_file():
        raise StoreError(
            f"The JSON backend was selected ({reason}) but there is no store "
            f"at {root} (looked there because: {root_reason}). Create one with "
            f"`init-db`, or load a published campaign with `import-campaign`. "
            f"Do NOT continue play from memory.")
    found = json.loads(marker.read_text()).get("format_version")
    if found != SUPPORTED_FORMAT:
        raise StoreError(
            f"The store at {root} is format {found}, and this build reads "
            f"{SUPPORTED_FORMAT}. Update the plugin rather than writing to it.")
    return store
```

- [ ] **Step 4: Run the switch tests**

Run: `uv run --project skills/mythras-gm python -m pytest tests/test_backend_switch.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add skills/mythras-gm/store/__init__.py tests/test_backend_switch.py
git commit -m "feat(store): backend switch that never silently falls back

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Port the helper layer in `mythras_gm.py`

**Files:**
- Modify: `skills/mythras-gm/mythras_gm.py:84-325`

**Interfaces:**
- Consumes: `resolve_store` (Task 7).
- Produces: module-level `get_store()` returning the cached active store, and rewritten `_fetch`/`_write`/`_set_attr`/`_get_entity`/`_link_to_campaign`/`declared`/`_opt`/`_optf` that delegate. Task 9 removes the last `_fetch`/`_write` callers.

**This task changes no call sites.** The 134 `_set_attr` / `_get_entity` / `_link_to_campaign` uses keep working untouched — that is the point of keeping their signatures.

- [ ] **Step 1: Verify the current suite is green, so regressions are attributable**

Run: `cd /Users/gullyburns/mythras-gm && uv run --project skills/mythras-gm python -m pytest tests/ -v`
Expected: all pass (some TypeDB tests may skip). **Record the pass count** — it is the number Step 5 must match.

- [ ] **Step 2: Replace the driver layer**

Replace `mythras_gm.py` lines 84–89 (the hard-exit import) with nothing — delete them. Then replace `_connect`/`get_driver` (lines 123–149) and the helper block (193–325) with:

```python
from store import resolve_store, StoreError

_STORE = None


def get_store(create=False):
    """The active campaign store.

    This used to be get_driver(), and it used to hard-exit the whole process
    at import time when typedb-driver was missing -- which alone made Cowork
    impossible. The backend now resolves at first use, and an unavailable one
    is reported as itself rather than swapped for another.
    """
    global _STORE
    if _STORE is None:
        try:
            _STORE = resolve_store(create=create)
        except StoreError as e:
            fail(str(e))
    return _STORE


# --- compatibility shims ----------------------------------------------------
# These keep the signatures 134 call sites already use. `driver` is ignored;
# it is threaded through so this task touches no call sites, and Task 9 drops
# the parameter once the raw-TypeQL callers are gone.

def _set_attr(driver, entity_type, entity_id, attr, value, quote=True):
    try:
        get_store().set_attr(entity_type, entity_id, attr, value)
    except StoreError as e:
        fail(str(e))


def _get_entity(driver, entity_type, entity_id, attrs):
    try:
        return get_store().get_entity(entity_type, entity_id, attrs)
    except StoreError as e:
        fail(str(e))


def _link_to_campaign(driver, campaign_id, element_id, element_type):
    try:
        get_store().add_member(campaign_id, element_id, element_type)
    except StoreError as e:
        fail(str(e))


def declared(driver, *type_names):
    return get_store().declared(*type_names)
```

`_opt` and `_optf` build TypeQL fragments, so they stay for now and move into
`TypeDBStore` in Task 9 as their callers are ported.

- [ ] **Step 3: Make `get_driver()` a shim that keeps Task 9's work compiling**

The ~137 raw-TypeQL sites still call `with get_driver() as driver:`. Keep them
working for one task:

```python
from contextlib import contextmanager


@contextmanager
def get_driver():
    """Transitional. Yields the TypeDB store's driver so not-yet-ported
    raw-TypeQL sites keep working. Task 9 deletes this, and every remaining
    caller with it."""
    store = get_store()
    if not hasattr(store, "driver"):
        fail("This command still needs TypeDB and has not been ported to the "
             "store interface yet. Run it under MYTHRAS_BACKEND=typedb.")
    yield store.driver


def _fetch(driver, query):
    return get_store()._fetch(query)


def _write(driver, *queries):
    return get_store()._write(*queries)
```

- [ ] **Step 4: Point `resolve_campaign` at the store**

Replace the `_fetch` in `resolve_campaign` (around line 175) with:

```python
    rows = get_store().list_entities("myth-campaign")
    rows = [{"id": r["id"], "name": r.get("name")} for r in rows]
```

and update its two `fail()` messages to say "store" rather than "database" —
`get_store().describe()["location"]` is the string to name.

- [ ] **Step 5: Run the full suite under TypeDB and confirm no regression**

```bash
MYTHRAS_BACKEND=typedb uv run --project skills/mythras-gm python -m pytest tests/ -v
```
Expected: the same pass count as Step 1. Any new failure is this task's, not Task 9's.

- [ ] **Step 6: Commit**

```bash
git add skills/mythras-gm/mythras_gm.py
git commit -m "refactor(cli): helper layer delegates to CampaignStore

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Port the raw-TypeQL call sites, shape by shape

**Files:**
- Modify: `skills/mythras-gm/mythras_gm.py` (~137 sites)

**Interfaces:**
- Consumes: `get_store()` (Task 8).
- Produces: a `mythras_gm.py` with no `_fetch`, no `_write`, no `get_driver`, and no `typedb` import.

**Port by shape, not by command.** Each sub-step below is one shape across the whole file: one pattern to learn, one `grep` to enumerate, one kind of edit. Commit after each. Doing it command-by-command means re-deriving the same translation 88 times.

- [ ] **Step 1: Shape A — campaign membership (23 sites)**

Enumerate: `grep -n "myth-campaign-membership" skills/mythras-gm/mythras_gm.py`

Before:
```python
    ids = _fetch(driver, f'''
        match
          $camp isa myth-campaign, has id "{escape_string(campaign_id)}";
          (campaign: $camp, element: $b) isa myth-campaign-membership;
          $b isa myth-beat, has id $i;
        fetch {{ "id": $i }};''')
    return [_beat_record(driver, r["id"]) for r in ids]
```

After:
```python
    ids = get_store().members(campaign_id, "myth-beat")
    return [_beat_record(driver, bid) for bid in ids]
```

Note the result shape changes from `[{"id": ...}]` to `[str]` — fix each
caller's unpacking as you go.

Run: `MYTHRAS_BACKEND=typedb uv run --project skills/mythras-gm python -m pytest tests/ -v`
Expected: same pass count as Task 8 Step 5.

Commit: `git commit -am "refactor(cli): campaign membership through the store"`

- [ ] **Step 2: Shape B — single-hop relation walks (≈25 sites)**

Enumerate: `grep -n "isa myth-\(presence\|participation\|event-involvement\|faction-membership\|template-instance\|lore-about\|agenda-holder\|agenda-target\|beat-of\|beat-at\|beat-cast\|beat-outcome\|fact-from\|fact-about\|knows\|agenda-requires\|consequence\|fact-supersedes\)" skills/mythras-gm/mythras_gm.py`

Before:
```python
        rows = _fetch(driver, f'''
            match
              $c isa myth-character, has id "{escape_string(pid)}";
              (located: $c, location: $l) isa myth-presence;
              $l has id $li;
            fetch {{ "id": $li }};''')
        places.extend(r["id"] for r in rows)
```

After:
```python
        places.extend(get_store().related("myth-presence", "located", pid, "location"))
```

When the original constrains the far side's type (`$l isa myth-location;`),
pass `to_type="myth-location"`.

**`_subject_knowledge_edges` (line 1269) is the one site that needs relation
attributes.** Port it with `relation_pairs`, and extend
`TypeDBStore.relation_pairs` to fetch the `myth-knows` attributes so the
`test_link_carries_attributes` xfail from Task 6 can be removed:

```python
    def relation_pairs(self, relation, role_a, role_b, type_a=None, type_b=None):
        a_clause = f"$a isa {type_a};" if type_a else ""
        b_clause = f"$b isa {type_b};" if type_b else ""
        rel_attrs = self.declared(*model.RELATION_TYPES[relation]["owns"])
        # `try` guards a missing VALUE; declared() above guards a missing TYPE.
        # Both are needed, and they must be trimmed together or the fetch names
        # a variable no clause bound, which is an error.
        opt = "".join(f" try {{ $rel has {a} $x{i}; }};"
                      for i, a in enumerate(rel_attrs))
        keys = "".join(f', "{a}": $x{i}' for i, a in enumerate(rel_attrs))
        rows = self._fetch(f'''
            match
              {a_clause} {b_clause}
              $rel isa {relation}, links ({role_a}: $a, {role_b}: $b);
              $a has id $ai; $b has id $bi;{opt}
            fetch {{ "a": $ai, "b": $bi{keys} }};''')
        return [(r["a"], r["b"],
                 {k: v for k, v in r.items() if k not in ("a", "b") and v is not None})
                for r in rows]
```

The attribute names come from `model.RELATION_TYPES[relation]["owns"]`, which
Task 1 generated from the LinkML model and the parity test holds to
`schema.tql` — nothing is hand-listed here.

Then delete the `xfail` marker from `test_link_carries_attributes`. `JsonStore`
needs no change: it already stores `attrs` verbatim.

`_subject_knowledge_edges` also needs the three-role shape of `myth-knows`
(`knower`, then `fact` *or* `subject`, each `@card(0..1)`). Callers that walk
knower→fact use `related("myth-knows", "knower", kid, "fact")`; knower→subject
uses `to_role="subject"`. A `related` call whose `to_role` is unbound on a
given row simply skips that row, which is what both backends do.

Run and commit as in Step 1.

- [ ] **Step 3: Shape C — entity inserts (≈30 sites)**

Enumerate: `grep -n "insert \$[a-z] isa myth-" skills/mythras-gm/mythras_gm.py`

Before:
```python
    q = f'''insert $c isa myth-character,
        has id "{cid}", has name "{escape_string(args.name)}",
        has myth-char-type "{args.char_type}",
        has created-at {ts};'''
    with get_driver() as driver:
        _write(driver, q)
```

After:
```python
    get_store().put_entity("myth-character", cid, {
        "name": args.name,
        "myth-char-type": args.char_type,
        "created-at": ts,
    })
```

Escaping moves into the store — drop the `escape_string` calls at these sites.

Run and commit.

- [ ] **Step 4: Shape D — list/filter reads (≈20 sites)**

Enumerate: `grep -n "_fetch(driver" skills/mythras-gm/mythras_gm.py` — what
remains after Steps 1–3 is mostly this shape.

Before:
```python
        rows = _fetch(driver, f'''
            match $c isa myth-character, has myth-char-type "pc", has id $i;
            fetch {{ "id": $i }};''')
```

After:
```python
        rows = get_store().list_entities("myth-character", where={"myth-char-type": "pc"})
```

Ranking, sorting and `--limit` already happen in Python after the fetch, so
none of them move.

Run and commit.

- [ ] **Step 5: Shape E — the rules graph and the legacy migration**

`load-rules` (line 4784) holds all four negations in the file, and they are a
one-time migration deleting legacy rules with no `myth-rule-system`.

Before:
```python
            _write(driver, '''
                match $r isa myth-rule; not { $r has myth-rule-system $s; };
                      $rel isa myth-rule-tagged, links (rule: $r);
                delete $rel;''')
```

After:
```python
            store = get_store()
            legacy = [r["id"] for r in store.list_entities("myth-rule")
                      if not r.get("myth-rule-system")]
            for rid in legacy:
                for facet in store.related("myth-rule-tagged", "rule", rid, "facet"):
                    store.unlink("myth-rule-tagged", {"rule": rid, "facet": facet})
                for other in store.related("myth-rule-link", "rule", rid, "linked"):
                    store.unlink("myth-rule-link", {"rule": rid, "linked": other})
                for other in store.related("myth-rule-link", "linked", rid, "rule"):
                    store.unlink("myth-rule-link", {"rule": other, "linked": rid})
                store.delete_entity("myth-rule", rid)
```

Ensure `list_entities("myth-rule")` requests `myth-rule-system` — pass it in
`where=None` and read from the returned doc, which for the TypeDB backend
means adding it to the attribute list that `list_entities` fetches. Simplest:
call `store.list_entities("myth-rule")` then
`store.get_entity("myth-rule", rid, ["myth-rule-system"])` per row.

Port `query-rules`, `get-rule`, `list-rules`, `list-facets` and
`_facet_vocabulary` the same way, using `related` and `list_entities`. The
faceted ranking is already pure Python and does not move.

Run: `MYTHRAS_BACKEND=typedb uv run --project skills/mythras-gm python -m pytest tests/test_rules_system.py -v`
Expected: all pass.

Commit.

- [ ] **Step 6: Delete the transitional shims**

Remove `get_driver`, `_fetch`, `_write`, `_opt`, `_optf` from
`mythras_gm.py`, and drop the now-unused `driver` first parameter from
`_set_attr`, `_get_entity`, `_link_to_campaign`, `declared` and the
`_record`/`_brief` helpers. Update every call site — the compiler finds them:

```bash
grep -n "get_driver\|_fetch(\|_write(\|_opt(\|_optf(" skills/mythras-gm/mythras_gm.py
```
Expected after the edit: no matches.

- [ ] **Step 7: Verify the TypeDB import is gone**

Run: `grep -n "typedb" skills/mythras-gm/mythras_gm.py`
Expected: no matches.

Run: `MYTHRAS_BACKEND=json MYTHRAS_STORE=/tmp/mythras-smoke uv run --project skills/mythras-gm python skills/mythras-gm/mythras_gm.py init-db`
Expected: JSON success output, `/tmp/mythras-smoke/store.json` exists, and **no `typedb-driver not installed` error** — proof the hard import is gone.

- [ ] **Step 8: Run the whole suite on both backends**

```bash
MYTHRAS_BACKEND=typedb uv run --project skills/mythras-gm python -m pytest tests/ -v
MYTHRAS_BACKEND=json   uv run --project skills/mythras-gm python -m pytest tests/ -v
```
Expected: both green.

- [ ] **Step 9: Commit**

```bash
git add skills/mythras-gm/mythras_gm.py skills/mythras-gm/store/typedb_store.py \
        tests/test_store_conformance.py
git commit -m "refactor(cli): every query through the store interface

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: Port `campaign_io.py` and `novelist.py`

**Files:**
- Modify: `skills/mythras-gm/campaign_io.py` (49 sites)
- Modify: `skills/mythras-gm/novelist.py`

**Interfaces:**
- Consumes: `get_store()` (Task 8), the ported helpers (Task 9).
- Produces: export/import and novelization working on both backends.

- [ ] **Step 1: Port `campaign_io._member_ids` and `_relation_pairs`**

These two helpers (lines 103–125) front most of the file's DB access.

Before:
```python
def _member_ids(driver, campaign_id, etype):
    rows = gm._fetch(driver, f'''...''')
    return [r["id"] for r in rows]
```

After:
```python
def _member_ids(campaign_id, etype):
    return gm.get_store().members(campaign_id, etype)


def _relation_pairs(campaign_id, rel, role_a, role_b, type_a, type_b):
    return gm.get_store().relation_pairs(rel, role_a, role_b, type_a, type_b)
```

Drop the `driver` argument at every call site.

- [ ] **Step 2: Port the remaining sites in `export_campaign` and `import_campaign`**

Apply the same five shapes from Task 9. `import_campaign` is mostly Shape C
(entity inserts) and Shape B (relation links); wrap each entity's insert plus
its campaign link in one `with gm.get_store().transaction():` block so a
failed import does not leave a half-loaded campaign.

- [ ] **Step 3: Port `novelist.py`**

Enumerate: `grep -n "get_driver\|_fetch\|_write" skills/mythras-gm/novelist.py`
Apply the same shapes.

- [ ] **Step 4: Run the tests that cover these**

```bash
MYTHRAS_BACKEND=typedb uv run --project skills/mythras-gm python -m pytest tests/test_novelist.py tests/test_cli_ergonomics.py -v
MYTHRAS_BACKEND=json   uv run --project skills/mythras-gm python -m pytest tests/test_novelist.py tests/test_cli_ergonomics.py -v
```
Expected: both green.

- [ ] **Step 5: Verify no driver references remain anywhere**

Run: `grep -rn "typedb\|get_driver" skills/mythras-gm/*.py`
Expected: matches only in `store/typedb_store.py`.

- [ ] **Step 6: Commit**

```bash
git add skills/mythras-gm/campaign_io.py skills/mythras-gm/novelist.py
git commit -m "refactor(io): campaign export/import and novelization through the store

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 11: Backend-aware `init-db`, `stop-db`, `doctor`, and the preflight

**Files:**
- Modify: `skills/mythras-gm/mythras_gm.py` (`cmd_init_db`, `cmd_stop_db`, `cmd_doctor`, `cmd_load_schema`)
- Modify: `hooks/session-start.sh`

**Interfaces:**
- Consumes: `resolve_store`, `resolve_backend` (Task 7); `JsonStore.check_oplog` (Task 5).
- Produces: `doctor` JSON gaining `backend`, `backend_reason`, `location`, `consistency`.

- [ ] **Step 1: Write the test**

```python
# tests/test_backend_switch.py (append)
import json
import subprocess
import sys
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "skills" / "mythras-gm" / "mythras_gm.py"


def _run(cmd, env_extra, tmp_path):
    import os
    env = dict(os.environ, MYTHRAS_BACKEND="json",
               MYTHRAS_STORE=str(tmp_path / "campaigns"), **env_extra)
    r = subprocess.run([sys.executable, str(CLI)] + cmd,
                       capture_output=True, text=True, env=env)
    return json.loads(r.stdout)


def test_init_db_creates_a_json_store(tmp_path):
    out = _run(["init-db"], {}, tmp_path)
    assert out["success"] is True
    assert out["backend"] == "json"
    assert (tmp_path / "campaigns" / "store.json").exists()


def test_doctor_reports_the_backend_and_why(tmp_path):
    _run(["init-db"], {}, tmp_path)
    out = _run(["doctor"], {}, tmp_path)
    assert out["backend"] == "json"
    assert "MYTHRAS_BACKEND" in out["backend_reason"]
    assert out["consistency"] == "ok"


def test_stop_db_is_a_noop_that_says_so(tmp_path):
    _run(["init-db"], {}, tmp_path)
    out = _run(["stop-db"], {}, tmp_path)
    assert out["success"] is True
    assert "json" in out["message"].lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --project skills/mythras-gm python -m pytest tests/test_backend_switch.py -k "init_db or doctor or stop_db" -v`
Expected: FAIL — `KeyError: 'backend'`

- [ ] **Step 3: Implement**

```python
def cmd_init_db(args):
    backend, reason = resolve_backend()
    store = get_store(create=True)
    if backend == "typedb":
        store.load_schema()             # existing behaviour, unchanged
    out({"success": True, "backend": backend, "reason": reason,
         "location": store.describe()["location"],
         "database": store.describe()["location"]})   # `database` kept: the
                                                      # session-start hook reads it


def cmd_stop_db(args):
    backend, _reason = resolve_backend()
    if backend == "json":
        out({"success": True, "backend": "json",
             "message": "The json backend has no server to stop."})
        return
    ...                                  # existing TypeDB shutdown, unchanged


def cmd_doctor(args):
    backend, reason = resolve_backend()
    report = {"backend": backend, "backend_reason": reason}
    try:
        store = resolve_store()
        health = store.describe()
        report.update(location=health["location"], healthy=health["healthy"],
                      detail=health["detail"])
        problems = store.check_oplog() if hasattr(store, "check_oplog") else []
        report["consistency"] = "ok" if not problems else problems
        report["success"] = health["healthy"] and not problems
    except StoreError as e:
        report.update(success=False, healthy=False, error=str(e))
    out(report)
```

`cmd_load_schema` under the JSON backend is a no-op that reports the model is
built in: `out({"success": True, "backend": "json", "message": "The json
backend carries its schema in store/model.py; nothing to load."})`.

- [ ] **Step 4: Make the preflight backend-aware**

In `hooks/session-start.sh`, the `init-db` call and its success message already
read a `database` key, which Step 3 keeps populated. Add the backend to the
message so the model knows which world it is in:

```bash
if OUT=$(uv run -q --project "$GM" python "$GM/mythras_gm.py" init-db 2>&1); then
  DB=$(printf '%s' "$OUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("database","?"))' 2>/dev/null || echo "$TYPEDB_DATABASE")
  BK=$(printf '%s' "$OUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("backend","typedb"))' 2>/dev/null || echo typedb)
  echo "mythras-gm ready: ${BK} backend at ${DB}. State persists; roll everything through the CLI."
  exit 0
fi
```

The refusal text below it needs no change — it is backend-agnostic already,
and `init-db` reports its own remedy.

- [ ] **Step 5: Run the tests**

Run: `uv run --project skills/mythras-gm python -m pytest tests/test_backend_switch.py -v`
Expected: 11 passed.

- [ ] **Step 6: Commit**

```bash
git add skills/mythras-gm/mythras_gm.py hooks/session-start.sh
git commit -m "feat(cli): backend-aware init-db, stop-db, doctor and preflight

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 12: Round-trip equivalence, packaging, and docs

**Files:**
- Create: `tests/test_roundtrip_equivalence.py`
- Modify: `skills/mythras-gm/pyproject.toml`
- Modify: `skills/mythras-gm/SKILL.md`, `skills/mythras-gm/USAGE.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: the proof that both backends hold the same game.

- [ ] **Step 1: Write the equivalence test**

```python
# tests/test_roundtrip_equivalence.py
"""The two backends must hold the same game.

Export a campaign from one backend, import it into the other, export again:
the two published trees must be identical. If they are not, a campaign that
moves between Code and Cowork loses something, and the loss would show up at
the table rather than here.
"""
import filecmp
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1] / "skills" / "mythras-gm"
CLI = SKILL / "mythras_gm.py"
IO = SKILL / "campaign_io.py"


def _cli(args, env):
    r = subprocess.run([sys.executable, str(CLI)] + args,
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def _json_env(root):
    return dict(os.environ, MYTHRAS_BACKEND="json", MYTHRAS_STORE=str(root))


def _seed(env, campaign="myth-campaign-rt"):
    _cli(["init-db"], env)
    _cli(["create-campaign", "--campaign", campaign, "--name", "Roundtrip"], env)
    _cli(["create-character", "--campaign", campaign, "--name", "Magda",
          "--char-type", "pc"], env)
    _cli(["add-location", "--campaign", campaign, "--name", "The Roost"], env)
    _cli(["log-event", "--campaign", campaign, "--type", "scene",
          "--narrative", 'She said "no" and left.'], env)
    return campaign


def _export(env, campaign, outdir):
    r = subprocess.run([sys.executable, str(IO), "export", "--campaign", campaign,
                        "--out", str(outdir)], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr


def _trees_equal(a, b):
    cmp = filecmp.dircmp(str(a), str(b))
    def walk(d):
        assert not d.left_only and not d.right_only, (d.left_only, d.right_only)
        assert not d.diff_files, d.diff_files
        for sub in d.subdirs.values():
            walk(sub)
    walk(cmp)


def test_json_store_roundtrips_through_the_publish_tree(tmp_path):
    """JSON -> export -> import into a fresh JSON store -> export. Identical."""
    env_a = _json_env(tmp_path / "a")
    campaign = _seed(env_a)
    _export(env_a, campaign, tmp_path / "tree1")

    env_b = _json_env(tmp_path / "b")
    _cli(["init-db"], env_b)
    subprocess.run([sys.executable, str(IO), "import", "--path",
                    str(tmp_path / "tree1")], check=True, env=env_b)
    _export(env_b, campaign, tmp_path / "tree2")
    _trees_equal(tmp_path / "tree1", tmp_path / "tree2")


@pytest.mark.skipif(not os.getenv("MYTHRAS_TEST_TYPEDB"),
                    reason="set MYTHRAS_TEST_TYPEDB=1 with a server running")
def test_typedb_and_json_export_identical_trees(tmp_path):
    """The test that proves the backends hold the same game."""
    env_t = dict(os.environ, MYTHRAS_BACKEND="typedb",
                 TYPEDB_DATABASE="mythras_pytest")
    campaign = _seed(env_t)
    _export(env_t, campaign, tmp_path / "from_typedb")

    env_j = _json_env(tmp_path / "jsonstore")
    _cli(["init-db"], env_j)
    subprocess.run([sys.executable, str(IO), "import", "--path",
                    str(tmp_path / "from_typedb")], check=True, env=env_j)
    _export(env_j, campaign, tmp_path / "from_json")
    _trees_equal(tmp_path / "from_typedb", tmp_path / "from_json")
```

- [ ] **Step 2: Run it**

```bash
uv run --project skills/mythras-gm python -m pytest tests/test_roundtrip_equivalence.py -v
MYTHRAS_TEST_TYPEDB=1 uv run --project skills/mythras-gm python -m pytest tests/test_roundtrip_equivalence.py -v
```
Expected: the JSON round-trip passes; the cross-backend test passes with a
server running. A diff here means an attribute or relation is dropped by one
backend — fix the backend, not the test.

- [ ] **Step 3: Make `typedb-driver` optional**

```toml
[project]
name = "mythras-gm"
version = "1.1.0"
requires-python = ">=3.11,<3.14"
dependencies = [
    "pyyaml>=6.0.0",
]

[project.optional-dependencies]
typedb = ["typedb-driver>=3.8.0,<3.9"]

[dependency-groups]
dev = [
    "pytest>=9.1.1",
    "linkml>=1.8",
    "typedb-driver>=3.8.0,<3.9",
]
```

Verify the JSON backend runs with no driver installed:

```bash
cd /tmp && python3 -m venv nodb && ./nodb/bin/pip install pyyaml
MYTHRAS_BACKEND=json MYTHRAS_STORE=/tmp/mythras-nodb \
  ./nodb/bin/python /Users/gullyburns/mythras-gm/skills/mythras-gm/mythras_gm.py init-db
```
Expected: JSON success. This is the Cowork case, proven.

- [ ] **Step 4: Document the two backends**

In `SKILL.md`, after the "Database and campaign defaults" paragraph, add:

```markdown
**Two storage backends.** In Claude Code the game runs on TypeDB (port 1730,
database `mythras`). In Claude Chat and Cowork, where no server can be
started, it runs on a tree of JSON files under `$MYTHRAS_STORE` — the same
game, the same 88 commands, the same guarantees. `doctor` reports which
backend is active and why.

**The backend never switches on you.** If the CLI was told to use TypeDB and
the server is unreachable, it refuses loudly rather than opening an empty file
store. A refusal means the save is unavailable, not that it is empty: do not
continue play from memory, and do not claim anything persisted.
```

In `USAGE.md`, document `MYTHRAS_BACKEND` and `MYTHRAS_STORE` alongside the
existing `TYPEDB_*` variables, and note that moving a campaign between
backends is `export-campaign` → copy → `import-campaign`.

In `README.md`, update the "What's in the box" tree to include `store/` and
`schema/mythras.linkml.yaml`, and soften the opening line's "in TypeDB" to
name both backends.

- [ ] **Step 5: Run everything, both backends**

```bash
cd /Users/gullyburns/mythras-gm
MYTHRAS_BACKEND=json   uv run --project skills/mythras-gm python -m pytest tests/ -v
MYTHRAS_BACKEND=typedb uv run --project skills/mythras-gm python -m pytest tests/ -v
```
Expected: both green, no xfails remaining.

- [ ] **Step 6: Commit**

```bash
git add tests/test_roundtrip_equivalence.py skills/mythras-gm/pyproject.toml \
        skills/mythras-gm/SKILL.md skills/mythras-gm/USAGE.md README.md
git commit -m "test(store): cross-backend equivalence; make typedb-driver optional

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Open item for the implementer

`WORKSPACE_ROOTS` in `store/__init__.py` ships empty. Before this feature is
useful in Cowork, confirm the real workspace path there and add it — a
one-line change, guarded by `resolve_store_root`'s existence-and-writability
probe so a wrong entry is skipped rather than used. Until then, Cowork
sessions need `MYTHRAS_STORE` set explicitly, which `SKILL.md` should say.
