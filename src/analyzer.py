"""Command-line entry point: python src/analyzer.py <target>."""

import argparse
from pathlib import Path
import sys

from project_analyzer.reporter import build_report, render_terminal, write_reports
from project_analyzer.scanner import scan_project, validate_target


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def positive_integer(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("--top must be a positive integer.") from None
    if number < 1:
        raise argparse.ArgumentTypeError("--top must be a positive integer.")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description="Analyze C/header files and write JSON and Markdown reports.")
    parser.add_argument("target", help="C project directory to scan recursively")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "output"),
                        help="report directory (default: this analyzer project's output folder)")
    parser.add_argument("--top", type=positive_integer, default=3,
                        help="number of largest files to show (positive integer; default: 3)")
    args = parser.parse_args(argv)
    try:
        if not args.target.strip() or not args.output.strip():
            raise ValueError("Target and output paths must not be empty.")
        target = validate_target(args.target)
        output = Path(args.output).expanduser().resolve()
        if output == target or output in target.parents:
            raise ValueError("Output directory must not equal or contain the target directory.")
        if output.exists() and not output.is_dir():
            raise ValueError("Output path must be a directory.")
        scan = scan_project(target, output)
        report = build_report(target, scan, args.top)
        write_reports(report, output)
        print(render_terminal(report))
        print("Reports written: report.json and report.md")
        return 0
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except (OSError, RuntimeError):
        print("Error: Cannot access a path or write reports. Check permissions and available disk space."
              " If replacing reports failed, the two reports may be from different runs.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
