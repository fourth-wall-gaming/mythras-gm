"""Test configuration.

**Point every TypeDB-touching test at a throwaway database, and do it here**,
because `mythras_gm` reads `TYPEDB_DATABASE` into a module-level constant at
import time. pytest loads conftest before any test module, which is the only
hook early enough to matter.

Why this exists: `test_novelist.py::test_extract_seeded_campaign` seeds a real
campaign through the real CLI in a subprocess that inherits the environment. It
therefore wrote to whatever the CLI defaulted to, and never cleaned up. Twenty
`ztest-novelist` campaigns had accumulated in the live game database before
anyone looked. A test suite must not be able to touch real data by default.
"""

import os
import sys

TEST_DB = "mythras_pytest"

# Databases the suite must never write to, whatever the environment says. The
# skill's own live DB is `mythras`; the rest are the former Alhazen split DBs
# (guarded so an inherited shell export can never redirect a run onto them) and
# the retired `alh_mythras` fallback.
LIVE_DATABASES = {"mythras", "alh_mythras", "alh_core", "alh_deep_research",
                  "alh_personal", "alh_biorodeo", "dismech", "alhazen_notebook"}

_inherited = os.environ.get("TYPEDB_DATABASE")
if _inherited in LIVE_DATABASES:
    print(f"conftest: refusing inherited TYPEDB_DATABASE={_inherited!r}; "
          f"redirecting tests to {TEST_DB!r}", file=sys.stderr)

# Force, do not default: the dangerous case is precisely a developer with the
# live database exported in their shell.
os.environ["TYPEDB_DATABASE"] = TEST_DB

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "mythras-gm"))

import pytest  # noqa: E402


def _driver():
    try:
        from typedb.driver import TypeDB, Credentials, DriverOptions
    except ImportError:
        return None
    try:
        return TypeDB.driver(
            f"{os.getenv('TYPEDB_HOST', 'localhost')}:{os.getenv('TYPEDB_PORT', '1729')}",
            Credentials(os.getenv("TYPEDB_USERNAME", "admin"),
                        os.getenv("TYPEDB_PASSWORD", "password")),
            DriverOptions(is_tls_enabled=False))
    except Exception:
        return None


@pytest.fixture(scope="session", autouse=True)
def throwaway_database():
    """Create the test database, load the schema, drop it afterwards.

    Skips silently when TypeDB is unreachable -- the bulk of the suite is pure
    logic and must keep running without a server.
    """
    d = _driver()
    if d is None:
        yield None
        return

    assert TEST_DB not in LIVE_DATABASES, "test database name collides with a live one"

    created = False
    try:
        from typedb.driver import TransactionType
        if not d.databases.contains(TEST_DB):
            d.databases.create(TEST_DB)
            created = True
        schema_path = os.path.join(os.path.dirname(__file__), "..", "skills",
                                   "mythras-gm", "schema.tql")
        base_path = os.path.join(os.path.dirname(__file__), "..", "skills",
                                 "mythras-gm", "base-schema.tql")
        with d.transaction(TEST_DB, TransactionType.SCHEMA) as tx:
            for p in (base_path, schema_path):
                if os.path.exists(p):
                    tx.query(open(p, encoding="utf-8").read()).resolve()
            tx.commit()
    except Exception as exc:      # provisioning failed; let tests skip themselves
        print(f"conftest: could not provision {TEST_DB}: {exc}", file=sys.stderr)
        yield None
        return

    yield TEST_DB

    if created:
        try:
            d.databases.get(TEST_DB).delete()
        except Exception as exc:
            print(f"conftest: could not drop {TEST_DB}: {exc}", file=sys.stderr)
