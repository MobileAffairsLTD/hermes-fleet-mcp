"""Run a Hermes chat as a background subprocess and poll for its reply."""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path


class ChatRunner:
    """Spawns ``hermes -z "<msg>"`` (one-shot, prints only the final reply) in the
    background and lets callers poll for completion via ``get``."""

    def __init__(self, hermes_bin: str = "hermes"):
        self.hermes_bin = hermes_bin
        self._lock = threading.Lock()
        self._runs: dict[str, dict] = {}
        self._tmp = Path(tempfile.gettempdir()) / "hermes-fleet-mcp"

    def start(self, agent: str, message: str, caller: str = "") -> dict:
        session_id = f"hf_{uuid.uuid4().hex[:16]}"
        self._tmp.mkdir(parents=True, exist_ok=True)
        out_path = self._tmp / f"{session_id}.out"

        if agent and agent != "default":
            cmd = [self.hermes_bin, "--profile", agent, "-z", message]
        else:
            cmd = [self.hermes_bin, "-z", message]

        env = dict(os.environ)
        env["HERMES_ACCEPT_HOOKS"] = "1"

        with open(out_path, "wb") as f:
            proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)

        run = {
            "session_id": session_id,
            "agent": agent,
            "message": message,
            "caller": caller,
            "proc": proc,
            "out_path": out_path,
            "started_at": time.time(),
            "done": False,
            "reply": "",
        }
        with self._lock:
            self._runs[session_id] = run
        return {"session_id": session_id, "status": "running"}

    def get(self, session_id: str) -> dict:
        with self._lock:
            run = self._runs.get(session_id)
        if not run:
            return {"session_id": session_id, "status": "unknown"}
        proc: subprocess.Popen = run["proc"]
        if proc.poll() is None:
            return {
                "session_id": session_id,
                "status": "running",
                "agent": run["agent"],
                "caller": run["caller"],
                "elapsed_seconds": round(time.time() - run["started_at"], 1),
            }
        if not run["done"]:
            run["reply"] = self._read_reply(run["out_path"])
            run["done"] = True
        return {
            "session_id": session_id,
            "status": "completed",
            "exit_code": proc.returncode,
            "agent": run["agent"],
            "caller": run["caller"],
            "reply": run["reply"],
            "elapsed_seconds": round(time.time() - run["started_at"], 1),
        }

    @staticmethod
    def _read_reply(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            return ""
