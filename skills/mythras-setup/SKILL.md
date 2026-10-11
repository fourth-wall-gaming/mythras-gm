---
name: mythras-setup
description: Diagnose or force first-run setup of the Mythras game database — when the session-start preflight could not bring the game up automatically, or to opt into the Docker-managed TypeDB path.
---

# Set the game up

`$GM` is the engine directory — the session-start hook's ready line names it
absolutely; see **CLI** in the `mythras-gm` skill for the fallback.

The session-start hook already does this automatically on every session:
download the native TypeDB server (a one-time ~25MB fetch), start it, create
the database, define the schema, load the rules graph. Use this skill only
when that failed, or when you deliberately want the Docker-managed path
instead of the built-in native one.

On Codex, one more cause belongs at the top of the list: **plugin-bundled hooks
are not trusted until the user reviews them**, so on a fresh install the
preflight has not run at all. That is not a broken setup; it is an untrusted
one. Say so, and have them trust the hook rather than chasing a database fault.

## Steps

1. **Diagnose first, rather than guessing:**

   ```bash
   uv run -q --project "$GM" python "$GM/mythras_gm.py" doctor
   ```

   Read every `false` check aloud. The usual causes: no network for the
   first-run download; a platform with no native build (rare -- mac, Linux and
   Windows on x86_64/arm64 are all covered); or something else already using
   the port. Under a sandboxed host, also: no write access outside the
   workspace, and no outbound network — see `docs/CODEX.md`.

2. **Force it, if the hook's automatic attempt didn't run or didn't finish:**

   ```bash
   uv run -q --project "$GM" python "$GM/mythras_gm.py" init-db
   ```

   Every step is reported in the `steps` array; read them out if any is
   `false`.

3. **If the user prefers Docker** (they already run `docker-compose.yml`, or
   there is no native build for their platform), use `--docker` instead:

   ```bash
   uv run -q --project "$GM" python "$GM/mythras_gm.py" init-db --docker --pull
   ```

   `--pull` allows a first-run image pull, which is the one genuinely slow
   step left (several hundred megabytes) -- tell the user it will take a few
   minutes, unlike the ordinary native path.

4. **When it reports `Ready.`**, say so plainly and offer the next step —
   which is the `mythras-play` skill if a campaign already exists, or
   installing a campaign plugin if one does not. `list-campaigns` tells you
   which.

## What this does not do

It does not create or import a campaign. A campaign arrives either from its own
plugin (the `purewater` or `veilwrack` entry in this repo's marketplace, each of
which brings its own start command) or from `create-campaign` for a world of
your own.
