#!/usr/bin/env python3
"""Fetch pinned public RTL examples, run them, and archive verified evidence."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
JOBS = (
    {
        "name": "ready-valid-verification",
        "url": "https://github.com/Rivoryxa-Technologies/ready-valid-verification.git",
        "revision": "7c4c1913d7db92192b13de47dcb666f445c4717e",
        "command": ["python3", "run.py", "--evidence-dir", "{evidence}"],
        "summary_glob": "evidence/*/summary.json",
        "overall_key": "ok",
        "cases_key": "cases",
        "case_key": "outcome_ok",
        "case_identity": "name",
        "expected_cases": [
            "correct-w1-s7", "mutant-w1-s7", "correct-w8-s1", "mutant-w8-s1",
            "correct-w8-s2025", "mutant-w8-s2025", "correct-w17-s99", "mutant-w17-s99",
        ],
        "required_sources": ["run.py", "tb/tb_ready_valid.sv", "rtl/ready_valid_buffer.sv",
                             "rtl/ready_valid_buffer_mutant.sv"],
    },
    {
        "name": "reset-recovery-verification",
        "url": "https://github.com/Rivoryxa-Technologies/reset-recovery-verification.git",
        "revision": "66555fcb2a060e9269dbc464d6b20fc1cfb3415e",
        "command": ["python3", "tools/run.py"],
        "summary_glob": "repo/runs/*/summary.json",
        "overall_key": "overall_pass",
        "cases_key": "results",
        "case_key": "expected_outcome_observed",
        "case_identity": "reset",
        "expected_cases": [
            [config, variant, seed]
            for config in ("short_narrow", "default", "deep_wide")
            for variant in ("correct", "mutant") for seed in (1, 17, 2026)
        ],
        "required_sources": ["rtl/response_pipeline.sv", "tb/tb_reset_recovery.sv", "tools/run.py"],
    },
    {
        "name": "round-robin-verification",
        "url": "https://github.com/Rivoryxa-Technologies/round-robin-verification.git",
        "revision": "049b015a782d48ae3ed491a2ef102147e7906705",
        "command": ["python3", "tools/run.py", "--artifacts", "{evidence}"],
        "summary_glob": "evidence/*/summary.json",
        "overall_key": "passed",
        "cases_key": "cases",
        "case_key": "passed",
        "case_identity": "name",
        "expected_cases": [
            "correct_w{}_s{}".format(width, seed)
            for width in (1, 2, 3, 4, 7) for seed in (1, 17, 2026)
        ] + ["mutant_starvation_w4_s17"],
        "required_sources": ["rtl/round_robin_arbiter.sv", "rtl/fixed_priority_mutant.sv",
                             "tb/arbiter_tb.sv", "tools/run.py"],
    },
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def execute(command: list[str], cwd: Path, timeout: float, log: Path) -> dict:
    """Run one process group and retain combined output, including launch errors."""
    started = time.monotonic()
    timed_out = False
    try:
        process = subprocess.Popen(
            command, cwd=str(cwd), text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, start_new_session=(os.name == "posix"),
        )
        try:
            output, _ = process.communicate(timeout=timeout)
            returncode = process.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            output, _ = process.communicate()
            output = (output or "") + "\nAUTOMATION_TIMEOUT\n"
            returncode = 124
    except OSError as exc:
        output = "AUTOMATION_EXEC_ERROR: {}\n".format(exc)
        returncode = 127
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(output or "", encoding="utf-8")
    return {
        "command": command,
        "returncode": returncode,
        "timed_out": timed_out,
        "seconds": round(time.monotonic() - started, 6),
        "log": log.name,
    }


def case_identity(case: dict, kind: str):
    if kind == "name":
        return case.get("name")
    config = case.get("config")
    if kind == "reset" and isinstance(config, dict):
        return [config.get("name"), case.get("variant"), case.get("seed")]
    return None


def validate_summary(summary_path: Path, checkout: Path, job: dict, not_before: float) -> tuple[bool, str, dict | None]:
    """Validate freshness, schema, semantic outcomes, and hashes against checkout."""
    if not summary_path.is_file():
        return False, "summary missing", None
    if summary_path.stat().st_mtime + 1e-6 < not_before:
        return False, "summary is stale", None
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False, "summary is malformed", None
    if not isinstance(data, dict):
        return False, "summary root is not an object", None
    if data.get("schema_version") != 1:
        return False, "unsupported summary schema", data
    cases = data.get(job["cases_key"])
    if data.get(job["overall_key"]) is not True or not isinstance(cases, list) or not cases:
        return False, "overall or case result is not an exact pass", data
    if any(not isinstance(case, dict) or case.get(job["case_key"]) is not True for case in cases):
        return False, "one or more exact case outcomes did not pass", data
    actual_cases = [case_identity(case, job["case_identity"]) for case in cases]
    expected_cases = job["expected_cases"]
    if len(actual_cases) != len(expected_cases) or actual_cases != expected_cases:
        return False, "case matrix is incomplete, duplicated, or reordered", data
    hashes = data.get("source_sha256")
    if not isinstance(hashes, dict) or not hashes:
        return False, "source hashes missing", data
    missing_sources = [path for path in job["required_sources"] if path not in hashes]
    if missing_sources:
        return False, "required source hashes missing: " + ", ".join(missing_sources), data
    for relative, expected in hashes.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            return False, "source hash entry is malformed", data
        source = (checkout / relative).resolve()
        try:
            source.relative_to(checkout.resolve())
        except ValueError:
            return False, "source hash path escapes checkout", data
        if not source.is_file() or sha256_file(source) != expected:
            return False, "source hash mismatch: " + relative, data
    return True, "verified exact outcomes and source hashes", data


def copy_evidence(source: Path, destination: Path) -> None:
    if source.exists():
        shutil.copytree(source, destination, dirs_exist_ok=True)


def select_single_summary(paths: list[Path]) -> tuple[Path | None, str | None]:
    if len(paths) != 1:
        return None, "expected exactly one fresh summary; found {}".format(len(paths))
    return paths[0], None


def run_job(job: dict, run_dir: Path, timeout: float, git: str) -> dict:
    job_dir = run_dir / "jobs" / job["name"]
    checkout = job_dir / "repo"
    evidence = job_dir / "evidence"
    checkout.mkdir(parents=True)
    steps = []
    steps.append(execute([git, "init", "-q"], checkout, timeout, job_dir / "git-init.log"))
    if steps[-1]["returncode"] == 0:
        steps.append(execute([git, "fetch", "--depth", "1", job["url"], job["revision"]],
                             checkout, timeout, job_dir / "git-fetch.log"))
    if steps[-1]["returncode"] == 0:
        steps.append(execute([git, "checkout", "-q", "--detach", "FETCH_HEAD"],
                             checkout, timeout, job_dir / "git-checkout.log"))
    revision = ""
    if steps[-1]["returncode"] == 0:
        revision_step = execute([git, "rev-parse", "HEAD"], checkout, timeout, job_dir / "git-revision.log")
        steps.append(revision_step)
        revision = (job_dir / "git-revision.log").read_text(encoding="utf-8").strip()

    test_started_wall = time.time()
    if revision == job["revision"]:
        command = [part.format(evidence=str(evidence)) for part in job["command"]]
        test = execute(command, checkout, timeout, job_dir / "test.log")
        steps.append(test)
    else:
        test = {"command": job["command"], "returncode": None, "timed_out": False,
                "seconds": 0.0, "log": "test.log"}
        (job_dir / "test.log").write_text("test skipped: pinned checkout failed\n", encoding="utf-8")

    summaries = list(job_dir.glob(job["summary_glob"]))
    summary_path, selection_error = select_single_summary(summaries)
    if selection_error:
        valid, reason, summary = False, selection_error, None
    else:
        valid, reason, summary = validate_summary(summary_path, checkout, job, test_started_wall)
    passed = (all(step["returncode"] == 0 and not step["timed_out"] for step in steps)
              and revision == job["revision"] and valid)
    if summary is not None:
        shutil.copy2(summary_path, job_dir / "validated-summary.json")
    if (checkout / "runs").exists():
        copy_evidence(checkout / "runs", job_dir / "evidence")
    shutil.rmtree(checkout)
    return {
        "name": job["name"], "url": job["url"], "expected_revision": job["revision"],
        "executed_revision": revision, "passed": passed, "validation": reason,
        "steps": steps, "seconds": round(sum(step["seconds"] for step in steps), 6),
        "validated_summary": "validated-summary.json" if summary is not None else None,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds per process")
    parser.add_argument("--archive", type=Path, default=ROOT / "artifacts")
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a positive finite number")
    git = shutil.which("git")
    if git is None:
        print("ERROR: git is required", file=sys.stderr)
        return 2

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = args.archive.resolve() / run_id
    run_dir.mkdir(parents=True)
    started = time.monotonic()
    results = []
    for job in JOBS:
        try:
            result = run_job(job, run_dir, args.timeout, git)
        except Exception as exc:
            result = {
                "name": job["name"], "url": job["url"],
                "expected_revision": job["revision"], "executed_revision": "",
                "passed": False, "validation": "runner error: {}: {}".format(type(exc).__name__, exc),
                "steps": [], "seconds": 0.0, "validated_summary": None,
            }
        results.append(result)
        print("{} {}: {}".format("PASS" if result["passed"] else "FAIL", job["name"], result["validation"]))
    manifest = {
        "schema_version": 1, "run_id": run_id,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "platform": platform.platform(), "python_version": platform.python_version(),
        "timeout_seconds_per_process": args.timeout,
        "runner_sha256": sha256_file(Path(__file__)),
        "jobs": results, "total_seconds": round(time.monotonic() - started, 6),
        "passed": all(result["passed"] for result in results),
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Evidence manifest: " + str(manifest_path))
    return 0 if manifest["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
