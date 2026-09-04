import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hermes_fleet_mcp.state import HermesState  # noqa: E402


def _make_home(tmp_path: Path) -> Path:
    home = tmp_path / "hermes"
    home.mkdir(parents=True)
    (home / "config.yaml").write_text("model:\n  default: deepseek-v4-pro\n  provider: deepseek\ntoolsets:\n  - web\n  - hermes-cli\n")
    prof = home / "profiles" / "dev"
    prof.mkdir(parents=True)
    (prof / "config.yaml").write_text("model:\n  default: gpt-4o\n  provider: openai\ntoolsets:\n  - github\n")
    (home / "cron" / "jobs.json").parent.mkdir(parents=True, exist_ok=True)
    (home / "cron" / "jobs.json").write_text(json.dumps({
        "jobs": [{"id": "j1", "name": "nightly", "prompt": "do the thing", "schedule": {"kind": "cron", "expr": "0 3 * * *"}, "enabled": True}],
        "updated_at": "2026-09-04T00:00:00",
    }))
    skills = home / "skills" / "foo"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("---\nname: foo\ndescription: A test skill\n---\n\nbody\n")
    return home


def test_list_agents(tmp_path):
    state = HermesState(hermes_home=_make_home(tmp_path))
    agents = state.list_agents()
    names = {a["name"] for a in agents}
    assert names == {"default", "dev"}
    dev = next(a for a in agents if a["name"] == "dev")
    assert dev["model"] == "gpt-4o"
    assert dev["toolsets"] == ["github"]


def test_list_crons_and_skills(tmp_path):
    state = HermesState(hermes_home=_make_home(tmp_path))
    crons = state.list_crons()
    assert len(crons) == 1 and crons[0]["name"] == "nightly"
    skills = state.list_skills()
    assert len(skills) == 1 and skills[0]["name"] == "foo"


def test_missing_files_are_graceful(tmp_path):
    state = HermesState(hermes_home=tmp_path / "empty")
    assert state.list_agents() == []
    assert state.list_sessions() == []
    assert state.list_crons() == []
    assert state.list_skills() == []
    assert state.node_status()["agents_count"] == 0
