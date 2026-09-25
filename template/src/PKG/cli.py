"""The command line: run every check, render once, exit on what was found.

A check that raises becomes a skipped section carrying the reason. One broken input must not
take the other checks down with it — a tool that dies on repository ninety of a hundred is worth
less than one that says what it could not read.
"""
import argparse
import pathlib
import sys
import traceback

from . import report, serve
from .findings import Section


def example_check(root):
    """Delete this and register the real checks below. The shape is the contract:
    take the root, return a Section, raise if the check genuinely cannot run."""
    readme = root / "README.md"
    if not readme.exists():
        raise FileNotFoundError("no README.md")
    return Section(check="example", title="Example", question="Does the README say anything?",
                   checked=("README.md is %d bytes" % readme.stat().st_size,))


CHECKS = {
    "example": example_check,
}


def collect(root, names, debug=False):
    sections = []
    for name in names:
        try:
            sections.append(CHECKS[name](root))
        except Exception as error:                    # one bad check, not a dead run
            if debug:
                traceback.print_exc()
            sections.append(Section(check=name, title=name.replace("-", " ").title(),
                                    question="", skipped="%s: %s" % (type(error).__name__, error)))
    return sections


def build_parser():
    parser = argparse.ArgumentParser(prog=__package__, description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".", type=pathlib.Path, help="the project to look at")
    parser.add_argument("--only", action="append", choices=sorted(CHECKS), metavar="CHECK",
                        help="run one check; repeatable (%s)" % ", ".join(sorted(CHECKS)))
    parser.add_argument("--json", action="store_true", help="machine-readable, to stdout")
    parser.add_argument("--html", type=pathlib.Path, metavar="PATH", help="write one HTML page")
    parser.add_argument("--quiet", action="store_true", help="exit code only")
    parser.add_argument("--no-colour", action="store_true")
    parser.add_argument("--debug", action="store_true", help="show tracebacks from failed checks")
    parser.add_argument("--serve", nargs="?", const=8000, type=int, metavar="PORT",
                        help="serve the report at / and /report.json instead of printing it")
    parser.add_argument("--host", default="127.0.0.1",
                        help="who may reach --serve; 0.0.0.0 exposes it to the network")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = args.repo.resolve()
    if not root.is_dir():
        sys.stderr.write("not a directory: %s\n" % args.repo)
        return 2
    names = args.only or sorted(CHECKS)
    if args.serve is not None:
        # rebuilt per request, so reloading the page re-reads the repository
        return serve.serve(serve.routes_for(
            lambda: report.page(collect(root, names, debug=args.debug),
                                title=__package__, subtitle=str(root)),
            lambda: report.as_json(collect(root, names, debug=args.debug), {"root": str(root)})),
            host=args.host, port=args.serve)
    sections = collect(root, names, debug=args.debug)
    if args.html:
        args.html.write_text(report.page(sections, title=__package__, subtitle=str(root)),
                             encoding="utf-8")
    if args.json:
        sys.stdout.write(report.as_json(sections, {"root": str(root)}))
    elif not args.quiet:
        colour = not args.no_colour and sys.stdout.isatty()
        sys.stdout.write(report.terminal(sections, colour=colour))
    return report.exit_code(sections)
