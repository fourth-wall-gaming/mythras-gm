#!/usr/bin/env python
"""Standalone session provisioner for mythras-gm -- no Alhazen required.

Run at SessionStart (see hooks/hooks.json). Idempotent:

  1. Ensure a TypeDB server is reachable at $TYPEDB_HOST:$TYPEDB_PORT. If one is
     already up (e.g. an existing TypeDB on 1729) it is ADOPTED as-is. Otherwise
     start -- creating it the first time -- our own container
     $MYTHRAS_TYPEDB_CONTAINER (default: mythras-typedb) with its own data
     volume, and wait for it. No other tool or plugin is required.
  2. Create the $TYPEDB_DATABASE database (default: mythras) if absent, loading
     base-schema.tql then schema.tql.
  3. Load the rules graph (mythras_gm.py load-rules), which is itself idempotent.

Prints a short status line and always exits 0 -- a provisioning hiccup should
warn, not abort the session.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HOST = os.getenv("TYPEDB_HOST", "localhost")
PORT = os.getenv("TYPEDB_PORT", "1729")
DB = os.getenv("TYPEDB_DATABASE", "mythras")
CONTAINER = os.getenv("MYTHRAS_TYPEDB_CONTAINER", "mythras-typedb")
IMAGE = os.getenv("MYTHRAS_TYPEDB_IMAGE", "typedb/typedb:3.8.0")


def _driver():
    from typedb.driver import TypeDB, Credentials, DriverOptions
    return TypeDB.driver(
        f"{HOST}:{PORT}",
        Credentials(os.getenv("TYPEDB_USERNAME", "admin"),
                    os.getenv("TYPEDB_PASSWORD", "password")),
        DriverOptions(is_tls_enabled=False))


def _connect(retries=1):
    last = None
    for _ in range(retries):
        try:
            return _driver()
        except Exception as exc:      # not up yet
            last = exc
            time.sleep(1)
    raise last


def _container_exists():
    r = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name=^{CONTAINER}$",
         "--format", "{{.Names}}"],
        capture_output=True, text=True)
    return CONTAINER in r.stdout.split()


def ensure_server():
    # Already reachable? Adopt it. On a machine that already runs a TypeDB
    # (e.g. an existing Alhazen container on 1729) we use that server and leave
    # any existing 'mythras' database completely untouched.
    try:
        _connect().close()
        return True
    except Exception:
        pass
    # Nothing reachable: bring up our OWN container, creating it the first time
    # with its own named data volume -- no other tool or plugin required.
    if _container_exists():
        subprocess.run(["docker", "start", CONTAINER],
                       capture_output=True, text=True)
    else:
        subprocess.run(
            ["docker", "run", "-d", "--name", CONTAINER,
             "-p", f"{PORT}:1729",
             "-v", f"{CONTAINER}-data:/var/lib/typedb/data",
             IMAGE],
            capture_output=True, text=True)
    for _ in range(60):
        try:
            _connect().close()
            return True
        except Exception:
            time.sleep(1)
    return False


def ensure_database(driver):
    from typedb.driver import TransactionType
    if driver.databases.contains(DB):
        return "exists"
    driver.databases.create(DB)
    with driver.transaction(DB, TransactionType.SCHEMA) as tx:
        for fname in ("base-schema.tql", "schema.tql"):
            with open(os.path.join(HERE, fname), encoding="utf-8") as fh:
                tx.query(fh.read()).resolve()
        tx.commit()
    return "created"


def main():
    if not ensure_server():
        print(f"mythras-gm: TypeDB not reachable at {HOST}:{PORT} and could not "
              f"start container '{CONTAINER}'. Start TypeDB, then reopen the session.")
        sys.exit(0)
    try:
        driver = _connect()
        state = ensure_database(driver)
        driver.close()
    except Exception as exc:
        print(f"mythras-gm: database provisioning skipped ({exc})")
        sys.exit(0)
    # load rules (idempotent); quiet on success
    subprocess.run(
        ["uv", "run", "--project", HERE, "python",
         os.path.join(HERE, "mythras_gm.py"), "load-rules"],
        capture_output=True, text=True)
    print(f"mythras-gm: database '{DB}' {state}; rules loaded.")
    sys.exit(0)


if __name__ == "__main__":
    main()
