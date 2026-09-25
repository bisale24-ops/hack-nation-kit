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
