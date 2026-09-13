# Compound beat triggers, and the story acting over the arc

**Status:** design, approved in conversation 2026-09-13
**Repo:** mythras-gm · affects `mythras_engine.py`, `mythras_gm.py`, `schema.tql`
**Campaign side:** the arc document format in `purewater-campaign-v2`

## The problem

A beat fires on one of two things: the world clock reaching its `time_index`,
or the agenda behind it filling a progress clock. That makes the living world a
**timetable**. Events happen because a number went up, not because the story
arrived somewhere — so the antagonist's moves land on a schedule the party
cannot influence, and the party's work does not visibly cause anything.

Two further defects follow from the same root:

- **Nothing checks that a beat still makes sense.** `due_beats` tests the
  trigger; `beat_staging` tests presence. Neither looks at the beat's cast or
  place. In the archived Gardwen run this shows up as nine cancelled beats and
  one pivot cancelled three times over — all of it cleaned up by hand, after
  the fact. A beat whose cast includes a man shot dead on night one will fire
  exactly as written.
- **A pending beat cannot be interrogated.** There is no way to ask why
  something has not happened, so the GM either forgets it exists or invents a
  reason.

## The shape of the fix

**The story document is the source. It compiles down to beats. One direction.**

```
the-story.md          the authored story: five acts, branching, unscheduled
      |
      |   an arc document per run -- one path through it, with front matter
      v
act-1.arc.md          thread: entries with `by` and `needs`
      |
      |   sync-arc: resolves slugs to ids, writes ids back, reconciles
      v
myth-beat             the run's live state
      |
      |   tick: evaluate, check coherence, stage
      v
     fires / held / waiting
```

Nothing reads upward. Beats are a projection and never the source.

### Conditions accelerate; time backstops

The central rule, and the one that keeps the doomline pressing:

> **`needs` decides when a beat can fire early. `by` decides when it fires
> anyway.**

If the party earns a beat sooner, it comes sooner. If they never do, the world
acts on its own timetable regardless. A thread can be accelerated but never
stalled, so no beat can wait forever and quietly die.

**This is backward compatible by reinterpretation rather than by addition.**
Today `when` means *fires at*. It comes to mean *fires at, at the latest* —
and for a beat with no `needs` those are identical. All 47 existing beats keep
their exact current behaviour with no migration.

### The grammar

Three condition kinds, deliberately no more:

| Kind | Waits on | Why it is in |
|---|---|---|
| `played` | another beat reaching `played` or `narrated` | ordering; makes threads instead of timetables |
| `fact` | a `myth-fact` reaching `established` | truth in the world, regardless of who knows it |
| `knows` | a `myth-knows` edge between a character and a fact | knowledge rather than truth — this is what makes an antagonist *react* |

Conditions are ANDed. There is no `or`, no nesting, and no negation: a beat
that needs alternatives is two beats, which is also clearer to read.

**Presence is deliberately excluded.** Presence already decides *staging* —
whether the party witnesses a beat. Letting it also decide *firing* would
collapse "does this happen" and "do they see it" into one thing, and the
doomline depends on those being separate.

In the arc document:

```yaml
- title: Santo comes back for what he left
  id: myth-beat-9378bbb3ab2e      # written back by sync-arc
  by: d1/night                    # backstop -- fires here regardless
  needs:                          # all of these -- fires sooner if met
    - played: the-room-afterwards
    - fact: the-knife-is-found
    - knows: {who: hanzo, fact: the-party-have-the-scroll}
```

Authored by slug or title. `sync-arc` resolves each to an id and writes the
resolved form back, so the next sync matches on identity rather than on a title
since reworded.

**Refusal rule.** An unknown condition kind, or a slug resolving to nothing, is
a hard error at `sync-arc` time that names what is valid. Never an empty-set
success, which silently means *never fires* — the failure mode where a thread
dies quietly and nobody notices for three sessions.

### Storage

One new attribute, `myth-beat-needs-json`, on `myth-beat`. No change to the
relation graph. Additive, so it applies to the live database with a `define`.

### Evaluation

`beat_is_due(beat, now_index, clock_filled)` gains a fourth argument: a
world-state snapshot — the set of played beat ids, established fact ids, and
`(knower, fact)` pairs. It stays a **pure function**, unit-testable with no
database, which matters because it is the most consequential function in the
engine and goes from two branches to four.

```python
def beat_is_due(beat, now_index, clock_filled=None, world=None) -> bool
```

`world=None` preserves today's behaviour exactly.

## The safeguard

**The engine detects; the GM decides.** Nothing is cancelled automatically.

Note who that is. The GM reads the arc document, edits it, runs `sync-arc` and
`tick`, and narrates — so these checks are a guard rail on **the GM's own
drift**, not a report to an absent human. That is why the placement below
matters more than the checks themselves.

**Hold, don't cancel.** A beat failing a coherence check is held and reported,
never cancelled.

**`held` is a finding, not a status.** The beat's `myth-beat-status` stays
`pending` and nothing is written to the database by the check. Holding is a
decision about one `tick` -- the beat is withheld from that tick's output and
re-evaluated on the next one. A status only changes when the GM acts on it. Cancelling is a judgement about the story; holding is a
judgement about coherence, and only the second is the engine's to make.

**Expect revision, not deletion.** The common case is not that a beat becomes
wrong — it is that **a beat becomes someone else's**. *Santo comes back for
what he left* does not stop being a good scene when Santo dies on night one; it
becomes *Blau comes back for what he left*, and is colder and worse for the
party. The house still wants its property back. Circumstances changed the hand
on it, not the pressure behind it. The system already has the vocabulary for
this: `revise-beat` ("bend a planned beat to match what play has made true")
and a `rewritten` status distinct from `cancelled`. Held beats are presented as
a **revision prompt first**.

Three doors from a held beat, in this order:

1. **Revise it** — the default and the usual answer.
2. **Let it stand** — the check was over-cautious; fire it.
3. **Cancel it** — the scene genuinely died with the man.

All three are edits to the arc document, not direct writes to beat records. The
document stays the thing that is edited; the next `sync-arc` carries it down.

### The checks

Only structural truths, so that a complaint is always real:

| Kind | Fires when |
|---|---|
| `cast-is-dead` | a pending beat's cast includes a character whose status is dead or removed |
| `cast-is-gone` | a cast member is no longer in the campaign |
| `place-is-gone` | the beat's place no longer exists |

**Explicitly not built:** any check that reads a beat's prose and judges whether
it contradicts the fact graph. It cannot be done reliably, and false alarms are
how a check gets ignored.

### Where the checks run

**`tick` is the load-bearing placement**, because the thing being guarded
against is the GM's own drift rather than a human's forgetfulness — and `tick`
is the one command run every scene. A guard that lived only in a command
someone has to remember to run would be worth very little.

- **`tick`** — pre-flight after `due_beats`, before staging. Due beats are
  **partitioned**, not filtered: `due` (fire these) and `held` (with reasons and
  the edit each implies). A held beat never appears anywhere it could be read as
  something to narrate.
- **`check-consistency`** — the same checks in bulk, between sessions, beside
  the existing `orphaned-future` and `beat-on-dead-agenda` problems.
- **`sync-arc --dry-run`** — surfaces it while the arc document is being
  authored, the only moment it is cheap to act on.

## Reporting, because the GM is the consumer

**`forecast` gains "what is this waiting on".** For each pending beat, which
conditions are met and which are not: *waiting on 2 of 3 — the knife has been
found; Hanzo does not yet know they have the scroll.* Today "why has this not
happened" is unanswerable.

**`tick` reports near-misses** — beats one condition short of firing. The data
is already computed. It tells the GM what the party is one step away from
detonating, which is how a session steers toward drama rather than away from
it, and it is the direct counter to the failure mode where the world stays
quiet because nothing happened to be scheduled.

## What is not in scope

- `unless` / auto-cancelling clauses. Divergence is an authoring event; the
  cast checks provide the reminder at the moment the beat would have fired.
- `or`, nesting, negation in the grammar.
- Presence as a trigger condition.
- Any rewrite of the 47 archived beats. They are the archived run's history.

## Testing

- `beat_is_due` gets a table of cases per condition kind, plus the three that
  matter most: no `needs` behaves exactly as today; `by` fires with conditions
  unmet; conditions met fires before `by`.
- Coherence checks get a positive and a negative case each.
- `sync-arc` gets a round-trip test: slugs in, ids written back, second sync
  reports `unchanged`.
- A refusal test per malformed condition, asserting the error names the valid
  kinds.
- The existing 157 tests must stay green, and a regression test asserts that a
  beat with no `needs` is unaffected.

## Order of work

1. `beat_is_due` + world snapshot, pure, with tests. No wiring.
2. Schema attribute + `sync-arc` authoring, resolution and write-back.
3. `tick` partition into due/held, and the coherence checks.
4. `forecast` waiting-on, and `tick` near-misses.
5. The Act I arc document for the new run.
