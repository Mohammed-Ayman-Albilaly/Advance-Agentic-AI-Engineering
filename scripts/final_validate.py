"""Produce a truthful final submission gate report.

This validator never marks missing external evidence as passed. It checks source,
automated tests, runtime dependencies, and exact success markers produced by the
three Step 8 live evidence scripts.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"


def has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def marker(path: Path, key: str) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="replace").lower()
    return f"{key.lower()}=true" in text


def main() -> int:
    test_run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    pytest_output = (test_run.stdout + test_run.stderr).strip()

    live_openai = marker(EVIDENCE / "step08_live_openai.txt", "LIVE_OPENAI_SUCCESS")
    real_graph = marker(EVIDENCE / "step08_full_graph_hitl.txt", "REPLAN_LOOP_SUCCESS")
    durable_hitl = marker(EVIDENCE / "step08_full_graph_hitl.txt", "HITL_RESTART_RESUME_SUCCESS")
    docker_live = marker(EVIDENCE / "step08_docker_health.txt", "DOCKER_HEALTH_SUCCESS")

    checks = {
        "automated_tests": test_run.returncode == 0,
        "langgraph_installed": has_module("langgraph"),
        "checkpoint_sqlite_installed": has_module("langgraph.checkpoint.sqlite"),
        "openai_sdk_installed": has_module("openai") and hasattr(__import__("openai"), "OpenAI"),
        "openai_key_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "docker_cli_available": shutil.which("docker") is not None,
        "live_openai_evidence": live_openai,
        "real_langgraph_loop_evidence": real_graph,
        "durable_hitl_restart_resume_evidence": durable_hitl,
        "live_docker_health_evidence": docker_live,
    }
    submission_ready = (
        checks["automated_tests"]
        and live_openai
        and real_graph
        and durable_hitl
        and docker_live
    )
    report = {
        "submission_ready": submission_ready,
        "checks": checks,
        "pytest_returncode": test_run.returncode,
        "pytest_output": pytest_output,
        "pending_required_evidence": [
            name
            for name, ok in {
                "live OpenAI function-calling": live_openai,
                "real LangGraph re-plan loop": real_graph,
                "durable HITL restart/resume": durable_hitl,
                "live Docker /health": docker_live,
            }.items()
            if not ok
        ],
    }

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "step08_submission_gate.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    lines = [
        "=== UNIFLOW AI FINAL SUBMISSION GATE ===",
        f"automated_tests={'PASS' if checks['automated_tests'] else 'FAIL'}",
        f"pytest_summary={pytest_output.splitlines()[-1] if pytest_output else 'no output'}",
        f"langgraph_installed={checks['langgraph_installed']}",
        f"checkpoint_sqlite_installed={checks['checkpoint_sqlite_installed']}",
        f"openai_sdk_installed={checks['openai_sdk_installed']}",
        f"openai_key_configured={checks['openai_key_configured']}",
        f"docker_cli_available={checks['docker_cli_available']}",
        f"live_openai_evidence={live_openai}",
        f"real_langgraph_loop_evidence={real_graph}",
        f"durable_hitl_restart_resume_evidence={durable_hitl}",
        f"live_docker_health_evidence={docker_live}",
        "pending=" + (", ".join(report["pending_required_evidence"]) or "none"),
        f"SUBMISSION_READY={str(submission_ready).lower()}",
    ]
    text = "\n".join(lines) + "\n"
    (EVIDENCE / "step08_submission_gate.txt").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if checks["automated_tests"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
