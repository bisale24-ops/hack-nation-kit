"""The same report over HTTP, in case the challenge wants a URL rather than a terminal.

The standard library only, bound to localhost unless told otherwise, and every response is
built fresh — reload the page and the repository is read again, which is what makes it usable
as a demo. Requests are logged to stdout, never to stderr, because the build gate asserts that
stderr stays empty.
"""
import http.server
import json
import socketserver
import sys


class _Handler(http.server.BaseHTTPRequestHandler):
    routes = {}                       # path -> callable returning (content_type, bytes)
    stream = sys.stdout

    def do_GET(self):                 # noqa: N802 — the base class names it
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        builder = self.routes.get(path)
        if builder is None:
            self._send(404, "text/plain; charset=utf-8",
                       ("no such path: %s\navailable: %s\n"
                        % (path, ", ".join(sorted(self.routes)))).encode("utf-8"))
            return
        try:
            content_type, body = builder()
        except Exception as error:    # a broken check must not take the server down
            self._send(500, "text/plain; charset=utf-8",
                       ("the report could not be built: %s: %s\n"
                        % (type(error).__name__, error)).encode("utf-8"))
            return
        self._send(200, content_type, body)

    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        self.stream.write("%s %s\n" % (self.address_string(), fmt % args))
        self.stream.flush()


class Server(socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def build(routes, host="127.0.0.1", port=8000, stream=sys.stdout):
    """A server that is not yet running. `port=0` picks a free one; read it off server_address."""
    handler = type("Handler", (_Handler,), {"routes": dict(routes), "stream": stream})
    try:
        return Server((host, port), handler)
    except OSError as error:
        raise SystemExit("cannot listen on %s:%s — %s" % (host, port, error))


def serve(routes, host="127.0.0.1", port=8000, stream=sys.stdout):
    server = build(routes, host, port, stream)
    address = server.server_address
    stream.write("http://%s:%d/  (ctrl-c to stop)\n" % (host, address[1]))
    stream.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        stream.write("\nstopped\n")
    finally:
        server.server_close()
    return 0


def routes_for(page, payload):
    """The two routes every one of these tools has: a page to look at, a document to parse."""
    return {
        "/": lambda: ("text/html; charset=utf-8", page().encode("utf-8")),
        "/report.json": lambda: ("application/json; charset=utf-8",
                                 json.dumps(json.loads(payload()), indent=2).encode("utf-8")),
    }
