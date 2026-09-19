import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "mythras-gm"))
import mythras_gm as gm

def test_piece_system_defaults_to_mythras():
    assert gm._piece_system({"id": "combat/impale"}) == "mythras"

def test_piece_system_reads_frontmatter():
    assert gm._piece_system({"id": "cfi/spell-heal", "system": "classic-fantasy"}) == "classic-fantasy"

def test_piece_system_strips_and_lowercases():
    assert gm._piece_system({"system": " Classic-Fantasy "}) == "classic-fantasy"
