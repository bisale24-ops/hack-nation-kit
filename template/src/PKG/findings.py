"""What the tool found, separated from how it is printed.

A section is one question the tool asked. It carries what it confirmed and what it could not
check, because a report that only lists problems cannot be told apart from a report that failed
to run.
"""
import dataclasses
import typing


@dataclasses.dataclass(frozen=True)
class Finding:
    kind: str                     # the machine-readable label, e.g. "broken", "unbacked"
    title: str                    # one line, the claim or the problem
    detail: str = ""              # the evidence, quoted from the file
    where: str = ""               # path, or path:line


@dataclasses.dataclass(frozen=True)
class Section:
    check: str
    title: str
    question: str                 # what this section asked, in one sentence
    findings: typing.Tuple[Finding, ...] = ()
    checked: typing.Tuple[str, ...] = ()      # what it looked at and found sound
    skipped: str = ""             # why it could not run; empty when it ran

    @property
    def ran(self):
        return not self.skipped

    @property
    def passed(self):
        return self.ran and not self.findings


def counts(sections, order):
    """How many findings of each kind, in the order the report presents them."""
    tally = dict((kind, 0) for kind in order)
    for section in sections:
        for finding in section.findings:
            tally[finding.kind] = tally.get(finding.kind, 0) + 1
    return tally
