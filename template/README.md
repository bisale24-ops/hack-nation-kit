# PKG

<!-- One sentence. The question this answers, not the technology it uses. -->
{{ONE LINE}}

```bash
./run.sh --repo path/to/project      # nothing to install
```

## The problem

<!-- Three or four sentences. Who has this problem today, what they do instead, and why that
     is worse. No adjectives about the solution. -->
{{PROBLEM}}

## What it does

| it asks | it reads | it says |
|---|---|---|
| {{question}} | {{source of truth}} | {{verdict}} |

## What it does not do

<!-- The single most persuasive section in a hackathon README. State the boundary before a judge
     finds it. -->
- {{limit}}

## Running it

```bash
./run.sh --repo .            # a terminal report, exit 1 when something is broken
./run.sh --repo . --json     # the same result, machine-readable
./run.sh --repo . --html report.html   # one offline page
```

## How it was checked

```bash
./check.sh ~/.venvs/py39/bin/python python3
```

<!-- Fill in with real numbers once they exist: tests, interpreters, repositories it was run
     against, and what came back. A number here is worth a paragraph of claims. -->
{{N}} tests on Python 3.9 and 3.13, run against {{M}} real repositories.

## Prior art

<!-- Name the closest existing tools and say what is different. A judge who finds them first
     assumes you did not look. -->
{{TOOL}} — {{what it does instead}}.

## Licence

MIT.
