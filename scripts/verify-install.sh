#!/usr/bin/env bash
#
# mythras-gm install check.
#
# Run this on a machine where the game will not start. It answers one question
# -- can this machine run the game, and if not, what do you do about it -- and
# it answers it in words somebody who is here to play can act on.
#
# Two deliberate constraints:
#
#   1. It NEVER changes anything. No installs, no downloads, no config edits,
#      no database writes. Somebody running a diagnostic on a machine they are
#      unsure about should not have to wonder what it did.
#
#   2. It names a REMEDY for every failure, and the remedy is an action, not a
#      concept. "Approve the startup check in /plugins" is an action. "The
#      SessionStart hook is untrusted" is a concept, and a concept is no use to
#      the person who has to fix it.
#
# Usage:  bash verify-install.sh
# Exit:   0 if nothing blocks play, 1 otherwise.

set -uo pipefail
unset VIRTUAL_ENV

GM_REL="skills/mythras-gm/mythras_gm.py"
BLOCKING=0
declare -a REMEDIES=()

row() { printf '  %-18s %-6s %s\n' "$1" "$2" "${3:-}"; }

fail() {
  row "$1" "FAIL" "$2"
  BLOCKING=$((BLOCKING + 1))
  REMEDIES+=("$3")
}

echo
echo "mythras-gm install check"
echo "========================"
echo

# --- host ------------------------------------------------------------------
# Which agent is installed here decides where its plugins live, and every path
# below follows from it.

HOST="unknown"
PLUGIN_TREE=""
if [ -d "${HOME}/.codex/plugins" ]; then
  HOST="Codex"; PLUGIN_TREE="${HOME}/.codex/plugins"
fi
if [ -d "${HOME}/.claude/plugins" ]; then
  if [ -n "$PLUGIN_TREE" ]; then
    HOST="Codex and Claude Code"; PLUGIN_TREE="${HOME}/.codex/plugins and ${HOME}/.claude/plugins"
  else
    HOST="Claude Code"; PLUGIN_TREE="${HOME}/.claude/plugins"
  fi
fi
row "host" "--" "${HOST}${PLUGIN_TREE:+ (plugins in ${PLUGIN_TREE})}"

# --- engine ----------------------------------------------------------------
# Where the game's own code is. Looked for in the order we trust the answer,
# and deliberately across BOTH hosts' trees: the same plugin is installed to
# ~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/ under Codex and to
# ~/.claude/plugins/... under Claude Code, and a machine can have both.

find_engine() {
  if [ -n "${MYTHRAS_GM_ROOT:-}" ] && [ -f "${MYTHRAS_GM_ROOT}/${GM_REL}" ]; then
    printf '%s' "${MYTHRAS_GM_ROOT}"; return 0
  fi
  # The breadcrumb the engine drops when it first starts, host-neutral location
  # first. Each is CHECKED before it is trusted: a plugin upgrade can leave a
  # pointer naming a directory that no longer holds the CLI, and reporting that
  # path as the engine sends somebody to debug the wrong directory. An empty or
  # whitespace-only file (an interrupted write) must read as absent, not as "/".
  local pointer p
  for pointer in "${HOME:-}/.mythras-gm/engine-root" \
                 "${HOME:-}/.claude/mythras-gm/engine-root"; do
    [ -f "$pointer" ] || continue
    p=$(head -1 "$pointer" 2>/dev/null | tr -d '[:space:]')
    [ -n "$p" ] && [ -f "${p}/${GM_REL}" ] && { printf '%s' "$p"; return 0; }
  done
  # This script ships inside the plugin, so its own location is a strong hint.
  local here; here=$(cd "$(dirname "${BASH_SOURCE[0]:-/nonexistent}")/.." 2>/dev/null && pwd)
  [ -n "$here" ] && [ -f "${here}/${GM_REL}" ] && { printf '%s' "$here"; return 0; }
  local tree hit
  for tree in "${HOME}/.codex/plugins" "${HOME}/.claude/plugins"; do
    [ -d "$tree" ] || continue
    hit=$(find "$tree" -maxdepth 7 -path "*/${GM_REL}" 2>/dev/null | sort -V | tail -1)
    [ -n "$hit" ] && { printf '%s' "${hit%/${GM_REL}}"; return 0; }
  done
  [ -f "${HOME}/mythras-gm/${GM_REL}" ] && { printf '%s' "${HOME}/mythras-gm"; return 0; }
  return 1
}

if GM_ROOT=$(find_engine); then
  row "engine" "ok" "$GM_ROOT"
  GM_SKILL="${GM_ROOT}/skills/mythras-gm"
else
  fail "engine" "not found on this machine" \
    "The game's code is not installed. In your agent, open /plugins, add the marketplace https://github.com/fourth-wall-gaming/mythras-gm.git, install mythras-gm, then START A NEW SESSION -- a plugin's skills only appear in a session opened after it was installed."
  GM_SKILL=""
fi

# --- uv --------------------------------------------------------------------

if command -v uv >/dev/null 2>&1; then
  row "uv" "ok" "$(uv --version 2>/dev/null | head -1)"
else
  fail "uv" "not installed" \
    "Install uv, which is what runs the game's code: https://docs.astral.sh/uv/ -- then start a new session."
fi

# --- can anything be written where the save goes ---------------------------
# Under a sandboxed agent this is the quiet one: the game is installed, the
# code runs, and the first write outside the working directory is refused.

SAVE_HOME="${MYTHRAS_TYPEDB_HOME:-${HOME}/.claude/mythras-gm/typedb}"
PROBE_DIR=$(dirname "$SAVE_HOME")
if mkdir -p "$PROBE_DIR" 2>/dev/null && touch "${PROBE_DIR}/.write-probe" 2>/dev/null; then
  rm -f "${PROBE_DIR}/.write-probe"
  row "writable" "ok" "$SAVE_HOME"
else
  fail "writable" "cannot write to $PROBE_DIR" \
    "Your agent is not allowed to write there, so the game cannot keep a save. On Codex, add this to ~/.codex/config.toml and restart:

    [sandbox_workspace_write]
    network_access = true
    writable_roots = [\"${PROBE_DIR}\"]

Ask your agent to make that change for you if you would rather not edit the file yourself."
fi

# --- network ---------------------------------------------------------------
# Only needed once, for the first-run download of the database server (~25MB).
# If the server is already downloaded this is advisory, not blocking.

CDN="https://repo.typedb.com"
if command -v curl >/dev/null 2>&1; then
  CODE=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$CDN" 2>/dev/null || echo 000)
  if [ "$CODE" != "000" ]; then
    row "network" "ok" "reached ${CDN} (${CODE})"
  elif [ -d "$SAVE_HOME" ] && find "$SAVE_HOME" -name "typedb_server_bin" -print -quit 2>/dev/null | grep -q .; then
    row "network" "--" "no outbound network, but the server is already downloaded"
  else
    fail "network" "cannot reach ${CDN}" \
      "The game needs one ~25MB download the first time it runs, and this machine cannot reach the internet from inside the agent. On Codex, set network_access = true under [sandbox_workspace_write] in ~/.codex/config.toml and restart. Your agent can make that change for you."
  fi
else
  row "network" "--" "curl not present; skipped"
fi

# --- database --------------------------------------------------------------
# The engine's own doctor knows far more than this script should duplicate, so
# ask it and report its verdict.

DB_OK=0
if [ -n "$GM_SKILL" ] && command -v uv >/dev/null 2>&1; then
  DOC=$(uv run -q --project "$GM_SKILL" python "${GM_SKILL}/mythras_gm.py" doctor 2>&1)
  VERDICT=$(printf '%s' "$DOC" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("verdict",""))' 2>/dev/null || true)
  if printf '%s' "$DOC" | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("ok") else 1)' 2>/dev/null; then
    row "database" "ok" "${VERDICT:-reachable}"
    DB_OK=1
  else
    # The commonest cause on a fresh Codex install is not a database fault at
    # all: Codex does not trust a plugin's hooks until you review them, so the
    # startup check that would have brought the database up never ran -- and
    # could not warn you, because it is the thing that did not run.
    HINT="Open /plugins in Codex, find Mythras, and approve its startup check -- Codex will not run a plugin's startup check until you say yes to it. Then start a new session. If you have already approved it, run the game's own setup help and read out any failed check."
    fail "database" "not reachable${VERDICT:+ -- $VERDICT}" "$HINT"
  fi
else
  fail "database" "not checked (engine or uv missing)" \
    "Fix the items above first, then run this check again."
fi

# --- a campaign plugin's view of the engine --------------------------------
# A campaign (Purewater, Veilwrack) is a separate plugin that has to FIND the
# engine, because a plugin cannot be told where a sibling lives. Worth checking
# only if one is installed.

CAMPAIGN=""
for tree in "${HOME}/.codex/plugins" "${HOME}/.claude/plugins"; do
  [ -d "$tree" ] || continue
  hit=$(find "$tree" -maxdepth 7 -name "engine.sh" -path "*/scripts/*" 2>/dev/null | head -1)
  [ -n "$hit" ] && { CAMPAIGN="$hit"; break; }
done
if [ -n "$CAMPAIGN" ]; then
  if ( set +u; . "$CAMPAIGN" >/dev/null 2>&1; [ -n "${GM_ROOT:-}" ] ); then
    row "campaign" "ok" "its engine lookup works"
  else
    fail "campaign" "the campaign cannot find the engine" \
      "The campaign is installed but cannot see the game's code. Tell your agent to set MYTHRAS_GM_ROOT=${GM_ROOT:-<the engine path above>} in your environment, and report this as a bug."
  fi
fi

# --- verdict ---------------------------------------------------------------

echo
if [ "$BLOCKING" -eq 0 ]; then
  echo "Nothing is blocking play. Ask to play and the game should come up."
  [ "$DB_OK" -eq 1 ] || echo "(The database check did not confirm; re-run after a new session.)"
  echo
  exit 0
fi

echo "${BLOCKING} thing(s) to fix, in order:"
echo
i=1
for r in "${REMEDIES[@]}"; do
  printf '%d. %s\n\n' "$i" "$r"
  i=$((i + 1))
done
echo "Nothing was changed by this check."
echo
exit 1
