"""Run with: python -m unittest discover -s tests -v."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import shutil
import sys
import unittest
import uuid
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyzer import main
from project_analyzer.counter import count_text
from project_analyzer.reporter import build_report, render_markdown, write_reports
from project_analyzer.scanner import EXCLUDED_DIRECTORIES, scan_project, validate_target


class CounterTests(unittest.TestCase):
    def test_sample_counts(self):
        expected = {
            "main.c": (8, 6, 1, 1, 1, 0),
            "example.c": (10, 5, 4, 1, 1, 1),
            "example.h": (7, 4, 1, 2, 0, 0),
        }
        keys = ("total_lines", "code_lines", "comment_lines", "blank_lines", "todo_count", "fixme_count")
        for name, values in expected.items():
            with self.subTest(name=name):
                stats = count_text((ROOT / "tests/sample_project" / name).read_text(encoding="utf-8"))
                self.assertEqual(tuple(stats[key] for key in keys), values)

    def test_mixed_comments_and_code(self):
        stats = count_text("/* start\n \t\nend */ int x; /* again */\n/* only */ // tail\n")
        self.assertEqual((stats["total_lines"], stats["code_lines"], stats["comment_lines"], stats["blank_lines"]), (4, 1, 2, 1))

    def test_strings_characters_and_escapes(self):
        text = 'char *url = "https://x/*path*/";\nchar quote = \'"\';\nchar *s = "escaped \\\" // text";\n// real\n'
        stats = count_text(text)
        self.assertEqual(stats["code_lines"], 3)
        self.assertEqual(stats["comment_lines"], 1)

    def test_line_endings_and_no_final_newline(self):
        for text in ("int x;\n// c\n\n", "int x;\r\n// c\r\n\r\n", "int x;\r// c\r\r"):
            self.assertEqual(count_text(text)["total_lines"], 3)
        self.assertEqual(count_text("int x;")["total_lines"], 1)
        self.assertEqual(count_text("")["total_lines"], 0)
        self.assertEqual(count_text("\n")["blank_lines"], 1)

    def test_marker_rule(self):
        stats = count_text('// TODO TODO FIXME\n"TODO"; int TODO_count; // todo NOTTODO FIXME2\n')
        self.assertEqual(stats["todo_count"], 3)
        self.assertEqual(stats["fixme_count"], 1)

    def test_sum_invariant(self):
        fragments = ["", " ", "/*", "*/", "// TODO", "int x;", '"/*"', "/* c */ int x;"]
        for first in fragments:
            for second in fragments:
                stats = count_text(first + "\n" + second)
                self.assertEqual(stats["total_lines"], sum(stats[key] for key in ("code_lines", "comment_lines", "blank_lines")))

    def test_unclosed_block_comment(self):
        stats = count_text("/* unfinished\nstill comment\n")
        self.assertEqual(stats["comment_lines"], 2)

    def test_continued_string(self):
        stats = count_text('char *s = "hello\\\n// string";\n// comment\n')
        self.assertEqual(stats["code_lines"], 2)
        self.assertEqual(stats["comment_lines"], 1)


class FileTests(unittest.TestCase):
    def setUp(self):
        # Keep all fixtures under the ignored output folder, even in sandboxes.
        self.base = ROOT / "output" / ("test-" + uuid.uuid4().hex)
        self.base.mkdir(parents=True)
        self.addCleanup(self.clean_fixture)
        self.target = self.base / "project"
        self.target.mkdir()
        self.output = self.base / "reports"

    def clean_fixture(self):
        resolved = self.base.resolve()
        if resolved.parent != (ROOT / "output").resolve() or not resolved.name.startswith("test-"):
            raise RuntimeError("Refusing to remove a directory outside test fixtures.")
        shutil.rmtree(resolved)

    def add_file(self, relative, text="int x;\n"):
        path = self.target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def cli(self, *args):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            code = main([str(self.target), "--output", str(self.output), *args])
        return code, stream.getvalue()

    def test_recursive_scan_and_extensions(self):
        for name in ("a.c", "include/a.h", "nested/b.C"):
            self.add_file(name)
        self.add_file("ignored.py")
        self.assertEqual([item["path"] for item in scan_project(self.target)["files"]], ["a.c", "include/a.h", "nested/b.C"])

    def test_all_exclusions_at_multiple_depths(self):
        self.add_file("keep.c")
        for name in EXCLUDED_DIRECTORIES:
            self.add_file(f"{name}/bad.c")
            self.add_file(f"nested/{name}/bad.h")
        self.add_file("BUILD/also_bad.c")
        self.assertEqual(len(scan_project(self.target)["files"]), 1)

    def test_output_directory_excluded(self):
        self.add_file("keep.c")
        self.add_file("generated/old.c")
        self.assertEqual(len(scan_project(self.target, self.target / "generated")["files"]), 1)

    def test_empty_directory(self):
        code, output = self.cli()
        self.assertEqual(code, 0)
        self.assertIn("No readable", output)
        data = json.loads((self.output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(data["summary"]["code_ratio"], 0.0)
        self.assertTrue(data["complete"])

    def test_missing_target_and_file_target(self):
        for path in (self.base / "missing", self.add_file("file.c")):
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_target(path)

    def test_invalid_utf8_skipped_with_warning(self):
        self.add_file("good.c")
        (self.target / "bad.c").write_bytes(b"\xff\xfe")
        code, output = self.cli()
        self.assertEqual(code, 0)
        self.assertIn("Partial results", output)
        data = json.loads((self.output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(data["summary"]["file_count"], 1)
        self.assertEqual(data["discovered_file_count"], 2)
        self.assertEqual(data["skipped_file_count"], 1)

    def test_bom_supported(self):
        self.add_file("bom.c", "\ufeff// comment\n")
        self.assertEqual(scan_project(self.target)["files"][0]["comment_lines"], 1)

    def test_unreadable_file_warning(self):
        self.add_file("denied.c")
        with patch.object(Path, "read_text", side_effect=PermissionError):
            data = scan_project(self.target)
        self.assertEqual(data["skipped_file_count"], 1)
        self.assertEqual(data["files"], [])
        self.assertIn("Cannot read file", data["warnings"][0]["reason"])

    def test_unreadable_directory_warning(self):
        def denied_walk(root, onerror):
            onerror(PermissionError(13, "denied", str(root / "restricted")))
            return iter([])
        with patch("project_analyzer.scanner.os.walk", side_effect=denied_walk):
            data = scan_project(self.target)
        self.assertEqual(data["warnings"][0]["path"], "restricted")

    def test_symlinks_skipped(self):
        self.add_file("keep.c")
        try:
            (self.target / "loop").symlink_to(self.target, target_is_directory=True)
            (self.target / "alias.c").symlink_to(self.target / "keep.c")
        except (OSError, NotImplementedError):
            self.skipTest("Host does not permit creating symbolic links.")
        self.assertEqual(len(scan_project(self.target)["files"]), 1)

    def test_reports_and_top_order(self):
        for name, count in (("z.c", 4), ("a.c", 4), ("small.h", 1)):
            self.add_file(name, "int x;\n" * count)
        code, output = self.cli("--top", "2")
        self.assertEqual(code, 0)
        self.assertIn("Files analyzed: 3", output)
        data = json.loads((self.output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual([item["path"] for item in data["top_files"]], ["a.c", "z.c"])
        self.assertEqual(data["summary"]["total_lines"], 9)
        self.assertEqual(data["summary"]["code_ratio"], 100.0)
        self.assertEqual(data["target"], "project")
        self.assertNotIn(str(self.base), json.dumps(data))
        markdown = (self.output / "report.md").read_text(encoding="utf-8")
        for heading in ("## Summary", "## Top 2 files", "## Per-file statistics", "## Counting rules"):
            self.assertIn(heading, markdown)

    def test_markdown_escapes_filenames(self):
        report = build_report(self.target, {"files": [], "warnings": [{"path": "a|<b>.c", "reason": "test"}], "discovered_file_count": 0, "skipped_file_count": 0}, 3)
        self.assertIn("a&#124;&lt;b&gt;.c", render_markdown(report))

    def test_output_file_error(self):
        self.output.write_text("existing", encoding="utf-8")
        code, output = self.cli()
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", output)
        self.assertEqual(self.output.read_text(), "existing")

    def test_output_cannot_contain_target(self):
        for output in (self.target, self.base):
            code, _ = self.cli("--output", str(output))
            self.assertEqual(code, 1)

    def test_report_write_permission_failure(self):
        with patch("project_analyzer.reporter.tempfile.NamedTemporaryFile", side_effect=PermissionError):
            code, output = self.cli()
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", output)

    def test_json_and_markdown_replace_failure(self):
        for blocked_name in ("report.json", "report.md"):
            with self.subTest(name=blocked_name):
                self.output.mkdir(exist_ok=True)
                blocked = self.output / blocked_name
                if blocked.is_file():
                    blocked.unlink()
                blocked.mkdir()
                code, output = self.cli()
                self.assertEqual(code, 1)
                self.assertNotIn("Traceback", output)
                self.assertEqual(list(self.output.glob(".report-*.tmp")), [])
                blocked.rmdir()

    def test_invalid_top_values(self):
        for value in ("0", "-1", "abc", "2.5"):
            with self.subTest(value=value), self.assertRaises(SystemExit) as error:
                self.cli("--top", value)
            self.assertEqual(error.exception.code, 2)

    def test_empty_paths(self):
        for args in (["", "--output", str(self.output)], [str(self.target), "--output", ""]):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 1)

    def test_subprocess_invalid_target(self):
        result = subprocess.run([sys.executable, str(ROOT / "src/analyzer.py"), str(self.base / "missing")],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not exist", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_subprocess_from_different_working_directory(self):
        self.add_file("main.c")
        result = subprocess.run([sys.executable, str(ROOT / "src/analyzer.py"), str(self.target),
                                 "--output", str(self.output)], cwd=self.base,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.output / "report.json").exists())

    def test_default_output_is_project_relative(self):
        with patch("analyzer.write_reports") as writer, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(ROOT / "tests/sample_project")]), 0)
        self.assertEqual(writer.call_args.args[1], ROOT / "output")


if __name__ == "__main__":
    unittest.main()
