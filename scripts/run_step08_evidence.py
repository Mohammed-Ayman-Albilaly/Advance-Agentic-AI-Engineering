"""Attempt all Step 8 live evidence and always finish with final_validate.py."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script: str) -> int:
    print(f"\n>>> {script}")
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, check=False)
    print(f"<<< {script}: returncode={result.returncode}")
    return result.returncode


def main() -> None:
    # Each proof is independent. Missing prerequisites do not prevent the others.
    run("demo_step08_full_graph.py")
    run("demo_step08_live_llm.py")
    run("demo_step08_docker.py")
    run("final_validate.py")


if __name__ == "__main__":
    main()
