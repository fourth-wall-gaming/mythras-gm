---
description: First-run setup — fetch the TypeDB image, start the game server, and load the schema and rules. Slow, and only needed once.
---

# Set the game up

Run this once, on a machine that has never run mythras-gm before, or any time
the session-start hook tells you the install is not usable.

It is separate from the session-start hook for one reason: it is allowed to be
slow. The hook never pulls a container image, because a several-hundred-megabyte
download inside a session-start hook is indistinguishable from a hang. This
command does pull, and tells the user what it is doing while it happens.

## Steps

1. **Tell the user this will take a few minutes on a first run**, then:

   ```bash
   GM="${CLAUDE_PLUGIN_ROOT}/skills/mythras-gm"
   uv run -q --project "$GM" python "$GM/mythras_gm.py" init-db --pull
   ```

   That brings up the TypeDB container (pulling the image if it is missing),
   creates the database, defines the schema, and loads the rules graph. Every
   step is reported in the `steps` array; read them out if any is `false`.

2. **If it fails**, run the diagnostic and report what it says rather than
   guessing:

   ```bash
   uv run -q --project "$GM" python "$GM/mythras_gm.py" doctor
   ```

   The usual causes, in order of likelihood: Docker is not running; Docker is not
   installed; something else is already using the port.

3. **When it reports `Ready.`**, say so plainly and offer the next step — which
   is `/mythras-gm:play` if a campaign already exists, or installing a campaign
   plugin if one does not. `list-campaigns` tells you which.

## What this does not do

It does not create or import a campaign. A campaign arrives either from its own
plugin (`/plugin install purewater@fourth-wall-gaming`, which brings its own
start command) or from `create-campaign` for a world of your own.
