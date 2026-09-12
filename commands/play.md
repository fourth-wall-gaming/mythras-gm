---
description: Start or resume a session at the table — loads the conduct rules, the save file, and the world clock, then recaps in voice and stops.
---

Run the startup ritual in this order and do not skip a step. The point of the
ritual is that the first beat of a session is the one most likely to be in the
wrong voice, because the wrong voice feels like competence.

1. **Read `${CLAUDE_PLUGIN_ROOT}/skills/mythras-gm/TABLE.md`, then
   `${CLAUDE_PLUGIN_ROOT}/skills/mythras-gm/styles/gamesmaster.md`.** Both, in
   full, before narrating one line. About 1.2k tokens once.

2. **`list-campaigns`** — find the campaign. If the id the user expects is not
   in the list, **STOP**. Do not import anything; importing a package next to a
   live save forks it.

3. **`get-context --campaign <id> --compact`** — the save file. Scene, PC combat
   cards, NPCs, factions, recent events.

4. **`tick --campaign <id> --to "<time key>"`** if the clock has moved. Watches
   are `dawn / day / dusk / night`. Roll every beat that comes due, including
   offscreen ones — a beat is an attempt, not a script.

5. **Refresh Luck** to maximum for every PC (it replenishes per session, not per
   night) and **`log-event --type session-start`**.

6. **Recap in two to four sentences, in voice**, and then **stop**. Do not open
   with a question, a menu, or a summary of the rules. End the recap on the
   situation the player is standing in, and hand them the floor.

Before any NPC speaks for the first time in a scene, `brief --id <npc>`. If it
returns no notes, that NPC gets one line of business and no dialogue until you
write them.
