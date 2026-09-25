"""A model that can use tools, and a transcript of what it actually did.

The loop itself is twenty lines. Everything else here is the part that decides whether a demo
survives being watched: a model that names a tool that does not exist, emits arguments that are
not JSON, calls the same tool with the same arguments forever, or hits a tool that raises. None
of those may end the run with a traceback — each is handed back to the model as a result, which
is both what recovers the run and what makes the transcript honest.

    weather = Tool("weather", "Look up a city's weather", 
                   {"type": "object", "properties": {"city": {"type": "string"}},
                    "required": ["city"]},
                   lambda city: "17C and raining in %s" % city)
    run = Agent(model, [weather], "You answer with one sentence.").run("What is it like in Bishkek?")
    print(run.answer)
    print(run.transcript())
"""
import dataclasses
import time
import typing

from .findings import Finding, Section

ANSWERED = "answered"
STEP_LIMIT = "step limit"
REPEATING = "repeating itself"
OUT_OF_TIME = "out of time"


@dataclasses.dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict                       # JSON schema for the arguments, sent to the provider
    run: typing.Callable[..., typing.Any]

    def spec(self):
        return {"name": self.name, "description": self.description, "schema": self.schema}


@dataclasses.dataclass(frozen=True)
class Step:
    name: str
    arguments: dict
    result: str
    failed: bool = False
    seconds: float = 0.0


@dataclasses.dataclass(frozen=True)
class Run:
    answer: str
    steps: typing.Tuple[Step, ...]
    stopped: str
    calls: int = 0                     # requests that actually left the machine

    @property
    def finished(self):
        return self.stopped == ANSWERED

    def transcript(self):
        lines = []
        for index, step in enumerate(self.steps, 1):
            arguments = ", ".join("%s=%r" % pair for pair in sorted(step.arguments.items()))
            lines.append("%2d  %s(%s)" % (index, step.name, arguments))
            head = step.result if len(step.result) <= 160 else step.result[:157] + "..."
            lines.append("    %s%s" % ("FAILED: " if step.failed else "", head))
        lines.append("    stopped: %s" % self.stopped)
        return "\n".join(lines)

    def section(self, title="Agent", question="What did it do?"):
        """The run, rendered by the same report code as everything else."""
        findings = tuple(
            Finding("broken", "%s failed" % step.name, step.result, "step %d" % index)
            for index, step in enumerate(self.steps, 1) if step.failed)
        checked = tuple("%s(%s)" % (step.name, ", ".join(sorted(step.arguments)))
                        for step in self.steps if not step.failed)
        return Section(check="agent", title=title, question=question,
                       findings=findings, checked=checked,
                       skipped="" if self.steps or self.finished else "the model used no tools")


class Agent:
    def __init__(self, model, tools, system="", max_steps=8, max_seconds=None,
                 max_repeats=3, max_tokens=1024, clock=time.monotonic):
        self.model = model
        self.tools = {tool.name: tool for tool in tools}
        if len(self.tools) != len(tools):
            raise ValueError("two tools share a name: %s" % ", ".join(t.name for t in tools))
        self.system = system
        self.max_steps = max_steps
        self.max_seconds = max_seconds
        self.max_repeats = max_repeats
        self.max_tokens = max_tokens
        self.clock = clock

    def _execute(self, call):
        """Run one tool call. Every way this can go wrong becomes a result, not an exception."""
        started = self.clock()
        if call.malformed:
            return Step(call.name, {}, "the arguments were not valid JSON: %s — send them again"
                        % call.malformed[:200], True, self.clock() - started)
        tool = self.tools.get(call.name)
        if tool is None:
            return Step(call.name, call.arguments,
                        "there is no tool named %r. The tools are: %s"
                        % (call.name, ", ".join(sorted(self.tools))), True,
                        self.clock() - started)
        try:
            result = tool.run(**call.arguments)
        except TypeError as error:                  # wrong or missing arguments
            return Step(call.name, call.arguments, "%s was called wrongly: %s"
                        % (call.name, error), True, self.clock() - started)
        except Exception as error:                  # the tool itself failed
            return Step(call.name, call.arguments, "%s raised %s: %s"
                        % (call.name, type(error).__name__, error), True,
                        self.clock() - started)
        return Step(call.name, call.arguments, "" if result is None else str(result), False,
                    self.clock() - started)

    def run(self, task):
        messages = [{"role": "user", "content": task}]
        specs = [tool.spec() for tool in self.tools.values()]
        steps, seen, deadline = [], {}, None
        if self.max_seconds is not None:
            deadline = self.clock() + self.max_seconds
        last_text = ""

        for _ in range(self.max_steps):
            if deadline is not None and self.clock() > deadline:
                return Run(last_text, tuple(steps), OUT_OF_TIME, self.model.calls)
            reply = self.model.chat(self.system, messages, tools=specs,
                                    max_tokens=self.max_tokens)
            last_text = reply.text or last_text
            if not reply.wants_tools:
                return Run(reply.text, tuple(steps), ANSWERED, self.model.calls)

            messages.append({"role": "assistant", "content": reply.text,
                             "tool_calls": list(reply.tool_calls)})
            for call in reply.tool_calls:
                fingerprint = (call.name, repr(sorted(call.arguments.items())))
                seen[fingerprint] = seen.get(fingerprint, 0) + 1
                if seen[fingerprint] > self.max_repeats:
                    steps.append(Step(call.name, call.arguments,
                                      "called with the same arguments %d times"
                                      % seen[fingerprint], True))
                    return Run(last_text, tuple(steps), REPEATING, self.model.calls)
                step = self._execute(call)
                steps.append(step)
                messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name,
                                 "content": step.result})
        return Run(last_text, tuple(steps), STEP_LIMIT, self.model.calls)
