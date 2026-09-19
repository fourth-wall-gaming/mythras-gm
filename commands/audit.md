---
description: Audit a session transcript against the conduct rules — turn length, NPC speech length, banned constructions.
argument-hint: [path to transcript]
---

Run the voice audit over `$1` (a transcript in
`===== ASSISTANT [timestamp] =====` form):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/voice_audit.py" "$1"
```

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
