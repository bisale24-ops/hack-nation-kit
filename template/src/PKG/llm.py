"""One model call, over the standard library, with the sprint's four failure modes handled.

A hackathon burns hours on the same things: a key that is not where the code looks, a rate limit
at the worst moment, a demo that costs money and behaves differently every run, and two providers
that describe the same tool call in two different shapes. So: keys come from ~/.config, retries
are automatic, every answer is cached on disk, and `chat` speaks one message format that is
translated at the edge.

    model = Model.from_env("anthropic")
    print(model.ask("You are terse.", "Name three colours."))

Nothing here is imported from a third-party package, so a fresh machine needs no `pip install`
before the first call works.
"""
import dataclasses
import hashlib
import json
import os
import pathlib
import time
import typing
import urllib.error
import urllib.request

CACHE = pathlib.Path(os.environ.get("LLM_CACHE", ".llm-cache"))

# live:   always call, never store            cache:  serve a stored answer, else call and store
# replay: serve a stored answer, else raise   off:    refuse to call at all
MODES = ("live", "cache", "replay", "off")

PROVIDERS = {
    "anthropic": {
        "base": "https://api.anthropic.com",
        "path": "/v1/messages",
        "key_env": "ANTHROPIC_API_KEY",
        "key_file": "anthropic.key",
        "model": "claude-sonnet-5",
    },
    # Any OpenAI-shaped endpoint: sponsor gateways, OpenRouter, Together, a local server.
    "openai": {
        "base": "https://api.openai.com",
        "path": "/v1/chat/completions",
        "key_env": "OPENAI_API_KEY",
        "key_file": "openai.key",
        "model": "gpt-4o-mini",
    },
}


class LLMError(RuntimeError):
    """A call that cannot be retried into success: no key, a refusal, a cache miss in replay."""


@dataclasses.dataclass(frozen=True)
class ToolCall:
    """One request from the model to run one tool."""
    id: str
    name: str
    arguments: typing.Dict[str, typing.Any] = dataclasses.field(default_factory=dict)
    malformed: str = ""       # the raw string, when the model emitted arguments that are not JSON


@dataclasses.dataclass(frozen=True)
class Reply:
    text: str = ""
    tool_calls: typing.Tuple[ToolCall, ...] = ()
    stop_reason: str = ""
    raw: typing.Optional[dict] = None

    @property
    def wants_tools(self):
        return bool(self.tool_calls)


def read_key(provider, config_dir=None):
    """The environment first, then ~/.config/<provider>.key. Never a literal in the source."""
    spec = PROVIDERS[provider]
    from_env = os.environ.get(spec["key_env"], "").strip()
    if from_env:
        return from_env
    home = pathlib.Path(config_dir) if config_dir else pathlib.Path.home() / ".config"
    path = home / spec["key_file"]
    try:
        key = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        raise LLMError("no API key: set %s, or put it in %s" % (spec["key_env"], path))
    if not key:
        raise LLMError("%s is empty" % path)
    return key


def _post(url, headers, payload, timeout):
    """The only place this module touches the network. Swapped out wholesale in the tests."""
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers=dict(headers, **{"content-type": "application/json"}))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:          # a status is an answer, not a crash
        return error.code, error.read()
    except urllib.error.URLError as error:           # DNS, TLS, no route: retryable
        return 0, str(error.reason).encode("utf-8")


# ---- the neutral message format ---------------------------------------------------------
#
# {"role": "user",      "content": "..."}
# {"role": "assistant", "content": "...", "tool_calls": [ToolCall, ...]}
# {"role": "tool",      "tool_call_id": "...", "name": "...", "content": "..."}
#
# Both providers are reached from this one shape, because getting it wrong in one direction at
# three in the morning is a whole hour.

def _anthropic_messages(messages):
    out = []
    for message in messages:
        role = message["role"]
        if role == "tool":
            block = {"type": "tool_result", "tool_use_id": message["tool_call_id"],
                     "content": message.get("content", "")}
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)     # results for one turn go in one message
            else:
                out.append({"role": "user", "content": [block]})
        elif role == "assistant" and message.get("tool_calls"):
            content = []
            if message.get("content"):
                content.append({"type": "text", "text": message["content"]})
            for call in message["tool_calls"]:
                content.append({"type": "tool_use", "id": call.id, "name": call.name,
                                "input": call.arguments})
            out.append({"role": "assistant", "content": content})
        else:
            out.append({"role": role, "content": message.get("content", "")})
    return out


def _openai_messages(messages):
    out = []
    for message in messages:
        role = message["role"]
        if role == "tool":
            out.append({"role": "tool", "tool_call_id": message["tool_call_id"],
                        "content": message.get("content", "")})
        elif role == "assistant" and message.get("tool_calls"):
            out.append({"role": "assistant", "content": message.get("content") or None,
                        "tool_calls": [{"id": call.id, "type": "function",
                                        "function": {"name": call.name,
                                                     "arguments": json.dumps(call.arguments)}}
                                       for call in message["tool_calls"]]})
        else:
            out.append({"role": role, "content": message.get("content", "")})
    return out


class Model:
    """A configured endpoint. `ask` for one question, `chat` when there are tools."""

    def __init__(self, provider="anthropic", name=None, key=None, base=None,
                 mode=None, cache=None, transport=None, sleep=time.sleep, timeout=120):
        if provider not in PROVIDERS:
            raise LLMError("unknown provider %r, expected one of %s"
                           % (provider, ", ".join(sorted(PROVIDERS))))
        spec = PROVIDERS[provider]
        self.provider = provider
        self.name = name or os.environ.get("LLM_MODEL") or spec["model"]
        self.base = (base or os.environ.get("LLM_BASE_URL") or spec["base"]).rstrip("/")
        self.path = spec["path"]
        self.key = key
        self.mode = mode or os.environ.get("LLM_MODE") or "cache"
        if self.mode not in MODES:
            raise LLMError("unknown mode %r, expected one of %s" % (self.mode, ", ".join(MODES)))
        self.cache = pathlib.Path(cache) if cache is not None else CACHE
        self.transport = transport or _post
        self.sleep = sleep
        self.timeout = timeout
        self.calls = 0                                # how many requests actually left the machine

    @classmethod
    def from_env(cls, provider="anthropic", **kwargs):
        kwargs.setdefault("key", read_key(provider))
        return cls(provider, **kwargs)

    # ---- request and response shapes, the only provider-specific code -------------------

    def _payload(self, system, messages, tools, max_tokens, temperature):
        if self.provider == "anthropic":
            body = {"model": self.name, "max_tokens": max_tokens,
                    "messages": _anthropic_messages(messages)}
            if system:
                body["system"] = system
            if tools:
                body["tools"] = [{"name": t["name"], "description": t.get("description", ""),
                                  "input_schema": t["schema"]} for t in tools]
        else:
            converted = ([{"role": "system", "content": system}] if system else [])
            converted.extend(_openai_messages(messages))
            body = {"model": self.name, "messages": converted, "max_tokens": max_tokens}
            if tools:
                body["tools"] = [{"type": "function",
                                  "function": {"name": t["name"],
                                               "description": t.get("description", ""),
                                               "parameters": t["schema"]}} for t in tools]
        if temperature is not None:
            body["temperature"] = temperature
        return body

    def _headers(self):
        if self.provider == "anthropic":
            return {"x-api-key": self.key or "", "anthropic-version": "2023-06-01"}
        return {"authorization": "Bearer %s" % (self.key or "")}

    @staticmethod
    def _reply(provider, data):
        """Pull the answer out, and say which field was missing rather than raising KeyError."""
        try:
            if provider == "anthropic":
                text, calls = [], []
                for block in data["content"]:
                    if block.get("type") == "text":
                        text.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        calls.append(ToolCall(id=block.get("id", ""), name=block["name"],
                                              arguments=block.get("input") or {}))
                return Reply("".join(text), tuple(calls), data.get("stop_reason", ""), data)
            message = data["choices"][0]["message"]
            calls = []
            for call in message.get("tool_calls") or ():
                function = call.get("function", {})
                raw = function.get("arguments", "")
                try:
                    arguments = json.loads(raw) if raw else {}
                    malformed = ""
                    if not isinstance(arguments, dict):
                        arguments, malformed = {}, raw
                except ValueError:
                    # models do emit broken JSON; the caller gets to hand it back, not a crash
                    arguments, malformed = {}, raw
                calls.append(ToolCall(id=call.get("id", ""), name=function.get("name", ""),
                                      arguments=arguments, malformed=malformed))
            return Reply(message.get("content") or "", tuple(calls),
                         data["choices"][0].get("finish_reason", ""), data)
        except (KeyError, IndexError, TypeError) as error:
            raise LLMError("unexpected response shape: %s in %s"
                           % (error, json.dumps(data)[:400]))

    # ---- cache ----

    def _slot(self, payload):
        stamp = hashlib.sha256(
            json.dumps([self.base, self.path, payload], sort_keys=True, default=str)
            .encode("utf-8")).hexdigest()[:32]
        return self.cache / ("%s.json" % stamp)

    # ---- the call ----

    def chat(self, system, messages, tools=None, max_tokens=1024, temperature=None, attempts=4):
        """A full turn. Returns a Reply, which may carry tool calls instead of text."""
        payload = self._payload(system, messages, tools, max_tokens, temperature)
        slot = self._slot(payload)
        if self.mode in ("cache", "replay"):
            try:
                stored = json.loads(slot.read_text(encoding="utf-8"))
                return self._reply(self.provider, stored["raw"])
            except (OSError, ValueError, KeyError):
                pass
            if self.mode == "replay":
                raise LLMError("replay mode and nothing cached at %s" % slot)
        if self.mode == "off":
            raise LLMError("mode is 'off': this code path is not allowed to call a model")
        if not self.key:
            raise LLMError("no API key configured for %s" % self.provider)

        delay, last = 1.0, ""
        for attempt in range(1, attempts + 1):
            self.calls += 1
            status, raw = self.transport(
                self.base + self.path, self._headers(), payload, self.timeout)
            if status == 200:
                data = json.loads(raw.decode("utf-8", "replace"))
                reply = self._reply(self.provider, data)
                if self.mode == "cache":
                    try:
                        self.cache.mkdir(parents=True, exist_ok=True)
                        slot.write_text(json.dumps({"model": self.name, "text": reply.text,
                                                    "raw": data}), encoding="utf-8")
                    except OSError:
                        pass    # a read-only disk must not throw away an answer already paid for
                return reply
            last = "%s %s" % (status, raw[:300].decode("utf-8", "replace"))
            if status not in (0, 408, 409, 429) and not 500 <= status < 600:
                raise LLMError("%s refused the request: %s" % (self.provider, last))
            if attempt < attempts:
                self.sleep(delay)
                delay *= 2
        raise LLMError("%s attempts, last failure: %s" % (attempts, last))

    def ask(self, system, prompt, max_tokens=1024, temperature=None, attempts=4):
        """One question, one string back."""
        return self.chat(system, [{"role": "user", "content": prompt}],
                         max_tokens=max_tokens, temperature=temperature,
                         attempts=attempts).text
