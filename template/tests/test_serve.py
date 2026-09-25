"""The HTTP surface, driven by real requests against a real socket on a random free port."""
import io
import json
import threading
import urllib.error
import urllib.request

import pytest

from PKG import serve


@pytest.fixture
def running():
    servers = []

    def start(routes):
        stream = io.StringIO()
        server = serve.build(routes, host="127.0.0.1", port=0, stream=stream)
        servers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return "http://127.0.0.1:%d" % server.server_address[1], stream

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def get(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.headers["content-type"], response.read().decode()


def report_routes(page="<!doctype html><h1>hi</h1>", payload='{"sections": []}'):
    return serve.routes_for(lambda: page, lambda: payload)


def test_the_page_is_served_at_the_root(running):
    base, _ = running(report_routes())
    status, content_type, body = get(base + "/")
    assert status == 200 and content_type.startswith("text/html")
    assert body == "<!doctype html><h1>hi</h1>"


def test_the_json_is_served_and_parses(running):
    base, _ = running(report_routes())
    status, content_type, body = get(base + "/report.json")
    assert status == 200 and content_type.startswith("application/json")
    assert json.loads(body) == {"sections": []}


def test_a_query_string_does_not_change_the_route(running):
    base, _ = running(report_routes())
    assert get(base + "/report.json?t=1")[0] == 200


def test_an_unknown_path_is_404_and_says_what_exists(running):
    base, _ = running(report_routes())
    with pytest.raises(urllib.error.HTTPError) as raised:
        get(base + "/nowhere")
    assert raised.value.code == 404
    body = raised.value.read().decode()
    assert "/report.json" in body


def test_a_builder_that_raises_is_500_and_the_server_stays_up(running):
    def explodes():
        raise RuntimeError("the check died")

    base, _ = running({"/": explodes, "/ok": lambda: ("text/plain", b"fine")})
    with pytest.raises(urllib.error.HTTPError) as raised:
        get(base + "/")
    assert raised.value.code == 500 and "the check died" in raised.value.read().decode()
    assert get(base + "/ok")[0] == 200          # the next request still works


def test_the_report_is_rebuilt_on_every_request(running):
    counter = {"n": 0}

    def page():
        counter["n"] += 1
        return "<h1>%d</h1>" % counter["n"]

    base, _ = running(serve.routes_for(page, lambda: "{}"))
    assert get(base + "/")[2] == "<h1>1</h1>"
    assert get(base + "/")[2] == "<h1>2</h1>"


def test_requests_are_logged_to_the_stream_it_was_given_not_to_stderr(running, capsys):
    base, stream = running(report_routes())
    get(base + "/")
    assert "GET /" in stream.getvalue()
    assert capsys.readouterr().err == ""


def test_a_port_that_cannot_be_bound_is_a_message_not_a_traceback():
    with pytest.raises(SystemExit) as raised:
        serve.build({}, host="127.0.0.1", port=1)     # privileged, and we are not root
    assert "cannot listen" in str(raised.value)
