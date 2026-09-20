---
description: Diagnose or force a first-run setup — when the session-start hook could not bring the game up automatically, or to opt into --docker.
---

# Set the game up

The session-start hook already does this automatically on every session:
download the native TypeDB server (a one-time ~25MB fetch), start it, create
the database, define the schema, load the rules graph. Run this command only
when that failed, or when you deliberately want the Docker-managed path
instead of the built-in native one.

## Steps

1. **Diagnose first, rather than guessing:**

   ```bash
   GM="${CLAUDE_PLUGIN_ROOT}/skills/mythras-gm"
   uv run -q --project "$GM" python "$GM/mythras_gm.py" doctor
   ```

   Read every `false` check aloud. The usual causes: no network for the
   first-run download; a platform with no native build (rare -- mac, Linux and
   Windows on x86_64/arm64 are all covered); or something else already using
   the port.

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
   which is `/mythras-gm:play` if a campaign already exists, or installing a
   campaign plugin if one does not. `list-campaigns` tells you which.

## What this does not do

It does not create or import a campaign. A campaign arrives either from its own
plugin (`/plugin install purewater@fourth-wall-gaming`, which brings its own
start command) or from `create-campaign` for a world of your own.
