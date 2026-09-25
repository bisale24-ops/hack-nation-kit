"""The tool-calling loop, driven by a scripted model. Nothing here touches a network."""
import pytest

from PKG.agent import ANSWERED, Agent, OUT_OF_TIME, REPEATING, STEP_LIMIT, Tool
from PKG.llm import Reply, ToolCall

SCHEMA = {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}


class Script:
    """A model that says what it was told to say, and keeps every message it was sent."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.seen = []
        self.calls = 0

    def chat(self, system, messages, tools=None, max_tokens=1024):
        self.seen.append({"system": system, "messages": [dict(m) for m in messages],
                          "tools": tools})
        self.calls += 1
        if not self.replies:
            raise AssertionError("the loop asked for more turns than the test supplied")
        return self.replies.pop(0)


def uses(name, arguments, identifier="c1", malformed=""):
    return Reply(tool_calls=(ToolCall(identifier, name, arguments, malformed),))


def weather(city):
    return "17C and raining in %s" % city


def tool(run=weather, name="weather"):
    return Tool(name, "Look up a city's weather", SCHEMA, run)


# ---- the ordinary path --------------------------------------------------------------------

def test_an_answer_without_tools_ends_the_run():
    run = Agent(Script(Reply("Bishkek is fine.")), [tool()]).run("how is it?")
    assert run.answer == "Bishkek is fine." and run.steps == () and run.finished


def test_one_tool_call_then_an_answer():
    model = Script(uses("weather", {"city": "Bishkek"}), Reply("It is raining."))
    run = Agent(model, [tool()]).run("how is it?")
    assert run.answer == "It is raining." and run.stopped == ANSWERED
    assert [(s.name, s.result) for s in run.steps] == [("weather", "17C and raining in Bishkek")]


def test_the_result_is_sent_back_to_the_model():
    model = Script(uses("weather", {"city": "Bishkek"}), Reply("done"))
    Agent(model, [tool()]).run("how is it?")
    second = model.seen[1]["messages"]
    assert second[-2]["role"] == "assistant" and second[-2]["tool_calls"][0].name == "weather"
    assert second[-1] == {"role": "tool", "tool_call_id": "c1", "name": "weather",
                          "content": "17C and raining in Bishkek"}


def test_two_calls_in_one_turn_both_run():
    model = Script(Reply(tool_calls=(ToolCall("a", "weather", {"city": "Osh"}),
                                     ToolCall("b", "weather", {"city": "Naryn"}))),
                   Reply("both"))
    run = Agent(model, [tool()]).run("two cities")
    assert [s.arguments["city"] for s in run.steps] == ["Osh", "Naryn"]


def test_the_tools_are_described_to_the_model():
    model = Script(Reply("nothing to do"))
    Agent(model, [tool()]).run("hello")
    assert model.seen[0]["tools"] == [{"name": "weather",
                                       "description": "Look up a city's weather",
                                       "schema": SCHEMA}]


def test_a_tool_returning_none_is_an_empty_result_not_the_word_none():
    model = Script(uses("weather", {"city": "X"}), Reply("ok"))
    run = Agent(model, [tool(run=lambda city: None)]).run("go")
    assert run.steps[0].result == ""


def test_a_tool_returning_a_number_is_stringified():
    model = Script(uses("weather", {"city": "X"}), Reply("ok"))
    run = Agent(model, [tool(run=lambda city: 17)]).run("go")
    assert run.steps[0].result == "17"


# ---- the four ways a model breaks a loop ---------------------------------------------------

def test_a_tool_that_does_not_exist_is_handed_back_and_the_run_continues():
    model = Script(uses("wether", {"city": "X"}), Reply("sorry, fixed"))
    run = Agent(model, [tool()]).run("go")
    assert run.steps[0].failed and "no tool named" in run.steps[0].result
    assert "weather" in run.steps[0].result       # it is told what does exist
    assert run.answer == "sorry, fixed" and run.finished


def test_a_tool_that_raises_is_handed_back_not_propagated():
    def explodes(city):
        raise ValueError("the service is down")

    model = Script(uses("weather", {"city": "X"}), Reply("i will try later"))
    run = Agent(model, [tool(run=explodes)]).run("go")
    assert run.steps[0].failed
    assert "ValueError" in run.steps[0].result and "service is down" in run.steps[0].result
    assert run.finished


def test_wrong_arguments_are_handed_back_with_the_reason():
    model = Script(uses("weather", {"town": "X"}), Reply("fixed"))
    run = Agent(model, [tool()]).run("go")
    assert run.steps[0].failed and "called wrongly" in run.steps[0].result


def test_arguments_that_are_not_json_are_handed_back_verbatim():
    model = Script(uses("weather", {}, malformed='{"city": "Bish'), Reply("fixed"))
    run = Agent(model, [tool()]).run("go")
    assert run.steps[0].failed and '{"city": "Bish' in run.steps[0].result


def test_a_tool_that_raises_keyboardinterrupt_is_not_swallowed():
    def stop(city):
        raise KeyboardInterrupt

    model = Script(uses("weather", {"city": "X"}))
    with pytest.raises(KeyboardInterrupt):
        Agent(model, [tool(run=stop)]).run("go")


# ---- the three ways a loop ends badly ------------------------------------------------------

def test_the_same_call_over_and_over_stops_the_run():
    same = uses("weather", {"city": "X"})
    model = Script(same, same, same, same, same, same)
    run = Agent(model, [tool()], max_steps=9, max_repeats=3).run("go")
    assert run.stopped == REPEATING
    assert run.steps[-1].failed and "same arguments" in run.steps[-1].result


def test_a_different_argument_is_not_a_repeat():
    model = Script(uses("weather", {"city": "A"}), uses("weather", {"city": "B"}),
                   uses("weather", {"city": "C"}), uses("weather", {"city": "D"}),
                   Reply("done"))
    run = Agent(model, [tool()], max_repeats=1).run("go")
    assert run.stopped == ANSWERED and len(run.steps) == 4


def test_the_step_limit_ends_the_run_and_keeps_the_last_words():
    model = Script(*[Reply("thinking", tool_calls=(ToolCall("i", "weather", {"city": str(i)}),))
                     for i in range(3)])
    run = Agent(model, [tool()], max_steps=3).run("go")
    assert run.stopped == STEP_LIMIT and run.answer == "thinking" and len(run.steps) == 3


def test_a_time_budget_ends_the_run():
    ticks = iter([0, 0, 0, 0, 99, 99, 99, 99])
    model = Script(uses("weather", {"city": "X"}), uses("weather", {"city": "Y"}), Reply("late"))
    run = Agent(model, [tool()], max_seconds=10, clock=lambda: next(ticks)).run("go")
    assert run.stopped == OUT_OF_TIME


def test_two_tools_with_one_name_is_refused_when_the_agent_is_built():
    with pytest.raises(ValueError):
        Agent(Script(), [tool(), tool()])


# ---- what the run can be shown as ----------------------------------------------------------

def test_the_transcript_names_every_call_and_how_it_ended():
    model = Script(uses("weather", {"city": "Bishkek"}), Reply("done"))
    text = Agent(model, [tool()]).run("go").transcript()
    assert "weather(city='Bishkek')" in text
    assert "17C and raining" in text and "stopped: answered" in text


def test_a_long_result_is_shortened_in_the_transcript_only():
    model = Script(uses("weather", {"city": "X"}), Reply("done"))
    run = Agent(model, [tool(run=lambda city: "y" * 500)]).run("go")
    assert len(run.steps[0].result) == 500          # the record keeps everything
    assert "..." in run.transcript()                # the transcript does not


def test_the_section_separates_what_worked_from_what_failed():
    def explodes(city):
        raise ValueError("no")

    model = Script(Reply(tool_calls=(ToolCall("a", "weather", {"city": "X"}),
                                     ToolCall("b", "broken", {"city": "Y"}))),
                   Reply("done"))
    run = Agent(model, [tool(), tool(run=explodes, name="broken")]).run("go")
    section = run.section()
    assert [f.title for f in section.findings] == ["broken failed"]
    assert section.checked == ("weather(city)",)


def test_a_run_with_no_tool_use_is_a_skipped_section_not_an_empty_one():
    section = Agent(Script(Reply("just talking")), [tool()]).run("go").section()
    assert section.skipped == "" or not section.ran   # answered, so nothing was skipped
    assert section.findings == ()
