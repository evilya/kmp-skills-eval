"""Shared helpers: logging, config loading, project resolution."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Colors
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
BLUE = "\033[0;34m"
BOLD = "\033[1m"
NC = "\033[0m"

ROOT_DIR = Path(__file__).resolve().parent.parent


def log_info(msg: str) -> None:
    print(f"{BLUE}[info]{NC} {msg}")


def log_step(msg: str) -> None:
    print(f"{BOLD}{GREEN}[step]{NC} {msg}")


def log_warn(msg: str) -> None:
    print(f"{YELLOW}[warn]{NC} {msg}", file=sys.stderr)


def log_error(msg: str) -> None:
    print(f"{RED}[error]{NC} {msg}", file=sys.stderr)


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        log_error(f"Required tool '{name}' not found. Please install it.")
        sys.exit(1)


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


def _parse_conf(text: str) -> dict:
    """Parse a shell-style KEY=VALUE config file."""
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        # Handle quoted values
        if len(value) >= 2 and value[0] in ('"', "'") and value[0] in value[1:]:
            q = value[0]
            value = value[1:value.index(q, 1)]
        else:
            # Strip inline comment
            if "#" in value:
                value = value[:value.index("#")].strip()
            value = value.strip('"').strip("'")
        result[key.strip()] = value
    return result


def load_defaults() -> dict:
    """Load config with precedence: defaults.conf → defaults.local.conf → env vars."""
    conf = _parse_conf((ROOT_DIR / "config" / "defaults.conf").read_text())
    local_conf = ROOT_DIR / "config" / "defaults.local.conf"
    if local_conf.exists():
        conf.update(_parse_conf(local_conf.read_text()))
    return conf


def load_skill_json(skill: str) -> dict:
    """Load skills/<skill>/skill.json."""
    json_path = ROOT_DIR / "skills" / skill / "skill.json"
    if json_path.exists():
        return json.loads(json_path.read_text())

    log_error(f"Skill config not found: {json_path}")
    sys.exit(1)


def load_projects() -> dict:
    """Load config/projects.json."""
    return json.loads((ROOT_DIR / "config" / "projects.json").read_text())


def resolve_projects(filter_str: str | None = None) -> list[str]:
    """Resolve project names from filter string.

    filter_str can be: None/empty (all) or "kampkit,kmm-rss-reader" (csv).
    """
    data = load_projects()
    if not filter_str:
        return data["projects"]

    return [name.strip() for name in filter_str.split(",") if name.strip()]


def get_project_path(project_name: str) -> Path:
    """Get the filesystem path for a project."""
    data = load_projects()
    pool_root = Path(data["pool_root"]).expanduser()
    if project_name not in data["projects"]:
        log_error(f"Project '{project_name}' not found in projects.json")
        sys.exit(1)
    return pool_root / project_name


def get_eval_file(skill: str, project: str) -> Path | None:
    """Get the eval JSON file for a project under a skill."""
    path = ROOT_DIR / "skills" / skill / "evals" / f"{project}.json"
    return path if path.exists() else None


def list_skills() -> list[dict]:
    """List available skills with metadata from skill.json."""
    skills_dir = ROOT_DIR / "skills"
    results = []
    for d in sorted(skills_dir.iterdir()):
        if not d.is_dir():
            continue
        info = {"name": d.name, "description": "", "injection_type": "unknown", "eval_count": 0}
        json_path = d / "skill.json"
        if json_path.exists():
            data = json.loads(json_path.read_text())
            info["description"] = data.get("description", "")
            info["injection_type"] = data.get("injection", {}).get("type", "unknown")
        evals_dir = d / "evals"
        if evals_dir.is_dir():
            info["eval_count"] = len(list(evals_dir.glob("*.json")))
        results.append(info)
    return results


def list_projects_table() -> None:
    """Print project pool as a formatted table."""
    data = load_projects()
    print(f"{BOLD}Project Pool{NC} ({data['pool_root']})")
    print()
    for name in data["projects"]:
        print(f"  {name}")
