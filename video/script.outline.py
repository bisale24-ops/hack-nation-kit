"""The eight scenes, with the words already budgeted. Copy to video/script.py and replace.

    ~/.venvs/video/bin/python kit/video/render.py video/script.py --length-only --max-seconds 175

Measured pace is about 2.7 words per second including the pause after each scene, so a
three-minute limit is roughly 480 words all in. The budget below spends 465 of them and runs
as it stands, which means the pacing can be checked before a single frame exists.

Replace a `card:` scene with `term:` as soon as you have real captured output for it — a frame
of genuine terminal output is worth three of prose. Never retype output for the camera.

Rules that have cost a submission before: the video must be public, under the limit, and the
last scene must say the narration is synthesised.
"""

VOICE = "en-US-AndrewNeural"

SCENES = [
    # 1 — the problem, in the words of the person who has it. No product yet. (~65 words)
    ("card:problem",
     "Somebody, somewhere, does this by hand today. They open the file, they read down the "
     "list, and they decide. It takes them twenty minutes, they do it every week, and they get "
     "it wrong about one time in ten, because nothing in their tooling is looking at the thing "
     "they are actually deciding about. That is the whole problem, and it is worth saying "
     "before anything is built."),

    # 2 — the one question the product answers, and what it reads to answer it. (~55 words)
    ("card:idea",
     "So here is one question, asked precisely. What does this input claim, and what in the "
     "repository actually backs that claim? One command, four checks, one page. Nothing is "
     "imported, nothing is executed, and nothing is fetched over the network, which is what "
     "makes the answer the same on your machine as on mine."),

    # 3 — the product answering it, on a real input. Swap to term: or shot: — (~70 words)
    ("card:first",
     "This is it running against something real, not a fixture. The input came from a public "
     "project that has no idea we exist. Each line of the report names the claim, the file it "
     "came from, and what was checked against it, so nothing has to be taken on trust. The "
     "verdict at the top is the only part that is an opinion, and it is one line."),

    # 4 — a second case with a different shape, so it is clearly not a one-trick demo. (~60 words)
    ("card:second",
     "And a second case, deliberately unlike the first. Here the answer is that there is "
     "nothing wrong, which is the result that matters most: a tool with an opinion about a "
     "well kept project is simply a tool that is wrong. It says what it confirmed, and it says "
     "which checks could not run and why."),

    # 5 — the one clever thing, explained so a judge can repeat it. (~55 words)
    ("card:how",
     "The part worth explaining is how it decides. Two sources say different things, and only "
     "one of them is enforced. Everything downstream follows from getting that ordering right, "
     "and getting it wrong is exactly the mistake the projects themselves are making, which is "
     "why the check finds anything at all."),

    # 6 — the numbers. This is the scene judges remember. (~65 words)
    ("card:scale",
     "Then the part that is not a demo. Sixty-nine inputs, three output formats each, a script "
     "that exits non-zero on any unexpected output at all. A hundred and twenty-six tests, on "
     "both supported versions of Python. Every accusation the tool makes was reproduced by hand "
     "against the file it accuses, and three of them did not survive that and were dropped."),

    # 7 — the boundary, and one correction. Say it before a judge finds it. (~55 words)
    ("card:limits",
     "What it does not do. It does not read anything it cannot check offline, it does not judge "
     "what it cannot parse, and it says so in the report rather than staying quiet. One test "
     "here had to be rewritten: written the ordinary way it passed whether or not the code was "
     "correct."),

    # 8 — name, repository, licence, and the sentence about the narration. (~40 words)
    ("card:end",
     "That is the whole thing. The repository is public and M I T licensed, the report is a "
     "single offline page, and the narration in this video is synthesised — there is no "
     "presenter."),
]

CARDS = {
    "problem": """<h1>{{who does this by hand}}</h1>
    <p class=sub>{{what they do today, and what it costs them}}</p>
    <table>
      <tr><td>{{the manual step}}</td><td class=d>{{how long it takes}}</td></tr>
      <tr><td>{{the thing that drifts}}</td><td class=d>{{how often it is wrong}}</td></tr>
    </table>""",

    "idea": """<h1>{{product name}}</h1>
    <p class=sub>{{the one question, as a question}}</p>
    <table>
      <tr><th>check</th><th>the claim</th><th>what backs it</th></tr>
      <tr><td>{{}}</td><td>{{}}</td><td>{{}}</td></tr>
      <tr><td>{{}}</td><td>{{}}</td><td>{{}}</td></tr>
    </table>
    <p class=foot>Nothing imported, nothing executed, nothing fetched.</p>""",

    "first": """<h1>{{the first real input}}</h1>
    <pre>{{paste the real output here, or make this a term: scene}}</pre>""",

    "second": """<h1>{{the second, unlike the first}}</h1>
    <pre>{{real output}}</pre>""",

    "how": """<h1>{{the one mechanism}}</h1>
    <pre>{{before → after, or the rule in two lines}}</pre>
    <p class=foot>{{why getting it wrong is the bug everyone has}}</p>""",

    "scale": """<h1>What was actually run</h1>
    <table>
      <tr><td>{{N}} inputs</td><td class=d>{{where they came from}}</td></tr>
      <tr><td>{{M}} tests</td><td class=d>on {{versions}}</td></tr>
      <tr><td>{{K}} findings</td><td class=d>each reproduced by hand</td></tr>
      <tr><td>{{J}} dropped</td><td class=d>did not survive checking</td></tr>
    </table>""",

    "limits": """<h1>What it does not do</h1>
    <table>
      <tr><td>{{limit}}</td><td class=d>{{why that boundary}}</td></tr>
      <tr><td>{{limit}}</td><td class=d>{{why}}</td></tr>
    </table>
    <p class=foot>{{the correction you made to your own work}}</p>""",

    "end": """<h1>{{product name}}</h1>
    <p class=sub>{{the one question, once more}}</p>
    <p class=big>github.com/bisale24-ops/{{repo}}</p>
    <p class=foot>MIT licensed · {{M}} tests, {{N}} inputs, no network ·
    the narration in this video is synthesised, there is no presenter.</p>""",
}
