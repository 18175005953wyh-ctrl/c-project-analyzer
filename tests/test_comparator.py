"""Comparison contracts and real CLI error/overwrite regression tests."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import shutil
import uuid
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from project_analyzer.comparator import compare_reports, validate_report
from project_analyzer.counter import count_text
from project_analyzer.reporter import build_report, render_terminal, render_markdown


def report(files=None):
    items = [{"path": path, "type": ".c", **count_text(text)}
             for path, text in (files or {}).items()]
    return build_report(Path("project"), {"files": items, "warnings": [],
                        "discovered_file_count": len(items), "skipped_file_count": 0}, 3)


class ModelTests(unittest.TestCase):
    def test_all_summary_deltas(self):
        before = report({"a.c": "int a;\n// TODO\n\n"})
        after = report({"b.c": "// FIXME\n"})
        result = compare_reports(before, after)
        expected = {"file_count": (1, 1, 0), "total_lines": (3, 1, -2),
                    "code_lines": (1, 0, -1), "comment_lines": (1, 1, 0),
                    "blank_lines": (1, 0, -1), "todo_count": (1, 0, -1),
                    "fixme_count": (0, 1, 1)}
        for key, values in expected.items():
            self.assertEqual(tuple(result["summary_delta"][key].values()), values)

    def test_added_paths_unicode_spaces(self):
        result = compare_reports(report(), report({"源 码/a.c": "", "z.c": ""}))
        self.assertEqual(result["added_files"], ["z.c", "源 码/a.c"])

    def test_removed_paths(self):
        self.assertEqual(compare_reports(report({"old.c": ""}), report())["removed_files"], ["old.c"])

    def test_each_statistic_can_mark_changed(self):
        before = report({"a.c": "int a;\n"})
        for text in ("// comment\n", "\n", "int a; // TODO\n", "int a; // FIXME\n", "int a;\nint b;\n"):
            with self.subTest(text=text):
                result = compare_reports(before, report({"a.c": text}))
                self.assertEqual([x["path"] for x in result["changed_files"]], ["a.c"])

    def test_equal_stats_not_content_diff(self):
        result = compare_reports(report({"a.c": "int a;\n"}), report({"a.c": "int b;\n"}))
        self.assertEqual(result["unchanged_files"], ["a.c"])
        self.assertEqual(result["unchanged_file_count"], 1)
        self.assertEqual(result["changed_files"], [])

    def test_empty_both_directions(self):
        for before, after in ((report(), report()), (report(), report({"a.c": "int a;"})),
                              (report({"a.c": "int a;"}), report())):
            result = compare_reports(before, after)
            self.assertEqual(result["summary_delta"]["file_count"]["delta"],
                             len(after["files"]) - len(before["files"]))

    def test_target_mismatch_warning(self):
        before = report()
        before["target"] = "other"
        self.assertIn("Baseline target differs", compare_reports(before, report())["warnings"][0])

    def test_partial_warning(self):
        before = report()
        before["complete"] = False
        self.assertIn("Partial scan", compare_reports(before, report())["warnings"][0])

    def test_duplicate_paths_rejected(self):
        data = report({"a.c": ""})
        data["files"] *= 2
        with self.assertRaisesRegex(ValueError, "duplicate file path"):
            validate_report(data)

    def test_wrong_count_types(self):
        for value in (True, None, -1, 1.5, "1", [], {}):
            data = report()
            data["summary"]["todo_count"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_report(data)

    def test_bad_file_types_paths_and_metadata(self):
        for field, value in (("path", None), ("path", "../a.c"), ("path", "/a.c"),
                             ("path", "C:/a.c"), ("path", "a//b.c"), ("total_lines", True)):
            data = report({"a.c": ""})
            data["files"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_report(data)
        for field in ("target", "analyzed_at", "complete"):
            data = report()
            data[field] = []
            with self.assertRaises(ValueError):
                validate_report(data)

    def test_inconsistent_summary_rejected(self):
        data = report()
        data["summary"]["todo_count"] = 1
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_report(data)

    def test_inputs_not_mutated(self):
        before, after = report(), report({"a.c": "int x;"})
        saved = copy.deepcopy((before, after))
        compare_reports(before, after)
        self.assertEqual((before, after), saved)

    def test_markdown_escapes_comparison_paths(self):
        after = report({"a|<b>[x].c": "int x;"})
        after["comparison"] = compare_reports(report(), after)
        section = render_markdown(after).split("## Comparison")[1]
        self.assertIn("a&#124;&lt;b&gt;&#91;x&#93;.c", section)


class CliTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "output").mkdir(exist_ok=True)
        self.base = ROOT / "output" / ("test-compare-" + uuid.uuid4().hex)
        self.base.mkdir()
        self.addCleanup(self.clean_fixture)
        self.target = self.base / "project"
        self.target.mkdir()
        self.output = self.base / "current"
        self.baseline = self.base / "baseline.json"

    def clean_fixture(self):
        resolved = self.base.resolve()
        if resolved.parent != (ROOT / "output").resolve() or not resolved.name.startswith("test-compare-"):
            raise RuntimeError("Refusing cleanup outside test fixtures.")
        shutil.rmtree(resolved)

    def save(self, data):
        self.baseline.write_text(json.dumps(data), encoding="utf-8")

    def cli(self, compare=True):
        args = [sys.executable, "-B", str(ROOT / "src/analyzer.py"), str(self.target),
                "--output", str(self.output)]
        if compare:
            args += ["--compare", str(self.baseline)]
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=15)

    def assert_error(self, text):
        result = self.cli()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(text, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.output.exists())

    def test_missing_baseline(self):
        self.assert_error("Cannot read comparison report")

    def test_damaged_json(self):
        self.baseline.write_text("{", encoding="utf-8")
        self.assert_error("invalid JSON")

    def test_missing_required_fields(self):
        for key in ("summary", "files"):
            data = report()
            del data[key]
            self.save(data)
            self.assert_error(key)

    def test_foreign_report_invalid_types(self):
        for data in ([], {"summary": [], "files": []}, {**report(), "files": {}},
                     {**report(), "files": [None]}):
            self.save(data)
            self.assert_error("Invalid comparison report")

    def test_bad_encoding(self):
        self.baseline.write_bytes(b"\xff")
        self.assert_error("UTF-8")

    def test_duplicate_json_keys(self):
        self.baseline.write_text('{"summary": {}, "summary": {}}', encoding="utf-8")
        self.assert_error("duplicate keys")

    def test_positive_delta(self):
        self.save(report())
        (self.target / "a.c").write_text("int x;\n", encoding="utf-8")
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Files: 0 -> 1 (+1)", result.stdout)
        self.assertIn("Total lines: 0 -> 1 (+1)", result.stdout)

    def test_negative_delta(self):
        self.save(report({"a.c": "int x;\n" * 3}))
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Total lines: 3 -> 0 (-3)", result.stdout)

    def test_json_markdown_terminal_agree(self):
        self.save(report({"a.c": "// TODO\n"}))
        (self.target / "a.c").write_text("int x;\nint y;\n", encoding="utf-8")
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads((self.output / "report.json").read_text(encoding="utf-8"))
        md = (self.output / "report.md").read_text(encoding="utf-8")
        for key, item in data["comparison"]["summary_delta"].items():
            self.assertIn(f"| {key} | {item['before']} | {item['after']} | {item['delta']:+d} |", md)
        self.assertIn("a.c: total_lines +1, code_lines +2, comment_lines -1, todo_count -1", md)
        self.assertIn("todo_count -1", result.stdout)

    def test_no_compare_preserves_original_rendering(self):
        result = self.cli(False)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads((self.output / "report.json").read_text(encoding="utf-8"))
        expected = report()
        expected["analyzed_at"] = data["analyzed_at"]
        self.assertEqual(data, expected)
        self.assertEqual(result.stdout, render_terminal(expected) + "\nReports written: report.json and report.md\n")
        self.assertEqual((self.output / "report.md").read_text(encoding="utf-8"), render_markdown(expected))
        self.assertNotIn("comparison", data)

    def test_read_before_overwriting_same_output(self):
        self.output.mkdir()
        self.baseline = self.output / "report.json"
        self.save(report({"old.c": "int x;"}))
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(self.baseline.read_text(encoding="utf-8"))
        self.assertEqual(data["comparison"]["removed_files"], ["old.c"])

    def test_invalid_baseline_never_overwritten(self):
        self.output.mkdir()
        self.baseline = self.output / "report.json"
        self.baseline.write_text("broken", encoding="utf-8")
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.baseline.read_text(), "broken")


if __name__ == "__main__":
    unittest.main()
