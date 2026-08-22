"""Pure helpers for character scores.

Deliberately free of TypeDB imports so the logic is unit-testable without a
database. See CHARACTER-SCORES.md for what a score is and why.
"""

import copy

SCORE_SLOTS = (
    "want", "ought", "driver", "stated_reason", "focus", "status",
    "tactics", "when_lied_to", "blind_spot", "rhythm", "physical",
    "secret", "observed",
)

WHEN_LIED_TO_VALUES = ("catch", "miss", "half")
FOCUS_VALUES = ("promotion", "prevention")
MIN_TACTICS = 3


def deep_merge(current, incoming):
    """Merge `incoming` into `current` without mutating either.

    Dicts merge recursively; lists EXTEND (so appending one observation does
    not discard the log); everything else overwrites. Use --replace-json when
    you genuinely mean to replace.
    """
    if not isinstance(current, dict):
        return copy.deepcopy(incoming)
    out = copy.deepcopy(current)
    for key, value in (incoming or {}).items():
        existing = out.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            out[key] = deep_merge(existing, value)
        elif isinstance(existing, list) and isinstance(value, list):
            out[key] = existing + copy.deepcopy(value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def validate_score(score):
    """Return warnings about a score. Never raises; never blocks a write."""
    warnings = []
    if not isinstance(score, dict):
        return ["score is not an object"]

    missing = [s for s in SCORE_SLOTS if s not in score]
    if missing:
        warnings.append(f"missing slots: {', '.join(missing)}")

    driver = score.get("driver")
    stated = score.get("stated_reason")
    if driver and stated and str(driver).strip() == str(stated).strip():
        warnings.append(
            "stated_reason matches driver -- the character is then a "
            "self-analyst, which is the failure this instrument exists to stop")

    wlt = score.get("when_lied_to")
    if wlt is not None and wlt not in WHEN_LIED_TO_VALUES:
        warnings.append(
            f"when_lied_to '{wlt}' not one of {', '.join(WHEN_LIED_TO_VALUES)}")

    focus = score.get("focus")
    if focus is not None and focus not in FOCUS_VALUES:
        warnings.append(f"focus '{focus}' not one of {', '.join(FOCUS_VALUES)}")

    tactics = score.get("tactics")
    if tactics is not None:
        if not isinstance(tactics, list):
            warnings.append("tactics must be an ordered list")
        elif len(tactics) < MIN_TACTICS:
            warnings.append(
                f"tactics ladder has {len(tactics)} rung(s); want at least "
                f"{MIN_TACTICS}, ending in a threat response")
    return warnings
