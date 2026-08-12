"""Build/run Docker Compose and capture live /health evidence.

Requires Docker Engine/Desktop with `docker compose` available.
No external LLM is needed for this deployment proof.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

EVIDENCE = Path("evidence/step08_docker_health.txt")


def run(*args: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)


def main() -> None:
    if shutil.which("docker") is None:
        raise SystemExit("Docker CLI not found. Install/start Docker Desktop or Docker Engine.")

    env = os.environ.copy()
    # Keep deployment proof independent from external provider credentials.
    env["LLM_PROVIDER"] = "not_configured"
    env["LLM_MODEL"] = ""
    env["OPENAI_API_KEY"] = ""

    up = subprocess.run(
        ["docker", "compose", "up", "-d", "--build"],
        text=True,
        capture_output=True,
        timeout=600,
        check=False,
        env=env,
    )
    if up.returncode != 0:
        EVIDENCE.write_text("DOCKER_HEALTH_SUCCESS=false\n" + up.stderr, encoding="utf-8")
        raise SystemExit(up.returncode)

    response = None
    last_error = ""
    try:
        for _ in range(60):
            try:
                with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=3) as r:
                    body = r.read().decode("utf-8")
                    response = json.loads(body)
                    if r.status == 200 and response.get("status") == "ok":
                        break
            except Exception as exc:
                last_error = str(exc)
                time.sleep(2)

        ps = run("docker", "compose", "ps")
        success = bool(response and response.get("status") == "ok")
        lines = [
            "=== STEP 8 LIVE DOCKER DEPLOYMENT EVIDENCE ===",
            f"docker_compose_build_returncode={up.returncode}",
            "health_response=" + json.dumps(response, ensure_ascii=False) if response else "health_response=null",
            "docker_compose_ps=",
            ps.stdout.strip(),
            f"last_health_error={last_error}" if not success else "last_health_error=",
            f"DOCKER_HEALTH_SUCCESS={str(success).lower()}",
        ]
        text = "\n".join(lines) + "\n"
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(text, encoding="utf-8")
        print(text, end="")
        if not success:
            raise SystemExit(2)
    finally:
        subprocess.run(
            ["docker", "compose", "down"],
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
            env=env,
        )


if __name__ == "__main__":
    main()
