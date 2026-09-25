"""The measurement harness: what it counts, and what it does when the thing under test breaks."""
import json

from PKG.evals import (Case, Contains, Equals, Matches, Satisfies, as_expect, load_cases,
                       passed, run_cases, section, summary, table)


def double(n):
    return n * 2


def cases():
    return [Case("two", {"n": 2}, 4), Case("three", {"n": 3}, 6),
            Case("wrong", {"n": 4}, 9)]


# ---- how an answer is judged ---------------------------------------------------------------

def test_a_plain_value_means_equality():
    assert isinstance(as_expect(7), Equals)
    assert Equals(7).check(7)[0] and not Equals(7).check(8)[0]


def test_a_mismatch_says_both_sides():
    ok, reason = Equals(7).check(8)
    assert not ok and "7" in reason and "8" in reason


def test_contains_ignores_case_by_default():
    assert Contains("BISHKEK").check("in bishkek today")[0]
    assert not Contains("BISHKEK", fold_case=False).check("in bishkek today")[0]


def test_matches_is_a_search_not_a_full_match():
    assert Matches(r"\d+C").check("it is 17C outside")[0]
    assert not Matches(r"\d+F").check("it is 17C outside")[0]


def test_a_callable_becomes_a_predicate():
    assert isinstance(as_expect(lambda got: True), Satisfies)
    assert Satisfies(lambda got: got > 3).check(4)[0]


def test_a_predicate_may_return_its_own_reason():
    ok, reason = Satisfies(lambda got: (False, "too small by 2")).check(1)
    assert not ok and reason == "too small by 2"


def test_a_predicate_is_named_in_the_reason():
    def is_even(got):
        return got % 2 == 0

    ok, reason = Satisfies(is_even).check(3)
    assert not ok and "is_even" in reason


# ---- running them ---------------------------------------------------------------------------

def test_every_case_runs_and_the_order_is_kept():
    results = run_cases(cases(), double)
    assert [r.case.name for r in results] == ["two", "three", "wrong"]
    assert [r.ok for r in results] == [True, True, False]


def test_a_function_that_raises_is_a_failed_case_not_a_dead_run():
    def explodes(n):
        raise ZeroDivisionError("nope")

    results = run_cases(cases(), explodes)
    assert [r.ok for r in results] == [False, False, False]
    assert all("ZeroDivisionError" in r.crashed for r in results)


def test_a_crash_and_a_wrong_answer_are_told_apart():
    def half_broken(n):
        if n == 3:
            raise ValueError("no")
        return n * 2

    results = run_cases(cases(), half_broken)
    assert results[1].crashed and not results[2].crashed
    assert results[2].reason and results[2].got == 8


def test_timing_is_recorded_from_the_clock_given():
    ticks = iter([0, 1, 1, 3, 3, 6])
    results = run_cases(cases(), double, clock=lambda: next(ticks))
    assert [r.seconds for r in results] == [1, 2, 3]


def test_the_count_is_the_count():
    assert passed(run_cases(cases(), double)) == 2


def test_the_summary_is_the_number_a_judge_reads():
    numbers = summary(run_cases(cases(), double))
    assert numbers["cases"] == 3 and numbers["passed"] == 2 and numbers["failed"] == 1
    assert numbers["rate"] == round(2 / 3, 4) and numbers["crashed"] == 0


def test_the_summary_of_nothing_does_not_divide_by_zero():
    assert summary([])["rate"] == 0.0


# ---- what it is shown as ---------------------------------------------------------------------

def test_the_table_names_the_failure_and_ends_with_the_score():
    text = table(run_cases(cases(), double))
    assert "FAIL" in text and "wrong" in text
    assert text.strip().endswith("2 of 3 passed  ·  0.0s") or "2 of 3 passed" in text


def test_a_passing_run_has_no_fail_lines():
    assert "FAIL" not in table(run_cases(cases()[:2], double))


def test_the_section_turns_failures_into_findings():
    result = section(run_cases(cases(), double))
    assert [f.title for f in result.findings] == ["wrong"]
    assert result.checked == ("2 of 3 cases, 67%",)


def test_a_crash_is_broken_and_a_wrong_answer_only_drifted():
    def half_broken(n):
        if n == 3:
            raise ValueError("no")
        return n * 2

    kinds = {f.title: f.kind for f in section(run_cases(cases(), half_broken)).findings}
    assert kinds["three"] == "broken" and kinds["wrong"] == "drifted"


def test_no_cases_is_a_skipped_section_not_a_perfect_score():
    assert section([]).skipped == "no cases were given"


# ---- cases from a file -------------------------------------------------------------------------

def test_cases_load_from_json_with_all_three_expect_forms(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([
        {"name": "plain", "given": {"n": 2}, "expect": 4},
        {"given": {"n": 3}, "expect": {"contains": "6"}},
        {"name": "regex", "given": {"n": 4}, "expect": {"matches": "^8$"}, "tags": ["slow"]},
    ]))
    loaded = load_cases(path)
    assert [c.name for c in loaded] == ["plain", "case 2", "regex"]
    assert loaded[2].tags == ("slow",)
    results = run_cases(loaded, lambda n: str(n * 2) if n > 2 else n * 2)
    assert [r.ok for r in results] == [True, True, True]


def test_a_case_file_without_given_still_loads(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([{"name": "bare", "expect": 1}]))
    assert load_cases(path)[0].given == {}
