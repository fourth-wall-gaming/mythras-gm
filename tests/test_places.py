"""A place card is the same idea as an actor card: the entry says where a place
is, the card says what it does to a scene. These pin the second one, and pin the
guidance that makes the gap visible when it is missing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "mythras-gm"))
import mythras_gm as gm


SCHEMA = (Path(__file__).resolve().parent.parent
          / "skills" / "mythras-gm" / "schema.tql").read_text()


def test_schema_gives_locations_staging_notes():
    assert "attribute myth-staging-notes, value string;" in SCHEMA
    loc = SCHEMA[SCHEMA.index("entity myth-location"):]
    loc = loc[:loc.index(";")]
    assert "owns myth-staging-notes" in loc


def test_update_location_can_write_them():
    p = gm.build_parser()
    args = p.parse_args(["update-location", "--id", "myth-loc-1",
                         "--staging-notes", "SENSE: tar and cold iron"])
    assert args.staging_notes == "SENSE: tar and cold iron"


def test_list_locations_exists_and_infers_the_campaign():
    gm.build_parser().parse_args(["list-locations"])   # --campaign not required
    assert "list-locations" in gm.NEEDS_CAMPAIGN


def test_brief_routes_a_location_id_to_the_place_briefing():
    import inspect
    src = inspect.getsource(gm.cmd_brief)
    assert 'args.id.startswith("myth-loc-")' in src
    assert "_brief_location" in src


def test_an_unstaged_place_says_so_rather_than_returning_nothing():
    import inspect
    src = inspect.getsource(gm._brief_location)
    # The failure mode being guarded against is a silent empty field, which
    # reads like "this place needs no notes".
    assert "NO STAGING NOTES" in src
    assert "update-location --staging-notes" in src


def test_the_index_reports_the_debt_not_just_the_rows():
    import inspect
    src = inspect.getsource(gm.cmd_list_locations)
    assert '"unstaged"' in src and "guidance" in src
