"""The inputs a demo never has: no files, wrong bytes, loops, absurd sizes.

Run as a subprocess where the thing under test is a real stream or a real exit code, because
pytest replaces stdout and swallows warnings before they get there.
"""
import os
import pathlib
import subprocess
import sys

import pytest

SRC = str(pathlib.Path(__file__).resolve().parents[1] / "src")


def run(*args, cwd=None):
    environment = dict(os.environ, PYTHONPATH=SRC, PYTHONWARNINGS="always")
    return subprocess.run([sys.executable, "-m", "PKG", *args], cwd=cwd,
                          capture_output=True, text=True, env=environment)


def test_an_empty_directory_does_not_crash(tmp_path):
    assert run("--repo", str(tmp_path)).returncode in (0, 1)


def test_nothing_is_written_to_stderr_even_when_every_check_skips(tmp_path):
    assert run("--repo", str(tmp_path)).stderr == ""


def test_a_readme_of_invalid_utf8_is_read_anyway(tmp_path):
    (tmp_path / "README.md").write_bytes(b"\xff\xfe not text at all")
    done = run("--repo", str(tmp_path))
    assert done.returncode in (0, 1) and done.stderr == ""


def test_a_symlink_loop_is_survived(tmp_path):
    (tmp_path / "README.md").write_text("# x")
    (tmp_path / "loop").symlink_to(tmp_path, target_is_directory=True)
    assert run("--repo", str(tmp_path)).returncode in (0, 1)


def test_a_dangling_symlink_where_the_readme_should_be(tmp_path):
    (tmp_path / "README.md").symlink_to(tmp_path / "gone")
    done = run("--repo", str(tmp_path))
    assert done.returncode in (0, 1) and "Traceback" not in done.stderr


def test_a_very_long_single_line(tmp_path):
    (tmp_path / "README.md").write_text("x" * 2_000_000)
    assert run("--repo", str(tmp_path)).returncode in (0, 1)


def test_the_help_text_works_and_exits_zero():
    done = run("--help")
    assert done.returncode == 0 and "--repo" in done.stdout


def test_a_path_that_does_not_exist_is_exit_two_with_a_message(tmp_path):
    done = run("--repo", str(tmp_path / "nope"))
    assert done.returncode == 2 and "not a directory" in done.stderr


@pytest.mark.parametrize("form", (["--json"], ["--quiet"], ["--no-colour"]))
def test_every_output_form_is_quiet_on_stderr(tmp_path, form):
    (tmp_path / "README.md").write_text("# x")
    assert run("--repo", str(tmp_path), *form).stderr == ""


def test_output_is_not_coloured_when_it_is_not_a_terminal(tmp_path):
    (tmp_path / "README.md").write_text("# x")
    assert "\033" not in run("--repo", str(tmp_path)).stdout


def test_the_served_report_answers_a_real_request(tmp_path):
    """The CLI wiring, not just serve.py: a real process, a real port, a real fetch."""
    import json as _json
    import urllib.request

    (tmp_path / "README.md").write_text("# served\n")
    process = subprocess.Popen(
        [sys.executable, "-m", "PKG", "--repo", str(tmp_path), "--serve", "0"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=dict(os.environ, PYTHONPATH=SRC, PYTHONUNBUFFERED="1"))
    try:
        line = process.stdout.readline().strip()
        assert line.startswith("http://127.0.0.1:"), line
        base = line.split()[0].rstrip("/")
        with urllib.request.urlopen(base + "/", timeout=10) as response:
            page = response.read().decode()
        with urllib.request.urlopen(base + "/report.json", timeout=10) as response:
            payload = _json.loads(response.read().decode())
        assert page.startswith("<!doctype html>") and "Example" in page
        assert payload["root"] == str(tmp_path.resolve())
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_serving_binds_to_localhost_unless_told_otherwise(tmp_path):
    (tmp_path / "README.md").write_text("# x\n")
    process = subprocess.Popen(
        [sys.executable, "-m", "PKG", "--repo", str(tmp_path), "--serve", "0"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=dict(os.environ, PYTHONPATH=SRC, PYTHONUNBUFFERED="1"))
    try:
        assert "127.0.0.1" in process.stdout.readline()
    finally:
        process.terminate()
        process.wait(timeout=10)
