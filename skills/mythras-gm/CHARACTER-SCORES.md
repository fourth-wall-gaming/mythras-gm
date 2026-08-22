# Character Scores

A character score is a structured record of *how an NPC works* — motive, status
behaviour, and how they escalate — stored on the character in TypeDB and added
to after every scene they appear in.

## The problem it solves

Across three sessions of one campaign, six different NPCs ran the identical beat
when the players tried to work them:

| NPC | Line |
|---|---|
| Grullock | *"You're reading that."* |
| Velligan | *"You are doing me."* |
| Aurengall | *"Do not do the voice at me."* |
| Grixvell | *"You are working me. I want that said."* |
| Prill | *"That's why you're sat there and not him."* |
| Nibb | *"You're doing it again. That's twice."* |

Their diction was genuinely distinct — Grixvell's clause-numbering sounds
nothing like Velligan's inventory clipping. What was identical was structural:

> **Every one of them was perceptive, self-aware, and able to articulate their
> own motive.**

That is one temperament in six costumes, and the temperament is the GM's. Its
worst casualty was Nibb, who is *designed* as the comic foil — the goblin who
gets fooled and then hurt — and who was played as a shrewd operator three
sessions running.

## Why a voice card is not the fix

Diction, tics and sentence length are surface. Two characters with different
vocabularies still converge if they share the same relationship to their own
interiority, the same perceptiveness, and the same escalation behaviour. A
score therefore operates on **motive, status and escalation**, not voice.

## The thirteen slots

| Slot | What goes in it | Why it is there |
|---|---|---|
| `want` | Active, present tense, aimed at another person | The super-objective: what they are pursuing in every scene |
| `ought` | The duty or standard they hold themselves to. **Must conflict with `want`** | Behaviour lives in the gap between the ideal self and the ought self |
| `driver` | What actually moves them | The truth, for the GM only |
| `stated_reason` | The sincere, tidy account they would give — **and it is wrong** | People confabulate causes rather than report them (Nisbett & Wilson) |
| `focus` | `promotion` (chasing gains) or `prevention` (avoiding loss) | Predicts *how* they escalate, so the ladder is generated rather than invented |
| `status` | Map of counterpart → status played, plus what breaks it | Status is relational, not a trait: nobody is "high status", they are high status *to someone* |
| `tactics` | Ordered list. Each rung is tried and abandoned only on failure. The last rung is the threat response — fight, flight, freeze or fawn | The primary anti-sameness device |
| `when_lied_to` | `catch`, `miss`, or `half` (notices, says nothing) | Directly prevents the six-line failure above |
| `blind_spot` | Stated as an attribution asymmetry where possible | Others are judged by disposition, oneself by circumstance |
| `rhythm` | Sentence shape; what they do with a silence | Low status fills silence, high status lets it work |
| `physical` | Hands, props, habitual business | Usually the strongest single element at the table |
| `secret` | One true thing never said aloud | The actor knows; the audience does not |
| `observed` | Dated log of what the character actually did in play | See *Accretion* |

## The two rules that carry most of the value

> **1. `stated_reason` must differ from `driver`.** If they match, the character
> is a self-analyst, and the flaw returns wearing a new costume.
>
> **2. `when_lied_to` defaults to `miss`.** Perceptiveness is a scarce resource
> spent deliberately, never the house style. At most one NPC per session sees
> through the party, and never the same one twice running.

`validate_score` in `score_tools.py` warns on both, along with unknown `focus`
or `when_lied_to` values and tactics ladders shorter than three rungs. Warnings
are advisory — they are reported on write and never block it.

## Accretion, not authorship

Scores are **not** written in full up front. An NPC gets a thin score when they
first matter — `want`, `status`, one or two tactics. After each scene, append
what they actually did to `observed`.

- **Invented lines are provisional** and may be revised freely.
- **Observed lines are binding** and constrain every future scene.

A score therefore cannot drift away from the character, because it is a record
of play rather than a plan for it.

## Using it at the table

1. **Read before the scene, not during.** When an NPC is about to matter, pull
   the score first. Mid-scene is too late; you will already have defaulted.
2. **Play the ladder in order.** Start at rung one and escalate only on failure,
   including failure against a die roll. Do not jump to the bottom rung because
   it is the interesting one.
3. **Keep the perceptiveness ledger.** One `gm-note` per session recording who
   saw through the squad. If an NPC caught them last session, that NPC does not
   catch them this session.

## Storage and CLI

Scores live in `myth-extras-json` under a top-level `score` key. Write them with
`update-character --extras`, which **merges**: dicts merge recursively and lists
extend, so appending one observation cannot discard the rest of the score.

Create or extend a score:

```bash
uv run --project . python mythras_gm.py update-character --id <char> \
  --extras '{"score":{"want":"...","focus":"prevention","tactics":["...","...","..."],"when_lied_to":"miss"}}'
```

Append an observation after a scene:

```bash
uv run --project . python mythras_gm.py update-character --id <char> \
  --extras '{"score":{"observed":["s5: fooled by Gilt again, did not notice"]}}'
```

The response carries `score_warnings` when the score as it now stands is
incomplete or breaks a rule. To overwrite rather than merge — rarely what you
want — add `--replace-json`.

## A worked example: Under-Steward Nibb

```json
{"score": {
  "want": "to be told, out loud and in front of someone, that I did it correctly",
  "ought": "the paper must be handled properly, whatever it costs me",
  "driver": "terror of going back down a rung, where he was for eleven years",
  "stated_reason": "somebody has to keep the records straight or the household stops",
  "focus": "prevention",
  "status": {
    "Vorgath": "very low, appeasing; will not raise his eyes",
    "Grixvell": "low, deferential -- treats the contract as a superior",
    "the squad": "high, and he cannot hold it; collapses the moment one pushes back"
  },
  "tactics": ["appease", "over-explain", "invoke procedure", "collapse (fawn)"],
  "when_lied_to": "miss",
  "blind_spot": "reads his own failures as bad luck and everyone else's as laziness; believes he is respected when he is merely tolerated",
  "rhythm": "runs on in one long clause, then stops dead mid-sentence when contradicted",
  "physical": "writing case clutched flat against his chest like a breastplate",
  "secret": "he cannot actually read quickly, and copies things twice to be sure",
  "observed": []
}}
```

Under this score Nibb would **not** have caught Gilt a third time in the
muster-yard of session 4. That scene stands as played; the score governs from
here.
