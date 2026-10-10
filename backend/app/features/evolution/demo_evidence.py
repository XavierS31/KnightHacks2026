"""Q1 evidence for C's demo slice: v1 preservation, labeled fixture analysis and Neon usage.

Read-only. It never writes the product tree or the database and never prints DATABASE_URL.
Run: python -m backend.app.features.evolution.demo_evidence [--out artifacts/evidence/c-slice.json]
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from backend.app.features.evolution.analysis import analyze_fixture_sessions
from backend.app.features.evolution.evidence import EvidenceMismatch
from backend.app.features.integration.product.freeze import implementation_hashes
from backend.app.features.integration.product.handoff import MANIFEST, ProductHandoff
from backend.app.shared.contracts import Contract, Session
from backend.app.shared.database import DatabaseUnavailable, NeonDatabase
from backend.app.shared.fixtures import EXPERIMENT, SESSIONS
from backend.app.shared.settings import Settings, get_settings

CheckStatus = Literal["pass", "fail", "not_established"]
# 001 tables and whether each has a fixture column.
CORE_TABLES = {"product_versions": True, "experiments": True, "sessions": True,
               "actions": False, "feedback": False, "jobs": True}
STREAM_MODES = ("unavailable", "live", "replay", "fixture")


class Check(Contract):
    name: str
    status: CheckStatus
    detail: str
    facts: dict[str, Any] = {}


class SliceReport(Contract):
    generated_at: datetime
    app_mode: Literal["fixture", "live"]
    checks: list[Check]


def v1_source_check(handoff: ProductHandoff, current_hashes: dict[str, str]) -> Check:
    """The frozen v1 sources must be unchanged; a patched tree is not v1."""
    facts = {"version_id": str(handoff.version.id), "label": handoff.version.label,
             "commit_sha": handoff.version.commit_sha,
             "fixed_check_ids": [check.id for check in handoff.checks]}
    frozen = handoff.implementation_hashes
    drifted = sorted(path for path in frozen.keys() & current_hashes.keys()
                     if frozen[path] != current_hashes[path])
    missing = sorted(frozen.keys() - current_hashes.keys())
    added = sorted(current_hashes.keys() - frozen.keys())
    if handoff.version.status != "validated":
        return Check(name="v1_source_preserved", status="fail", facts=facts,
                     detail=f"The v1 manifest status is {handoff.version.status!r}, not 'validated'.")
    if drifted or missing or added:
        return Check(name="v1_source_preserved", status="fail",
                     facts={**facts, "drifted": drifted, "missing": missing, "added": added},
                     detail="The working tree differs from the frozen v1 sources.")
    return Check(name="v1_source_preserved", status="pass", facts=facts,
                 detail=f"All {len(frozen)} frozen v1 source fingerprints match the working tree. "
                        "The Docker image identity is A's readiness check.")


def fixture_analysis_check(experiment_id: UUID, sessions: list[Session]) -> Check:
    """The demo's offline analysis must stay labeled fixture and claim nothing it did not see."""
    try:
        report = analyze_fixture_sessions(experiment_id, sessions)
    except EvidenceMismatch as exc:
        return Check(name="fixture_analysis_labeled", status="fail", detail=str(exc))
    facts = {"mode": report.mode, "method": report.method, "inference_used": report.inference_used,
             "sessions_seen": report.sessions_seen, "feedback_present": report.feedback_present,
             "clusters": len(report.clusters)}
    if report.mode != "fixture" or report.inference_used or report.role_runs or report.proposals:
        return Check(name="fixture_analysis_labeled", status="fail", facts=facts,
                     detail="Fixture analysis claims inference, role runs or proposals.")
    if report.feedback_present == 0 and report.clusters:
        return Check(name="fixture_analysis_labeled", status="fail", facts=facts,
                     detail="Fixture analysis grouped feedback that does not exist.")
    return Check(name="fixture_analysis_labeled", status="pass", facts=facts,
                 detail="Fixture analysis is labeled fixture, uses no inference and creates "
                        "no proposal.")


def neon_host(settings: Settings) -> bool:
    """True only for a *.neon.tech host. The host itself is never reported."""
    try:
        host = conninfo_to_dict(settings.database_url.get_secret_value()).get("host") or ""
    except Exception:
        return False
    return host.endswith(".neon.tech")


def database_snapshot(database: NeonDatabase) -> dict[str, Any]:
    """Read server identity, migration history and core-table usage in one read-only snapshot."""
    with database.connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '5s'")
            cursor.execute("SELECT current_setting('server_version') AS server_version, "
                           "current_database() AS database, now() AS read_at")
            server = cursor.fetchone()
            cursor.execute("SELECT version, checksum, applied_at FROM schema_migrations ORDER BY version")
            migrations = cursor.fetchall()
            counts = {}
            for table, flagged in CORE_TABLES.items():
                fixture = "count(*) FILTER (WHERE fixture)" if flagged else "0"
                cursor.execute(f"SELECT count(*) AS total, {fixture} AS fixture FROM {table}")
                counts[table] = cursor.fetchone()
            cursor.execute("SELECT id, label, status, commit_sha, fixture, created_at "
                           "FROM product_versions ORDER BY created_at, id")
            versions = cursor.fetchall()
            cursor.execute("SELECT provenance->>'stream_mode' AS stream_mode, fixture, count(*) AS total "
                           "FROM sessions GROUP BY 1, 2 ORDER BY 1 NULLS FIRST, 2")
            stream_modes = cursor.fetchall()
    return {"server": server, "migrations": migrations, "counts": counts,
            "versions": versions, "stream_modes": stream_modes}


def neon_usage_check(snapshot: dict[str, Any], on_neon_host: bool) -> Check:
    counts = snapshot["counts"]
    facts = {"neon_host": on_neon_host,
             "server_version": snapshot["server"]["server_version"],
             "database": snapshot["server"]["database"],
             "read_at": snapshot["server"]["read_at"].isoformat(),
             "migrations": [{"version": row["version"], "checksum": row["checksum"],
                             "applied_at": row["applied_at"].isoformat()}
                            for row in snapshot["migrations"]],
             "rows": {table: {"total": row["total"], "fixture": row["fixture"]}
                      for table, row in counts.items()}}
    if not on_neon_host:
        return Check(name="neon_usage", status="fail", facts=facts,
                     detail="The configured database host is not a *.neon.tech host.")
    if not snapshot["migrations"]:
        return Check(name="neon_usage", status="fail", facts=facts,
                     detail="Neon answered, but no migration is recorded in schema_migrations.")
    live_sessions = counts["sessions"]["total"] - counts["sessions"]["fixture"]
    if live_sessions == 0 or counts["actions"]["total"] == 0:
        return Check(name="neon_usage", status="not_established", facts=facts,
                     detail="Neon answered with the migrated schema, but it holds no non-fixture "
                            "sessions with actions. The demo pipeline has not written to it.")
    return Check(name="neon_usage", status="pass", facts=facts,
                 detail=f"Neon holds {live_sessions} non-fixture sessions, "
                        f"{counts['actions']['total']} actions and {counts['feedback']['total']} "
                        "feedback records.")


def versions_check(snapshot: dict[str, Any], handoff: ProductHandoff) -> list[Check]:
    """v1 stays registered with its frozen commit; an approved v2 is a separate row."""
    rows = [{"id": str(row["id"]), "label": row["label"], "status": row["status"],
             "commit_sha": row["commit_sha"], "fixture": row["fixture"]}
            for row in snapshot["versions"]]
    v1 = [row for row in rows if row["id"] == str(handoff.version.id)]
    if not v1:
        v1_check = Check(name="v1_registered", status="not_established", facts={"versions": rows},
                         detail="Neon has no product_versions row for the frozen v1.")
    elif v1[0]["commit_sha"] != handoff.version.commit_sha or v1[0]["status"] != "validated":
        v1_check = Check(name="v1_registered", status="fail", facts={"v1": v1[0]},
                         detail="The stored v1 row no longer matches the frozen manifest.")
    else:
        v1_check = Check(name="v1_registered", status="pass", facts={"v1": v1[0]},
                         detail="The stored v1 row matches the frozen manifest identity and commit.")
    v2 = [row for row in rows if row["status"] == "approved" and not row["fixture"]
          and row["id"] != str(handoff.version.id)]
    if not v2:
        v2_check = Check(name="v2_registered", status="not_established", facts={"approved": []},
                         detail="No human-approved v2 is stored. Patch runs live in memory until "
                                "durable records exist.")
    elif v1_check.status != "pass":
        v2_check = Check(name="v2_registered", status="fail", facts={"approved": v2},
                         detail="An approved v2 is stored, but v1 is not preserved beside it.")
    else:
        v2_check = Check(name="v2_registered", status="pass", facts={"approved": v2},
                         detail="Approved v2 rows are stored beside the unchanged v1 row.")
    return [v1_check, v2_check]


def replay_label_check(snapshot: dict[str, Any]) -> Check:
    """Every stored session must say whether it is live, replay, fixture or unavailable."""
    modes = [{"stream_mode": row["stream_mode"], "fixture": row["fixture"], "total": row["total"]}
             for row in snapshot["stream_modes"]]
    unlabeled = sum(row["total"] for row in modes if row["stream_mode"] not in STREAM_MODES)
    mislabeled = sum(row["total"] for row in modes
                     if (row["stream_mode"] == "fixture") != row["fixture"])
    facts = {"sessions_by_stream_mode": modes}
    if unlabeled or mislabeled:
        return Check(name="replay_labeled", status="fail", facts=facts,
                     detail=f"{unlabeled} stored sessions have no valid stream label and "
                            f"{mislabeled} disagree with their fixture flag.")
    if not modes:
        return Check(name="replay_labeled", status="not_established", facts=facts,
                     detail="No stored sessions to label.")
    return Check(name="replay_labeled", status="pass", facts=facts,
                 detail="Every stored session carries a valid live/replay/fixture/unavailable label.")


def live_checks(settings: Settings, database: NeonDatabase, handoff: ProductHandoff) -> list[Check]:
    names = ["neon_usage", "v1_registered", "v2_registered", "replay_labeled"]
    if settings.app_mode != "live" or not settings.database_url.get_secret_value():
        return [Check(name=name, status="not_established",
                      detail="Needs APP_MODE=live and DATABASE_URL; no connection was attempted.")
                for name in names]
    try:
        snapshot = database_snapshot(database)
    except DatabaseUnavailable as exc:
        return [Check(name=name, status="fail", detail=str(exc)) for name in names]
    return [neon_usage_check(snapshot, neon_host(settings)), *versions_check(snapshot, handoff),
            replay_label_check(snapshot)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="Also write the JSON report to this path.")
    args = parser.parse_args(argv)
    settings = get_settings()
    handoff = ProductHandoff.model_validate_json(MANIFEST.read_text())
    database = NeonDatabase(settings)
    try:
        checks = [v1_source_check(handoff, implementation_hashes()),
                  fixture_analysis_check(EXPERIMENT.id, SESSIONS),
                  *live_checks(settings, database, handoff)]
    finally:
        database.close()
    report = SliceReport(generated_at=datetime.now(UTC), app_mode=settings.app_mode, checks=checks)
    text = report.model_dump_json(indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
    print(text)
    return 1 if any(check.status == "fail" for check in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
