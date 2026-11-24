"""Refresh existing seed records by key. Run with -m tools.refresh_seed [--apply]."""
import argparse
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from fmeda_tool.db.database import DatabaseService, get_project_root, get_seed_json_path


# Synthetic row IDs belong to the operational database. Match child records
# using the identifiers carried by the JSON instead.
KEYS = {
    "library_metadata": ("library_id",),
    "profiles": ("id",),
    "components": ("id",),
    "component_aliases": ("component_id", "alias", "alias_type"),
    "component_failure_rates": ("component_id", "profile_id"),
    "failure_modes": ("id",),
    "component_failure_modes": ("component_id", "failure_mode_id", "profile_id"),
    "legacy_components": ("id",),
    "legacy_failure_modes": ("legacy_component_id", "name"),
}


def records(conn, table, keys, fields):
    columns = ", ".join((*keys, *fields))
    result = {}
    for row in conn.execute(f"SELECT {columns} FROM {table}"):
        key = row[:len(keys)]
        if key in result:
            raise ValueError(f"Ambiguous {table} key {key}")
        result[key] = row[len(keys):]
    return result


def refresh(target, seed, apply=False):
    mode = "rw" if apply else "ro"
    with TemporaryDirectory(dir=target.parent) as tmp:
        staged = Path(tmp) / "seed.sqlite"
        ok, message = DatabaseService.initialize_from_seed(db_path=staged, seed_path=seed)
        if not ok:
            raise ValueError(message)
        with closing(sqlite3.connect(staged)) as source, closing(sqlite3.connect(
                target.resolve().as_uri() + "?mode=" + mode, uri=True)) as db, db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
            changed = 0
            for table, keys in KEYS.items():
                fields = [r[1] for r in source.execute(f"PRAGMA table_info({table})")
                          if r[1] not in (*keys, "id", "created_at", "updated_at", "status")]
                expected = records(source, table, keys, fields)
                current = records(db, table, keys, fields)
                if expected.keys() - current.keys():
                    raise ValueError(f"Missing or changed key in {table}: {next(iter(expected.keys() - current.keys()))}")
                for key, values in expected.items():
                    changes = [(field, old, new) for field, old, new in zip(fields, current[key], values)
                               if old != new]
                    if not changes:
                        continue
                    changed += 1
                    print(table, key, changes)
                    if apply:
                        assignments = ", ".join(f"{field}=?" for field, _, _ in changes)
                        predicate = " AND ".join(f"{field}=?" for field in keys)
                        count = db.execute(f"UPDATE {table} SET {assignments} WHERE {predicate}",
                                           (*[new for _, _, new in changes], *key)).rowcount
                        if count != 1:
                            raise ValueError(f"Unexpected update count for {table} {key}")
                if apply:
                    actual = records(db, table, keys, fields)
                    if actual.keys() != current.keys() or any(actual[k] != v for k, v in expected.items()):
                        raise ValueError(f"Verification failed for {table}")
            if db.execute("PRAGMA foreign_key_check").fetchone() or db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("Database integrity check failed")
            print(f"{changed} changed rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="commit verified changes")
    refresh(get_project_root() / "data" / "fmeda.sqlite", get_seed_json_path(), parser.parse_args().apply)
