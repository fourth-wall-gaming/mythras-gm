#!/usr/bin/env python3
"""
mapgen.py -- render area maps for a campaign through the ElevenLabs Image API.

A campaign usually has one city-wide map and no way to zoom in. This renders a
set of area sheets -- one district, region or building each -- at 2K/4K, passing
the existing map as a style reference on every call so the set reads as sheets
from a single atlas rather than a pile of unrelated pictures.

    mapgen list
    mapgen style-ref [--upload PNG]
    mapgen render SLUG [--res 4K] [--quality max] [--seed N] [--dry-run]
    mapgen render --all [--yes]
    mapgen status GENERATION_ID

Specs live in the CAMPAIGN, not here: <campaign>/maps/areas/*.md, each a
markdown file with YAML front-matter (slug, title, tier, style, aspect_ratio,
seed, labels, do_not_label) and a body holding the drawing brief. Two shared
style blocks sit beside them -- _style-cadastral.md for plan-view district
sheets and _style-floorplan.md for building interiors -- and are prepended at
render time.

The API reference this is written against is in
references/elevenlabs-api.llms.txt. Two things from it shape this file:

  * There is NO negative_prompt field. Everything to be excluded has to be said
    inside the prompt, which is why the style blocks carry their exclusions as
    prose rather than as a separate list.
  * Generation is asynchronous and content_url expires in about an hour, so a
    render is create -> poll -> download immediately, never create-and-return.

Deliberately uses stdlib urllib rather than the elevenlabs SDK: mythras_gm.py
already hand-rolls urllib for the TypeDB download, and the REST surface here is
four endpoints. Adding a dependency to pyproject.toml for that is not a trade
worth making.
"""

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

API_BASE = os.getenv("ELEVENLABS_API_BASE", "https://api.elevenlabs.io").rstrip("/")

# The docs disagree with themselves: the API reference page says /v1/flows/image,
# the quickstart's runnable curl says /v1/flows/image/create. Try the documented-
# with-an-example one first and fall back, rather than making the caller guess.
CREATE_PATHS = ("/v1/flows/image/create", "/v1/flows/image")

DEFAULT_MODEL = os.getenv("MAPGEN_MODEL", "gpt-image-2.5-flare")
DEFAULT_RESOLUTION = "4K"
DEFAULT_QUALITY = "max"
POLL_FLOOR_SECONDS = 2.0          # the docs' stated minimum for images
POLL_TIMEOUT_SECONDS = 900

STYLE_BLOCKS = {"cadastral": "_style-cadastral.md",
                "floorplan": "_style-floorplan.md"}


def out(obj):
    print(json.dumps(obj, default=str))


def fail(msg, remedy=None, code=1):
    payload = {"success": False, "error": msg}
    if remedy:
        payload["remedy"] = remedy
    out(payload)
    sys.exit(code)


# --- locating the campaign -------------------------------------------------

def campaign_root(explicit=None):
    """Where the maps live. Explicit flag, then env, then the working dir."""
    root = explicit or os.getenv("MYTHRAS_CAMPAIGN_DIR") or os.getcwd()
    root = os.path.abspath(os.path.expanduser(root))
    if not os.path.isdir(os.path.join(root, "maps")):
        fail("no maps/ directory under %s" % root,
             "Pass --campaign <path to the campaign repo>, or set "
             "MYTHRAS_CAMPAIGN_DIR, or run this from the campaign's root.")
    return root


def areas_dir(root):
    return os.path.join(root, "maps", "areas")


def assets_cache_path(root):
    return os.path.join(areas_dir(root), ".assets.json")


# --- spec files ------------------------------------------------------------

def _split_front_matter(text):
    """Return (front_matter_dict, body). Tolerates a file with no front matter."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end].strip("\n")
    body = text[end + 4:].lstrip("\n")
    try:
        import yaml
        meta = yaml.safe_load(raw) or {}
    except ImportError:
        fail("pyyaml is needed to read map specs but is not installed",
             "Run through uv so the project's dependencies are present: "
             "uv run -q --project <skill dir> python mapgen.py ...")
    except Exception as e:
        return {"_parse_error": str(e)}, body
    if not isinstance(meta, dict):
        meta = {"_parse_error": "front matter is not a mapping"}
    return meta, body


def load_spec(path):
    with open(path, encoding="utf-8") as fh:
        meta, body = _split_front_matter(fh.read())
    slug = meta.get("slug") or os.path.splitext(os.path.basename(path))[0]
    return {
        "slug": slug,
        "title": meta.get("title", slug),
        "tier": meta.get("tier", "district"),
        "style": meta.get("style", "cadastral"),
        "aspect_ratio": str(meta.get("aspect_ratio", "4:3")),
        "seed": meta.get("seed"),
        "labels": meta.get("labels") or [],
        "do_not_label": meta.get("do_not_label") or [],
        "revision": (meta.get("revision") or "").strip(),
        "body": body.strip(),
        "path": path,
        "parse_error": meta.get("_parse_error"),
    }


def load_specs(root):
    d = areas_dir(root)
    if not os.path.isdir(d):
        fail("no map specs at %s" % d,
             "Create maps/areas/ in the campaign and add one .md spec per area, "
             "plus _style-cadastral.md and _style-floorplan.md.")
    specs = []
    for name in sorted(os.listdir(d)):
        if not name.endswith(".md") or name.startswith("_"):
            continue
        path = os.path.join(d, name)
        # A spec is a file with YAML front matter. Without this check a README
        # dropped in beside them is read as a spec, and `render --all` spends a
        # generation drawing a map of its own documentation.
        with open(path, encoding="utf-8") as fh:
            if not fh.read(3).startswith("---"):
                continue
        specs.append(load_spec(path))
    return specs


def load_style_block(root, style):
    name = STYLE_BLOCKS.get(style)
    if not name:
        fail("unknown style %r" % style,
             "Use one of: %s" % ", ".join(sorted(STYLE_BLOCKS)))
    path = os.path.join(areas_dir(root), name)
    if not os.path.isfile(path):
        fail("missing style block %s" % path,
             "Every spec prepends a shared style block. Create %s." % name)
    with open(path, encoding="utf-8") as fh:
        _, body = _split_front_matter(fh.read())
    return body.strip()


def assemble_prompt(spec, style_text, revising=False):
    """Style block + area brief + labels + the do-not-label list, as one string.

    The do-not-label list is appended last and phrased as an instruction because
    the API has no negative prompt; it is the only place these exclusions can
    live.

    When `revising`, a preamble explains that a SECOND reference image is the
    previous attempt at this same sheet, and the spec's `revision:` note says
    what to fix about it. Passing the old render back in is what keeps a
    re-roll from throwing away the parts that already worked.
    """
    parts = []
    if revising:
        parts += [
            "TWO REFERENCE IMAGES ARE SUPPLIED.",
            "",
            "The FIRST is the master city map -- the authority for style and "
            "geography, described below.",
            "",
            "The SECOND is a PREVIOUS ATTEMPT AT THIS VERY SHEET. Keep what it "
            "gets right: its framing, its layout, the parts of its linework and "
            "lettering that already match the master. Redraw it with the faults "
            "below corrected. This is a revision of that drawing, not a fresh "
            "start from nothing.",
            "",
        ]
        if spec["revision"]:
            parts += ["CORRECT THESE FAULTS IN THE PREVIOUS ATTEMPT:", "",
                      spec["revision"], ""]
        parts += ["-" * 70, ""]
    parts += [style_text, "", "AREA BRIEF -- %s" % spec["title"],
              "", "THE TITLE CARTOUCHE ON THIS SHEET READS: %s" % spec["title"],
              "", spec["body"]]
    if spec["labels"]:
        parts += ["", "LETTER EXACTLY THESE LABELS, spelled as written, and no "
                      "other place names:"]
        parts += ["  - %s" % s for s in spec["labels"]]
    if spec["do_not_label"]:
        parts += ["", "DO NOT name, letter or label any of the following "
                      "anywhere on this sheet. They are secret and must not "
                      "appear in the drawing or its legend:"]
        parts += ["  - %s" % s for s in spec["do_not_label"]]
    return "\n".join(parts).strip()


# --- the API ---------------------------------------------------------------

def api_key():
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        fail("ELEVENLABS_API_KEY is not set, so nothing can be generated",
             "Create a key with Image & Video permission at "
             "https://elevenlabs.io/app/settings/api-keys and export it as "
             "ELEVENLABS_API_KEY. The Image API needs a Pro plan or above.")
    return key


def _read_error(e):
    try:
        raw = e.read().decode("utf-8", "replace")
    except Exception:
        return str(e)
    try:
        return json.dumps(json.loads(raw))
    except Exception:
        return raw[:500]


def _request(method, path, data=None, headers=None, timeout=120):
    url = path if path.startswith("http") else API_BASE + path
    hdrs = {"xi-api-key": api_key()}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        detail = _read_error(e)
        if e.code == 402:
            fail("ElevenLabs rejected this as a billing problem (402): %s" % detail,
                 "The Image & Video API needs a Pro plan or above. Upgrade the "
                 "workspace, or generate the maps by hand in the playground.")
        if e.code in (401, 403):
            fail("ElevenLabs rejected the API key (%d): %s" % (e.code, detail),
                 "Check ELEVENLABS_API_KEY, and that the key has the "
                 "Image & Video permission enabled.")
        raise
    except urllib.error.URLError as e:
        fail("could not reach %s: %s" % (url, e),
             "Check network access to api.elevenlabs.io.")
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def post_json(path, payload, timeout=120):
    return _request("POST", path, data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}, timeout=timeout)


def create_generation(payload):
    """POST the job, working around the documented path ambiguity."""
    last = None
    for path in CREATE_PATHS:
        try:
            return post_json(path, payload), path
        except urllib.error.HTTPError as e:
            if e.code == 404:
                last = e
                continue
            fail("image generation was rejected (%d): %s" % (e.code, _read_error(e)),
                 "Check model_id, aspect_ratio, resolution and quality against "
                 "references/elevenlabs-api.llms.txt -- the allowed values differ "
                 "per model.")
    fail("neither documented create path exists: %s" % ", ".join(CREATE_PATHS),
         "The API moved. Re-check "
         "https://elevenlabs.io/docs/api-reference/flows/image/create and update "
         "CREATE_PATHS in mapgen.py. Last error: %s" % last)


def get_generation(generation_id):
    return _request("GET", "/v1/flows/image/%s" % generation_id)


def upload_asset(path, name=None):
    """POST /v1/assets as multipart/form-data, without the requests library."""
    name = name or os.path.basename(path)
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as fh:
        content = fh.read()
    boundary = "----mapgen%s" % uuid.uuid4().hex
    nl = b"\r\n"
    body = b"".join([
        b"--", boundary.encode(), nl,
        b'Content-Disposition: form-data; name="name"', nl, nl,
        name.encode("utf-8"), nl,
        b"--", boundary.encode(), nl,
        ('Content-Disposition: form-data; name="asset"; filename="%s"' % name).encode("utf-8"), nl,
        ("Content-Type: %s" % mime).encode(), nl, nl,
        content, nl,
        b"--", boundary.encode(), b"--", nl,
    ])
    return _request("POST", "/v1/assets", data=body,
                    headers={"Content-Type":
                             "multipart/form-data; boundary=%s" % boundary},
                    timeout=300)


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "mythras-gm-mapgen/1.0"})
    with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as fh:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
    return os.path.getsize(dest)


def poll_until_done(generation_id, timeout=POLL_TIMEOUT_SECONDS, quiet=False):
    started = time.time()
    while True:
        r = get_generation(generation_id)
        status = r.get("status")
        if status in ("completed", "failed"):
            return r
        if time.time() - started > timeout:
            fail("gave up waiting for %s after %ds (last status: %s)"
                 % (generation_id, timeout, status),
                 "The job may still finish. Check it with: "
                 "mapgen status %s" % generation_id)
        if not quiet:
            print("  %s ... %ds" % (status, int(time.time() - started)),
                  file=sys.stderr)
        time.sleep(POLL_FLOOR_SECONDS)


# --- the style reference ---------------------------------------------------

def read_assets_cache(root):
    p = assets_cache_path(root)
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}
    return {}


def write_assets_cache(root, data):
    p = assets_cache_path(root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")


def ensure_style_ref(root, upload_path=None):
    """The asset_id of the master map, uploading it once if needed.

    Cached in maps/areas/.assets.json and tracked in git: an asset id is not a
    secret, and keeping it with the specs is what makes a re-render reproducible
    rather than merely similar.
    """
    cache = read_assets_cache(root)
    if not upload_path and cache.get("style_ref", {}).get("asset_id"):
        return cache["style_ref"]

    candidate = upload_path or os.path.join(root, "maps", "purewater-map.png")
    if not os.path.isfile(candidate):
        # fall back to any single png sitting directly in maps/
        maps = os.path.join(root, "maps")
        pngs = [f for f in sorted(os.listdir(maps)) if f.lower().endswith(".png")]
        if len(pngs) == 1:
            candidate = os.path.join(maps, pngs[0])
        else:
            fail("no style reference map found",
                 "Pass one explicitly: mapgen style-ref --upload <path to the "
                 "existing map>. Candidates in maps/: %s" % (", ".join(pngs) or "none"))

    asset = upload_asset(candidate, os.path.basename(candidate))
    entry = {
        "asset_id": asset.get("asset_id"),
        "name": asset.get("name"),
        "mime_type": asset.get("mime_type"),
        "source": os.path.relpath(candidate, root),
        "sha256": _sha256(candidate),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    cache["style_ref"] = entry
    write_assets_cache(root, cache)
    return entry


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# --- commands --------------------------------------------------------------

def cmd_list(args):
    root = campaign_root(args.campaign)
    specs = load_specs(root)
    rows = []
    for s in specs:
        png = os.path.join(areas_dir(root), s["slug"] + ".png")
        side = os.path.join(areas_dir(root), s["slug"] + ".json")
        rows.append({
            "slug": s["slug"], "title": s["title"], "tier": s["tier"],
            "style": s["style"], "aspect_ratio": s["aspect_ratio"],
            "rendered": os.path.isfile(png),
            "size_bytes": os.path.getsize(png) if os.path.isfile(png) else None,
            "has_provenance": os.path.isfile(side),
            "parse_error": s["parse_error"],
        })
    out({"success": True, "campaign": root, "count": len(rows),
         "style_ref": read_assets_cache(root).get("style_ref"), "specs": rows})


def cmd_style_ref(args):
    root = campaign_root(args.campaign)
    if args.show:
        entry = read_assets_cache(root).get("style_ref")
        out({"success": bool(entry), "style_ref": entry})
        return
    entry = ensure_style_ref(root, args.upload)
    out({"success": True, "style_ref": entry,
         "cache": os.path.relpath(assets_cache_path(root), root)})


def cmd_status(args):
    r = get_generation(args.generation_id)
    out({"success": r.get("status") != "failed", "generation": r})


def _render_one(root, spec, args, style_cache):
    style_text = style_cache.setdefault(
        spec["style"], load_style_block(root, spec["style"]))

    previous = os.path.join(areas_dir(root), spec["slug"] + ".png")
    revising = bool(getattr(args, "revise", False)) and os.path.isfile(previous)
    if getattr(args, "revise", False) and not revising:
        return {"slug": spec["slug"], "ok": False,
                "error_message": "--revise needs a previous render at %s"
                                 % os.path.relpath(previous, root)}

    prompt = assemble_prompt(spec, style_text, revising=revising)
    seed = args.seed if args.seed is not None else spec["seed"]

    payload = {
        "model_id": args.model,
        "prompt": prompt,
        "aspect_ratio": spec["aspect_ratio"],
        "resolution": args.res,
        "quality": args.quality,
    }
    if seed is not None:
        payload["seed"] = int(seed)

    if args.dry_run:
        return {"slug": spec["slug"], "dry_run": True,
                "prompt_chars": len(prompt), "prompt": prompt,
                "request": {k: v for k, v in payload.items() if k != "prompt"}}

    ref = ensure_style_ref(root)
    payload["images"] = [{"type": "asset", "asset_id": ref["asset_id"]}]

    if revising:
        # Snapshot the old render before it is overwritten -- it is the second
        # reference, and losing it would make the revision unrepeatable.
        archive = os.path.join(areas_dir(root), "previous")
        os.makedirs(archive, exist_ok=True)
        kept = os.path.join(archive, spec["slug"] + ".png")
        if not os.path.exists(kept):
            shutil.copy2(previous, kept)
        with open(kept, "rb") as fh:
            payload["images"].append({
                "type": "inline_base64",
                "content_base64": base64.b64encode(fh.read()).decode("ascii"),
                "mime_type": "image/png",
            })

    created, path_used = create_generation(payload)
    gen_id = created.get("id")
    if not gen_id:
        fail("create returned no generation id: %s" % json.dumps(created),
             "Check references/elevenlabs-api.llms.txt for the expected shape.")

    result = poll_until_done(gen_id, quiet=args.quiet)
    if result.get("status") == "failed":
        return {"slug": spec["slug"], "ok": False,
                "generation_id": gen_id,
                "failure_reason": result.get("failure_reason"),
                "error_message": result.get("error_message")}

    url = result.get("content_url")
    if not url:
        return {"slug": spec["slug"], "ok": False, "generation_id": gen_id,
                "error_message": "completed but no content_url"}

    dest = os.path.join(areas_dir(root), spec["slug"] + ".png")
    size = download(url, dest)

    side = {
        "slug": spec["slug"], "title": spec["title"], "tier": spec["tier"],
        "style": spec["style"],
        "model_id": args.model, "resolution": args.res, "quality": args.quality,
        "aspect_ratio": spec["aspect_ratio"], "seed": seed,
        "generation_id": gen_id, "create_path": path_used,
        "style_ref_asset_id": ref["asset_id"],
        "revised_from_previous": revising,
        "prompt": prompt,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "spec_file": os.path.relpath(spec["path"], root),
        "rendered_at": datetime.now(timezone.utc).isoformat(),
        "bytes": size,
    }
    with open(os.path.join(areas_dir(root), spec["slug"] + ".json"),
              "w", encoding="utf-8") as fh:
        json.dump(side, fh, indent=2)
        fh.write("\n")

    return {"slug": spec["slug"], "ok": True, "generation_id": gen_id,
            "file": os.path.relpath(dest, root), "bytes": size, "seed": seed}


def cmd_render(args):
    root = campaign_root(args.campaign)
    specs = load_specs(root)
    if args.all:
        targets = specs
        expensive = args.res == "4K" and args.quality in ("max", "xhigh")
        if expensive and not args.yes and not args.dry_run:
            fail("refusing to render %d sheets at %s/%s without --yes"
                 % (len(targets), args.res, args.quality),
                 "That is the most expensive setting, times every sheet. Prove "
                 "the style on one or two at --res 1K --quality high first, then "
                 "re-run with --yes.")
    else:
        if not args.slug:
            fail("render needs a SLUG, or --all",
                 "See what exists with: mapgen list")
        targets = [s for s in specs if s["slug"] == args.slug]
        if not targets:
            fail("no spec with slug %r" % args.slug,
                 "Known slugs: %s" % ", ".join(s["slug"] for s in specs))

    style_cache, results = {}, []
    for spec in targets:
        if spec["parse_error"]:
            results.append({"slug": spec["slug"], "ok": False,
                            "error_message": "bad front matter: %s" % spec["parse_error"]})
            continue
        results.append(_render_one(root, spec, args, style_cache))

    ok = all(r.get("ok") or r.get("dry_run") for r in results)
    out({"success": ok, "campaign": root, "count": len(results),
         "model": args.model, "resolution": args.res, "quality": args.quality,
         "results": results})
    if not ok:
        sys.exit(1)


def build_parser():
    p = argparse.ArgumentParser(prog="mapgen", description=__doc__.split("\n")[1])
    p.add_argument("--campaign", help="campaign repo root (default: $MYTHRAS_CAMPAIGN_DIR or cwd)")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("list", help="show every area spec and whether it is rendered")

    s = sub.add_parser("style-ref", help="upload or show the master-map style reference")
    s.add_argument("--upload", help="path to the map to use as the style reference")
    s.add_argument("--show", action="store_true", help="print the cached reference only")

    s = sub.add_parser("render", help="render one area, or all of them")
    s.add_argument("slug", nargs="?")
    s.add_argument("--all", action="store_true")
    s.add_argument("--model", default=DEFAULT_MODEL)
    s.add_argument("--res", default=DEFAULT_RESOLUTION,
                   choices=["512", "1K", "2K", "3K", "4K"])
    s.add_argument("--quality", default=DEFAULT_QUALITY,
                   choices=["low", "medium", "high", "xhigh", "max"])
    s.add_argument("--seed", type=int, help="override the spec's seed")
    s.add_argument("--dry-run", action="store_true",
                   help="assemble and print the prompt without calling the API")
    s.add_argument("--revise", action="store_true",
                   help="pass the existing render back as a second reference and "
                        "apply the spec's revision note; the old image is kept "
                        "under previous/")
    s.add_argument("--yes", action="store_true", help="confirm an expensive --all run")
    s.add_argument("--quiet", action="store_true", help="no progress on stderr")

    s = sub.add_parser("status", help="check one generation by id")
    s.add_argument("generation_id")

    return p


def main():
    args = build_parser().parse_args()
    if not args.command:
        build_parser().print_help()
        sys.exit(1)
    {"list": cmd_list, "style-ref": cmd_style_ref,
     "render": cmd_render, "status": cmd_status}[args.command](args)


if __name__ == "__main__":
    main()
