"""The command line, run through main() with real files underneath."""
import json

import pytest

from PKG import cli
from PKG.findings import Section


@pytest.fixture
def project(tmp_path):
    (tmp_path / "README.md").write_text("# a project\n")
    return tmp_path


def test_a_clean_project_exits_zero(project, capsys):
    assert cli.main(["--repo", str(project)]) == 0
    assert "EXAMPLE" in capsys.readouterr().out


def test_quiet_prints_nothing_at_all(project, capsys):
    cli.main(["--repo", str(project), "--quiet"])
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_json_is_json_and_carries_the_root(project, capsys):
    cli.main(["--repo", str(project), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["root"] == str(project.resolve())


def test_html_is_written_where_asked(project, tmp_path):
    out = tmp_path / "report.html"
    cli.main(["--repo", str(project), "--html", str(out)])
    assert out.read_text().startswith("<!doctype html>")


def test_a_missing_directory_is_exit_two_and_a_message(tmp_path, capsys):
    assert cli.main(["--repo", str(tmp_path / "nowhere")]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_a_file_where_a_directory_belongs_is_also_exit_two(tmp_path):
    target = tmp_path / "f"
    target.write_text("x")
    assert cli.main(["--repo", str(target)]) == 2


def test_a_check_that_raises_becomes_a_skipped_section_not_a_crash(tmp_path, capsys):
    assert cli.main(["--repo", str(tmp_path)]) == 0        # no README: example_check raises
    assert "skipped: FileNotFoundError" in capsys.readouterr().out


def test_one_failing_check_leaves_the_others_running(tmp_path, monkeypatch, capsys):
    def explodes(root):
        raise ValueError("boom")

    monkeypatch.setitem(cli.CHECKS, "explodes", explodes)
    monkeypatch.setitem(cli.CHECKS, "fine",
                        lambda root: Section("fine", "Fine", "q", checked=("it ran",)))
    cli.main(["--repo", str(tmp_path), "--json"])
    titles = {s["check"]: s["skipped"] for s in json.loads(capsys.readouterr().out)["sections"]}
    assert "boom" in titles["explodes"] and titles["fine"] == ""


def test_only_runs_one_check(project, capsys, monkeypatch):
    monkeypatch.setitem(cli.CHECKS, "second",
                        lambda root: Section("second", "Second", "q"))
    cli.main(["--repo", str(project), "--only", "example", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert [s["check"] for s in payload["sections"]] == ["example"]


def test_nothing_reaches_stderr_on_a_normal_run(project, capsys):
    cli.main(["--repo", str(project)])
    assert capsys.readouterr().err == ""
