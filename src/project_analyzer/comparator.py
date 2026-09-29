"""Validate saved statistics and compare them without reading historical source."""

import json
from pathlib import Path, PurePosixPath, PureWindowsPath


FILE_METRICS = ("total_lines", "code_lines", "comment_lines", "blank_lines",
                "todo_count", "fixme_count")
SUMMARY_METRICS = ("file_count",) + FILE_METRICS


def validate_report(report):
    """Reject ambiguous/inconsistent baselines; unrelated extra fields are allowed."""
    def invalid(message):
        raise ValueError("Invalid comparison report: " + message)

    def counts(data, keys, label):
        if not isinstance(data, dict):
            invalid(label + " must be an object.")
        for key in keys:
            if type(data.get(key)) is not int or data[key] < 0:
                invalid(label + "." + key + " must be a non-negative integer.")
        if data["total_lines"] != sum(data[k] for k in FILE_METRICS[1:4]):
            invalid(label + " line totals are inconsistent.")

    if not isinstance(report, dict):
        invalid("root must be an object.")
    counts(report.get("summary"), SUMMARY_METRICS, "summary")
    if not isinstance(report.get("files"), list):
        invalid("files must be an array.")
    for key in ("target", "analyzed_at"):
        if key in report and not isinstance(report[key], str):
            invalid(key + " must be a string.")
    if "complete" in report and type(report["complete"]) is not bool:
        invalid("complete must be a boolean.")
    seen = set()
    for item in report["files"]:
        counts(item, FILE_METRICS, "file")
        path = item.get("path")
        if (not isinstance(path, str) or not path or "\x00" in path
                or PurePosixPath(path).is_absolute() or PureWindowsPath(path).drive
                or any(part in ("", ".", "..") for part in path.split("/"))):
            invalid("file path must be a non-empty relative POSIX path.")
        if path in seen:
            invalid("duplicate file path.")
        seen.add(path)
    if report["summary"]["file_count"] != len(seen):
        invalid("file_count does not match files.")
    for key in FILE_METRICS:
        if report["summary"][key] != sum(item[key] for item in report["files"]):
            invalid("summary." + key + " does not match files.")
    return report


def load_baseline(path):
    if not str(path).strip():
        raise ValueError("Comparison report path must not be empty.")
    try:
        text = Path(path).expanduser().read_text(encoding="utf-8-sig")
    except OSError:
        raise ValueError("Cannot read comparison report. Check its path and permissions.") from None
    except UnicodeError:
        raise ValueError("Comparison report must use UTF-8.") from None
    try:
        report = json.loads(text, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError):
        raise ValueError("Comparison report contains invalid JSON or duplicate keys.") from None
    return validate_report(report)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def metric_delta(before, after, keys):
    return {key: {"before": before[key], "after": after[key],
                  "delta": after[key] - before[key]} for key in keys}


def compare_reports(before, after):
    validate_report(before)
    validate_report(after)
    old = {item["path"]: item for item in before["files"]}
    new = {item["path"]: item for item in after["files"]}
    changed, unchanged = [], []
    for path in sorted(old.keys() & new.keys()):
        delta = metric_delta(old[path], new[path], FILE_METRICS)
        if any(item["delta"] for item in delta.values()):
            changed.append({"path": path, "metrics": delta})
        else:
            unchanged.append(path)
    warnings = []
    if before.get("target") != after.get("target") or not before.get("target"):
        warnings.append("Baseline target differs or is unknown; confirm both reports describe the intended project.")
    if before.get("complete") is False or after.get("complete") is False:
        warnings.append("Partial scan: added/removed files may reflect unreadable files, not actual creation/deletion.")
    return {
        "baseline_analyzed_at": before.get("analyzed_at"),
        "baseline_target": before.get("target"),
        "summary_delta": metric_delta(before["summary"], after["summary"], SUMMARY_METRICS),
        "added_files": sorted(new.keys() - old.keys()),
        "removed_files": sorted(old.keys() - new.keys()),
        "changed_files": changed,
        "unchanged_files": unchanged,
        "unchanged_file_count": len(unchanged),
        "warnings": warnings,
    }
