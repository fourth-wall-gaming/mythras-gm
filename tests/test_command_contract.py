"""Contract tests over the whole command table.

These run without a database and without a server, and they hold for EVERY
subcommand rather than for the handful somebody remembered to test. The engine
has 88 subcommands; before this file, 52 of them were never named in any test,
including `roll-skill`, `set-scene`, `apply-damage` and `import-campaign`.

Every check here exists because its absence let a real bug ship:

- `update-campaign` crashed on every invocation for weeks, because three flags
  were appended to build_parser after a bare `sub.add_parser("list-campaigns")`
  and bound to whatever `s` still pointed at (retire-canon).
- `get-campaign` could not read back the arc that `update-campaign` had just
  written, so a loaded arc was indistinguishable from a missing one.

Both are mechanical faults in the command table, and both are the kind that a
per-command happy-path test would have missed and a table-wide invariant
catches.
"""
import inspect
import re

import pytest

import mythras_gm as gm


def _subparsers():
    parser = gm.build_parser()
    action = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
    return action.choices


SUBCOMMANDS = sorted(_subparsers())

# Commands that deliberately have no cmd_* handler, with the reason.
NO_HANDLER = {}


def handler_for(cmd):
    return getattr(gm, "cmd_" + cmd.replace("-", "_"), None)


def test_there_are_subcommands_at_all():
    """If build_parser changes shape, every test below would pass vacuously."""
    assert len(SUBCOMMANDS) > 50, f"only found {len(SUBCOMMANDS)} subcommands"


@pytest.mark.parametrize("cmd", SUBCOMMANDS)
def test_every_subcommand_has_a_handler(cmd):
    """Dispatch is `globals()["cmd_" + name.replace("-","_")]`. A subcommand with
    no handler parses fine and then fails at the dispatch line, which reads to a
    user as the command not existing."""
    if cmd in NO_HANDLER:
        pytest.skip(NO_HANDLER[cmd])
    assert handler_for(cmd) is not None, (
        f"`{cmd}` parses but has no cmd_{cmd.replace('-', '_')} to dispatch to"
    )


def test_every_handler_is_reachable_as_a_subcommand():
    """The other direction: a cmd_* function with no subcommand is dead code
    that looks live, and gets maintained for nothing."""
    handlers = {n[len("cmd_"):] for n in dir(gm)
                if n.startswith("cmd_") and callable(getattr(gm, n))}
    reachable = {c.replace("-", "_") for c in SUBCOMMANDS}
    orphans = sorted(handlers - reachable)
    assert not orphans, f"handlers with no subcommand: {orphans}"


@pytest.mark.parametrize("cmd", SUBCOMMANDS)
def test_every_subcommand_renders_help(cmd):
    """`--help` is the only documentation most flags ever get, and argparse
    raises while formatting a malformed help string rather than at definition."""
    sp = _subparsers()[cmd]
    text = sp.format_help()
    assert text.strip(), f"`{cmd} --help` renders empty"
    assert "usage:" in text


@pytest.mark.parametrize("cmd", SUBCOMMANDS)
def test_every_handler_reads_only_flags_its_own_subparser_defines(cmd):
    """The update-campaign bug, generalised. A handler reading args.X where X is
    not a dest on its own subparser raises AttributeError for every caller.

    getattr(args, "x", default) is deliberate and safe, so those are stripped
    before scanning.
    """
    fn = handler_for(cmd)
    if fn is None:
        pytest.skip("no handler")
    src = re.sub(r'getattr\(\s*args\s*,[^)]*\)', '', inspect.getsource(fn))
    read = set(re.findall(r'\bargs\.([a-zA-Z_][a-zA-Z0-9_]*)', src))
    dests = {a.dest for a in _subparsers()[cmd]._actions} | {"command", "func"}
    missing = sorted(read - dests)
    assert not missing, f"`{cmd}` reads flags it does not define: {missing}"


@pytest.mark.parametrize("cmd", SUBCOMMANDS)
def test_required_flags_are_really_required(cmd):
    """A flag marked required must actually stop a bare invocation.

    Adding an alias un-requires the canonical flag (RELAXED_REQUIRED records
    which), and those are re-enforced later in dispatch rather than by argparse,
    so they are exempt here.
    """
    sp = _subparsers()[cmd]
    required = {a.dest for a in sp._actions if getattr(a, "required", False)}
    relaxed = gm.RELAXED_REQUIRED.get(cmd, set())
    if not (required - set(relaxed)):
        pytest.skip("no unconditionally required flags")
    with pytest.raises(SystemExit):
        gm.build_parser().parse_args([cmd])


@pytest.mark.parametrize("cmd", SUBCOMMANDS)
def test_choice_flags_reject_a_value_outside_their_choices(cmd):
    """A choices= list that is not enforced lets a typo reach a TypeQL insert,
    where it becomes a stored value nothing can read back."""
    sp = _subparsers()[cmd]
    choicey = [a for a in sp._actions if a.choices and a.option_strings]
    if not choicey:
        pytest.skip("no choice flags")
    a = choicey[0]
    with pytest.raises(SystemExit):
        gm.build_parser().parse_args([cmd, a.option_strings[0], "definitely-not-a-choice"])


@pytest.mark.parametrize("cmd", SUBCOMMANDS)
def test_campaign_scoped_commands_say_how_campaign_defaults(cmd):
    """--campaign resolves from $MYTHRAS_CAMPAIGN or the only campaign in the
    database. A command that takes it without saying so reads as mandatory, and
    the GM passes an id into every call for no reason."""
    sp = _subparsers()[cmd]
    camp = [a for a in sp._actions if a.dest == "campaign" and a.option_strings]
    if not camp or camp[0].required:
        pytest.skip("no optional --campaign")
    # An alias un-requires its canonical flag at build time and the requirement
    # is re-enforced in dispatch, so a relaxed flag is required, not optional.
    if "campaign" in gm.RELAXED_REQUIRED.get(cmd, set()):
        pytest.skip("required, relaxed for alias handling")
    assert camp[0].help, f"`{cmd} --campaign` is optional and undocumented"


def test_help_that_promises_a_default_is_telling_the_truth():
    """`--campaign` help says it defaults to $MYTHRAS_CAMPAIGN or the only
    campaign in the database. That promise is kept by the NEEDS_CAMPAIGN loop at
    the end of build_parser, which un-requires the flag.

    A command carrying that help string while still requiring the flag tells the
    GM they can omit it and then refuses the call. `timeline` and `forecast`
    were the two: every other campaign-scoped command defaults, and those two
    errored with 'the following arguments are required: --campaign'.
    """
    liars = []
    for cmd, sp in sorted(_subparsers().items()):
        camp = [a for a in sp._actions
                if a.dest == "campaign" and a.option_strings]
        if not camp:
            continue
        promises = camp[0].help and "defaults to" in camp[0].help
        if promises and camp[0].required:
            liars.append(cmd)
    assert not liars, (
        "these say --campaign defaults and then require it: " + repr(liars))


def test_every_cli_command_the_rules_graph_names_actually_exists():
    """The rules are read at the table and tell the GM what to run.

    `skill/experience` told GMs to use `award-experience` and `improve-skill`
    for as long as it had existed, and neither command was ever written. The
    gap surfaced mid-session with three experience rolls owed, and the rolls
    had to be done by hand in a shell loop.

    Nothing else caught it: the other contract tests check the parser against
    the handlers, which agreed with each other perfectly. The rules text is a
    third party that can disagree with both.
    """
    import pathlib
    import re as _re

    rules_dir = pathlib.Path(gm.__file__).resolve().parent / "rules"
    if not rules_dir.is_dir():
        pytest.skip(f"no rules directory at {rules_dir}")

    known = set(SUBCOMMANDS)
    # Words that look like commands in prose but are not, plus the two shell
    # verbs the rules legitimately mention.
    ignore = {"mythras-gm", "uv", "python", "gm"}

    offenders = {}
    for path in sorted(rules_dir.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        # Backticked hyphenated lower-case words: how the rules name a command.
        for token in _re.findall(r"`([a-z][a-z-]{3,})`", text):
            if token in known or token in ignore or "-" not in token:
                continue
            # Only flag it when the surrounding sentence is telling somebody to
            # run something, rather than naming a game concept like
            # `special-effect`.
            for line in text.splitlines():
                if f"`{token}`" not in line:
                    continue
                if _re.search(r"\b(CLI|command|run|use|call)\b", line, _re.I):
                    offenders.setdefault(token, set()).add(
                        str(path.relative_to(rules_dir)))

    assert not offenders, (
        "the rules graph tells the GM to run commands that do not exist: "
        + repr({k: sorted(v) for k, v in offenders.items()}))
