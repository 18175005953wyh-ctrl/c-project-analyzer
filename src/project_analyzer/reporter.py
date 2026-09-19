"""Build one report model and render it as terminal text, JSON and Markdown."""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile


COUNT_KEYS = ("total_lines", "code_lines", "comment_lines", "blank_lines",
              "todo_count", "fixme_count")
RULES = [
    "Count physical lines; a final newline does not add a blank line.",
    "Whitespace-only lines are blank, including inside block comments.",
    "A line containing code and comments is classified as code.",
    "Recognize // and /* ... */ comments; quoted strings/characters honor escapes.",
    "TODO and FIXME are case-sensitive whole-word matches anywhere in the file, including strings and code.",
    "Percentages use all physical lines as the denominator; empty input yields 0%.",
    "Totals include only successfully decoded UTF-8 files; warnings indicate partial results.",
    "This is a text approximation, not a full C parser or preprocessor.",
]


def build_report(target, scan_result, top):
    files = scan_result["files"]
    totals = {key: sum(item[key] for item in files) for key in COUNT_KEYS}
    total = totals["total_lines"]
    totals["code_ratio"] = round(100 * totals["code_lines"] / total, 2) if total else 0.0
    totals["comment_ratio"] = round(100 * totals["comment_lines"] / total, 2) if total else 0.0
    totals["file_count"] = len(files)
    totals["c_file_count"] = sum(item["type"] == ".c" for item in files)
    totals["h_file_count"] = sum(item["type"] == ".h" for item in files)
    return {
        "target": Path(target).name or ".",
        "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "complete": not scan_result["warnings"],
        "discovered_file_count": scan_result["discovered_file_count"],
        "skipped_file_count": scan_result["skipped_file_count"],
        "summary": totals,
        "files": files,
        "top_files": sorted(files, key=lambda item: (-item["total_lines"], item["path"]))[:top],
        "top_requested": top,
        "warnings": scan_result["warnings"],
        "rules": RULES,
    }


def safe_text(value):
    """Avoid control characters in terminal output and Markdown tables."""
    return "".join(char if char.isprintable() else " " for char in str(value))


def markdown_cell(value):
    return (safe_text(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace("\\", "&#92;").replace("|", "&#124;")
            .replace("`", "&#96;").replace("*", "&#42;").replace("_", "&#95;")
            .replace("[", "&#91;").replace("]", "&#93;"))


def render_terminal(report):
    data = report["summary"]
    lines = ["===== C Project Analyzer =====", f"Target: {safe_text(report['target'])}",
             f"Files analyzed: {data['file_count']} (C: {data['c_file_count']}, H: {data['h_file_count']})",
             f"Files discovered: {report['discovered_file_count']}; skipped: {report['skipped_file_count']}",
             f"Total lines: {data['total_lines']}",
             f"Code lines: {data['code_lines']} ({data['code_ratio']:.2f}%)",
             f"Comment lines: {data['comment_lines']} ({data['comment_ratio']:.2f}%)",
             f"Blank lines: {data['blank_lines']}",
             f"TODO: {data['todo_count']}; FIXME: {data['fixme_count']}",
             f"Top {report['top_requested']} files (by total lines):"]
    for index, item in enumerate(report["top_files"], 1):
        lines.append(f"  {index}. {safe_text(item['path'])}: {item['total_lines']} lines")
    if not report["files"]:
        lines.append("No readable C/header files found.")
    if not report["complete"]:
        lines.append("WARNING: Partial results. See warnings below and in reports.")
    for warning in report["warnings"]:
        lines.append(f"  Warning: {safe_text(warning['path'])}: {warning['reason']}")
    return "\n".join(lines)


def render_markdown(report):
    data = report["summary"]
    lines = ["# C Project Analyzer Report", "",
             f"Target: {markdown_cell(report['target'])}", "",
             f"Analyzed at (UTC): {report['analyzed_at']}", "",
             f"Complete: {'yes' if report['complete'] else 'no (partial results)'}", "",
             "## Summary", "", "| Metric | Value |", "| --- | ---: |"]
    for key, value in data.items():
        suffix = "%" if key.endswith("_ratio") else ""
        lines.append(f"| {key} | {value}{suffix} |")
    lines.extend([f"| discovered_file_count | {report['discovered_file_count']} |",
                  f"| skipped_file_count | {report['skipped_file_count']} |", "",
                  f"## Top {report['top_requested']} files", "",
                  "| Rank | File | Total lines |", "| ---: | --- | ---: |"])
    for index, item in enumerate(report["top_files"], 1):
        lines.append(f"| {index} | {markdown_cell(item['path'])} | {item['total_lines']} |")
    lines.extend(["", "## Per-file statistics", "",
                  "| File | Total | Code | Comments | Blank | TODO | FIXME |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for item in report["files"]:
        values = " | ".join(str(item[key]) for key in COUNT_KEYS)
        lines.append(f"| {markdown_cell(item['path'])} | {values} |")
    lines.extend(["", "## Warnings", ""])
    if report["warnings"]:
        for warning in report["warnings"]:
            lines.append(f"- {markdown_cell(warning['path'])}: {warning['reason']}")
    else:
        lines.append("None.")
    lines.extend(["", "## Counting rules", ""])
    lines.extend(f"- {rule}" for rule in report["rules"])
    return "\n".join(lines) + "\n"


def write_reports(report, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    documents = {
        "report.json": json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        "report.md": render_markdown(report),
    }
    # Write temporary siblings, then replace each report to avoid truncated files.
    temporary_paths = []
    try:
        for name, content in documents.items():
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                             dir=output, prefix=".report-", suffix=".tmp",
                                             delete=False) as handle:
                temporary = Path(handle.name)
                temporary_paths.append((temporary, output / name))
                handle.write(content)
        for temporary, destination in temporary_paths:
            temporary.replace(destination)
    finally:
        for temporary, _ in temporary_paths:
            temporary.unlink(missing_ok=True)
