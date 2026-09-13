"""The fate graph is authored by a human in a text editor, at speed, usually
the night before. These pin the two things that matter: prose the parser does
not understand is never lost, and every way a GM can leave the graph broken is
reported rather than discovered at the table."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "mythras-gm"))
import mythras_gm as gm


def parse(tmp_path, text):
    p = tmp_path / "g.md"
    p.write_text(text)
    return gm.parse_graph(p)


GOOD = """
# A campaign

Any amount of preamble. Nobody parses this.

## NODE A1 · The ford
WHEN d-3/dawn
ENTRY start
TAKES nothing

She has followed the column for three weeks.

IF nobody
  -> A2   SETS MAGDA=missed
IF Gardwen
  ROLL Perception (Standard) to notice the litter,
  and Insight afterwards to read who is guarding it
  -> A2   SETS MAGDA=met
  -> END  she turns back

## NODE A2 · The gate
ENTRY A1
TAKES a coin, or a piece of somebody's dignity
IF nobody
  -> END
"""


def test_parses_the_shape(tmp_path):
    g = parse(tmp_path, GOOD)
    assert g["order"] == ["A1", "A2"]
    a1 = g["nodes"]["A1"]
    assert a1["name"] == "The ford"
    assert a1["when"] == "d-3/dawn"
    assert a1["entry"] == ["start"]
    assert a1["takes"] == "nothing"
    assert [b["who"] for b in a1["branches"]] == ["nobody", "Gardwen"]


def test_unrecognised_lines_survive_as_prose(tmp_path):
    g = parse(tmp_path, GOOD)
    assert "She has followed the column for three weeks." in g["nodes"]["A1"]["prose"]


def test_preamble_before_the_first_node_is_dropped(tmp_path):
    # Not lost -- it is in the file, which is the artefact. It just isn't a node.
    g = parse(tmp_path, GOOD)
    assert all("preamble" not in p for n in g["nodes"].values() for p in n["prose"])


def test_a_wrapped_roll_keeps_its_tail(tmp_path):
    roll = parse(tmp_path, GOOD)["nodes"]["A1"]["branches"][1]["roll"]
    assert roll.endswith("who is guarding it")


def test_prose_after_an_exit_is_prose_not_roll(tmp_path):
    g = parse(tmp_path, """
## NODE A1 · x
ENTRY start
TAKES a thing
IF nobody
  ROLL Perception
  -> END
  and then a stray sentence
""")
    assert g["nodes"]["A1"]["branches"][0]["roll"] == "Perception"
    assert "and then a stray sentence" in g["nodes"]["A1"]["prose"]


def test_flags_are_collected_off_the_exits(tmp_path):
    r = gm.validate_graph(parse(tmp_path, GOOD))
    assert r["flags"] == {"MAGDA": ["met", "missed"]}


def test_end_is_a_legal_destination(tmp_path):
    assert gm.validate_graph(parse(tmp_path, GOOD))["ok"]


def test_fenced_blocks_are_documentation_not_nodes(tmp_path):
    g = parse(tmp_path, GOOD + """
Here is how to write one:

```
## NODE T9.1 · An example in the manual
ENTRY T9.0
  -> T9.2
```
""")
    assert "T9.1" not in g["nodes"]
    assert gm.validate_graph(g)["ok"]


# -- every way a GM leaves it broken ------------------------------------------

@pytest.mark.parametrize("kind,text", [
    ("dangling-exit", """
## NODE A1 · x
ENTRY start
TAKES a thing
IF nobody
  -> A9
"""),
    ("unknown-entry", """
## NODE A1 · x
ENTRY A7
TAKES a thing
IF nobody
  -> END
"""),
    ("dead-end", """
## NODE A1 · x
ENTRY start
TAKES a thing
"""),
    ("takes-nothing", """
## NODE A1 · x
ENTRY start
IF nobody
  -> END
"""),
    ("no-default", """
## NODE A1 · x
ENTRY start
TAKES a thing
IF Gardwen
  -> END
"""),
    ("orphan", """
## NODE A1 · x
ENTRY start
TAKES a thing
IF nobody
  -> END

## NODE A2 · unreachable
TAKES a thing
IF nobody
  -> END
"""),
])
def test_validator_catches(tmp_path, kind, text):
    r = gm.validate_graph(parse(tmp_path, text))
    assert kind in {p["kind"] for p in r["problems"]}, r["problems"]


def test_an_opening_is_not_an_orphan(tmp_path):
    kinds = {p["kind"] for p in gm.validate_graph(parse(tmp_path, GOOD))["problems"]}
    assert "orphan" not in kinds


def test_mermaid_labels_edges_with_presence_and_flags(tmp_path):
    m = gm.graph_mermaid(parse(tmp_path, GOOD))
    assert m.startswith("flowchart TD")
    assert 'A1["The ford"]' in m
    assert "A1 -->|Gardwen MAGDA=met| A2" in m
    assert "END" not in m                      # END is an exit, not a box


def test_dots_in_ids_survive_mermaid(tmp_path):
    m = gm.graph_mermaid(parse(tmp_path, """
## NODE T1.1 · x
ENTRY start
TAKES a thing
IF nobody
  -> T1.2

## NODE T1.2 · y
TAKES a thing
IF nobody
  -> END
"""))
    assert "T1_1 -->|nobody| T1_2" in m


def test_the_live_campaign_graph_is_clean():
    p = Path("/Users/gullyburns/purewater-campaign-v2/setting/purewater.graph.md")
    if not p.exists():
        pytest.skip("campaign package not checked out here")
    r = gm.validate_graph(gm.parse_graph(p))
    assert r["ok"], r["problems"]
