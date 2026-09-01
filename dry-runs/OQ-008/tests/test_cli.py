"""Runs the actual `python -m lmd build` command as a subprocess -- the way
a real user invokes it -- rather than only calling internal functions in
process, to check the CLI's exit codes and error reporting are real.
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "lmd", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_building_the_example_contract_succeeds(tmp_path):
    out_file = tmp_path / "contract.html"
    result = run_cli("build", "examples/contract.md", "-o", str(out_file))
    assert result.returncode == 0, result.stderr
    assert out_file.exists()
    html_out = out_file.read_text(encoding="utf-8")
    assert "Mutual Non-Disclosure Agreement" in html_out
    assert "Section 2.2(a)" in html_out


def test_cli_exits_nonzero_and_reports_the_line_on_a_broken_document(tmp_path):
    broken = tmp_path / "broken.md"
    broken.write_text(
        "# Section One {#one}\n\nSee [[ref:nonexistent]] for details.\n",
        encoding="utf-8",
    )
    out_file = tmp_path / "broken.html"
    result = run_cli("build", str(broken), "-o", str(out_file))
    assert result.returncode == 1
    assert "nonexistent" in result.stderr
    assert not out_file.exists()


def test_cli_reports_missing_source_file_cleanly():
    result = run_cli("build", "does/not/exist.md", "-o", "out/whatever.html")
    assert result.returncode == 1
    assert "no such file" in result.stderr.lower()
