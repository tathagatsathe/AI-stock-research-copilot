#!/usr/bin/env python3
"""Run agent eval suite and write JSON artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "evals" / "runs"


def main() -> int:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "pytest", "tests/evals", "-q"]
    completed = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    artifact = {
        "timestamp": timestamp,
        "exit_code": completed.returncode,
        "passed": completed.returncode == 0,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }
    out_path = RUNS_DIR / f"{timestamp}.json"
    out_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"Eval artifact written to {out_path}")
    print(completed.stdout)
    if completed.stderr:
        print(completed.stderr, file=sys.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
