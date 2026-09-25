"""Three renderings of the same sections: a terminal, a JSON document, one HTML page.

The page is deliberately a single file with no stylesheet, no script tag from anywhere else and
no image: a judge opens it offline and it is entirely the result.
"""
import dataclasses
import html
import json

ORDER = ("broken", "unbacked", "drifted")
LABEL = {"broken": "broken", "unbacked": "nothing behind it", "drifted": "drifted"}
# Kinds that make the exit code non-zero. Widen deliberately, never by accident.
FAILING = ("broken",)


def terminal(sections, colour=True):
    def paint(text, code):
        return "\033[%sm%s\033[0m" % (code, text) if colour else text

    lines = []
    for section in sections:
        if not section.ran:
            lines.append("%s  %s" % (paint(section.title.upper(), "2"),
                                     paint("skipped: " + section.skipped, "2")))
            continue
        head = "%s  %s" % (section.title.upper(),
                           paint("%d finding%s" % (len(section.findings),
                                                   "" if len(section.findings) == 1 else "s"),
                                 "33" if section.findings else "32"))
        lines.append(head)
        for finding in section.findings:
            lines.append("  %s  %s" % (paint(LABEL.get(finding.kind, finding.kind), "33"),
                                       finding.title))
            if finding.detail:
                lines.append("      " + paint(finding.detail, "2"))
            if finding.where:
                lines.append("      " + paint(finding.where, "2"))
        for confirmed in section.checked:
            lines.append("  " + paint("ok  " + confirmed, "2"))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def as_json(sections, extra=None):
    payload = {"sections": [dataclasses.asdict(section) for section in sections]}
    if extra:
        payload.update(extra)
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


PAGE = """<!doctype html><meta charset=utf-8><title>{title}</title><style>
 :root {{ --bg:#fbfaf7; --ink:#1a1a18; --dim:#6b6a64; --line:#e2e0d8; --warn:#8a5a12; --ok:#2f6f45; }}
 @media (prefers-color-scheme: dark) {{ :root:not([data-theme=light]) {{
   --bg:#16160f; --ink:#ecebe3; --dim:#9b9a90; --line:#2e2d25; --warn:#e0b063; --ok:#7fc79a; }} }}
 body {{ background:var(--bg); color:var(--ink); margin:0; padding:40px 16px;
   font:16px/1.6 system-ui,-apple-system,sans-serif; }}
 main {{ max-width:860px; margin:0 auto; }}
 h1 {{ font-size:30px; margin:0 0 4px; letter-spacing:-.02em; }}
 .sub {{ color:var(--dim); margin:0 0 28px; }}
 .score {{ display:flex; gap:28px; border:1px solid var(--line); border-radius:12px;
   padding:16px 20px; margin-bottom:28px; flex-wrap:wrap; }}
 .score b {{ display:block; font-size:24px; }}
 .score span {{ color:var(--dim); font-size:13px; text-transform:uppercase; letter-spacing:.06em; }}
 section {{ border-top:1px solid var(--line); padding:20px 0; }}
 h2 {{ font-size:19px; margin:0 0 2px; }}
 .q {{ color:var(--dim); font-size:14px; margin:0 0 14px; }}
 .f {{ border-left:3px solid var(--warn); padding:2px 0 2px 14px; margin:12px 0; }}
 .k {{ color:var(--warn); font-size:12px; text-transform:uppercase; letter-spacing:.06em; }}
 .d, .w {{ color:var(--dim); font-size:14px; }}
 .w {{ font-family:ui-monospace,Menlo,monospace; }}
 .ok {{ color:var(--ok); }} .none {{ color:var(--dim); font-size:14px; }}
</style><main>
<h1>{title}</h1><p class=sub>{subtitle}</p>
<div class=score>{score}</div>
{body}
</main>"""


def page(sections, title, subtitle=""):
    tally = {}
    for section in sections:
        for finding in section.findings:
            tally[finding.kind] = tally.get(finding.kind, 0) + 1
    score = "".join(
        "<div><b>%d</b><span>%s</span></div>" % (tally.get(kind, 0), html.escape(LABEL[kind]))
        for kind in ORDER)
    score += "<div><b>%d</b><span>checks run</span></div>" % sum(1 for s in sections if s.ran)

    blocks = []
    for section in sections:
        rows = []
        if not section.ran:
            rows.append('<p class=none>skipped: %s</p>' % html.escape(section.skipped))
        for finding in section.findings:
            rows.append(
                '<div class=f><div class=k>%s</div><div>%s</div>%s%s</div>' % (
                    html.escape(LABEL.get(finding.kind, finding.kind)),
                    html.escape(finding.title),
                    '<div class=d>%s</div>' % html.escape(finding.detail) if finding.detail else "",
                    '<div class=w>%s</div>' % html.escape(finding.where) if finding.where else ""))
        for confirmed in section.checked:
            rows.append('<p class="none ok">ok &nbsp;%s</p>' % html.escape(confirmed))
        if section.ran and not section.findings and not section.checked:
            rows.append('<p class=none>nothing to report</p>')
        blocks.append("<section><h2>%s</h2><p class=q>%s</p>%s</section>" % (
            html.escape(section.title), html.escape(section.question), "".join(rows)))

    return PAGE.format(title=html.escape(title), subtitle=html.escape(subtitle),
                       score=score, body="".join(blocks))


def exit_code(sections):
    return 1 if any(f.kind in FAILING for s in sections for f in s.findings) else 0
