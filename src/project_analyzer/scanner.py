"""Walk a directory without following links or entering excluded folders."""

import os
from pathlib import Path

from .counter import count_text


EXCLUDED_DIRECTORIES = {
    ".git", ".vs", ".vscode", ".idea", "build", "dist", "out",
    "__pycache__", "venv", ".venv",
}


def validate_target(target):
    path = Path(target).expanduser().resolve()
    if not path.exists():
        raise ValueError("Target path does not exist.")
    if not path.is_dir():
        raise ValueError("Target path must be a directory.")
    return path


def scan_project(target, output_directory=None):
    """Return readable-file stats, discovered counts and relative-path warnings."""
    root = validate_target(target)
    output = Path(output_directory).resolve() if output_directory is not None else None
    result = {"files": [], "warnings": [], "discovered_file_count": 0,
              "skipped_file_count": 0}

    def record_walk_error(error):
        path = Path(error.filename) if error.filename else root
        try:
            label = path.relative_to(root).as_posix()
        except ValueError:
            label = "(directory)"
        result["warnings"].append({"path": label, "reason": "Cannot read directory."})

    for directory, subdirectories, filenames in os.walk(root, onerror=record_walk_error):
        current = Path(directory)
        retained = []
        for name in sorted(subdirectories):
            child = current / name
            # Directory names are matched case-insensitively on every platform.
            if name.lower() in EXCLUDED_DIRECTORIES or child.is_symlink():
                continue
            if hasattr(child, "is_junction") and child.is_junction():
                continue
            if output is not None and child.resolve() == output:
                continue
            retained.append(name)
        subdirectories[:] = retained

        for name in sorted(filenames):
            path = current / name
            if path.suffix.lower() not in {".c", ".h"}:
                continue
            if path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            result["discovered_file_count"] += 1
            try:
                # utf-8-sig is UTF-8 with optional BOM removal.
                text = path.read_text(encoding="utf-8-sig")
            except UnicodeError:
                result["skipped_file_count"] += 1
                result["warnings"].append({"path": relative, "reason": "Invalid UTF-8; file skipped."})
                continue
            except OSError:
                result["skipped_file_count"] += 1
                result["warnings"].append({"path": relative, "reason": "Cannot read file; file skipped."})
                continue
            item = {"path": relative, "type": path.suffix.lower()}
            item.update(count_text(text))
            result["files"].append(item)
    result["files"].sort(key=lambda item: item["path"])
    return result
