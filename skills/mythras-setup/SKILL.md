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

## The person in front of you is here to play

They are not an engineer and should not have to become one to start a game.
Three rules for everything below:

- **Say what is wrong in the words they'd use.** "The game can't open its save
  file yet" — not "the SessionStart hook is untrusted" or "init-db returned a
  non-zero verdict".
- **Do the part you can do.** You can read and edit their config file; they
  should not be handed a TOML stanza and a path. **Offer to make the change
  yourself**, say what it does in one line, and do it when they agree.
- **Never improvise a game instead.** If the save cannot be opened, say so
  plainly and stop. Do not narrate, do not roll, and do not tell them anything
  was saved.

### On Codex, check this before anything else

Codex will not run a plugin's startup check until the user approves it. So on a
fresh install the check has not run at all — and it could not warn them,
because it is the thing that did not run. This looks exactly like a broken
database and is not one.

Say: *"Codex hasn't been given permission to run Mythras's startup step yet.
Open `/plugins`, find Mythras, and approve it — then start a new session."*
That is a click in a menu, so describe it as one.

### If it ran and still failed, it is usually one of two permissions

The game keeps its save outside your working folder and downloads a small
database server once. A sandboxed Codex blocks both. Both are fixed by the same
file, `~/.codex/config.toml`:

```toml
[sandbox_workspace_write]
network_access = true
writable_roots = ["~/.claude/mythras-gm"]
```

**Offer to add that for them** — read the file, merge rather than overwrite it,
and tell them it lets the game save and fetch its database. Then say they need
to **restart** Codex or start a new session for it to take effect, because a
config change does not reach a running session.

`scripts/verify-install.sh` in this plugin runs all of these checks at once and
names the remedy for each. Run it when you want the whole picture before
saying anything.

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
