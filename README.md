# hack-nation-kit

The scaffolding a hackathon sprint otherwise spends its first four hours building: a project
template that is green from the first commit, a model-calling layer with no dependencies, a
video pipeline that needs no presenter, and three gates that refuse to let bad work out.

Written before the 7th Global AI Hackathon opened, so the commit dates say plainly which part
of a submission was reused and which was written inside the window.

```bash
./preflight.sh --gate                     # an hour before the start: is this machine ready
./new.sh mytool "one line about it"       # a project, a first commit, a green gate
cd ../mytool && ./check.sh                # pytest on 3.9 and 3.13, the tool on itself, empty stderr
../kit/publish.sh                         # secrets, then the gate, then GitHub
```

## The template

`new.sh` stamps out `src/<name>/`, 126 tests and a two-interpreter CI matrix. Seven modules:

| | |
|---|---|
| `llm.py` | One model call over the standard library — no `pip install` before the first request works. Anthropic or any OpenAI-shaped endpoint, keys from `~/.config/<provider>.key`, automatic retries on 429 and 5xx, and every answer cached on disk. `LLM_MODE=replay` makes a demo repeatable and free. |
| `findings.py` | What a check found, kept apart from how it is printed. A section carries what it *confirmed* and why it was *skipped*, because a report that lists only problems cannot be told apart from one that failed to run. |
| `report.py` | The same sections as a terminal report, a JSON document, or one HTML page — no stylesheet, no script, no image, no request. A judge opens it offline. |
| `agent.py` | A model that uses tools, and a transcript of what it did. The loop is twenty lines; the rest handles a model naming a tool that does not exist, emitting arguments that are not JSON, calling the same tool forever, or hitting a tool that raises. Each is handed back as a result — none ends the run in a traceback. |
| `evals.py` | Cases in, a table out, a number at the bottom. "31 of 34, the three failures listed below" is a sentence a judge can act on; "it works well" is not. Failures and crashes are told apart, and a case that raises is a failed case rather than a dead run. |
| `serve.py` | The same report over HTTP, standard library only, bound to localhost, rebuilt per request — for a challenge that wants a URL rather than a terminal. |
| `cli.py` | A registry of checks where one that raises becomes a skipped section with its reason, rather than killing the run. `--serve` puts the report on a port. |

## The video pipeline

```bash
cp video/script.example.py ../mytool/video/script.py
~/.venvs/video/bin/python video/render.py ../mytool/video/script.py --length-only
~/.venvs/video/bin/python video/render.py ../mytool/video/script.py --out demo.mp4 --max-seconds 170
```

Three kinds of frame — an HTML card, a terminal frame read from genuinely captured output, and
an embedded image — narrated with edge-tts and assembled by ffmpeg. Two details that were bugs
before they were features:

- narration files are named by the hash of their text, so editing one line regenerates that line
  and only that line. Naming them by scene index silently keeps the old audio;
- `--max-seconds` exits non-zero instead of producing a video over the limit, and `--length-only`
  reports the length before anything is rendered.

`video/setup.sh` builds `~/.venvs/video` once and proves the whole chain by rendering a real
twenty-four-second mp4. `video/script.outline.py` is the eight-scene structure with the words
already budgeted — problem, question, two real runs, the mechanism, the numbers, the limits, the
close — and it runs as it stands, so pacing can be checked before a single frame exists. Measured
pace is about 2.7 words per second, so three minutes is roughly 480 words.

## The gates

| | |
|---|---|
| `template/check.sh` | pytest on every interpreter in the CI matrix, the tool run against itself, and an assertion that stderr stayed empty. |
| `publish.sh` | Scans the tracked tree for credentials and key files, runs the gate, and only then creates the repository. It refuses a red tree and a planted `sk-ant-…` alike. |
| `preflight.sh` | ffmpeg, both interpreters with pytest, chromium actually launching, `gh` signed in, disk space, reachability. |
| `verify.sh` | Eleven checks over all of the above — **three of which have to fail**. A gate that cannot go red proves nothing. |

## Requires

Python 3.9+, ffmpeg, and for video `~/.venvs/video` built by `video/setup.sh`. Nothing else:
the template has no runtime dependencies, and the tests import only pytest.

## Licence

MIT.
