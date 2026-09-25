"""The three renderings, and the promises the page makes about itself."""
import json
import re

from PKG import report
from PKG.findings import Finding, Section, counts

FOUND = Section(check="c", title="Claims", question="What is claimed?",
                findings=(Finding("broken", "readme calls parse()", "no such function", "README.md:12"),
                          Finding("unbacked", "coverage 100%", "nothing measured it", "README.md:3")),
                checked=("the licence badge matches LICENSE",))
CLEAN = Section(check="d", title="Docs", question="Do the examples run?",
                checked=("all four examples import",))
SKIPPED = Section(check="e", title="Notes", question="", skipped="no tags in this clone")


def test_terminal_names_every_finding_and_every_confirmation():
    text = report.terminal([FOUND, CLEAN, SKIPPED], colour=False)
    assert "readme calls parse()" in text and "README.md:12" in text
    assert "the licence badge matches LICENSE" in text
    assert "skipped: no tags in this clone" in text


def test_terminal_without_colour_emits_no_escape_sequences():
    assert "\033" not in report.terminal([FOUND, CLEAN, SKIPPED], colour=False)


def test_terminal_with_colour_does():
    assert "\033" in report.terminal([FOUND], colour=True)


def test_json_round_trips_and_keeps_the_fields():
    payload = json.loads(report.as_json([FOUND, SKIPPED], {"root": "/x"}))
    assert payload["root"] == "/x"
    first = payload["sections"][0]
    assert first["findings"][0]["where"] == "README.md:12"
    assert payload["sections"][1]["skipped"] == "no tags in this clone"


def test_a_clean_section_is_visibly_clean_not_absent():
    payload = json.loads(report.as_json([CLEAN]))
    assert payload["sections"][0]["findings"] == []
    assert payload["sections"][0]["checked"] == ["all four examples import"]


def test_the_page_fetches_nothing(tmp_path):
    html = report.page([FOUND, CLEAN, SKIPPED], "Tool", "/some/repo")
    for forbidden in ("<script", "<img", "http://", "https://", "<link", "@import", "url("):
        assert forbidden not in html, forbidden


def test_the_page_escapes_a_finding_that_contains_markup():
    nasty = Section(check="c", title="<b>t</b>", question="q",
                    findings=(Finding("broken", "<script>alert(1)</script>", "a & b", "<i>"),))
    html = report.page([nasty], "T")
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html and "a &amp; b" in html


def test_the_scorecard_counts_what_the_sections_hold():
    html = report.page([FOUND, CLEAN], "T")
    numbers = re.findall(r"<b>(\d+)</b><span>([^<]+)</span>", html)
    assert ("1", "broken") in numbers
    assert ("1", "nothing behind it") in numbers
    assert ("2", "checks run") in numbers


def test_a_skipped_section_does_not_count_as_a_check_that_ran():
    html = report.page([SKIPPED], "T")
    assert "<b>0</b><span>checks run</span>" in html


def test_the_exit_code_is_one_only_when_something_is_broken():
    assert report.exit_code([CLEAN, SKIPPED]) == 0
    assert report.exit_code([Section("c", "t", "q",
                                     findings=(Finding("unbacked", "x"),))]) == 0
    assert report.exit_code([FOUND]) == 1


def test_counts_reports_a_zero_rather_than_omitting_the_kind():
    assert counts([CLEAN], report.ORDER) == {"broken": 0, "unbacked": 0, "drifted": 0}


def test_every_kind_in_order_has_a_label():
    assert set(report.ORDER) <= set(report.LABEL)
