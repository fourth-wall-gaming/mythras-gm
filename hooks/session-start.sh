#!/usr/bin/env bash
#
# mythras-gm preflight. Runs once per session start.
#
# This used to be a single unreadable line inside hooks.json that located
# another plugin's Python file with a `find` glob, and printed a warning and
# exited 0 on every failure path. The glob missed on at least one machine, so
# the schema never loaded, and because every documented CLI call pipes stderr to
# /dev/null the model saw empty results rather than errors -- and went on
# narrating with nothing persisting. That is the bug this file exists to not
# have.
#
# Two rules here, both deliberate:
#
#   1. It NEVER exits non-zero. A user who has this plugin enabled and opens
#      Claude in an unrelated directory with Docker switched off should not have
#      their session blocked for a game they are not playing. On SessionStart,
#      hook stdout reaches the model, so an unambiguous refusal message gets the
#      behaviour we want without seizing the session.
#
#   2. It NEVER pulls a container image. A several-hundred-megabyte download
#      inside a session-start hook is indistinguishable from a hang. The slow
#      path is /mythras-gm:setup, and init-db says so when it is needed.

set -uo pipefail
unset VIRTUAL_ENV

export TYPEDB_PORT="${TYPEDB_PORT:-1730}"
export TYPEDB_DATABASE="${TYPEDB_DATABASE:-mythras}"

GM="${CLAUDE_PLUGIN_ROOT}/skills/mythras-gm"

if [ ! -f "$GM/mythras_gm.py" ]; then
  echo "mythras-gm: the plugin is installed but $GM/mythras_gm.py is missing, so the game cannot run at all. Reinstall the plugin."
  exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "mythras-gm: PREFLIGHT FAILED -- uv is not installed, so the CLI cannot run. Install it (https://docs.astral.sh/uv/) and start a new session. Until then there is no dice tower and no save file: do not narrate, do not roll, and do not claim anything persisted."
  exit 0
fi

if OUT=$(uv run -q --project "$GM" python "$GM/mythras_gm.py" init-db 2>&1); then
  DB=$(printf '%s' "$OUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("database","?"))' 2>/dev/null || echo "$TYPEDB_DATABASE")
  echo "mythras-gm ready: database ${DB} on ${TYPEDB_PORT}. State persists; roll everything through the CLI."
  exit 0
fi

# init-db reports its own remedy in JSON. Surface it verbatim, then be explicit
# about what the model must not do, because this is the exact situation in which
# it would otherwise cheerfully improvise a game that never gets saved.
REMEDY=$(printf '%s' "$OUT" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("remedy") or d.get("error") or "")' 2>/dev/null || true)
[ -z "$REMEDY" ] && REMEDY="$OUT"

cat <<MSG
mythras-gm: PREFLIGHT FAILED. The save file and the dice tower are both unavailable.

  ${REMEDY}

Until that is fixed: do not narrate a scene, do not roll dice, do not create or
update characters, and do not tell the user that anything has been saved. Say
what is wrong and offer to run /mythras-gm:setup. Diagnose with:
  uv run -q --project "$GM" python "$GM/mythras_gm.py" doctor
MSG
exit 0
