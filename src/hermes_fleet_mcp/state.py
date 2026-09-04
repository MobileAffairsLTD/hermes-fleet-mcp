"""Read a Hermes deployment's state from HERMES_HOME.

Agents = Hermes *profiles* (``config.yaml`` = "default", ``profiles/<name>/config.yaml``
= named). ``--profile <name>`` sets an isolated ``HERMES_HOME``, so sessions, crons and
skills are read per-profile. All readers are defensive: a missing file returns empty.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

DEFAULT_HERMES_HOME = Path.home() / ".hermes"

_FRONTMATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*", re.DOTALL)


def resolve_hermes_home(explicit: str | os.PathLike | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env).expanduser()
    return DEFAULT_HERMES_HOME


def _frontmatter(text: str) -> dict[str, Any]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1)) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class HermesState:
    def __init__(self, hermes_home: str | os.PathLike | None = None, hermes_bin: str = "hermes"):
        self.root = resolve_hermes_home(hermes_home)
        self.hermes_bin = hermes_bin
        self._started_at = time.time()

    # ---- profile -> isolated home resolution ----

    def _home_for(self, agent: str | None) -> Path:
        if not agent or agent == "default":
            return self.root
        return self.root / "profiles" / agent

    def _profile_paths(self) -> list[tuple[str, Path]]:
        out = [("default", self.root / "config.yaml")]
        profiles_dir = self.root / "profiles"
        if profiles_dir.is_dir():
            for cfg in sorted(profiles_dir.glob("*/config.yaml")):
                out.append((cfg.parent.name, cfg))
        return out

    # ---- agents (profiles) ----

    def list_agents(self) -> list[dict]:
        agents = []
        for name, path in self._profile_paths():
            agent = self._read_profile(name, path)
            if agent:
                agents.append(agent)
        return agents

    def _read_profile(self, name: str, path: Path) -> dict | None:
        if not path.is_file():
            return None
        try:
            cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return None
        model = cfg.get("model") or {}
        agent_cfg = cfg.get("agent") or {}
        home = self._home_for(name)
        return {
            "name": name,
            "model": model.get("default") or "",
            "provider": model.get("provider") or "",
            "toolsets": list(cfg.get("toolsets") or []),
            "max_turns": agent_cfg.get("max_turns"),
            "has_sessions": (home / "state.db").is_file(),
        }

    def get_agent(self, name: str) -> dict | None:
        for agent in self.list_agents():
            if agent["name"] == name:
                return agent
        return None

    # ---- sessions ----

    def _query_sessions(self, db_path: Path, limit: int, active_only: bool) -> list[dict]:
        if not db_path.is_file():
            return []
        limit = max(1, min(int(limit), 200))
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            conn.row_factory = sqlite3.Row
        except Exception:
            return []
        try:
            where = "archived != 1"
            if active_only:
                where += " AND ended_at IS NULL"
            rows = conn.execute(
                f"SELECT id, source, title, model, profile_name, cwd, git_branch, git_repo_root, "
                f"message_count, tool_call_count, started_at, ended_at, last_activity_at, "
                f"last_activity_description FROM sessions WHERE {where} "
                f"ORDER BY COALESCE(last_activity_at, started_at) DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def list_sessions(self, agent: str | None = None, limit: int = 20, active_only: bool = False) -> list[dict]:
        return self._query_sessions(self._home_for(agent) / "state.db", limit, active_only)

    def _count_sessions(self, agent: str | None = None) -> int:
        db_path = self._home_for(agent) / "state.db"
        if not db_path.is_file():
            return 0
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        except Exception:
            return 0
        try:
            row = conn.execute("SELECT COUNT(*) FROM sessions WHERE archived != 1").fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0
        finally:
            conn.close()

    # ---- crons ----

    def list_crons(self, agent: str | None = None) -> list[dict]:
        jobs_file = self._home_for(agent) / "cron" / "jobs.json"
        if not jobs_file.is_file():
            return []
        try:
            data = json.loads(jobs_file.read_text(encoding="utf-8"))
        except Exception:
            return []
        out = []
        for job in data.get("jobs") or []:
            if not isinstance(job, dict):
                continue
            out.append({
                "id": job.get("id"),
                "name": job.get("name"),
                "prompt": job.get("prompt"),
                "schedule": job.get("schedule"),
                "enabled": job.get("enabled", True),
                "state": job.get("state"),
                "next_run_at": job.get("next_run_at"),
                "skills": job.get("skills") or [],
                "deliver": job.get("deliver"),
            })
        return out

    # ---- skills ----

    def list_skills(self, agent: str | None = None) -> list[dict]:
        skills_dir = self._home_for(agent) / "skills"
        if not skills_dir.is_dir():
            return []
        out = []
        for sk in sorted(skills_dir.rglob("SKILL.md")):
            try:
                text = sk.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            fm = _frontmatter(text)
            out.append({
                "name": fm.get("name") or sk.parent.name,
                "description": fm.get("description") or "",
                "path": str(sk.relative_to(skills_dir)),
            })
        return out

    # ---- toolsets ----

    def list_toolsets(self) -> dict:
        toolsets: set[str] = set()
        for agent in self.list_agents():
            toolsets.update(agent.get("toolsets") or [])
        return {"toolsets": sorted(toolsets)}

    # ---- status ----

    def hermes_version(self) -> str:
        try:
            r = subprocess.run([self.hermes_bin, "--version"], capture_output=True, text=True, timeout=10)
            out = (r.stdout or r.stderr).strip().splitlines()
            return out[0] if out else "unknown"
        except Exception:
            return "unknown"

    def node_status(self) -> dict:
        return {
            "hermes_home": str(self.root),
            "hermes_version": self.hermes_version(),
            "agents_count": len(self.list_agents()),
            "sessions_count": self._count_sessions(),
            "crons_count": len(self.list_crons()),
            "skills_count": len(self.list_skills()),
            "toolsets": self.list_toolsets()["toolsets"],
            "bridge_uptime_seconds": round(time.time() - self._started_at, 1),
        }
