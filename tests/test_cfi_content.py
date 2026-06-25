import os, sys, glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "mythras-gm"))
import campaign_io

CFI_DIR = os.path.join(os.path.dirname(__file__), "..", "skills", "mythras-gm", "rules-cfi")
REQUIRED = {"id", "title", "system", "category", "domain", "topic", "kind", "summary"}

def _pieces():
    files = glob.glob(os.path.join(CFI_DIR, "**", "*.md"), recursive=True)
    return [(f, campaign_io._parse_md(f)[0]) for f in files
            if os.path.basename(f) != "FRONTMATTER.md"]

def test_every_piece_has_required_frontmatter():
    bad = []
    for f, meta in _pieces():
        missing = REQUIRED - set(meta)
        if missing:
            bad.append((f, missing))
    assert not bad, f"frontmatter gaps: {bad}"

def test_every_piece_is_classic_fantasy():
    for f, meta in _pieces():
        assert meta.get("system") == "classic-fantasy", f

def test_ids_are_unique_and_prefixed():
    seen = {}
    for f, meta in _pieces():
        rid = meta.get("id", "")
        assert rid.startswith("cfi/"), f
        assert rid not in seen, f"dup id {rid} in {f} and {seen.get(rid)}"
        seen[rid] = f
