"""Workspace management: copy projects to run directories."""

import subprocess
from pathlib import Path

from .util import log_error, log_info


def prepare_workspace(source_path: Path, outputs_dir: Path) -> None:
    """Copy project files to the outputs directory, excluding .git/build/.gradle."""
    if not source_path.is_dir():
        log_error(f"Project source not found: {source_path}")
        raise FileNotFoundError(source_path)

    outputs_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "rsync", "-a",
            "--exclude=.git",
            "--exclude=build",
            "--exclude=.gradle",
            "--exclude=.idea",
            "--exclude=*.iml",
            "--exclude=local.properties",
            f"{source_path}/",
            f"{outputs_dir}/",
        ],
        check=True,
    )
    log_info(f"Prepared workspace: {outputs_dir}")


def cleanup_workspace(outputs_dir: Path) -> None:
    """Remove build artifacts from workspace to save disk space."""
    if not outputs_dir.is_dir():
        return

    import shutil
    for pattern in ("build", ".gradle"):
        for d in outputs_dir.rglob(pattern):
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)

    log_info(f"Cleaned workspace: {outputs_dir}")
