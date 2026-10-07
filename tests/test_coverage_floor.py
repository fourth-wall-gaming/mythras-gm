"""The floor, and the things that could make it meaningless.

A coverage floor protects nothing on its own. Three separate moves defeat one,
and each has a test here:

  1. Lower the number until the build goes green.
  2. Run CI without a database, so the tests carrying half the coverage skip
     and the floor is met by a suite that barely ran. Measured: 77% with a
     server, 38% without.
  3. Stop passing --cov in CI, so the floor is configured and never applied.

The number itself lives in pyproject.toml so a local run and the workflow
enforce the same one. Raising it is welcome. Lowering it means editing
MINIMUM_FLOOR below, which is deliberate rather than incidental -- and if you
are doing that to make a red build green, the regression is the thing to fix.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"

# The floor may not drop below this without a deliberate edit to this line.
MINIMUM_FLOOR = 74


def _toml():
    try:
        import tomllib
    except ModuleNotFoundError:                     # pragma: no cover
        pytest.skip("tomllib needs Python 3.11+")
    with open(PYPROJECT, "rb") as fh:
        return tomllib.load(fh)


def test_a_coverage_floor_is_configured():
    cfg = _toml()["tool"]["coverage"]["report"]
    assert "fail_under" in cfg, \
        "no fail_under in pyproject.toml; the suite runs without a floor"


def test_the_floor_has_not_been_lowered():
    floor = _toml()["tool"]["coverage"]["report"]["fail_under"]
    assert floor >= MINIMUM_FLOOR, (
        f"the coverage floor is {floor}, below the agreed {MINIMUM_FLOOR}. "
        "If coverage genuinely regressed, fix the coverage; if the drop is "
        "intended, raise MINIMUM_FLOOR in this test deliberately."
    )


def test_coverage_measures_the_engine_and_not_its_dependencies():
    run = _toml()["tool"]["coverage"]["run"]
    assert run["source"] == ["skills/mythras-gm"], run
    omitted = " ".join(run.get("omit", []))
    assert ".venv" in omitted and "site-packages" in omitted, \
        "vendored dependencies would inflate the percentage"


def test_there_is_a_ci_workflow():
    assert WORKFLOW.is_file(), \
        "no CI workflow; the floor is only enforced when somebody remembers"


def test_ci_refuses_to_run_without_a_database():
    """Without MYTHRAS_REQUIRE_DB the database tests skip silently and the
    floor can be met by a suite that did not exercise the command layer."""
    text = WORKFLOW.read_text()
    assert "MYTHRAS_REQUIRE_DB" in text, (
        "CI does not set MYTHRAS_REQUIRE_DB, so a missing TypeDB would skip "
        "64 tests and drop real coverage from 77% to 38% without failing"
    )


def test_ci_actually_starts_a_database():
    text = WORKFLOW.read_text()
    assert "typedb/typedb:" in text, "CI has no TypeDB service container"
    assert "1730" in text, "the TypeDB port is not published to the job"


def test_ci_applies_the_floor_rather_than_merely_configuring_it():
    """`pytest --cov` is what makes fail_under bite. Running plain pytest in CI
    leaves the floor configured and unenforced."""
    text = WORKFLOW.read_text()
    assert "--cov" in text, "CI runs pytest without --cov; the floor never applies"


def test_the_ci_typedb_version_matches_the_engine():
    """conftest loads schema.tql into the service container. A version skew
    shows up as a schema error that looks like a test failure."""
    import mythras_gm as gm
    m = re.search(r"typedb/typedb:([0-9.]+)", WORKFLOW.read_text())
    assert m, "could not find the TypeDB image tag in the workflow"
    assert m.group(1) == gm.TYPEDB_VERSION, (
        f"CI runs TypeDB {m.group(1)} but the engine expects "
        f"{gm.TYPEDB_VERSION}"
    )


def test_the_test_database_is_never_a_live_one():
    """The one that already bit: twenty ztest campaigns accumulated in the live
    database because a subprocess inherited the default."""
    import conftest
    assert conftest.TEST_DB not in conftest.LIVE_DATABASES
    for name in ("mythras", "alh_mythras"):
        assert name in conftest.LIVE_DATABASES, \
            f"{name} is not on the refuse-list"
