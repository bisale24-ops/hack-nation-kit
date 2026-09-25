"""Measured results instead of claims: cases in, a table out, a number at the bottom.

A judge reading "it works well" has learned nothing. A judge reading "31 of 34 cases, the three
failures listed below" has learned everything, including that we looked. This is the smallest
thing that produces the second sentence, and it renders through the same report code as the
rest of the tool.

    cases = load_cases("evals/cases.json")
    results = run_cases(cases, my_function)
    print(table(results))
    raise SystemExit(0 if passed(results) == len(results) else 1)
"""
import dataclasses
import json
import pathlib
import re
import time
import traceback
import typing

from .findings import Finding, Section


class Expect:
    """How an answer is judged. Subclasses return (ok, reason)."""

    def check(self, got):
        raise NotImplementedError

    def describe(self):
        return self.__class__.__name__.lower()


@dataclasses.dataclass(frozen=True)
class Equals(Expect):
    value: typing.Any

    def check(self, got):
        return got == self.value, "expected %r, got %r" % (self.value, got)

    def describe(self):
        return "== %r" % (self.value,)


@dataclasses.dataclass(frozen=True)
class Contains(Expect):
    text: str
    fold_case: bool = True

    def check(self, got):
        haystack, needle = str(got), self.text
        if self.fold_case:
            haystack, needle = haystack.lower(), needle.lower()
        return needle in haystack, "%r is not in %r" % (self.text, str(got)[:120])

    def describe(self):
        return "contains %r" % self.text


@dataclasses.dataclass(frozen=True)
class Matches(Expect):
    pattern: str

    def check(self, got):
        return bool(re.search(self.pattern, str(got))), \
            "%r does not match %r" % (str(got)[:120], self.pattern)

    def describe(self):
        return "matches %r" % self.pattern


@dataclasses.dataclass(frozen=True)
class Satisfies(Expect):
    predicate: typing.Callable[[typing.Any], typing.Any]
    name: str = ""

    def check(self, got):
        verdict = self.predicate(got)
        if isinstance(verdict, tuple):
            return bool(verdict[0]), str(verdict[1])
        return bool(verdict), "%s said no about %r" % (self.describe(), str(got)[:120])

    def describe(self):
        return self.name or getattr(self.predicate, "__name__", "a predicate")


def as_expect(value):
    if isinstance(value, Expect):
        return value
    if callable(value):
        return Satisfies(value)
    return Equals(value)


@dataclasses.dataclass(frozen=True)
class Case:
    name: str
    given: typing.Dict[str, typing.Any]
    expect: typing.Any
    tags: typing.Tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class Result:
    case: Case
    got: typing.Any = None
    ok: bool = False
    reason: str = ""
    seconds: float = 0.0
    crashed: str = ""          # the traceback's last line, when the function raised


def load_cases(path):
    """Cases from JSON: [{"name": ..., "given": {...}, "expect": ..., "tags": [...]}].

    `expect` may be a plain value, or {"contains": "..."} / {"matches": "..."}.
    """
    raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    cases = []
    for index, entry in enumerate(raw):
        expect = entry.get("expect")
        if isinstance(expect, dict) and len(expect) == 1:
            kind, value = next(iter(expect.items()))
            expect = {"contains": Contains, "matches": Matches,
                      "equals": Equals}.get(kind, Equals)(value)
        cases.append(Case(name=entry.get("name") or "case %d" % (index + 1),
                          given=entry.get("given") or {}, expect=expect,
                          tags=tuple(entry.get("tags") or ())))
    return cases


def run_cases(cases, function, clock=time.monotonic):
    """Run every case. A case that raises is a failure with its reason, never a dead run."""
    results = []
    for case in cases:
        started = clock()
        try:
            got = function(**case.given)
        except Exception:
            line = traceback.format_exc().strip().splitlines()[-1]
            results.append(Result(case, None, False, line, clock() - started, line))
            continue
        ok, reason = as_expect(case.expect).check(got)
        results.append(Result(case, got, ok, "" if ok else reason, clock() - started))
    return results


def passed(results):
    return sum(1 for result in results if result.ok)


def table(results, width=34):
    lines = []
    for result in results:
        mark = "pass" if result.ok else "FAIL"
        lines.append("%-4s  %-*s  %6.2fs  %s" % (mark, width, result.case.name[:width],
                                                 result.seconds,
                                                 "" if result.ok else result.reason[:70]))
    total = len(results)
    took = sum(result.seconds for result in results)
    lines.append("")
    lines.append("%d of %d passed  ·  %.1fs" % (passed(results), total, took))
    return "\n".join(lines) + "\n"


def summary(results):
    total = len(results)
    return {"cases": total, "passed": passed(results), "failed": total - passed(results),
            "crashed": sum(1 for r in results if r.crashed),
            "seconds": round(sum(r.seconds for r in results), 3),
            "rate": round(passed(results) / total, 4) if total else 0.0}


def section(results, title="Evaluation", question="How many cases does it get right?"):
    findings = tuple(
        Finding("broken" if result.crashed else "drifted", result.case.name,
                result.reason, ", ".join("%s=%r" % pair for pair in sorted(result.case.given.items())))
        for result in results if not result.ok)
    numbers = summary(results)
    checked = ("%d of %d cases, %.0f%%" % (numbers["passed"], numbers["cases"],
                                           100 * numbers["rate"]),) if results else ()
    return Section(check="evals", title=title, question=question, findings=findings,
                   checked=checked, skipped="" if results else "no cases were given")
