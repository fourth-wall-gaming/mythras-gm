---
name: mythras-scenario
description: Propose, prepare or rebuild a playable adventure with active antagonists, credible danger, cast knowledge, three-act development and concrete situations, then persist it in the current game's save.
---

# Prepare a scenario

`$GM` is the engine directory named by the session-start ready line; see the
`mythras-gm` skill for the fallback. Read `$GM/SCENARIO.md` before deep
preparation. Use `$GM/BRAINSTORMING.md` when generating proposals and
`$GM/CONSEQUENCES.md` for operation resolution. Player instructions take
precedence. This method is portable; use the current game's actual mechanics
and persistence model. For Mythras use the GM CLI and TypeDB.

1. **Load the real starting state.** Read context, arc, agendas, beats and the
   PC sheet, plus `list-adventures` (the saga line and what has been played).
   If `clocks_ahead` is present, run `fixed-history` over the dates you plan to
   use. Preserve established history and earned victories. Review existing
   cast before inventing; a new PC need not receive an unrelated side plot.
2. **Select a premise.** Generate and present diverse pitches when requested;
   keep unchosen proposals outside live canon. If already selected, retain it.
   Record each pitch with `add-adventure` and mark the choice `chosen`. No
   saga line yet? Agree one sentence with the player and `set-saga`.
3. **Briefly interview the player.** Establish the desired mix of magic, combat,
   intrigue, exploration and mystery, plus tone and danger where unclear.
   Reuse answers already given. Do this before deeper scenario preparation.
4. **Build the conflict.** Name the PC's objective and relationships, a worthy
   antagonist, what they want and why, the concrete stake someone would kill
   for if pushed, their violence threshold, finite assets and next operation.
   For an agreed nonlethal genre, use a correspondingly serious commitment.
   Do not require a sympathetic villain, two villains, or cancellation of the
   PC's best ability. Use `$GM/CAST.md` for NPC portrayal; consequential new
   people can have agendas immediately.
5. **Build cast, knowledge and evidence.** Record each actor's intention,
   activity, capabilities, dependencies and limits, plus what they know,
   suspect and misunderstand. Give crucial discoveries independent routes.
6. **Develop three acts and playable situations.** Prepare an arrival/current
   position, commission and authority limits, base or landing, contact, first
   lead and first meaningful action. Develop changing objectives, revelations,
   opposition and decisive opportunities. Write encounter/mission cards with
   spaces, prerequisites, warning, counterplay, mechanics and outcome ranges.
   Fixed sequence counts, guaranteed reversals and inevitable losses are not
   requirements. Early victories can resolve the adventure.
7. **Persist and verify.** Use actual character, location, fact, knowledge,
   agenda, beat and arc commands. Planned outcomes remain not-yet-true; do not
   establish intended future harm or grant knowledge of it. Advance agendas
   only for achieved steps and resolve uncertain attempts with actual rules.
   Read the saved state back and run the readiness check in `SCENARIO.md`.
   `update-adventure --status prepared --arc-file ... --plan LORE_IDS`, then
   `--status active` when it is ready.
8. **Open or resume play.** Run the first playable situation with spoilers
   preserved. Provide a full GM walkthrough when requested. During OOC design
   review hold play and time, then incorporate feedback in documents and the
   live model before resuming. After play reconcile actual outcomes and retire
   operations made impossible by victory, surrender or lost resources.
9. **Conclude.** When the adventure's question is answered,
   `update-adventure --status concluded --outcome ...`. Then downtime and the
   next pitch, never an unplanned extension.

Keep the scenario prose in the campaign workspace and the live structure in
the save. A successful database write is not sufficient evidence of readiness.
