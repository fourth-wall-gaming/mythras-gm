---
name: mythras-audit
description: Audit a Mythras session transcript against the table's conduct rules — turn length, NPC speech length, banned constructions. Use when asked to check or audit how a session read.
---

# Audit a transcript

Run the voice audit over the transcript (a file in
`===== ASSISTANT [timestamp] =====` form):

```bash
python3 "$GM/../../scripts/voice_audit.py" <transcript>
```

`$GM` is the engine directory — the session-start hook's ready line names it
absolutely; see **CLI** in the `mythras-gm` skill for the fallback. The audit
script sits at the plugin root, one level above the `skills/` tree that holds
`$GM`.

Then read the result honestly, with these caveats in mind:

- **Measure table prose only.** If the transcript mixes play with engineering
  talk, the numbers are meaningless — the ban list itself contains every banned
  phrase. Filter to the play windows first.
- **The median is not the target.** `TABLE.md` section 2.1 sets turn length by
  where the decision falls, not by a word count. What matters is the tail: a
  turn over 400 words is a lecture whatever the rule says.
- **Check the hits before believing them.** Report false positives rather than
  "fixing" prose to satisfy a regex. An audit nobody trusts gets switched off.

Report what moved against the previous session, not just the absolute numbers.
