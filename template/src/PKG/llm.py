"""One model call, over the standard library, with the sprint's three failure modes handled.

A hackathon burns hours on the same three things: a key that is not where the code looks, a rate
limit at the worst moment, and a demo that costs money and behaves differently every time it runs.
So: keys come from ~/.config, retries are automatic, and every answer is cached on disk.

    model = Model.from_env("anthropic")
    print(model.ask("You are terse.", "Name three colours."))

Nothing here is imported from a third-party package, so a fresh machine needs no `pip install`
before the first call works.
"""
import hashlib
import json
import os
import pathlib
import time
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
        raise LLMError(
            "no API key: set %s, or put it in %s" % (spec["key_env"], path)
        )
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


class Model:
    """A configured endpoint. `ask` is the whole surface."""

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
        """Same thing, with the key read from the environment or ~/.config."""
        kwargs.setdefault("key", read_key(provider))
        return cls(provider, **kwargs)

    # ---- the request shape, which is the only part that differs between the two providers ----

    def _payload(self, system, prompt, max_tokens, temperature):
        if self.provider == "anthropic":
            body = {"model": self.name, "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}]}
            if system:
                body["system"] = system
            if temperature is not None:
                body["temperature"] = temperature
            return body
        messages = ([{"role": "system", "content": system}] if system else [])
        messages.append({"role": "user", "content": prompt})
        body = {"model": self.name, "messages": messages, "max_tokens": max_tokens}
        if temperature is not None:
            body["temperature"] = temperature
        return body

    def _headers(self):
        if self.provider == "anthropic":
            return {"x-api-key": self.key or "", "anthropic-version": "2023-06-01"}
        return {"authorization": "Bearer %s" % (self.key or "")}

    @staticmethod
    def _text(provider, data):
        """Pull the answer out, and say which field was missing rather than raising KeyError."""
        try:
            if provider == "anthropic":
                blocks = [b.get("text", "") for b in data["content"] if b.get("type") == "text"]
                return "".join(blocks)
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as error:
            raise LLMError("unexpected response shape: %s in %s"
                           % (error, json.dumps(data)[:400]))

    # ---- cache ----

    def _slot(self, payload):
        stamp = hashlib.sha256(
            json.dumps([self.base, self.path, payload], sort_keys=True).encode("utf-8")
        ).hexdigest()[:32]
        return self.cache / ("%s.json" % stamp)

    # ---- the call ----

    def ask(self, system, prompt, max_tokens=1024, temperature=None, attempts=4):
        """Return the model's text. Raises LLMError rather than returning a half-answer."""
        payload = self._payload(system, prompt, max_tokens, temperature)
        slot = self._slot(payload)
        if self.mode in ("cache", "replay"):
            try:
                return json.loads(slot.read_text(encoding="utf-8"))["text"]
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
                text = self._text(self.provider, json.loads(raw.decode("utf-8", "replace")))
                if self.mode == "cache":
                    try:
                        self.cache.mkdir(parents=True, exist_ok=True)
                        slot.write_text(json.dumps({"model": self.name, "text": text}),
                                        encoding="utf-8")
                    except OSError:
                        pass        # a read-only disk must not throw away an answer already paid for
                return text
            last = "%s %s" % (status, raw[:300].decode("utf-8", "replace"))
            if status not in (0, 408, 409, 429) and not 500 <= status < 600:
                raise LLMError("%s refused the request: %s" % (self.provider, last))
            if attempt < attempts:
                self.sleep(delay)
                delay *= 2
        raise LLMError("%s attempts, last failure: %s" % (attempts, last))
