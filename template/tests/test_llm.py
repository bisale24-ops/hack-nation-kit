"""The model layer, with the network replaced by a function that records what it was asked.

No test here may touch the network. If one does, it will hang in CI rather than fail, so the
transport is injected everywhere and `Model.transport` is never left at its default.
"""
import json

import pytest

from PKG.llm import LLMError, Model, read_key


@pytest.fixture(autouse=True)
def no_ambient_configuration(monkeypatch):
    """The machine running the tests must not be able to change their meaning."""
    for name in ("LLM_MODE", "LLM_MODEL", "LLM_BASE_URL", "LLM_CACHE",
                 "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


class Fake:
    """A transport that answers from a queue and remembers every request."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.seen = []

    def __call__(self, url, headers, payload, timeout):
        self.seen.append({"url": url, "headers": headers, "payload": payload})
        if not self.answers:
            raise AssertionError("the code asked for more answers than the test supplied")
        status, body = self.answers.pop(0)
        return status, json.dumps(body).encode("utf-8") if isinstance(body, dict) else body


def anthropic_answer(text):
    return 200, {"content": [{"type": "text", "text": text}]}


def openai_answer(text):
    return 200, {"choices": [{"message": {"content": text}}]}


def model(tmp_path, transport, **kwargs):
    kwargs.setdefault("key", "k")
    kwargs.setdefault("cache", tmp_path / "cache")
    kwargs.setdefault("sleep", lambda _: None)
    return Model(transport=transport, **kwargs)


# ---- keys -------------------------------------------------------------------------------

def test_key_comes_from_the_environment_first(tmp_path, monkeypatch):
    (tmp_path / "anthropic.key").write_text("from-file")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-env")
    assert read_key("anthropic", tmp_path) == "from-env"


def test_key_falls_back_to_the_config_file(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / "anthropic.key").write_text("  from-file\n")
    assert read_key("anthropic", tmp_path) == "from-file"


def test_a_missing_key_names_the_place_it_looked(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMError) as raised:
        read_key("anthropic", tmp_path)
    assert "ANTHROPIC_API_KEY" in str(raised.value) and "anthropic.key" in str(raised.value)


def test_an_empty_key_file_is_not_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / "anthropic.key").write_text("\n \n")
    with pytest.raises(LLMError):
        read_key("anthropic", tmp_path)


# ---- the two request shapes -------------------------------------------------------------

def test_anthropic_sends_system_beside_the_messages(tmp_path):
    fake = Fake(anthropic_answer("hi"))
    assert model(tmp_path, fake, provider="anthropic").ask("be terse", "hello") == "hi"
    sent = fake.seen[0]
    assert sent["payload"]["system"] == "be terse"
    assert sent["payload"]["messages"] == [{"role": "user", "content": "hello"}]
    assert sent["headers"]["x-api-key"] == "k"
    assert sent["url"].endswith("/v1/messages")


def test_openai_sends_system_as_the_first_message(tmp_path):
    fake = Fake(openai_answer("hi"))
    assert model(tmp_path, fake, provider="openai").ask("be terse", "hello") == "hi"
    sent = fake.seen[0]
    assert sent["payload"]["messages"][0] == {"role": "system", "content": "be terse"}
    assert sent["headers"]["authorization"] == "Bearer k"


def test_a_sponsor_gateway_replaces_the_base_url(tmp_path):
    fake = Fake(openai_answer("hi"))
    model(tmp_path, fake, provider="openai", base="https://gw.example/v9/").ask("", "x")
    assert fake.seen[0]["url"] == "https://gw.example/v9/v1/chat/completions"


def test_anthropic_text_blocks_are_joined_and_non_text_ignored(tmp_path):
    fake = Fake((200, {"content": [{"type": "thinking", "text": "no"},
                                   {"type": "text", "text": "a"},
                                   {"type": "text", "text": "b"}]}))
    assert model(tmp_path, fake).ask("", "x") == "ab"


def test_an_unexpected_shape_is_reported_not_raised_as_keyerror(tmp_path):
    fake = Fake((200, {"nothing": "useful"}))
    with pytest.raises(LLMError) as raised:
        model(tmp_path, fake).ask("", "x")
    assert "unexpected response shape" in str(raised.value)


def test_a_null_content_from_an_openai_endpoint_is_an_empty_string(tmp_path):
    fake = Fake((200, {"choices": [{"message": {"content": None}}]}))
    assert model(tmp_path, fake, provider="openai").ask("", "x") == ""


# ---- retries ----------------------------------------------------------------------------

def test_a_rate_limit_is_retried(tmp_path):
    fake = Fake((429, {"error": "slow down"}), anthropic_answer("ok"))
    slept = []
    assert model(tmp_path, fake, sleep=slept.append).ask("", "x") == "ok"
    assert len(fake.seen) == 2 and slept == [1.0]


def test_a_server_error_is_retried_and_the_wait_grows(tmp_path):
    fake = Fake((500, {}), (503, {}), anthropic_answer("ok"))
    slept = []
    assert model(tmp_path, fake, sleep=slept.append).ask("", "x") == "ok"
    assert slept == [1.0, 2.0]


def test_a_connection_failure_is_retried(tmp_path):
    fake = Fake((0, b"name resolution failed"), anthropic_answer("ok"))
    assert model(tmp_path, fake).ask("", "x") == "ok"


def test_a_bad_request_is_not_retried(tmp_path):
    fake = Fake((400, {"error": "max_tokens too large"}))
    with pytest.raises(LLMError) as raised:
        model(tmp_path, fake).ask("", "x")
    assert len(fake.seen) == 1
    assert "max_tokens too large" in str(raised.value)


def test_retries_run_out_and_say_what_the_last_failure_was(tmp_path):
    fake = Fake((429, {}), (429, {}), (429, {}), (429, {}))
    with pytest.raises(LLMError) as raised:
        model(tmp_path, fake).ask("", "x", attempts=4)
    assert "4 attempts" in str(raised.value) and "429" in str(raised.value)


# ---- the cache, which is what makes a demo repeatable ------------------------------------

def test_the_second_identical_question_does_not_leave_the_machine(tmp_path):
    fake = Fake(anthropic_answer("once"))
    first = model(tmp_path, fake)
    assert first.ask("s", "p") == "once"
    second = model(tmp_path, fake)
    assert second.ask("s", "p") == "once"
    assert len(fake.seen) == 1 and second.calls == 0


def test_a_different_question_is_a_different_slot(tmp_path):
    fake = Fake(anthropic_answer("a"), anthropic_answer("b"))
    one = model(tmp_path, fake)
    assert one.ask("s", "p") == "a"
    assert one.ask("s", "q") == "b"


def test_a_different_model_name_is_a_different_slot(tmp_path):
    fake = Fake(anthropic_answer("a"), anthropic_answer("b"))
    cache = tmp_path / "cache"
    assert model(tmp_path, fake, name="one", cache=cache).ask("s", "p") == "a"
    assert model(tmp_path, fake, name="two", cache=cache).ask("s", "p") == "b"


def test_live_mode_neither_reads_nor_writes_the_cache(tmp_path):
    fake = Fake(anthropic_answer("a"), anthropic_answer("b"))
    cache = tmp_path / "cache"
    assert model(tmp_path, fake, mode="live", cache=cache).ask("s", "p") == "a"
    assert model(tmp_path, fake, mode="live", cache=cache).ask("s", "p") == "b"
    assert not cache.exists()


def test_replay_mode_refuses_to_invent_an_answer(tmp_path):
    fake = Fake(anthropic_answer("a"))
    with pytest.raises(LLMError) as raised:
        model(tmp_path, fake, mode="replay").ask("s", "p")
    assert fake.seen == [] and "replay" in str(raised.value)


def test_replay_mode_serves_what_cache_mode_stored(tmp_path):
    fake = Fake(anthropic_answer("a"))
    cache = tmp_path / "cache"
    model(tmp_path, fake, cache=cache).ask("s", "p")
    assert model(tmp_path, fake, mode="replay", cache=cache).ask("s", "p") == "a"


def test_off_mode_calls_nothing_at_all(tmp_path):
    fake = Fake(anthropic_answer("a"))
    with pytest.raises(LLMError):
        model(tmp_path, fake, mode="off").ask("s", "p")
    assert fake.seen == []


def test_a_corrupt_cache_entry_is_a_cache_miss_not_a_crash(tmp_path):
    fake = Fake(anthropic_answer("fresh"))
    cache = tmp_path / "cache"
    first = model(tmp_path, fake, cache=cache)
    first.ask("s", "p")
    for slot in cache.iterdir():
        slot.write_text("{ this is not json")
    fake.answers.append(anthropic_answer("fresh"))
    assert model(tmp_path, fake, cache=cache).ask("s", "p") == "fresh"


def test_an_unwritable_cache_directory_does_not_lose_the_answer(tmp_path):
    fake = Fake(anthropic_answer("kept"))
    blocked = tmp_path / "wall"
    blocked.write_text("I am a file, not a directory")
    # The answer has already been paid for; failing to store it must not throw it away.
    assert model(tmp_path, fake, cache=blocked).ask("s", "p") == "kept"


# ---- configuration mistakes --------------------------------------------------------------

def test_an_unknown_provider_is_refused_by_name(tmp_path):
    with pytest.raises(LLMError) as raised:
        Model(provider="gemini")
    assert "gemini" in str(raised.value)


def test_an_unknown_mode_is_refused_by_name(tmp_path):
    with pytest.raises(LLMError) as raised:
        Model(mode="cached")
    assert "cached" in str(raised.value)


def test_no_key_is_refused_before_the_request_is_built(tmp_path):
    fake = Fake(anthropic_answer("a"))
    with pytest.raises(LLMError):
        Model(transport=fake, key=None, cache=tmp_path / "c", mode="live").ask("", "x")
    assert fake.seen == []


def test_the_environment_can_redirect_the_model_and_the_gateway(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "some-sponsor-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://sponsor.example")
    fake = Fake(openai_answer("hi"))
    model(tmp_path, fake, provider="openai").ask("", "x")
    assert fake.seen[0]["payload"]["model"] == "some-sponsor-model"
    assert fake.seen[0]["url"].startswith("https://sponsor.example/")
