"""Tests for mapgen.py, which renders area maps through the ElevenLabs Image API.

636 lines at 0% coverage until this file. It is a standalone tool rather than a
CLI subcommand, so the engine's command harness never reached it.

Nothing here touches the network. The HTTP surface is four endpoints behind
`_request`, so the tests that need it monkeypatch that one function; everything
else -- spec parsing, prompt assembly, the --revise contract, the asset cache --
is pure or filesystem-only and is tested directly.

The prompt is the product. A map that comes back wrong is almost always a prompt
that was assembled wrong, and the two facts that shape it both come from the
API's own limitations: there is NO negative_prompt field, so exclusions have to
be said inside the prompt; and --revise works by passing the previous render
back as a second reference, which only means anything if the preamble explains
which image is which.
"""
import base64
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills",
                                "mythras-gm"))
import mapgen


# --------------------------------------------------------------------------
# A campaign on disk, shaped the way mapgen expects to find one.
# --------------------------------------------------------------------------

SPEC = """---
slug: the-channels
title: The Channels
tier: district
style: cadastral
aspect_ratio: "3:2"
seed: 1234
labels:
  - Dyers' Reach
  - The Low Stair
do_not_label:
  - The Drowned Vault
revision: |
  The north bridge is drawn twice. Remove the duplicate.
---
A district of cut channels, timber walkways and dye-yards.
"""

STYLE_BLOCK = """---
title: Cadastral style
---
Plan view. Ink on laid paper. No people, no vignettes, no compass roses.
"""


@pytest.fixture
def campaign(tmp_path):
    """maps/areas/ with one spec, both style blocks, and a master map."""
    areas = tmp_path / "maps" / "areas"
    areas.mkdir(parents=True)
    (areas / "the-channels.md").write_text(SPEC)
    (areas / "_style-cadastral.md").write_text(STYLE_BLOCK)
    (areas / "_style-floorplan.md").write_text(STYLE_BLOCK)
    # A README dropped in beside the specs. render --all must not draw it.
    (areas / "README.md").write_text("These are the area specs.\n")
    (tmp_path / "maps" / "purewater-map.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return tmp_path


# --------------------------------------------------------------------------
# Front matter and specs
# --------------------------------------------------------------------------

def test_front_matter_splits_into_meta_and_body():
    meta, body = mapgen._split_front_matter(SPEC)
    assert meta["slug"] == "the-channels"
    assert meta["aspect_ratio"] == "3:2"
    assert body.startswith("A district of cut channels")


def test_a_file_with_no_front_matter_is_tolerated():
    meta, body = mapgen._split_front_matter("Just prose.\n")
    assert meta == {}
    assert body == "Just prose.\n"


def test_unterminated_front_matter_is_tolerated():
    """A spec someone is midway through editing must not crash the tool."""
    meta, body = mapgen._split_front_matter("---\nslug: x\n")
    assert meta == {}


def test_malformed_yaml_is_reported_not_raised():
    """A parse error has to survive as data: `list` shows it against the spec,
    which is how the author finds out which file is broken."""
    meta, _ = mapgen._split_front_matter("---\nslug: [unclosed\n---\nbody\n")
    assert meta.get("_parse_error")


def test_front_matter_that_is_not_a_mapping_is_an_error():
    meta, _ = mapgen._split_front_matter("---\n- a\n- b\n---\nbody\n")
    assert meta.get("_parse_error")


def test_load_spec_defaults_every_field(tmp_path):
    """A spec with only a body still renders. Defaults are what make a
    one-line spec usable."""
    p = tmp_path / "bare.md"
    p.write_text("---\ntitle: Bare\n---\nA place.\n")
    spec = mapgen.load_spec(str(p))
    assert spec["slug"] == "bare", "slug must fall back to the filename"
    assert spec["tier"] == "district"
    assert spec["style"] == "cadastral"
    assert spec["aspect_ratio"] == "4:3"
    assert spec["seed"] is None
    assert spec["labels"] == []
    assert spec["do_not_label"] == []
    assert spec["revision"] == ""


def test_load_spec_reads_the_revision_note(tmp_path):
    p = tmp_path / "s.md"
    p.write_text(SPEC)
    assert "drawn twice" in mapgen.load_spec(str(p))["revision"]


def test_aspect_ratio_is_always_a_string(tmp_path):
    """YAML reads 1:1 as something other than a string depending on quoting,
    and the API wants a string."""
    p = tmp_path / "r.md"
    p.write_text("---\nslug: r\naspect_ratio: 1\n---\nbody\n")
    assert isinstance(mapgen.load_spec(str(p))["aspect_ratio"], str)


def test_load_specs_skips_style_blocks_and_prose(campaign):
    """Underscore-prefixed files are shared style blocks, and a file with no
    front matter is not a spec. Without both checks, `render --all` spends a
    generation drawing a map of its own README."""
    specs = mapgen.load_specs(str(campaign))
    assert [s["slug"] for s in specs] == ["the-channels"]


# --------------------------------------------------------------------------
# Prompt assembly -- the product
# --------------------------------------------------------------------------

def test_prompt_carries_style_then_brief_then_labels(campaign):
    spec = mapgen.load_specs(str(campaign))[0]
    style = mapgen.load_style_block(str(campaign), "cadastral")
    prompt = mapgen.assemble_prompt(spec, style)

    assert prompt.startswith("Plan view."), "the style block must lead"
    assert "AREA BRIEF -- The Channels" in prompt
    assert "THE TITLE CARTOUCHE ON THIS SHEET READS: The Channels" in prompt
    assert "Dyers' Reach" in prompt and "The Low Stair" in prompt
    assert prompt.index("Plan view.") < prompt.index("AREA BRIEF")


def test_secret_places_are_excluded_inside_the_prompt(campaign):
    """There is no negative_prompt field in this API, so the do-not-label list
    has to be an instruction in the prompt itself. If it ever stops being
    appended, secrets get lettered onto a map handed to players."""
    spec = mapgen.load_specs(str(campaign))[0]
    style = mapgen.load_style_block(str(campaign), "cadastral")
    prompt = mapgen.assemble_prompt(spec, style)
    assert "DO NOT name, letter or label" in prompt
    assert "The Drowned Vault" in prompt
    assert prompt.index("The Drowned Vault") > prompt.index("DO NOT name")


def test_a_plain_prompt_never_mentions_two_reference_images(campaign):
    """The revise preamble must not leak into an ordinary render: it would tell
    the model to look for a second image that was never attached."""
    spec = mapgen.load_specs(str(campaign))[0]
    style = mapgen.load_style_block(str(campaign), "cadastral")
    prompt = mapgen.assemble_prompt(spec, style, revising=False)
    assert "TWO REFERENCE IMAGES" not in prompt
    assert "PREVIOUS ATTEMPT" not in prompt


def test_revising_explains_which_image_is_which(campaign):
    """The whole trick of --revise is the ordering: first image is the master
    map, second is the previous attempt. A model told the wrong way round
    redraws the city as the district."""
    spec = mapgen.load_specs(str(campaign))[0]
    style = mapgen.load_style_block(str(campaign), "cadastral")
    prompt = mapgen.assemble_prompt(spec, style, revising=True)

    assert prompt.startswith("TWO REFERENCE IMAGES ARE SUPPLIED.")
    assert prompt.index("The FIRST is the master city map") < \
        prompt.index("The SECOND is a PREVIOUS ATTEMPT")
    assert "CORRECT THESE FAULTS IN THE PREVIOUS ATTEMPT:" in prompt
    assert "drawn twice" in prompt
    assert "revision of that drawing, not a fresh start" in prompt


def test_revising_without_a_revision_note_still_explains_the_images(tmp_path):
    """A revision with no faults listed is a re-roll that keeps the framing.
    The preamble still has to describe both references."""
    p = tmp_path / "n.md"
    p.write_text("---\nslug: n\ntitle: N\n---\nA place.\n")
    spec = mapgen.load_spec(str(p))
    prompt = mapgen.assemble_prompt(spec, "STYLE", revising=True)
    assert "TWO REFERENCE IMAGES ARE SUPPLIED." in prompt
    assert "CORRECT THESE FAULTS" not in prompt


def test_load_style_block_rejects_an_unknown_style(campaign):
    with pytest.raises(SystemExit):
        mapgen.load_style_block(str(campaign), "watercolour")


def test_load_style_block_names_the_missing_file(tmp_path, capsys):
    (tmp_path / "maps" / "areas").mkdir(parents=True)
    with pytest.raises(SystemExit):
        mapgen.load_style_block(str(tmp_path), "cadastral")
    assert "_style-cadastral.md" in capsys.readouterr().out


# --------------------------------------------------------------------------
# The API surface. `_request` is the only thing that touches the network, so
# it is the only thing these tests replace.
# --------------------------------------------------------------------------

class FakeHTTPError(Exception):
    """Stands in for urllib.error.HTTPError, which needs a real fp to build."""
    def __init__(self, code):
        self.code = code
        super().__init__(f"HTTP {code}")


def test_api_key_refuses_to_run_without_one(monkeypatch, capsys):
    """A missing key must fail before anything is uploaded, and must say where
    to get one -- the permission needed is not obvious."""
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        mapgen.api_key()
    said = capsys.readouterr().out
    assert "ELEVENLABS_API_KEY" in said
    assert "Image & Video" in said, "the required permission must be named"


def test_api_key_returns_the_key_when_set(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk-test")
    assert mapgen.api_key() == "sk-test"


def test_create_generation_falls_back_to_the_other_documented_path(monkeypatch):
    """The API docs disagree with themselves about the create path, so mapgen
    tries both. If the first 404s the second must be attempted, or every render
    fails against whichever deployment has the other one."""
    tried = []

    def fake_post(path, payload, timeout=120):
        tried.append(path)
        if path == mapgen.CREATE_PATHS[0]:
            raise mapgen.urllib.error.HTTPError(path, 404, "nope", {}, None)
        return {"id": "gen-1"}

    monkeypatch.setattr(mapgen, "post_json", fake_post)
    created, used = mapgen.create_generation({"prompt": "x"})
    assert created["id"] == "gen-1"
    assert tried == list(mapgen.CREATE_PATHS)
    assert used == mapgen.CREATE_PATHS[1]


def test_create_generation_reports_which_path_was_used(monkeypatch):
    """The side-car records create_path, so a later failure can be traced to the
    endpoint that served it."""
    monkeypatch.setattr(mapgen, "post_json",
                        lambda p, payload, timeout=120: {"id": "gen-2"})
    _, used = mapgen.create_generation({"prompt": "x"})
    assert used == mapgen.CREATE_PATHS[0]


def test_create_generation_does_not_retry_a_rejection(monkeypatch):
    """A 422 is a bad payload, not a wrong path. Retrying the other path would
    hide the real error behind 'neither documented create path exists'."""
    calls = []

    def fake_post(path, payload, timeout=120):
        calls.append(path)
        raise mapgen.urllib.error.HTTPError(path, 422, "bad", {}, None)

    monkeypatch.setattr(mapgen, "post_json", fake_post)
    with pytest.raises(SystemExit):
        mapgen.create_generation({"prompt": "x"})
    assert len(calls) == 1, "a rejection must not be retried as a path problem"


def test_create_generation_gives_up_with_a_remedy_when_both_404(monkeypatch, capsys):
    def fake_post(path, payload, timeout=120):
        raise mapgen.urllib.error.HTTPError(path, 404, "nope", {}, None)

    monkeypatch.setattr(mapgen, "post_json", fake_post)
    with pytest.raises(SystemExit):
        mapgen.create_generation({"prompt": "x"})
    assert "CREATE_PATHS" in capsys.readouterr().out


def test_poll_returns_on_completed(monkeypatch):
    monkeypatch.setattr(mapgen, "get_generation",
                        lambda gid: {"status": "completed", "content_url": "u"})
    monkeypatch.setattr(mapgen.time, "sleep", lambda s: None)
    assert mapgen.poll_until_done("g", quiet=True)["status"] == "completed"


def test_poll_returns_on_failed_rather_than_waiting_out_the_timeout(monkeypatch):
    """A failed job is terminal. Treating it as pending would block for the
    full fifteen minutes."""
    monkeypatch.setattr(mapgen, "get_generation",
                        lambda gid: {"status": "failed",
                                     "failure_reason": "content_policy"})
    monkeypatch.setattr(mapgen.time, "sleep", lambda s: None)
    r = mapgen.poll_until_done("g", quiet=True)
    assert r["status"] == "failed"
    assert r["failure_reason"] == "content_policy"


def test_poll_gives_up_and_says_how_to_check_later(monkeypatch, capsys):
    """content_url expires in about an hour, but the job may still finish, so
    the timeout has to hand back the id rather than just erroring."""
    monkeypatch.setattr(mapgen, "get_generation", lambda gid: {"status": "running"})
    monkeypatch.setattr(mapgen.time, "sleep", lambda s: None)
    with pytest.raises(SystemExit):
        mapgen.poll_until_done("gen-xyz", timeout=-1, quiet=True)
    said = capsys.readouterr().out
    assert "gen-xyz" in said
    assert "mapgen status" in said


def test_the_poll_floor_respects_the_documented_minimum():
    assert mapgen.POLL_FLOOR_SECONDS >= 2.0, \
        "the API documents 2s as the minimum poll interval for images"


# --------------------------------------------------------------------------
# The asset cache and the style reference
# --------------------------------------------------------------------------

def test_the_asset_cache_round_trips(campaign):
    mapgen.write_assets_cache(str(campaign), {"style_ref": {"asset_id": "a1"}})
    assert mapgen.read_assets_cache(str(campaign))["style_ref"]["asset_id"] == "a1"


def test_a_corrupt_asset_cache_reads_as_empty_rather_than_raising(campaign):
    """Half-written JSON must not stop a render; re-uploading the master map is
    a cheap recovery and crashing is not."""
    path = mapgen.assets_cache_path(str(campaign))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write("{not json")
    assert mapgen.read_assets_cache(str(campaign)) == {}


def test_a_cached_style_ref_is_not_uploaded_again(campaign, monkeypatch):
    """Re-uploading on every render would burn quota and change the asset id,
    which is what makes a re-render reproducible."""
    mapgen.write_assets_cache(str(campaign),
                              {"style_ref": {"asset_id": "cached-1"}})
    monkeypatch.setattr(mapgen, "upload_asset",
                        lambda *a, **k: pytest.fail("uploaded despite a cache hit"))
    assert mapgen.ensure_style_ref(str(campaign))["asset_id"] == "cached-1"


def test_style_ref_uploads_once_and_records_the_digest(campaign, monkeypatch):
    monkeypatch.setattr(mapgen, "upload_asset", lambda path, name=None: {
        "asset_id": "new-1", "name": name, "mime_type": "image/png"})
    entry = mapgen.ensure_style_ref(str(campaign))
    assert entry["asset_id"] == "new-1"
    assert entry["sha256"], "no digest recorded for the reference map"
    assert entry["source"] == os.path.join("maps", "purewater-map.png")
    # and it is persisted, so the next run is a cache hit
    assert mapgen.read_assets_cache(str(campaign))["style_ref"]["asset_id"] == "new-1"


def test_style_ref_falls_back_to_a_lone_png(tmp_path, monkeypatch):
    """Not every campaign's map is called purewater-map.png."""
    (tmp_path / "maps" / "areas").mkdir(parents=True)
    (tmp_path / "maps" / "veilwrack.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    monkeypatch.setattr(mapgen, "upload_asset", lambda path, name=None: {
        "asset_id": "fallback-1", "name": name, "mime_type": "image/png"})
    entry = mapgen.ensure_style_ref(str(tmp_path))
    assert entry["source"] == os.path.join("maps", "veilwrack.png")


def test_style_ref_refuses_to_guess_between_several_pngs(tmp_path, capsys):
    """Picking one at random would silently style every sheet against the wrong
    master."""
    (tmp_path / "maps" / "areas").mkdir(parents=True)
    for n in ("a.png", "b.png"):
        (tmp_path / "maps" / n).write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(SystemExit):
        mapgen.ensure_style_ref(str(tmp_path))
    said = capsys.readouterr().out
    assert "a.png" in said and "b.png" in said, \
        "the candidates must be listed so the author can pick one"


# --------------------------------------------------------------------------
# --revise end to end, with the network replaced. This is the behaviour the
# feature exists for, and it has three parts: refuse without a previous
# render, snapshot the old one before overwriting, and attach it second.
# --------------------------------------------------------------------------

class Args:
    """A stand-in for the parsed namespace _render_one expects."""
    def __init__(self, **kw):
        self.model = "gpt-image-2.5-flare"
        self.res = "4K"
        self.quality = "max"
        self.seed = None
        self.dry_run = False
        self.quiet = True
        self.revise = False
        self.campaign = None
        self.__dict__.update(kw)


def test_dry_run_builds_the_prompt_and_calls_nothing(campaign, monkeypatch):
    """--dry-run is how you read a prompt before spending a generation, so it
    must not reach the API even to resolve the style reference."""
    monkeypatch.setattr(mapgen, "create_generation",
                        lambda p: pytest.fail("called the API during --dry-run"))
    monkeypatch.setattr(mapgen, "ensure_style_ref",
                        lambda *a, **k: pytest.fail("uploaded during --dry-run"))
    spec = mapgen.load_specs(str(campaign))[0]
    r = mapgen._render_one(str(campaign), spec, Args(dry_run=True), {})
    assert r["dry_run"] is True
    assert r["prompt_chars"] == len(r["prompt"])
    assert "prompt" not in r["request"], \
        "the request echo must not repeat the whole prompt"
    assert r["request"]["aspect_ratio"] == "3:2", "the spec's ratio was dropped"


def test_the_spec_seed_is_used_and_an_explicit_seed_overrides_it(campaign):
    spec = mapgen.load_specs(str(campaign))[0]
    from_spec = mapgen._render_one(str(campaign), spec, Args(dry_run=True), {})
    assert from_spec["request"]["seed"] == 1234

    override = mapgen._render_one(str(campaign), spec,
                                 Args(dry_run=True, seed=99), {})
    assert override["request"]["seed"] == 99


def test_revise_refuses_when_there_is_no_previous_render(campaign):
    """Without the old image there is nothing to revise, and rendering anyway
    would silently produce a fresh draw while reporting a revision."""
    spec = mapgen.load_specs(str(campaign))[0]
    r = mapgen._render_one(str(campaign), spec, Args(revise=True), {})
    assert r["ok"] is False
    assert "--revise needs a previous render" in r["error_message"]
    assert "the-channels.png" in r["error_message"]


def _stub_api(monkeypatch, captured):
    monkeypatch.setattr(mapgen, "ensure_style_ref",
                        lambda *a, **k: {"asset_id": "master-1"})

    def fake_create(payload):
        captured["payload"] = payload
        return {"id": "gen-7"}, mapgen.CREATE_PATHS[0]

    monkeypatch.setattr(mapgen, "create_generation", fake_create)
    monkeypatch.setattr(mapgen, "poll_until_done",
                        lambda gid, quiet=False: {"status": "completed",
                                                  "content_url": "http://x/y.png"})

    def fake_download(url, dest):
        with open(dest, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\nNEW")
        return 11

    monkeypatch.setattr(mapgen, "download", fake_download)


def test_an_ordinary_render_attaches_only_the_master_map(campaign, monkeypatch):
    captured = {}
    _stub_api(monkeypatch, captured)
    spec = mapgen.load_specs(str(campaign))[0]
    r = mapgen._render_one(str(campaign), spec, Args(), {})

    assert r["ok"] is True
    images = captured["payload"]["images"]
    assert len(images) == 1, "an ordinary render must send one reference"
    assert images[0] == {"type": "asset", "asset_id": "master-1"}


def test_revise_snapshots_the_old_render_and_attaches_it_second(campaign, monkeypatch):
    """The ordering is the contract: master map first, previous attempt second,
    matching the preamble. And the old file is copied to previous/ BEFORE being
    overwritten -- without that the revision is unrepeatable, because the
    reference it was drawn against is gone."""
    areas = campaign / "maps" / "areas"
    old_bytes = b"\x89PNG\r\n\x1a\nOLD"
    (areas / "the-channels.png").write_bytes(old_bytes)

    captured = {}
    _stub_api(monkeypatch, captured)
    spec = mapgen.load_specs(str(campaign))[0]
    r = mapgen._render_one(str(campaign), spec, Args(revise=True), {})
    assert r["ok"] is True

    kept = areas / "previous" / "the-channels.png"
    assert kept.is_file(), "the previous render was overwritten without a copy"
    assert kept.read_bytes() == old_bytes
    assert (areas / "the-channels.png").read_bytes() != old_bytes, \
        "the new render did not land"

    images = captured["payload"]["images"]
    assert len(images) == 2
    assert images[0]["asset_id"] == "master-1", "the master map must come first"
    assert images[1]["type"] == "inline_base64"
    assert images[1]["mime_type"] == "image/png"
    assert base64.b64decode(images[1]["content_base64"]) == old_bytes, \
        "the second reference is not the previous render"
    assert "TWO REFERENCE IMAGES" in captured["payload"]["prompt"]


def test_revise_does_not_clobber_an_existing_snapshot(campaign, monkeypatch):
    """A second revision must keep the ORIGINAL first attempt. Overwriting it
    each pass would lose the only copy of what the first render looked like."""
    areas = campaign / "maps" / "areas"
    (areas / "previous").mkdir()
    (areas / "previous" / "the-channels.png").write_bytes(b"FIRST")
    (areas / "the-channels.png").write_bytes(b"SECOND")

    _stub_api(monkeypatch, {})
    spec = mapgen.load_specs(str(campaign))[0]
    mapgen._render_one(str(campaign), spec, Args(revise=True), {})
    assert (areas / "previous" / "the-channels.png").read_bytes() == b"FIRST"


def test_a_render_writes_a_side_car_that_can_reproduce_it(campaign, monkeypatch):
    """The side-car is the provenance. Without the prompt and its digest there
    is no way to tell which prompt produced which sheet."""
    captured = {}
    _stub_api(monkeypatch, captured)
    spec = mapgen.load_specs(str(campaign))[0]
    mapgen._render_one(str(campaign), spec, Args(), {})

    side = json.loads((campaign / "maps" / "areas" / "the-channels.json")
                      .read_text())
    assert side["generation_id"] == "gen-7"
    assert side["style_ref_asset_id"] == "master-1"
    assert side["seed"] == 1234
    assert side["aspect_ratio"] == "3:2"
    assert side["revised_from_previous"] is False
    assert side["prompt_sha256"] and side["prompt"]
    assert side["spec_file"] == os.path.join("maps", "areas", "the-channels.md")


def test_the_side_car_records_that_a_render_was_a_revision(campaign, monkeypatch):
    (campaign / "maps" / "areas" / "the-channels.png").write_bytes(b"OLD")
    _stub_api(monkeypatch, {})
    spec = mapgen.load_specs(str(campaign))[0]
    mapgen._render_one(str(campaign), spec, Args(revise=True), {})
    side = json.loads((campaign / "maps" / "areas" / "the-channels.json")
                      .read_text())
    assert side["revised_from_previous"] is True


def test_a_failed_generation_is_reported_not_raised(campaign, monkeypatch):
    """render --all must carry on through one bad sheet and report it."""
    monkeypatch.setattr(mapgen, "ensure_style_ref",
                        lambda *a, **k: {"asset_id": "master-1"})
    monkeypatch.setattr(mapgen, "create_generation",
                        lambda p: ({"id": "gen-8"}, mapgen.CREATE_PATHS[0]))
    monkeypatch.setattr(mapgen, "poll_until_done",
                        lambda gid, quiet=False: {
                            "status": "failed",
                            "failure_reason": "content_policy",
                            "error_message": "refused"})
    spec = mapgen.load_specs(str(campaign))[0]
    r = mapgen._render_one(str(campaign), spec, Args(), {})
    assert r["ok"] is False
    assert r["failure_reason"] == "content_policy"
    assert r["generation_id"] == "gen-8"


def test_completed_with_no_content_url_is_reported(campaign, monkeypatch):
    """content_url expires in about an hour; a completed job without one is a
    real state and must not be downloaded as None."""
    monkeypatch.setattr(mapgen, "ensure_style_ref",
                        lambda *a, **k: {"asset_id": "m"})
    monkeypatch.setattr(mapgen, "create_generation",
                        lambda p: ({"id": "gen-9"}, mapgen.CREATE_PATHS[0]))
    monkeypatch.setattr(mapgen, "poll_until_done",
                        lambda gid, quiet=False: {"status": "completed"})
    spec = mapgen.load_specs(str(campaign))[0]
    r = mapgen._render_one(str(campaign), spec, Args(), {})
    assert r["ok"] is False
    assert "no content_url" in r["error_message"]


def test_create_returning_no_id_fails_loudly(campaign, monkeypatch, capsys):
    monkeypatch.setattr(mapgen, "ensure_style_ref",
                        lambda *a, **k: {"asset_id": "m"})
    monkeypatch.setattr(mapgen, "create_generation",
                        lambda p: ({}, mapgen.CREATE_PATHS[0]))
    spec = mapgen.load_specs(str(campaign))[0]
    with pytest.raises(SystemExit):
        mapgen._render_one(str(campaign), spec, Args(), {})
    assert "generation id" in capsys.readouterr().out


# --------------------------------------------------------------------------
# The CLI
# --------------------------------------------------------------------------

def test_the_parser_offers_the_documented_subcommands():
    parser = mapgen.build_parser()
    sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
    for name in ("list", "style-ref", "render", "status"):
        assert name in sub.choices, f"the docstring promises `mapgen {name}`"


def test_render_all_is_distinct_from_rendering_one_slug():
    """`render --all` at 4K/max is expensive, which is why it has --yes."""
    parser = mapgen.build_parser()
    sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
    dests = {a.dest for a in sub.choices["render"]._actions}
    for flag in ("all", "yes", "dry_run", "revise", "res", "quality", "seed"):
        assert flag in dests, f"`render` has no --{flag.replace('_', '-')}"


def test_every_mapgen_subcommand_has_a_handler():
    parser = mapgen.build_parser()
    sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
    for name in sub.choices:
        fn = getattr(mapgen, "cmd_" + name.replace("-", "_"), None)
        assert fn is not None, f"`mapgen {name}` has nothing to dispatch to"
